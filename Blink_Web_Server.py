from flask import Flask, render_template, send_file, jsonify, request, make_response
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
from nws_alerts import NWSAlerts, validate_nws_zone

app = Flask(__name__)

CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"
ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

snooze_manager = AlertSnooze()
logging.getLogger('blinkpy.sync_module').setLevel(logging.CRITICAL)
logging.getLogger('waitress.queue').setLevel(logging.ERROR)

# Initialize log rotator
log_rotator = LogRotator(LOG_FOLDER, max_backups=5)

# Define log file paths
WEBSERVER_LOG_FOLDER = log_rotator.get_system_log_folder("webserver")
PERF_LOG_FOLDER = log_rotator.get_system_log_folder("performance")
NWS_LOG_FOLDER = log_rotator.get_system_log_folder("nws-alerts")

# Weather caching
weather_cache = {
    'data': None,
    'timestamp': None,
    'lock': threading.Lock()
}

WEATHER_CACHE_DURATION = 30 * 60  # 30 minutes in seconds

# NWS Alert Monitor (global)
nws_monitor = None


# ============================================================================
# CACHE-CONTROL HEADERS
# ============================================================================

def add_no_cache_headers(response):
    """Add cache-busting headers to all responses"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


@app.after_request
def apply_caching(response):
    """Apply no-cache headers to all responses"""
    return add_no_cache_headers(response)


# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

def get_current_log_file(folder: Path, name: str) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return folder / f"{name}_{date_str}.log"


def log_web(msg: str):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(WEBSERVER_LOG_FOLDER, "webserver")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


def log_web_error(msg: str, exception: Exception = None):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(WEBSERVER_LOG_FOLDER, "webserver")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | ERROR | {msg}\n")
        if exception:
            import traceback
            f.write(traceback.format_exc() + "\n")


def log_web_performance(msg: str):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(PERF_LOG_FOLDER, "webserver-perf")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


def log_nws(msg: str):
    """Log NWS alert events to system/nws-alerts/nws-alerts_YYYY-MM-DD.log"""
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(NWS_LOG_FOLDER, "nws-alerts")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        log_web_error("Could not determine local IP", e)
        return "127.0.0.1"


def normalize_camera_name(cam_name: str) -> str:
    return cam_name.lower().replace(" ", "-")


def wifi_bars(dbm):
    if dbm is None:
        return 0
    if dbm >= -50: return 5
    if dbm >= -60: return 4
    if dbm >= -70: return 3
    if dbm >= -80: return 2
    if dbm >= -90: return 1
    return 0


def get_camera_images(camera_folder: Path, max_images: int = 5) -> list:
    """Get most recent images from camera folder (date-organized)"""
    images = []

    if not camera_folder.exists():
        return images

    # Get all date folders (YYYY-MM-DD)
    date_folders = sorted(
        [f for f in camera_folder.iterdir() if f.is_dir() and f.name.count('-') == 2],
        reverse=True
    )

    # Collect images from newest folders first
    for date_folder in date_folders:
        folder_images = sorted(
            date_folder.glob("*.jpg"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        for img in folder_images:
            # Store relative path: YYYY-MM-DD/filename.jpg
            relative_path = f"{date_folder.name}/{img.name}"
            images.append(relative_path)

            if len(images) >= max_images:
                return images

    return images


def get_camera_images_fresh(camera_folder: Path, max_images: int = 5) -> list:
    """
    Get most recent images with explicit freshness check (cache-busting)
    """
    images = []

    if not camera_folder.exists():
        return images

    try:
        date_folders = sorted(
            [f for f in camera_folder.iterdir() 
             if f.is_dir() and f.name.count('-') == 2 and len(f.name) == 10],
            reverse=True
        )
    except Exception as e:
        log_web_error(f"Error listing date folders in {camera_folder}", e)
        return images

    for date_folder in date_folders:
        try:
            folder_images = sorted(
                [f for f in date_folder.glob("*.jpg") if f.is_file()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            for img in folder_images:
                if img.exists() and img.is_file():
                    relative_path = f"{date_folder.name}/{img.name}"
                    images.append(relative_path)

                    if len(images) >= max_images:
                        return images
                        
        except Exception as e:
            log_web_error(f"Error reading images from {date_folder}", e)
            continue

    return images


def read_camera_status(camera_folder: Path) -> dict:
    """Read camera status from status.json file"""
    status_file = camera_folder / "status.json"
    
    default_status = {
        "temperature": "N/A",
        "battery": "N/A",
        "wifi_strength": None
    }
    
    if not status_file.exists():
        return default_status
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
        
        return {
            "temperature": status_data.get("temperature", "N/A"),
            "battery": status_data.get("battery", "N/A"),
            "wifi_strength": status_data.get("wifi_strength", None)
        }
        
    except Exception as e:
        log_web_error(f"Error reading status file {status_file}", e)
        return default_status


def detect_camera_issues(camera_folder: Path, camera_name: str, images: list) -> dict:
    """Detect camera issues"""
    alerts = {
        "is_offline": False,
        "offline_reason": "",
        "has_duplicates": False,
        "duplicate_count": 0
    }

    if not images or len(images) == 0:
        alerts["is_offline"] = True
        alerts["offline_reason"] = "No images available"
        return alerts

    duplicate_count = sum(1 for img_path in images[:3] if "_DUPLICATE" in img_path)
    
    if duplicate_count >= 2:
        alerts["has_duplicates"] = True
        alerts["duplicate_count"] = duplicate_count

    return alerts


def map_weather_code(code):
    """Map Tomorrow.io weather codes to descriptive text"""
    weather_codes = {
        0: "Unknown", 1000: "Clear", 1001: "Cloudy", 1100: "Mostly Clear",
        1101: "Partly Cloudy", 1102: "Mostly Cloudy", 2000: "Fog",
        2100: "Light Fog", 4000: "Drizzle", 4001: "Rain", 4200: "Light Rain",
        4201: "Heavy Rain", 5000: "Snow", 5001: "Flurries", 5100: "Light Snow",
        5101: "Heavy Snow", 8000: "Thunderstorm"
    }
    return weather_codes.get(code, "Unknown")


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
            host_url = token_data["host"]
            region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")
            blink.auth = Auth({}, session=session, no_prompt=True)
            blink.auth.region_id = region_id
            blink.auth.host = host_url
            blink.auth.token = token_data["token"]
            blink.auth.refresh_token = token_data["refresh_token"]
            blink.auth.client_id = token_data["client_id"]
            blink.auth.account_id = token_data["account_id"]
            blink.auth.user_id = token_data["user_id"]
            blink.urls = BlinkURLHandler(region_id)
            await blink.setup_post_verify()
            await blink.refresh()

            armed = any(sync.arm for sync in blink.sync.values())
            log_web_performance(f"get_blink_status | {time.time() - start_time:.2f}s")
            return {"armed": armed, "success": True}
    except Exception as e:
        log_web_error("Error getting Blink status", e)
        return {"success": False, "error": str(e)}


async def set_blink_arm_state(arm: bool):
    start_time = time.time()
    try:
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)

        async with ClientSession() as session:
            blink = Blink(session=session)
            host_url = token_data["host"]
            region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")
            blink.auth = Auth({}, session=session, no_prompt=True)
            blink.auth.region_id = region_id
            blink.auth.host = host_url
            blink.auth.token = token_data["token"]
            blink.auth.refresh_token = token_data["refresh_token"]
            blink.auth.client_id = token_data["client_id"]
            blink.auth.account_id = token_data["account_id"]
            blink.auth.user_id = token_data["user_id"]
            blink.urls = BlinkURLHandler(region_id)
            await blink.setup_post_verify()

            for sync in blink.sync.values():
                await sync.async_arm(arm)

            log_web_performance(f"set_blink_arm_state | {time.time() - start_time:.2f}s")
            return {"success": True, "armed": arm}
    except Exception as e:
        log_web_error("Error setting Blink arm state", e)
        return {"success": False, "error": str(e)}


# ============================================================================
# NWS ALERT INITIALIZATION
# ============================================================================

def start_nws_monitoring():
    global nws_monitor
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        nws_config = config.get("nws_alerts", {})
        if not nws_config.get("enabled"):
            log_web("NWS alerts disabled")
            return

        zone = nws_config.get("zone")
        if not zone:
            log_web("NWS enabled but no zone configured")
            return

        nws_monitor = NWSAlerts(zone=zone, log_function=log_nws)
        nws_monitor.start_polling_thread()
        log_web(f"NWS alert monitoring started for zone {zone}")

    except Exception as e:
        log_web_error("Failed to start NWS monitoring", e)


# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras_list = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)
        location = config.get("location", {})

        cameras = []
        for cam_name in cameras_list:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name

            images = get_camera_images(cam_folder, max_images=carousel_images)
            alerts = detect_camera_issues(cam_folder, cam_name, images)
            snooze_status = snooze_manager.get_snooze_status(normalized_name)
            
            status = read_camera_status(cam_folder)

            cameras.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "images": images,
                "temperature": status["temperature"],
                "battery": status["battery"],
                "wifi": wifi_bars(status["wifi_strength"]),
                "snooze_status": snooze_status,
                "alerts": alerts
            })

        all_snoozed = snooze_manager.are_all_cameras_snoozed(
            [cam["normalized_name"] for cam in cameras]
        )

        log_web(f"Index page loaded with {len(cameras)} cameras")

        response = make_response(render_template('index.html',
                               cameras=cameras,
                               config=config,
                               location=location,
                               all_snoozed=all_snoozed))
        
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

    except Exception as e:
        log_web_error("Error loading index page", e)
        return f"Error: {e}", 500


@app.route('/image/<camera_name>/<path:image_path>')
def serve_image(camera_name, image_path):
    try:
        cam_folder = CAMERAS_DIR / camera_name
        image_file = cam_folder / image_path

        if image_file.exists():
            mtime = image_file.stat().st_mtime
            
            response = send_file(
                image_file, 
                mimetype='image/jpeg',
                max_age=0,
                etag=str(mtime)
            )
            
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            return response
        else:
            log_web_error(f"Image not found: {image_file}")
            return "Image not found", 404

    except Exception as e:
        log_web_error(f"Error serving image: {camera_name}/{image_path}", e)
        return str(e), 500


@app.route('/api/weather')
def api_weather():
    start_time = time.time()
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        weather_config = config.get("weather", {})
        location = config.get("location", {})

        if not weather_config.get("enabled") or not weather_config.get("api_key"):
            return jsonify({"error": "Weather not configured"}), 400

        with weather_cache['lock']:
            if weather_cache['data'] and weather_cache['timestamp']:
                age = time.time() - weather_cache['timestamp']
                if age < WEATHER_CACHE_DURATION:
                    log_web_performance(f"weather_cache_hit | {time.time() - start_time:.2f}s")
                    return jsonify(weather_cache['data'])

        api_key = weather_config["api_key"]
        lat = location.get("lat", 40.3267)
        lon = location.get("lon", -80.0171)

        url = f"https://api.tomorrow.io/v4/weather/realtime?location={lat},{lon}&apikey={api_key}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        weather_code = data["data"]["values"].get("weatherCode", 0)
        weather_desc = map_weather_code(weather_code)

        weather_data = {
            "current_condition": [{
                "temp_F": round(data["data"]["values"]["temperature"] * 9 / 5 + 32),
                "FeelsLikeF": round(data["data"]["values"]["temperatureApparent"] * 9 / 5 + 32),
                "humidity": data["data"]["values"]["humidity"],
                "weatherDesc": [{"value": weather_desc}]
            }]
        }

        with weather_cache['lock']:
            weather_cache['data'] = weather_data
            weather_cache['timestamp'] = time.time()

        log_web_performance(f"weather_api_call | {time.time() - start_time:.2f}s")
        return jsonify(weather_data)

    except Exception as e:
        log_web_error("Weather API error", e)
        return jsonify({"error": str(e)}), 500


@app.route('/api/radar/config')
def api_radar_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        radar_config = config.get("radar", {})
        location = config.get("location", {})

        radar_config["lat"] = location.get("lat", 40.3267)
        radar_config["lon"] = location.get("lon", -80.0171)

        return jsonify({"success": True, "radar_config": radar_config})

    except Exception as e:
        log_web_error("Error loading radar config", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/arm/status')
def api_arm_status():
    result = asyncio.run(get_blink_status())
    return jsonify(result)


@app.route('/api/arm/set', methods=['POST'])
def api_arm_set():
    data = request.get_json()
    arm = data.get('arm', False)
    result = asyncio.run(set_blink_arm_state(arm))
    return jsonify(result)


@app.route('/api/snooze/status/<camera_name>')
def api_snooze_status(camera_name):
    status = snooze_manager.get_snooze_status(camera_name)
    return jsonify(status)


@app.route('/api/snooze/set', methods=['POST'])
def api_snooze_set():
    data = request.get_json()
    camera_name = data.get('camera_name')
    duration_minutes = data.get('duration_minutes')

    if not camera_name or not duration_minutes:
        return jsonify({"success": False, "error": "Missing parameters"}), 400

    try:
        snooze_manager.snooze_camera(camera_name, duration_minutes)
        return jsonify({"success": True})
    except Exception as e:
        log_web_error(f"Error setting snooze for {camera_name}", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/unset', methods=['POST'])
def api_snooze_unset():
    data = request.get_json()
    camera_name = data.get('camera_name')

    if not camera_name:
        return jsonify({"success": False, "error": "Missing camera_name"}), 400

    try:
        snooze_manager.unsnooze_camera(camera_name)
        return jsonify({"success": True})
    except Exception as e:
        log_web_error(f"Error removing snooze for {camera_name}", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/status')
def api_snooze_all_status():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras_list = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras_list]

        all_snoozed = snooze_manager.are_all_cameras_snoozed(camera_names)

        return jsonify({"success": True, "all_snoozed": all_snoozed})

    except Exception as e:
        log_web_error("Error checking snooze all status", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/set', methods=['POST'])
def api_snooze_all_set():
    data = request.get_json()
    duration_minutes = data.get('duration_minutes')

    if not duration_minutes:
        return jsonify({"success": False, "error": "Missing duration_minutes"}), 400

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras_list = config.get("cameras", [])
        camera_names = [normalize_camera_name(cam) for cam in cameras_list]

        snooze_manager.snooze_all_cameras(camera_names, duration_minutes)

        return jsonify({"success": True, "count": len(camera_names)})

    except Exception as e:
        log_web_error("Error snoozing all cameras", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/all/unset', methods=['POST'])
def api_snooze_all_unset():
    try:
        snooze_manager.unsnooze_all_cameras()
        return jsonify({"success": True})
    except Exception as e:
        log_web_error("Error unsnoozing all cameras", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snooze/cleanup', methods=['POST'])
def api_snooze_cleanup():
    try:
        snooze_manager.cleanup_expired_snoozes()
        return jsonify({"success": True})
    except Exception as e:
        log_web_error("Error cleaning up snoozes", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/cameras/refresh')
def api_cameras_refresh():
    """Enhanced camera refresh API with cache busting"""
    start_time = time.time()
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras_list = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)

        cameras = []
        
        for cam_name in cameras_list:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name

            images = get_camera_images_fresh(cam_folder, max_images=carousel_images)
            alerts = detect_camera_issues(cam_folder, cam_name, images)
            status = read_camera_status(cam_folder)

            last_update = None
            last_update_formatted = None
            
            if images:
                newest_image_path = cam_folder / images[0]
                if newest_image_path.exists():
                    try:
                        last_update = datetime.fromtimestamp(newest_image_path.stat().st_mtime)
                        last_update_formatted = last_update.strftime("%m/%d/%Y %I:%M:%S %p")
                    except Exception as e:
                        log_web_error(f"Error getting timestamp for {newest_image_path}", e)

            cameras.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "images": images,
                "temperature": status["temperature"],
                "battery": status["battery"],
                "wifi": wifi_bars(status["wifi_strength"]),
                "last_update": last_update.isoformat() if last_update else None,
                "last_update_formatted": last_update_formatted,
                "alerts": alerts
            })

        duration = time.time() - start_time
        log_web_performance(f"api_cameras_refresh | {duration:.2f}s | {len(cameras)} cameras")

        response = jsonify({
            "success": True,
            "cameras": cameras,
            "refresh_time": datetime.now().isoformat(),
            "cache_buster": int(time.time() * 1000)
        })
        
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

    except Exception as e:
        log_web_error("Error refreshing cameras", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/nws/config')
def api_nws_config():
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

    nws_config = config.get("nws_alerts", {})
    has_alerts = nws_monitor.get_alert_data().get("alert_active", False) if nws_monitor else False

    return jsonify({
        "success": True,
        "enabled": nws_config.get("enabled", False),
        "zone": nws_config.get("zone", ""),
        "has_alerts": has_alerts
    })


@app.route('/api/nws/alerts')
def api_nws_alerts():
    if not nws_monitor:
        return jsonify({
            "success": True,
            "alerts": [],
            "alert_active": False
        })

    return jsonify({
        "success": True,
        **nws_monitor.get_alert_data()
    })


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    WEBSERVER_LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    PERF_LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    NWS_LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    log_rotator.start_midnight_rotation_thread()
    start_nws_monitoring()

    log_web("=" * 60)
    log_web("BLINK WEB SERVER STARTING (WITH CACHE-BUSTING)")
    log_web("=" * 60)
    log_web(f"Web server log: {get_current_log_file(WEBSERVER_LOG_FOLDER, 'webserver')}")
    log_web(f"Performance log: {get_current_log_file(PERF_LOG_FOLDER, 'webserver-perf')}")
    log_web(f"NWS alerts log: {get_current_log_file(NWS_LOG_FOLDER, 'nws-alerts')}")
    log_web("=" * 60)

    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=6)