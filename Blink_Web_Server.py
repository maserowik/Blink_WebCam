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

# Import snooze manager
from alert_snooze import AlertSnooze, SNOOZE_DURATIONS

app = Flask(__name__)

# Configuration
CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"
ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

# Initialize snooze manager
snooze_manager = AlertSnooze()

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


def get_latest_images_from_date_folders(camera_folder: Path, carousel_images: int) -> list:
    """
    Get latest N images from date-organized folders

    Args:
        camera_folder: Path to camera folder
        carousel_images: Number of images to retrieve

    Returns:
        List of image paths (relative to camera folder)
    """
    all_images = []

    # Find all date folders (YYYY-MM-DD format)
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_folders = [d for d in camera_folder.iterdir()
                    if d.is_dir() and date_pattern.match(d.name)]

    # Sort by date (newest first)
    date_folders.sort(key=lambda d: d.name, reverse=True)

    # Collect images from newest to oldest
    for date_folder in date_folders:
        images_in_folder = sorted(
            date_folder.glob("*.jpg"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        for img in images_in_folder:
            # Store relative path: "2024-11-18/front-door_20241118_120000.jpg"
            relative_path = f"{date_folder.name}/{img.name}"
            all_images.append(relative_path)

            if len(all_images) >= carousel_images:
                return all_images

    return all_images


def get_most_recent_photo_time(camera_folder: Path) -> datetime | None:
    """
    Get the timestamp of the most recent photo for a camera

    Args:
        camera_folder: Path to camera folder

    Returns:
        datetime of most recent photo or None if no photos exist
    """
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_folders = [d for d in camera_folder.iterdir()
                    if d.is_dir() and date_pattern.match(d.name)]

    if not date_folders:
        return None

    # Sort by date (newest first)
    date_folders.sort(key=lambda d: d.name, reverse=True)

    # Check most recent date folder
    for date_folder in date_folders:
        images = sorted(
            date_folder.glob("*.jpg"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        if images:
            # Return modification time of most recent image
            return datetime.fromtimestamp(images[0].stat().st_mtime)

    return None


def get_latest_log_entry(log_folder: Path, camera_name: str) -> dict:
    """
    Get latest log entry from most recent log file

    Args:
        log_folder: Path to camera's log folder
        camera_name: Normalized camera name

    Returns:
        Dictionary with parsed log data
    """
    import re

    # Pattern: {camera_name}_YYYY-MM-DD.log
    pattern = re.compile(rf'^{re.escape(camera_name)}_(\d{{4}}-\d{{2}}-\d{{2}})\.log$')

    log_files = []
    for file in log_folder.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                date_str = match.group(1)
                log_files.append((date_str, file))

    if not log_files:
        return {
            'temp': 'N/A',
            'battery': 'N/A',
            'wifi': 0,
            'timestamp': 'N/A'
        }

    # Sort by date (newest first)
    log_files.sort(key=lambda x: x[0], reverse=True)
    latest_log = log_files[0][1]

    # Read last line
    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if not lines:
                return {
                    'temp': 'N/A',
                    'battery': 'N/A',
                    'wifi': 0,
                    'timestamp': 'N/A'
                }

            last_line = lines[-1]
            parts = last_line.split(" | ")

            temp = "N/A"
            battery = "N/A"
            wifi = 0
            timestamp = "N/A"

            if len(parts) >= 4:
                timestamp = parts[0]
                for part in parts:
                    if "Temp:" in part:
                        temp_str = part.split("Temp:")[1].strip().split()[0]
                        temp = temp_str.replace("\u00B0F", "").replace("\u00B0F", "")
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

            return {
                'temp': temp,
                'battery': battery,
                'wifi': wifi,
                'timestamp': timestamp
            }
    except Exception as e:
        print(f"Error parsing log for {camera_name}: {e}")
        return {
            'temp': 'N/A',
            'battery': 'N/A',
            'wifi': 0,
            'timestamp': 'N/A'
        }


def get_camera_data():
    """Read camera configuration and latest data"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)
        camera_data = []

        # Clean up expired snoozes before building camera data
        snooze_manager.cleanup_expired_snoozes()

        for cam_name in cameras:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name
            log_folder = LOG_FOLDER / "cameras" / normalized_name

            # Get latest N images from date folders
            images = get_latest_images_from_date_folders(cam_folder, carousel_images)

            # Get latest log entry
            log_data = get_latest_log_entry(log_folder, normalized_name)

            # Get snooze status for this camera
            snooze_status = snooze_manager.get_snooze_status(normalized_name)

            # Get most recent photo timestamp
            last_photo_time = get_most_recent_photo_time(cam_folder)
            last_update = None
            last_update_formatted = None

            if last_photo_time:
                last_update = last_photo_time.isoformat()
                last_update_formatted = last_photo_time.strftime("%m/%d/%Y %I:%M:%S %p")

            camera_data.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "images": images,
                "temperature": log_data['temp'],
                "battery": log_data['battery'],
                "wifi": log_data['wifi'],
                "timestamp": log_data['timestamp'],
                "snooze_status": snooze_status,
                "last_update": last_update,
                "last_update_formatted": last_update_formatted
            })

        return camera_data
    except Exception as e:
        print(f"Error reading camera data: {e}")
        import traceback
        traceback.print_exc()
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

    # Get list of normalized camera names for global snooze check
    camera_names = [cam['normalized_name'] for cam in cameras]
    all_snoozed = snooze_manager.are_all_cameras_snoozed(camera_names)

    return render_template('index.html', cameras=cameras, location=location, all_snoozed=all_snoozed)


@app.route('/api/cameras')
def api_cameras():
    """API endpoint for camera data"""
    cameras = get_camera_data()
    return jsonify(cameras)


@app.route('/api/camera/<camera_name>/last_update')
def api_camera_last_update(camera_name):
    """Get last update time for a specific camera"""
    normalized_name = normalize_camera_name(camera_name)
    cam_folder = CAMERAS_DIR / normalized_name

    last_photo_time = get_most_recent_photo_time(cam_folder)

    if last_photo_time:
        return jsonify({
            "success": True,
            "camera": camera_name,
            "last_update": last_photo_time.isoformat(),
            "last_update_formatted": last_photo_time.strftime("%m/%d/%Y %I:%M:%S %p"),
            "last_update_relative": get_relative_time(last_photo_time)
        })
    else:
        return jsonify({
            "success": False,
            "camera": camera_name,
            "error": "No photos found"
        }), 404


def get_relative_time(dt: datetime) -> str:
    """Convert datetime to relative time string (e.g., '5 minutes ago')"""
    now = datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


@app.route('/api/location')
def api_location():
    """API endpoint for location data"""
    location = get_location()
    return jsonify(location)


# REPLACE ONLY the @app.route('/api/weather') function in Blink_Web_Server.py
# Find it around line 250 and replace the entire function

@app.route('/api/weather')
def api_weather():
    """Weather API endpoint - proxies wttr.in to avoid CORS issues"""
    try:
        location = get_location()
        city = location.get("city", "Bethel Park")
        state = location.get("state", "PA")

        # Use the EXACT format that works in curl
        location_query = f"{city},{state}"
        url = f'https://wttr.in/{location_query}?format=j1'

        print(f"Fetching weather from: {url}")

        # Simple request with minimal headers (like curl)
        response = requests.get(
            url,
            timeout=10
        )

        print(f"Weather response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("Weather data received successfully")
            return jsonify(data)
        else:
            print(f"Weather API returned status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            raise Exception(f"HTTP {response.status_code}")

    except Exception as e:
        print(f'Weather error: {str(e)}')
        # Return valid fallback data
        return jsonify({
            'current_condition': [{
                'temp_F': '--',
                'FeelsLikeF': '--',
                'humidity': '--',
                'weatherDesc': [{'value': 'Service Unavailable'}]
            }]
        }), 200

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


# Snooze API Endpoints

@app.route('/api/snooze/durations')
def api_snooze_durations():
    """Get available snooze durations"""
    return jsonify({
        "durations": SNOOZE_DURATIONS,
        "formatted": {k: f"{v} min" if v < 60 else f"{v // 60} hr"
                      for k, v in SNOOZE_DURATIONS.items()}
    })


@app.route('/api/snooze/status/<camera_name>')
def api_snooze_status(camera_name):
    """Get snooze status for a specific camera"""
    status = snooze_manager.get_snooze_status(camera_name)
    return jsonify(status)


@app.route('/api/snooze/all/status')
def api_snooze_all_status():
    """Get global snooze all status"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras]

        all_snoozed = snooze_manager.are_all_cameras_snoozed(camera_names)

        return jsonify({
            "all_snoozed": all_snoozed,
            "success": True
        })
    except Exception as e:
        return jsonify({
            "all_snoozed": False,
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/snooze/set', methods=['POST'])
def api_snooze_set():
    """Snooze a camera for a specified duration"""
    data = request.get_json()
    camera_name = data.get('camera_name')
    duration_minutes = data.get('duration_minutes')

    if not camera_name or duration_minutes is None:
        return jsonify({"success": False, "error": "Missing camera_name or duration_minutes"}), 400

    try:
        snooze_manager.snooze_camera(camera_name, duration_minutes)
        status = snooze_manager.get_snooze_status(camera_name)
        return jsonify({"success": True, "status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/set', methods=['POST'])
def api_snooze_all_set():
    """Snooze all cameras for a specified duration"""
    data = request.get_json()
    duration_minutes = data.get('duration_minutes')

    if duration_minutes is None:
        return jsonify({"success": False, "error": "Missing duration_minutes"}), 400

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras]

        snooze_manager.snooze_all_cameras(camera_names, duration_minutes)

        return jsonify({"success": True, "count": len(camera_names)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/unset', methods=['POST'])
def api_snooze_unset():
    """Remove snooze from a camera"""
    data = request.get_json()
    camera_name = data.get('camera_name')

    if not camera_name:
        return jsonify({"success": False, "error": "Missing camera_name"}), 400

    try:
        snooze_manager.unsnooze_camera(camera_name)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/unset', methods=['POST'])
def api_snooze_all_unset():
    """Remove snooze from all cameras"""
    try:
        snooze_manager.unsnooze_all_cameras()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/cleanup', methods=['POST'])
def api_snooze_cleanup():
    """Cleanup expired snoozes"""
    try:
        snooze_manager.cleanup_expired_snoozes()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/list')
def api_snooze_list():
    """Get all currently snoozed cameras"""
    snoozed = snooze_manager.get_all_snoozed_cameras()

    # Format for JSON response
    formatted = {}
    for camera_name, expiry in snoozed.items():
        formatted[camera_name] = {
            "expiry": expiry.isoformat(),
            "expiry_formatted": expiry.strftime("%I:%M %p"),
            "expiry_full": expiry.strftime("%m/%d/%Y %I:%M %p")
        }

    return jsonify(formatted)


@app.route('/image/<camera_name>/<path:image_path>')
def get_image(camera_name, image_path):
    """
    Serve camera images (supports date-organized folders)

    Examples:
      /image/front-door/2024-11-18/front-door_20241118_120000.jpg
      /image/front-door/front-door_20241118_120000.jpg (legacy)
    """
    full_path = CAMERAS_DIR / camera_name / image_path
    if full_path.exists():
        return send_file(full_path, mimetype='image/jpeg')
    return "Image not found", 404


if __name__ == '__main__':
    print("=" * 60)
    print("\U0001F535 Blink Camera Web Server")
    print("=" * 60)

    local_ip = get_local_ip()

    try:
        from waitress import serve

        logging.getLogger("waitress.queue").setLevel(logging.ERROR)

        print("\u2705 Using Waitress production server")
        print(f"\U0001F3E0 Local access:   http://localhost:5000")
        print(f"\U0001F4F1 Network access: http://{local_ip}:5000")
        print("=" * 60)
        print("\u26A1 Press Ctrl+C to stop the server")
        print("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=6, channel_timeout=120, backlog=128)
    except ImportError:
        print("\u26A0\uFE0F Waitress not found - using Flask development server")
        print("\U0001F4E6 For production use, install Waitress:")
        print("   pip install waitress")
        print("=" * 60)
        print(f"\U0001F3E0 Local access:   http://localhost:5000")
        print(f"\U0001F4F1 Network access: http://{local_ip}:5000")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=False)