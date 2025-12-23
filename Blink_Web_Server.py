from flask import Flask, render_template, send_file, jsonify, request
from pathlib import Path
import json
import socket
from datetime import datetime, timedelta
import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler
import requests
import logging
import threading
import time

from alert_snooze import AlertSnooze, SNOOZE_DURATIONS
from log_rotation import LogRotator

app = Flask(__name__)

CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"
ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

snooze_manager = AlertSnooze()
logging.getLogger('blinkpy.sync_module').setLevel(logging.CRITICAL)

# Initialize log rotator
log_rotator = LogRotator(LOG_FOLDER, max_backups=5)

# Define log file paths
WEBSERVER_LOG_FOLDER = log_rotator.get_system_log_folder("webserver")
PERF_LOG_FOLDER = log_rotator.get_system_log_folder("performance")

# Weather caching
weather_cache = {
    'data': None,
    'timestamp': None,
    'lock': threading.Lock()
}

WEATHER_CACHE_DURATION = 30 * 60  # 30 minutes in seconds


# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

def get_current_log_file(folder: Path, name: str) -> Path:
    """Get current log file with today's date"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return folder / f"{name}_{date_str}.log"


def log_web(msg: str):
    """Log general web server events to system/webserver/webserver_YYYY-MM-DD.log"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(WEBSERVER_LOG_FOLDER, "webserver")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())


def log_web_error(msg: str, exception: Exception = None):
    """Log errors with tracebacks to web server log"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(WEBSERVER_LOG_FOLDER, "webserver")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | ERROR | {msg}\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
        if exception:
            import traceback
            f.write(traceback.format_exc())
            f.write("\n")

    print(line.strip())
    if exception:
        import traceback
        traceback.print_exc()


def log_web_performance(msg: str):
    """Log API timing metrics to system/performance/webserver-perf_YYYY-MM-DD.log"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(PERF_LOG_FOLDER, "webserver-perf")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        log_web_error(f"Could not determine local IP: {e}", e)
        return "127.0.0.1"


def normalize_camera_name(cam_name: str) -> str:
    return cam_name.lower().replace(" ", "-")


def wifi_bars(dbm: int | None) -> int:
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
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        location_data = config.get("location", {})
        if location_data:
            return location_data
        return {
            "city": "Bethel Park",
            "state": "PA",
            "display": "Bethel Park, PA",
            "lat": 40.3044,
            "lon": -80.0717
        }
    except Exception as e:
        log_web_error(f"Error reading location from config: {e}", e)
        return {
            "city": "Bethel Park",
            "state": "PA",
            "display": "Bethel Park, PA",
            "lat": 40.3044,
            "lon": -80.0717
        }


def get_latest_images_from_date_folders(camera_folder: Path, carousel_images: int) -> list:
    import re
    all_images = []
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_folders = [d for d in camera_folder.iterdir() if d.is_dir() and date_pattern.match(d.name)]
    date_folders.sort(key=lambda d: d.name, reverse=True)
    for date_folder in date_folders:
        images_in_folder = sorted(
            date_folder.glob("*.jpg"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for img in images_in_folder:
            relative_path = f"{date_folder.name}/{img.name}"
            all_images.append(relative_path)
            if len(all_images) >= carousel_images:
                return all_images
    return all_images


def get_most_recent_photo_time(camera_folder: Path) -> datetime | None:
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_folders = [d for d in camera_folder.iterdir() if d.is_dir() and date_pattern.match(d.name)]
    if not date_folders:
        return None
    date_folders.sort(key=lambda d: d.name, reverse=True)
    for date_folder in date_folders:
        images = sorted(date_folder.glob("*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)
        if images:
            return datetime.fromtimestamp(images[0].stat().st_mtime)
    return None


def get_latest_log_entry(log_folder: Path, camera_name: str) -> dict:
    import re
    date_folder_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    log_file_pattern = re.compile(rf'^{re.escape(camera_name)}_(\d{{4}}-\d{{2}}-\d{{2}})\.log$')
    log_files = []

    if not log_folder.exists():
        log_web(f"Log folder does not exist: {log_folder}")
        return {'temp': 'N/A', 'battery': 'N/A', 'wifi': 0, 'timestamp': 'N/A'}

    for item in log_folder.iterdir():
        if item.is_dir() and date_folder_pattern.match(item.name):
            date_str = item.name
            for log_file in item.glob(f"{camera_name}_*.log"):
                if log_file.is_file():
                    log_files.append((date_str, log_file))
        elif item.is_file():
            match = log_file_pattern.match(item.name)
            if match:
                date_str = match.group(1)
                log_files.append((date_str, item))
            elif item.name == f"{camera_name}.log":
                log_files.append(("9999-99-99", item))

    if not log_files:
        log_web(f"No log files found for {camera_name} in {log_folder}")
        return {'temp': 'N/A', 'battery': 'N/A', 'wifi': 0, 'timestamp': 'N/A'}

    log_files.sort(key=lambda x: x[0], reverse=True)
    latest_log = log_files[0][1]

    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            camera_data_line = None
            for line in reversed(lines):
                if "Temp:" in line and "Battery:" in line and "WiFi:" in line:
                    camera_data_line = line
                    break
            if not camera_data_line:
                return {'temp': 'N/A', 'battery': 'N/A', 'wifi': 0, 'timestamp': 'N/A'}
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
                        temp = "".join([c for c in temp_str if c.isdigit() or c in ".-"]) or "N/A"
                    elif "Battery:" in part:
                        battery_str = part.split("Battery:")[1].strip()
                        battery = battery_str.split()[0] if battery_str else "N/A"
                    elif "WiFi:" in part:
                        wifi_str = part.split("WiFi:")[1].strip()
                        try:
                            wifi = int(wifi_str.split("/")[0])
                        except:
                            wifi = 0
            return {'temp': temp, 'battery': battery, 'wifi': wifi, 'timestamp': timestamp}
    except Exception as e:
        log_web_error(f"Error parsing log for {camera_name}: {e}", e)
        return {'temp': 'N/A', 'battery': 'N/A', 'wifi': 0, 'timestamp': 'N/A'}


def get_camera_data():
    start_time = time.time()
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        cameras = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)
        camera_data = []

        snooze_manager.cleanup_expired_snoozes()

        for cam_name in cameras:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name
            log_folder = LOG_FOLDER / "cameras" / normalized_name

            images = get_latest_images_from_date_folders(cam_folder, carousel_images)
            log_data = get_latest_log_entry(log_folder, normalized_name)
            snooze_status = snooze_manager.get_snooze_status(normalized_name)
            last_photo_time = get_most_recent_photo_time(cam_folder)
            last_update = None
            last_update_formatted = None
            if last_photo_time:
                last_update = last_photo_time.isoformat()
                last_update_formatted = last_photo_time.strftime("%m/%d/%Y %I:%M:%S %p")

            alerts = check_camera_alerts(log_folder, normalized_name, log_data['wifi'])

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
                "last_update_formatted": last_update_formatted,
                "alerts": alerts
            })

        duration = time.time() - start_time
        log_web_performance(f"get_camera_data | {duration:.2f}s | {len(camera_data)} cameras")
        return camera_data
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error reading camera data (took {duration:.2f}s): {e}", e)
        log_web_performance(f"get_camera_data | {duration:.2f}s | ERROR")
        return []


def check_camera_alerts(log_folder: Path, camera_name: str, wifi_bars: int) -> dict:
    """Check camera log for alerts (offline status only)"""
    alerts = {
        "is_offline": False,
        "has_duplicates": False,
        "offline_reason": None,
        "duplicate_count": 0
    }

    if wifi_bars == 0:
        alerts["is_offline"] = True
        alerts["offline_reason"] = "No WiFi signal"

    return alerts


# ============================================================================
# BLINK API FUNCTIONS
# ============================================================================

async def get_blink_status():
    start_time = time.time()
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
            armed = any(sync_module.arm for sync_name, sync_module in blink.sync.items())

            duration = time.time() - start_time
            log_web_performance(f"get_blink_status | {duration:.2f}s | armed={armed}")
            return {"armed": armed, "success": True}
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error getting Blink status (took {duration:.2f}s): {e}", e)
        log_web_performance(f"get_blink_status | {duration:.2f}s | ERROR")
        return {"armed": False, "success": False, "error": str(e)}


async def set_blink_arm_state(arm: bool):
    start_time = time.time()
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
            for sync_name, sync_module in blink.sync.items():
                await sync_module.async_arm(arm)
                log_web(f"{'Armed' if arm else 'Disarmed'} {sync_name}")

            duration = time.time() - start_time
            log_web_performance(f"set_blink_arm_state | {duration:.2f}s | armed={arm}")
            return {"success": True, "armed": arm}
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error setting arm state (took {duration:.2f}s): {e}", e)
        log_web_performance(f"set_blink_arm_state | {duration:.2f}s | ERROR")
        return {"success": False, "error": str(e)}


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/')
def index():
    start_time = time.time()
    try:
        cameras = get_camera_data()
        location = get_location()
        camera_names = [cam['normalized_name'] for cam in cameras]
        all_snoozed = snooze_manager.are_all_cameras_snoozed(camera_names)

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except:
            config = {"poll_interval": 300}

        duration = time.time() - start_time
        log_web_performance(f"GET / | {duration:.2f}s | {len(cameras)} cameras")

        return render_template('index.html',
                               cameras=cameras,
                               location=location,
                               all_snoozed=all_snoozed,
                               config=config)
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error rendering index (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET / | {duration:.2f}s | ERROR")
        return "Internal Server Error", 500


@app.route('/api/cameras')
def api_cameras():
    start_time = time.time()
    try:
        cameras = get_camera_data()
        duration = time.time() - start_time
        log_web_performance(f"GET /api/cameras | {duration:.2f}s | {len(cameras)} cameras")
        return jsonify(cameras)
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/cameras (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/cameras | {duration:.2f}s | ERROR")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cameras/refresh')
def refresh_cameras():
    start_time = time.time()
    try:
        cameras_data = get_camera_data()
        duration = time.time() - start_time
        log_web_performance(f"GET /api/cameras/refresh | {duration:.2f}s | {len(cameras_data)} cameras")
        return jsonify({'success': True, 'cameras': cameras_data})
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/cameras/refresh (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/cameras/refresh | {duration:.2f}s | ERROR")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera/<camera_name>/last_update')
def api_camera_last_update(camera_name):
    start_time = time.time()
    try:
        normalized_name = normalize_camera_name(camera_name)
        cam_folder = CAMERAS_DIR / normalized_name
        last_photo_time = get_most_recent_photo_time(cam_folder)
        duration = time.time() - start_time

        if last_photo_time:
            log_web_performance(f"GET /api/camera/{camera_name}/last_update | {duration:.2f}s | SUCCESS")
            return jsonify({
                "success": True,
                "camera": camera_name,
                "last_update": last_photo_time.isoformat(),
                "last_update_formatted": last_photo_time.strftime("%m/%d/%Y %I:%M:%S %p"),
                "last_update_relative": get_relative_time(last_photo_time)
            })
        else:
            log_web_performance(f"GET /api/camera/{camera_name}/last_update | {duration:.2f}s | NOT_FOUND")
            return jsonify({"success": False, "camera": camera_name, "error": "No photos found"}), 404
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/camera/{camera_name}/last_update (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/camera/{camera_name}/last_update | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


def get_relative_time(dt: datetime) -> str:
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
    start_time = time.time()
    try:
        location = get_location()
        duration = time.time() - start_time
        log_web_performance(f"GET /api/location | {duration:.2f}s | SUCCESS")
        return jsonify(location)
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/location (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/location | {duration:.2f}s | ERROR")
        return jsonify({'error': str(e)}), 500


@app.route('/api/radar/config')
def api_radar_config():
    """Return complete radar configuration including Mapbox settings."""
    start_time = time.time()
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        location = config.get("location", {})
        radar_settings = config.get("radar", {})

        radar_data = {
            "enabled": radar_settings.get("enabled", False),
            "lat": location.get("lat", 40.3044),
            "lon": location.get("lon", -80.0717),
            "radar_station": location.get("radar_station", "KPBZ"),
            "city": location.get("city", "Bethel Park"),
            "state": location.get("state", "PA"),
            "display": location.get("display", "Bethel Park, PA"),
            "zoom": radar_settings.get("zoom", 7),
            "frames": radar_settings.get("frames", 5),
            "color": radar_settings.get("color", 2),
            "smooth": radar_settings.get("smooth", 1),
            "snow": radar_settings.get("snow", 1),
            "mapbox_token": radar_settings.get("mapbox_token", ""),
            "basemap_style": radar_settings.get("basemap_style", ""),
            "overlay_style": radar_settings.get("overlay_style", "")
        }

        duration = time.time() - start_time
        log_web_performance(f"GET /api/radar/config | {duration:.2f}s | SUCCESS")
        return jsonify({"success": True, "radar_config": radar_data})
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/radar/config (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/radar/config | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/weather')
def api_weather():
    """Fetch weather data from Tomorrow.io API with server-side caching"""
    start_time = time.time()

    with weather_cache['lock']:
        if weather_cache['data'] and weather_cache['timestamp']:
            cache_age = (datetime.now() - weather_cache['timestamp']).total_seconds()
            if cache_age < WEATHER_CACHE_DURATION:
                duration = time.time() - start_time
                log_web(f"Serving cached weather data (age: {int(cache_age)}s)")
                log_web_performance(f"GET /api/weather | {duration:.2f}s | CACHED")
                return jsonify(weather_cache['data'])

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        weather_config = config.get("weather", {})
        api_key = weather_config.get("api_key")

        if not api_key:
            log_web("ERROR: Tomorrow.io API key not configured")
            return jsonify({"error": "Tomorrow.io API key not configured"}), 500

        location = get_location()
        lat = location.get('lat', 40.3044)
        lon = location.get('lon', -80.0717)

        url = "https://api.tomorrow.io/v4/timelines"
        params = {
            "location": f"{lat},{lon}",
            "apikey": api_key,
            "units": "imperial",
            "timesteps": "current",
            "fields": "temperature,weatherCode,temperatureApparent,humidity,windSpeed,windDirection,windGust,pressureSeaLevel,precipitationType"
        }

        log_web(f"Fetching weather from Tomorrow.io Timelines API for {lat},{lon}")
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            timelines = data.get("data", {}).get("timelines", [])
            if not timelines or not timelines[0].get("intervals"):
                return jsonify({"error": "Invalid weather data format"}), 500

            values = timelines[0]["intervals"][0]["values"]

            weather_code = values.get("weatherCode", 0)
            weather_desc = map_weather_code(weather_code)

            formatted_response = {
                "current_condition": [{
                    "temp_F": str(int(values.get("temperature", 0))),
                    "FeelsLikeF": str(int(values.get("temperatureApparent", 0))),
                    "humidity": str(int(values.get("humidity", 0))),
                    "weatherDesc": [{"value": weather_desc}],
                    "windspeedMiles": str(int(values.get("windSpeed", 0))),
                    "winddir16Point": get_wind_direction(values.get("windDirection", 0)),
                    "precipMM": str(values.get("precipitationIntensity", 0)),
                    "pressure": str(int(values.get("pressureSeaLevel", 0)))
                }]
            }

            with weather_cache['lock']:
                weather_cache['data'] = formatted_response
                weather_cache['timestamp'] = datetime.now()

            duration = time.time() - start_time
            log_web(f"Weather fetched successfully: {weather_desc}, {values.get('temperature')}°F")
            log_web_performance(f"GET /api/weather | {duration:.2f}s | SUCCESS")
            return jsonify(formatted_response)

        elif response.status_code == 429:
            log_web(f"Tomorrow.io API rate limit hit!")
            log_web(f"Response: {response.text}")

            with weather_cache['lock']:
                if weather_cache['data']:
                    cache_age = (datetime.now() - weather_cache['timestamp']).total_seconds()
                    log_web(f"Returning stale cached data (age: {int(cache_age)}s) due to rate limit")
                    duration = time.time() - start_time
                    log_web_performance(f"GET /api/weather | {duration:.2f}s | RATE_LIMIT_CACHED")
                    return jsonify(weather_cache['data'])

            duration = time.time() - start_time
            log_web_performance(f"GET /api/weather | {duration:.2f}s | RATE_LIMIT")
            return jsonify({"error": "Weather service rate limit exceeded"}), 429
        else:
            log_web(f"Tomorrow.io API error: {response.status_code}")
            log_web(f"Response: {response.text}")
            duration = time.time() - start_time
            log_web_performance(f"GET /api/weather | {duration:.2f}s | HTTP_{response.status_code}")
            return jsonify({"error": "Weather service unavailable"}), 503

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error fetching weather (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/weather | {duration:.2f}s | ERROR")

        with weather_cache['lock']:
            if weather_cache['data']:
                cache_age = (datetime.now() - weather_cache['timestamp']).total_seconds()
                log_web(f"Returning cached data (age: {int(cache_age)}s) due to error")
                return jsonify(weather_cache['data'])

        return jsonify({"error": str(e)}), 500


def map_weather_code(code):
    """Map Tomorrow.io weather codes to descriptive text"""
    weather_codes = {
        0: "Unknown",
        1000: "Clear",
        1001: "Cloudy",
        1100: "Mostly Clear",
        1101: "Partly Cloudy",
        1102: "Mostly Cloudy",
        2000: "Fog",
        2100: "Light Fog",
        3000: "Light Wind",
        3001: "Wind",
        3002: "Strong Wind",
        4000: "Drizzle",
        4001: "Rain",
        4200: "Light Rain",
        4201: "Heavy Rain",
        5000: "Snow",
        5001: "Flurries",
        5100: "Light Snow",
        5101: "Heavy Snow",
        6000: "Freezing Drizzle",
        6001: "Freezing Rain",
        6200: "Light Freezing Rain",
        6201: "Heavy Freezing Rain",
        7000: "Ice Pellets",
        7101: "Heavy Ice Pellets",
        7102: "Light Ice Pellets",
        8000: "Thunderstorm"
    }
    return weather_codes.get(code, "Unknown")


def get_wind_direction(degrees):
    """Convert wind direction degrees to compass direction"""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]


@app.route('/image/<camera_name>/<path:image_path>')
def serve_camera_image(camera_name, image_path):
    """Serve camera images from date-organized folders"""
    start_time = time.time()
    try:
        cam_folder = CAMERAS_DIR / camera_name
        image_file = cam_folder / image_path

        if image_file.exists() and image_file.is_file():
            duration = time.time() - start_time
            log_web_performance(f"GET /image/{camera_name}/{image_path} | {duration:.2f}s | SUCCESS")
            return send_file(image_file, mimetype='image/jpeg')
        else:
            duration = time.time() - start_time
            log_web_performance(f"GET /image/{camera_name}/{image_path} | {duration:.2f}s | NOT_FOUND")
            return "Image not found", 404
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error serving image {camera_name}/{image_path} (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /image/{camera_name}/{image_path} | {duration:.2f}s | ERROR")
        return "Error serving image", 500


# ============================================================================
# SNOOZE ENDPOINTS
# ============================================================================

@app.route('/api/snooze/status/<camera_name>')
def api_snooze_status(camera_name):
    """Get snooze status for a specific camera"""
    start_time = time.time()
    try:
        status = snooze_manager.get_snooze_status(camera_name)
        duration = time.time() - start_time
        log_web_performance(f"GET /api/snooze/status/{camera_name} | {duration:.2f}s | SUCCESS")
        return jsonify(status)
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/status/{camera_name} (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/snooze/status/{camera_name} | {duration:.2f}s | ERROR")
        return jsonify({"error": str(e)}), 500


@app.route('/api/snooze/set', methods=['POST'])
def api_snooze_set():
    """Set snooze for a camera"""
    start_time = time.time()
    try:
        data = request.json
        camera_name = data.get('camera_name')
        duration_minutes = data.get('duration_minutes')

        if not camera_name or not duration_minutes:
            duration = time.time() - start_time
            log_web_performance(f"POST /api/snooze/set | {duration:.2f}s | BAD_REQUEST")
            return jsonify({"success": False, "error": "Missing parameters"}), 400

        snooze_manager.snooze_camera(camera_name, duration_minutes)
        duration = time.time() - start_time
        log_web(f"Snoozed {camera_name} for {duration_minutes} minutes")
        log_web_performance(f"POST /api/snooze/set | {duration:.2f}s | {camera_name} {duration_minutes}m")
        return jsonify({"success": True})

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/set (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/snooze/set | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/unset', methods=['POST'])
def api_snooze_unset():
    """Remove snooze from a camera"""
    start_time = time.time()
    try:
        data = request.json
        camera_name = data.get('camera_name')

        if not camera_name:
            duration = time.time() - start_time
            log_web_performance(f"POST /api/snooze/unset | {duration:.2f}s | BAD_REQUEST")
            return jsonify({"success": False, "error": "Missing camera_name"}), 400

        snooze_manager.unsnooze_camera(camera_name)
        duration = time.time() - start_time
        log_web(f"Removed snooze for {camera_name}")
        log_web_performance(f"POST /api/snooze/unset | {duration:.2f}s | {camera_name}")
        return jsonify({"success": True})

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/unset (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/snooze/unset | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/status')
def api_snooze_all_status():
    """Check if all cameras are snoozed"""
    start_time = time.time()
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        cameras = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras]

        all_snoozed = snooze_manager.are_all_cameras_snoozed(camera_names)

        duration = time.time() - start_time
        log_web_performance(f"GET /api/snooze/all/status | {duration:.2f}s | all_snoozed={all_snoozed}")
        return jsonify({
            "success": True,
            "all_snoozed": all_snoozed
        })
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/all/status (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/snooze/all/status | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/set', methods=['POST'])
def api_snooze_all_set():
    """Snooze all cameras"""
    start_time = time.time()
    try:
        data = request.json
        duration_minutes = data.get('duration_minutes')

        if not duration_minutes:
            duration = time.time() - start_time
            log_web_performance(f"POST /api/snooze/all/set | {duration:.2f}s | BAD_REQUEST")
            return jsonify({"success": False, "error": "Missing duration_minutes"}), 400

        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        cameras = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras]

        snooze_manager.snooze_all_cameras(camera_names, duration_minutes)

        duration = time.time() - start_time
        log_web(f"Snoozed all {len(camera_names)} cameras for {duration_minutes} minutes")
        log_web_performance(
            f"POST /api/snooze/all/set | {duration:.2f}s | {len(camera_names)} cameras {duration_minutes}m")
        return jsonify({
            "success": True,
            "count": len(camera_names)
        })

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/all/set (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/snooze/all/set | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/unset', methods=['POST'])
def api_snooze_all_unset():
    """Unsnooze all cameras"""
    start_time = time.time()
    try:
        snooze_manager.unsnooze_all_cameras()
        duration = time.time() - start_time
        log_web("Unsnoozed all cameras")
        log_web_performance(f"POST /api/snooze/all/unset | {duration:.2f}s | SUCCESS")
        return jsonify({"success": True})

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/all/unset (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/snooze/all/unset | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/cleanup', methods=['POST'])
def api_snooze_cleanup():
    """Cleanup expired snoozes"""
    start_time = time.time()
    try:
        snooze_manager.cleanup_expired_snoozes()
        duration = time.time() - start_time
        log_web_performance(f"POST /api/snooze/cleanup | {duration:.2f}s | SUCCESS")
        return jsonify({"success": True})

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/snooze/cleanup (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/snooze/cleanup | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ARM/DISARM ENDPOINTS
# ============================================================================

@app.route('/api/arm/status')
def api_arm_status():
    """Get current arm/disarm status"""
    start_time = time.time()
    try:
        result = asyncio.run(get_blink_status())
        duration = time.time() - start_time
        log_web_performance(f"GET /api/arm/status | {duration:.2f}s | armed={result.get('armed', False)}")
        return jsonify(result)
    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/arm/status (took {duration:.2f}s): {e}", e)
        log_web_performance(f"GET /api/arm/status | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/arm/set', methods=['POST'])
def api_arm_set():
    """Set arm/disarm state"""
    start_time = time.time()
    try:
        data = request.json
        arm = data.get('arm', False)

        result = asyncio.run(set_blink_arm_state(arm))
        duration = time.time() - start_time
        log_web_performance(f"POST /api/arm/set | {duration:.2f}s | arm={arm}")
        return jsonify(result)

    except Exception as e:
        duration = time.time() - start_time
        log_web_error(f"Error in /api/arm/set (took {duration:.2f}s): {e}", e)
        log_web_performance(f"POST /api/arm/set | {duration:.2f}s | ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Ensure log folders exist
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    WEBSERVER_LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    PERF_LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    # Start log rotation monitoring
    log_rotator.start_midnight_rotation_thread()

    log_web("=" * 60)
    log_web("BLINK WEB SERVER STARTING")
    log_web("=" * 60)
    log_web(f"Log folder: {LOG_FOLDER}")
    log_web(f"Web server log: {get_current_log_file(WEBSERVER_LOG_FOLDER, 'webserver')}")
    log_web(f"Performance log: {get_current_log_file(PERF_LOG_FOLDER, 'webserver-perf')}")
    log_web(f"Weather cache: {WEATHER_CACHE_DURATION // 60} minutes")
    log_web(f"Log rotation: Enabled (keeps 5 days of history)")
    log_web("=" * 60)

    local_ip = get_local_ip()
    try:
        from waitress import serve

        logging.getLogger("waitress.queue").setLevel(logging.ERROR)
        log_web("Using Waitress production server")
        log_web(f"Local access:   http://localhost:5000")
        log_web(f"Network access: http://{local_ip}:5000")
        log_web("=" * 60)
        log_web("Press Ctrl+C to stop the server")
        log_web("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=6, channel_timeout=120, backlog=128)
    except ImportError:
        log_web("Waitress not found - using Flask development server")
        log_web("For production use, install Waitress: pip install waitress")
        log_web("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=False)