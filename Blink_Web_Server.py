from flask import Flask, render_template, send_file, jsonify, request
from pathlib import Path
import json
import socket
from datetime import datetime
import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler
import requests
import logging

app = Flask(__name__)

# Configuration
CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"
ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

# Suppress blinkpy sync_module errors about last_refresh
logging.getLogger('blinkpy.sync_module').setLevel(logging.CRITICAL)


def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def normalize_camera_name(cam_name: str) -> str:
    """Convert camera name to lowercase kebab-case"""
    return cam_name.lower().replace(" ", "-")


def wifi_bars(dbm: int | None) -> int:
    """Convert WiFi signal strength to bars"""
    if dbm is None:
        return 0
    elif dbm >= -50:
        return 5
    elif dbm >= -60:
        return 4
    elif dbm >= -70:
        return 3
    elif dbm >= -80:
        return 2
    elif dbm >= -90:
        return 1
    else:
        return 0


def get_location():
    """Read location from config file"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        location_data = config.get("location", {})
        if location_data:
            return location_data
        else:
            return {
                "city": "Bethel Park",
                "state": "PA",
                "display": "Bethel Park, PA",
                "lat": 40.3267,
                "lon": -80.0171
            }
    except Exception as e:
        print(f"Error reading location: {e}")
        return {
            "city": "Bethel Park",
            "state": "PA",
            "display": "Bethel Park, PA",
            "lat": 40.3267,
            "lon": -80.0171
        }


def get_camera_data():
    """Read camera configuration and latest data"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)
        camera_data = []

        for cam_name in cameras:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name
            log_file = LOG_FOLDER / "cameras" / normalized_name / f"{normalized_name}.log"

            # Get latest N images
            images = []
            if cam_folder.exists():
                all_images = sorted(
                    cam_folder.glob("*.jpg"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                images = [img.name for img in all_images[:carousel_images]]

            # Get latest log entry
            temp = "N/A"
            battery = "N/A"
            wifi = 0
            timestamp = "N/A"

            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        if lines:
                            last_line = lines[-1]
                            parts = last_line.split(" | ")
                            if len(parts) >= 4:
                                timestamp = parts[0]
                                for part in parts:
                                    if "Temp:" in part:
                                        temp_str = part.split("Temp:")[1].strip().split()[0]
                                        temp = temp_str.replace("Â°F", "").replace("Ã‚Â°F", "")
                                        temp_clean = ""
                                        for char in temp:
                                            if char.isdigit() or char == '.' or char == '-':
                                                temp_clean += char
                                        temp = temp_clean if temp_clean else "N/A"
                                    elif "Battery:" in part:
                                        battery_str = part.split("Battery:")[1].strip()
                                        battery_parts = battery_str.split()
                                        battery = battery_parts[0] if battery_parts else "N/A"
                                    elif "WiFi:" in part:
                                        wifi_str = part.split("WiFi:")[1].strip()
                                        wifi_parts = wifi_str.split("/")
                                        try:
                                            wifi = int(wifi_parts[0])
                                        except:
                                            wifi = 0
                except Exception as e:
                    print(f"Error parsing log for {cam_name}: {e}")
                    pass

            camera_data.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "images": images,
                "temperature": temp,
                "battery": battery,
                "wifi": wifi,
                "timestamp": timestamp
            })

        return camera_data
    except Exception as e:
        print(f"Error reading camera data: {e}")
        return []


async def get_blink_status():
    """Get current armed/disarmed status from Blink"""
    try:
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)

        async with ClientSession() as session:
            blink = Blink(session=session)

            host_url = token_data.get("host", "")
            region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")

            blink.auth = Auth({}, session=session, no_prompt=True)
            blink.auth.region_id = region_id
            blink.auth.host = host_url
            blink.auth.token = token_data.get("token")
            blink.auth.refresh_token = token_data.get("refresh_token")
            blink.auth.client_id = token_data.get("client_id")
            blink.auth.account_id = token_data.get("account_id")
            blink.auth.user_id = token_data.get("user_id")
            blink.urls = BlinkURLHandler(region_id)

            await blink.setup_post_verify()
            await blink.refresh()

            # Check if any sync module is armed
            armed = False
            for sync_name, sync_module in blink.sync.items():
                if sync_module.arm:
                    armed = True
                    break

            return {"armed": armed, "success": True}

    except Exception as e:
        print(f"Error getting Blink status: {e}")
        return {"armed": False, "success": False, "error": str(e)}


async def set_blink_arm_state(arm: bool):
    """Arm or disarm all Blink sync modules"""
    try:
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)

        async with ClientSession() as session:
            blink = Blink(session=session)

            host_url = token_data.get("host", "")
            region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")

            blink.auth = Auth({}, session=session, no_prompt=True)
            blink.auth.region_id = region_id
            blink.auth.host = host_url
            blink.auth.token = token_data.get("token")
            blink.auth.refresh_token = token_data.get("refresh_token")
            blink.auth.client_id = token_data.get("client_id")
            blink.auth.account_id = token_data.get("account_id")
            blink.auth.user_id = token_data.get("user_id")
            blink.urls = BlinkURLHandler(region_id)

            await blink.setup_post_verify()

            # Arm or disarm all sync modules
            for sync_name, sync_module in blink.sync.items():
                if arm:
                    await sync_module.async_arm(True)
                    print(f"Armed {sync_name}")
                else:
                    await sync_module.async_arm(False)
                    print(f"Disarmed {sync_name}")

            return {"success": True, "armed": arm}

    except Exception as e:
        print(f"Error setting arm state: {e}")
        return {"success": False, "error": str(e)}


@app.route('/')
def index():
    """Main page with camera grid"""
    cameras = get_camera_data()
    location = get_location()
    return render_template('index.html', cameras=cameras, location=location)


@app.route('/api/cameras')
def api_cameras():
    """API endpoint for camera data"""
    cameras = get_camera_data()
    return jsonify(cameras)


@app.route('/api/location')
def api_location():
    """API endpoint for location data"""
    location = get_location()
    return jsonify(location)


@app.route('/api/weather')
def api_weather():
    """Weather API endpoint - proxies wttr.in to avoid CORS issues"""
    try:
        location = get_location()
        city = location.get("city", "Bethel Park")
        state = location.get("state", "PA")

        # Fetch weather from wttr.in server-side (no CORS issues)
        response = requests.get(
            f'https://wttr.in/{city},{state}?format=j1',
            timeout=10,
            headers={'User-Agent': 'Blink-Camera-Monitor/1.0'}
        )
        response.raise_for_status()

        return jsonify(response.json())

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Weather service timeout'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Weather service error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/arm/status')
def api_arm_status():
    """Get current armed/disarmed status"""
    result = asyncio.run(get_blink_status())
    return jsonify(result)


@app.route('/api/arm/set', methods=['POST'])
def api_arm_set():
    """Set armed/disarmed state"""
    data = request.get_json()
    arm = data.get('arm', False)
    result = asyncio.run(set_blink_arm_state(arm))
    return jsonify(result)


@app.route('/image/<camera_name>/<image_name>')
def get_image(camera_name, image_name):
    """Serve camera images"""
    image_path = CAMERAS_DIR / camera_name / image_name
    if image_path.exists():
        return send_file(image_path, mimetype='image/jpeg')
    return "Image not found", 404


if __name__ == '__main__':
    print("=" * 60)
    print("\U0001F3A5 Blink Camera Web Server")  # Camera emoji
    print("=" * 60)

    local_ip = get_local_ip()

    try:
        from waitress import serve

        logging.getLogger("waitress.queue").setLevel(logging.ERROR)
        
        print("\u2705 Using Waitress production server")  # Check mark
        print(f"\U0001F310 Local access:   http://localhost:5000")  # Globe emoji
        print(f"\U0001F310 Network access: http://{local_ip}:5000")
        print("=" * 60)
        print("Press Ctrl+C to stop the server")
        print("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=6, channel_timeout=120, backlog=128)
    except ImportError:
        print("\u26A0\uFE0F  Waitress not found - using Flask development server")  # Warning
        print("\U0001F4A1 For production use, install Waitress:")  # Light bulb
        print("   pip install waitress")
        print("=" * 60)
        print(f"\U0001F310 Local access:   http://localhost:5000")
        print(f"\U0001F310 Network access: http://{local_ip}:5000")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=False)