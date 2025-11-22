import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import sys
import warnings
from PIL import Image
import threading
import time
import io

# Import the new log rotation module
from log_rotation import LogRotator

# Import the new camera organizer module
from camera_organizer import CameraOrganizer

# Suppress the specific blinkpy warning about last_refresh
warnings.filterwarnings("ignore", message=".*last_refresh.*")


# Redirect stderr to suppress blinkpy interval calculation errors
class SuppressSpecificErrors:
    def __init__(self, stderr):
        self.stderr = stderr
        self.suppress_patterns = [
            "Error calculating interval",
            "unsupported operand type(s) for -: 'NoneType' and 'int'"
        ]

    def write(self, text):
        # Only write if it doesn't contain our suppressed patterns
        if not any(pattern in text for pattern in self.suppress_patterns):
            self.stderr.write(text)

    def flush(self):
        self.stderr.flush()


# Replace stderr with our filtered version
sys.stderr = SuppressSpecificErrors(sys.stderr)

# ---------------- Configuration ---------------- #
TOKEN_FILE = "blink_token.json"
CONFIG_FILE = "blink_config.json"

# Load token
with open(TOKEN_FILE, "r") as f:
    token_data = json.load(f)

# Load config (or use defaults)
if Path(CONFIG_FILE).exists():
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    # Create default config file
    config = {
        "poll_interval": 300,
        "max_days": 7,
        "cameras": [
            "Front Door",
            "Tree Front Door",
            "Back Door",
            "Garage Door"
        ]
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

POLL_INTERVAL = config.get("poll_interval", 300)  # seconds
MAX_DAYS = config.get("max_days", 7)
CAMERAS = config.get("cameras", [])

ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

# Create directories
CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FOLDER.mkdir(parents=True, exist_ok=True)

# Initialize log rotator (keeps 5 days of history)
log_rotator = LogRotator(LOG_FOLDER, max_backups=5)

# Initialize camera organizer
camera_organizer = CameraOrganizer(CAMERAS_DIR, max_days=MAX_DAYS)

# Define log file paths in organized folders
MAIN_LOG_FOLDER = log_rotator.get_system_log_folder("main")
TOKEN_LOG_FOLDER = log_rotator.get_system_log_folder("token")


# ---------------- Utility Functions ---------------- #
def normalize_camera_name(cam_name: str) -> str:
    """Convert camera name to lowercase kebab-case"""
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


def get_current_log_file(folder: Path, name: str) -> Path:
    """Get current log file with today's date"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return folder / f"{name}_{date_str}.log"


def log_main(msg: str):
    """Log to system/main/main_YYYY-MM-DD.log with automatic rotation check"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(MAIN_LOG_FOLDER, "main")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())


def log_token(msg: str):
    """Log token refresh events to system/token/token_YYYY-MM-DD.log file"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(TOKEN_LOG_FOLDER, "token")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    # Also log to main log
    log_main(msg)


def get_camera_log_file(cam_name: str) -> Path:
    """Get the log file path for a camera in its own folder"""
    normalized_name = normalize_camera_name(cam_name)
    camera_log_folder = log_rotator.get_camera_log_folder(normalized_name)
    date_str = datetime.now().strftime("%Y-%m-%d")
    return camera_log_folder / f"{normalized_name}_{date_str}.log"


def log_camera(cam_name: str, msg: str):
    """Log to cameras/{camera-name}/{camera-name}_YYYY-MM-DD.log file with automatic rotation check"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_camera_log_file(cam_name)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def ensure_camera_folder(cam_name: str) -> Path:
    normalized_name = normalize_camera_name(cam_name)
    cam_folder = CAMERAS_DIR / normalized_name
    cam_folder.mkdir(parents=True, exist_ok=True)
    return cam_folder


def schedule_midnight_cleanup():
    """Run cleanup once per day at midnight"""
    last_cleanup_date = datetime.now().date()

    def cleanup_worker():
        nonlocal last_cleanup_date
        while True:
            current_date = datetime.now().date()

            # Check if it's a new day
            if current_date > last_cleanup_date:
                log_main("=" * 60)
                log_main("MIDNIGHT CLEANUP - Cleaning up old day folders...")
                log_main("=" * 60)
                cleanup_stats = camera_organizer.cleanup_all_cameras()
                if cleanup_stats:
                    log_main(f"Cleanup complete: {len(cleanup_stats)} camera(s) cleaned")
                else:
                    log_main("No old folders to cleanup")
                log_main("=" * 60)
                last_cleanup_date = current_date

            # Check every minute
            time.sleep(60)

    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    log_main("\U0001F4C5 Midnight cleanup scheduler started")
    return thread


async def countdown(seconds: int):
    for remaining in range(seconds, 0, -1):
        print(f"\rWaiting {remaining} seconds for next snapshot...", end="")
        await asyncio.sleep(1)
    print("\rStarting next snapshot...               ")


async def wait_until_next_interval(interval_seconds):
    """Wait until the next aligned interval (0, 5, 10... minutes) with live countdown"""
    now = datetime.now()
    interval_minutes = interval_seconds // 60
    minutes_to_wait = interval_minutes - (now.minute % interval_minutes)
    seconds_to_wait = minutes_to_wait * 60 - now.second
    if seconds_to_wait <= 0:
        return

    # Live countdown
    for remaining in range(seconds_to_wait, 0, -1):
        print(f"\rWaiting {remaining} seconds for next snapshot...", end="")
        await asyncio.sleep(1)
    print("\rStarting next snapshot...               ")


# ---------------- Snapshot Function ---------------- #
async def take_snapshot(blink):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        log_main("Refreshing all cameras...")
        await blink.refresh(force=True)
        log_main("Refresh complete.")
    except Exception as e:
        log_main(f"Error refreshing blink: {e}")

    for cam_name, cam in blink.cameras.items():
        if cam_name not in CAMERAS:
            log_main(f"Skipping {cam_name} (not in config)")
            continue

        log_main(f"{'=' * 60}")
        log_main(f"Processing camera: {cam_name}")
        log_main(f"{'=' * 60}")

        cam_folder = ensure_camera_folder(cam_name)
        bars = wifi_bars(cam.wifi_strength)

        log_main(f"  Battery: {getattr(cam, 'battery', 'N/A')}")
        log_main(f"  Temperature: {getattr(cam, 'temperature', 'N/A')}")

        image_bytes = None
        source = "None"

        # ============ FIX: Request new snapshot FIRST ============
        try:
            log_main("  \U0001F4F8 Requesting new snapshot from camera...")
            snap_result = await cam.snap_picture()

            # Extract only useful info from the verbose response
            if isinstance(snap_result, dict):
                command_id = snap_result.get('id', 'unknown')
                state = snap_result.get('state_condition', 'unknown')
                log_main(f"  \u2705 Snapshot requested (ID: {command_id}, State: {state})")
            else:
                log_main(f"  \u2705 Snapshot requested")

            # Wait a moment for the snapshot to be processed
            await asyncio.sleep(3)

            # Refresh camera to get the new image
            await blink.refresh(force=True)

        except Exception as e:
            log_main(f"  \u26A0\uFE0F Snapshot request failed: {type(e).__name__}: {e}")

        # ============ Now get the media ============
        try:
            response = await cam.get_media()
            if response.status == 200:
                image_bytes = await response.read()
                source = "get_media"
                log_main(f"  \u2705 Downloaded {len(image_bytes)} bytes")
            else:
                log_main(f"  \u274C HTTP {response.status}")
        except Exception as e:
            log_main(f"  \u274C Download failed: {e}")

        # ============ Fallback: Try thumbnail ============
        if not image_bytes or len(image_bytes) < 1000:
            try:
                thumb_response = await cam.get_thumbnail()
                if thumb_response.status == 200:
                    image_bytes = await thumb_response.read()
                    source = "thumbnail"
                    log_main(f"  \u26A0\uFE0F Using thumbnail ({len(image_bytes)} bytes)")
            except Exception as e:
                log_main(f"  \u274C Thumbnail failed: {e}")

        # ============ Save image using camera_organizer ============
        if not image_bytes or len(image_bytes) < 1000:
            # Placeholder if method fails
            placeholder = Image.new("RGB", (640, 480), color=(255, 0, 0))
            buffer = io.BytesIO()
            placeholder.save(buffer, format='JPEG')
            image_bytes = buffer.getvalue()
            source = "placeholder"
            log_main(f"  \u26A0\uFE0F No valid image data, using placeholder")

        try:
            # Verify image data is valid before saving
            try:
                img = Image.open(io.BytesIO(image_bytes))
                img.verify()
                log_main(f"  \u2705 Valid {img.format} image {img.size}")
            except Exception as e:
                log_main(f"  \u26A0\uFE0F Image validation failed: {e}")

            # Use camera_organizer to save photo to date folder
            photo_path = camera_organizer.save_photo_to_date_folder(
                cam_folder,
                image_bytes,
                cam_name,
                datetime.now()
            )

            # Verify file was actually written
            if photo_path.exists():
                actual_size = photo_path.stat().st_size
                log_main(
                    f"  \u2705 Saved: {photo_path.parent.name}/{photo_path.name} ({actual_size:,} bytes, {source})")
            else:
                log_main(f"  \u274C File not found after save!")

        except Exception as e:
            log_main(f"  \u274C Save error: {e}")
            import traceback
            log_main(traceback.format_exc())

        # Log camera info to camera-specific log
        log_entry = (
            f"Temp: {cam.temperature}\u00B0F | Battery: {cam.battery} | "
            f"WiFi: {bars}/5 | Source: {source}"
        )
        log_camera(cam_name, log_entry)

        print(f"\n--- {cam_name} ---")
        print(f"Temperature: {cam.temperature}\u00B0F")
        print(f"Battery: {cam.battery}")
        print(f"WiFi: {bars}/5")
        print(f"Source: {source}")
        print("----------------------\n")


# ---------------- Main Blink Polling ---------------- #
async def poll_blink():
    # Load saved token data
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    async with ClientSession() as session:
        blink = Blink(session=session)

        # Extract the region code from the host URL
        host_url = token_data.get("host", "")
        region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")

        # CRITICAL: Create Auth with empty dict to prevent prompting
        blink.auth = Auth({}, session=session, no_prompt=True)

        # Manually set ALL auth properties from the saved token
        blink.auth.region_id = region_id
        blink.auth.host = host_url
        blink.auth.token = token_data.get("token")
        blink.auth.refresh_token = token_data.get("refresh_token")
        blink.auth.client_id = token_data.get("client_id")
        blink.auth.account_id = token_data.get("account_id")
        blink.auth.user_id = token_data.get("user_id")

        # Initialize the URLs handler with just the region_id
        blink.urls = BlinkURLHandler(region_id)

        try:
            # Setup using existing authentication
            await blink.setup_post_verify()

            log_main("=" * 50)
            log_main("CAMERAS FOUND BY API:")
            for cam_name in blink.cameras.keys():
                log_main(f"  - '{cam_name}'")
            log_main("=" * 50)
            log_main(f"CAMERAS IN CONFIG: {CAMERAS}")
            log_main("=" * 50)

        except Exception as e:
            log_main(f"Error during Blink setup: {e}")
            import traceback
            log_main(traceback.format_exc())
            return

        # Track token file modification time
        last_token_mtime = os.path.getmtime(TOKEN_FILE)

        # Start log rotation monitoring thread
        log_rotator.start_midnight_rotation_thread()

        # Start midnight cleanup scheduler
        schedule_midnight_cleanup()

        # Migrate any flat photos to date folders (one-time on startup)
        log_main("Checking for photos to migrate to date folders...")
        camera_organizer.migrate_all_cameras()

        # Startup snapshot
        log_main("Taking initial startup snapshot...")
        await take_snapshot(blink)
        await wait_until_next_interval(POLL_INTERVAL)

        while True:
            try:
                # STEP 1: Refresh blink connection and save token
                await blink.refresh(force=True)
                await blink.save(TOKEN_FILE)

                # STEP 2: Check if token file was externally modified
                current_token_mtime = os.path.getmtime(TOKEN_FILE)
                if current_token_mtime != last_token_mtime:
                    last_token_mtime = current_token_mtime

                    # Load the refreshed token to log details
                    with open(TOKEN_FILE, "r") as f:
                        refreshed_token = json.load(f)

                    # Log token refresh with details
                    log_token(f"Token refreshed successfully")
                    log_token(f"  New token (first 20 chars): {refreshed_token.get('token', '')[:20]}...")
                    log_token(f"  Account ID: {refreshed_token.get('account_id')}")
                    log_token(f"  Region: {refreshed_token.get('host')}")

                    # Re-initialize camera objects after token refresh
                    log_token(f"  Re-initializing camera objects after token refresh...")
                    try:
                        await blink.setup_post_verify()
                        log_token(f"  Camera objects re-initialized successfully")
                    except Exception as e:
                        log_token(f"  ERROR re-initializing cameras: {e}")

                # STEP 3: Take snapshot
                log_main("Starting snapshot cycle...")
                await take_snapshot(blink)

                # STEP 4: Wait for next interval
                await wait_until_next_interval(POLL_INTERVAL)

            except Exception as e:
                log_main(f"Error during polling loop: {e}")
                import traceback
                log_main(traceback.format_exc())
                await asyncio.sleep(30)


# ---------------- Script Entry ---------------- #
if __name__ == "__main__":
    CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    log_main("Blink WebCam script started.")
    log_main(f"Log rotation enabled: keeps 5 days of history")
    log_main(f"Photo retention: keeps {MAX_DAYS} days of photos per camera")
    log_main(f"Main log: {get_current_log_file(MAIN_LOG_FOLDER, 'main')}")
    log_main(f"Token log: {get_current_log_file(TOKEN_LOG_FOLDER, 'token')}")
    asyncio.run(poll_blink())