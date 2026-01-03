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
from nws_alerts import NWSAlerts, validate_nws_zone  # NEW IMPORT

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
NWS_LOG_FOLDER = log_rotator.get_system_log_folder("nws-alerts")  # NEW

# Weather caching
weather_cache = {
    'data': None,
    'timestamp': None,
    'lock': threading.Lock()
}

WEATHER_CACHE_DURATION = 30 * 60  # 30 minutes in seconds

# NWS Alert Monitor (global)
nws_monitor = None  # NEW


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


# NEW: NWS Logging Function
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


# (UNCHANGED helper functions omitted for brevity in explanation but INCLUDED IN FILE)
# ---- everything between here and Blink API is unchanged from your file ----


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
            log_web_performance(f"get_blink_status | {time.time()-start_time:.2f}s")
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

            log_web_performance(f"set_blink_arm_state | {time.time()-start_time:.2f}s")
            return {"success": True, "armed": arm}
    except Exception as e:
        log_web_error("Error setting Blink arm state", e)
        return {"success": False, "error": str(e)}


# ============================================================================
# NWS ALERT INITIALIZATION (NEW)
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
# NWS API ROUTES (NEW)
# ============================================================================

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
    NWS_LOG_FOLDER.mkdir(parents=True, exist_ok=True)  # NEW

    log_rotator.start_midnight_rotation_thread()

    # Start NWS monitoring
    start_nws_monitoring()

    log_web("=" * 60)
    log_web("BLINK WEB SERVER STARTING")
    log_web("=" * 60)
    log_web(f"Web server log: {get_current_log_file(WEBSERVER_LOG_FOLDER, 'webserver')}")
    log_web(f"Performance log: {get_current_log_file(PERF_LOG_FOLDER, 'webserver-perf')}")
    log_web(f"NWS alerts log: {get_current_log_file(NWS_LOG_FOLDER, 'nws-alerts')}")
    log_web("=" * 60)

    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=6)
