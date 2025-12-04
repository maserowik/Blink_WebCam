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
    Supports both flat and date-organized log structures

    Args:
        log_folder: Path to camera's log folder
        camera_name: Normalized camera name

    Returns:
        Dictionary with parsed log data
    """
    import re

    # Pattern for date folders: YYYY-MM-DD
    date_folder_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    # Pattern for log files: {camera_name}_YYYY-MM-DD.log
    log_file_pattern = re.compile(rf'^{re.escape(camera_name)}_(\d{{4}}-\d{{2}}-\d{{2}})\.log$')

    log_files = []

    # Check if log folder exists
    if not log_folder.exists():
        print(f"Log folder does not exist: {log_folder}")
        return {
            'temp': 'N/A',
            'battery': 'N/A',
            'wifi': 0,
            'timestamp': 'N/A'
        }

    # Search for log files in both flat and date-organized structures
    for item in log_folder.iterdir():
        # Check if it's a date folder (e.g., "2025-11-23")
        if item.is_dir() and date_folder_pattern.match(item.name):
            date_str = item.name
            # Look for log files inside the date folder
            for log_file in item.glob(f"{camera_name}_*.log"):
                if log_file.is_file():
                    log_files.append((date_str, log_file))

        # Also check for flat structure log files
        elif item.is_file():
            match = log_file_pattern.match(item.name)
            if match:
                date_str = match.group(1)
                log_files.append((date_str, item))
            # Check for non-dated log files (fallback)
            elif item.name == f"{camera_name}.log":
                log_files.append(("9999-99-99", item))

    if not log_files:
        print(f"No log files found for {camera_name} in {log_folder}")
        return {
            'temp': 'N/A',
            'battery': 'N/A',
            'wifi': 0,
            'timestamp': 'N/A'
        }

    # Sort by date (newest first)
    log_files.sort(key=lambda x: x[0], reverse=True)
    latest_log = log_files[0][1]

    # Read and parse the log
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

            # FIX: Find the last line that contains camera data (not PERF lines)
            camera_data_line = None
            for line in reversed(lines):
                if "Temp:" in line and "Battery:" in line and "WiFi:" in line:
                    camera_data_line = line
                    break

            if not camera_data_line:
                print(f"No camera data found in log: {latest_log}")
                return {
                    'temp': 'N/A',
                    'battery': 'N/A',
                    'wifi': 0,
                    'timestamp': 'N/A'
                }

            parts = camera_data_line.split(" | ")

            temp = "N/A"
            battery = "N/A"
            wifi = 0
            timestamp = "N/A"

            if len(parts) >= 2:
                timestamp = parts[0]

                for part in parts:
                    if "Temp:" in part:
                        temp_str = part.split("Temp:")[1].strip().split()[0]
                        # Remove degree symbols
                        temp = temp_str.replace("\u00B0F", "").replace("\u00B0", "").replace("F", "")
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
        import traceback
        traceback.print_exc()
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

@app.route('/api/cameras/refresh')
def refresh_cameras():
    """Return current camera data for AJAX refresh"""
    try:
        cameras_data = get_camera_data()
        return jsonify({'success': True, 'cameras': cameras_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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


@app.route('/api/weather')
def api_weather():
    """Weather API endpoint using only wttr.in with Unicode sky icons"""
    try:
        location = get_location()
        city = location.get("city", "Bethel Park")
        state = location.get("state", "PA")

        # Map weather descriptions to Unicode symbols
        def weather_to_unicode(desc: str):
            desc = desc.lower()
            if any(x in desc for x in ["sunny", "clear"]):
                return "\u2600"  # ☀ Sun
            elif any(x in desc for x in ["partly cloudy", "cloudy", "few clouds"]):
                return "\u26C5"  # ⛅ Sun behind cloud
            elif "cloud" in desc:
                return "\u2601"  # ☁ Cloud
            elif "rain" in desc:
                return "\u1F327"  # 🌧 Cloud with rain
            elif "thunder" in desc:
                return "\u26C8"  # ⛈ Thunderstorm
            elif "snow" in desc:
                return "\u2744"  # ❄ Snowflake
            elif any(x in desc for x in ["night clear", "clear night"]):
                return "\u263E"  # ☾ Crescent moon
            elif "fog" in desc or "mist" in desc:
                return "\u1F32B"  # 🌫 Fog (may render as emoji)
            else:
                return "\u2753"  # ❓ Unknown

        # Use wttr.in with 30 second timeout
        try:
            response = requests.get(
                f'https://wttr.in/{city},{state}?format=j1',
                timeout=30,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            )

            if response.status_code == 200:
                data = response.json()

                # Extract current condition description
                desc = data.get("current_condition", [{}])[0].get("weatherDesc", [{}])[0].get("value", "")
                data['weather_icon'] = weather_to_unicode(desc)

                return jsonify(data)
            else:
                print(f"wttr.in returned status code: {response.status_code}")
                return jsonify({'error': f'Weather service returned status {response.status_code}',
                                'weather_icon': "\u2753"}), 503

        except requests.exceptions.Timeout:
            print(f"wttr.in request timed out after 30 seconds")
            return jsonify({'error': 'Weather service timed out', 'weather_icon': "\u2753"}), 504

        except Exception as e:
            print(f"wttr.in failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Weather service unavailable', 'weather_icon': "\u2753"}), 503

    except Exception as e:
        print(f"Weather error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'weather_icon': "\u2753"}), 500



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
    try:
        data = request.get_json()

        camera_name = data.get('camera_name') if data else None
        duration_minutes = data.get('duration_minutes') if data else None

        if not camera_name or duration_minutes is None:
            error_msg = "Missing camera_name or duration_minutes"
            return jsonify({"success": False, "error": error_msg}), 400

        snooze_manager.snooze_camera(camera_name, duration_minutes)
        status = snooze_manager.get_snooze_status(camera_name)
        return jsonify({"success": True, "status": status})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/set', methods=['POST'])
def api_snooze_all_set():
    """Snooze all cameras for a specified duration"""
    try:
        data = request.get_json()

        duration_minutes = data.get('duration_minutes') if data else None

        if duration_minutes is None:
            error_msg = "Missing duration_minutes"
            return jsonify({"success": False, "error": error_msg}), 400

        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras]

        snooze_manager.snooze_all_cameras(camera_names, duration_minutes)

        return jsonify({"success": True, "count": len(camera_names)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/unset', methods=['POST'])
def api_snooze_unset():
    """Remove snooze from a camera"""
    try:
        data = request.get_json()

        camera_name = data.get('camera_name') if data else None

        if not camera_name:
            error_msg = "Missing camera_name in request"
            return jsonify({"success": False, "error": error_msg}), 400

        snooze_manager.unsnooze_camera(camera_name)
        return jsonify({"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/unset', methods=['POST'])
def api_snooze_all_unset():
    """Remove snooze from all cameras"""
    try:
        snooze_manager.unsnooze_all_cameras()
        return jsonify({"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
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

@app.route('/api/cameras/refresh')
def api_cameras_refresh():
    """Return current camera data for AJAX refresh"""
    try:
        cameras_data = get_camera_data()
        return jsonify({'success': True, 'cameras': cameras_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("Blink Camera Web Server")
    print("=" * 60)

    local_ip = get_local_ip()

    try:
        from waitress import serve

        logging.getLogger("waitress.queue").setLevel(logging.ERROR)

        print("Using Waitress production server")
        print(f"Local access:   http://localhost:5000")
        print(f"Network access: http://{local_ip}:5000")
        print("=" * 60)
        print("Press Ctrl+C to stop the server")
        print("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=6, channel_timeout=120, backlog=128)
    except ImportError:
        print("Waitress not found - using Flask development server")
        print("For production use, install Waitress:")
        print("   pip install waitress")
        print("=" * 60)
        print(f"Local access:   http://localhost:5000")
        print(f"Network access: http://{local_ip}:5000")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=False)