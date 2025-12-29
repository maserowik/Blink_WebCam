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
from functools import wraps
import hashlib

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
PERF_LOG_FOLDER = log_rotator.get_system_log_folder("performance")


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
    # REMOVED: print(line.strip())  # Console output removed


def log_token(msg: str):
    """Log token refresh events to system/token/token_YYYY-MM-DD.log file"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(TOKEN_LOG_FOLDER, "token")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    # REMOVED: print(line.strip())  # Console output removed


def log_performance(msg: str):
    """Log performance metrics to system/performance/performance_YYYY-MM-DD.log file"""
    log_rotator.check_and_rotate_if_needed()

    log_file = get_current_log_file(PERF_LOG_FOLDER, "performance")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)


def log_camera_performance(cam_name: str, operation: str, duration: float, success: bool = True):
    """Log how long camera operations take"""
    normalized_name = normalize_camera_name(cam_name)
    camera_log_folder = log_rotator.get_camera_log_folder(normalized_name)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = camera_log_folder / f"{normalized_name}_{date_str}.log"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    line = f"{timestamp} | PERF | {operation} | {duration:.2f}s | {status}\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)

    # Also log to main performance log
    log_performance(f"{cam_name} | {operation} | {duration:.2f}s | {status}")

    # Warn if operation is slow
    if duration > 30:
        log_main(f"\u26A0\uFE0F SLOW OPERATION: {cam_name} - {operation} took {duration:.2f}s")


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
    """Display countdown timer on console only"""
    for remaining in range(seconds, 0, -1):
        # print(f"\rWaiting {remaining} seconds for next snapshot...", end="", flush=True)
        await asyncio.sleep(1)
    # print("\rStarting next snapshot...               ", flush=True)


async def wait_until_next_interval(interval_seconds):
    """Wait until the next aligned interval (0, 5, 10... minutes) with live countdown"""
    now = datetime.now()
    interval_minutes = interval_seconds // 60
    minutes_to_wait = interval_minutes - (now.minute % interval_minutes)
    seconds_to_wait = minutes_to_wait * 60 - now.second
    if seconds_to_wait <= 0:
        return

    # Live countdown - only thing shown on console
    for remaining in range(seconds_to_wait, 0, -1):
        # print(f"\rWaiting {remaining} seconds for next snapshot...", end="", flush=True)
        await asyncio.sleep(1)
    # print("\rStarting next snapshot...               ", flush=True)


def with_timeout(seconds):
    """Decorator to add timeout to async functions"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                log_main(f"\u23F1\uFE0F Timeout in {func.__name__} after {seconds}s")
                return None

        return wrapper

    return decorator


# ---------------- Camera Processing Functions ---------------- #
async def process_single_camera(blink, cam_name, cam):
    """Process a single camera with timeout protection and detailed logging"""
    start_time = time.time()

    log_main(f"{'=' * 60}")
    log_main(f"Processing camera: {cam_name}")
    log_main(f"{'=' * 60}")

    cam_folder = ensure_camera_folder(cam_name)
    bars = wifi_bars(cam.wifi_strength)

    log_main(f"  Battery: {getattr(cam, 'battery', 'N/A')}")
    log_main(f"  Temperature: {getattr(cam, 'temperature', 'N/A')}")
    log_main(f"  WiFi Signal: {getattr(cam, 'wifi_strength', 'N/A')} dBm ({bars}/5 bars)")

    image_bytes = None
    source = "None"

    # REQUEST NEW SNAPSHOT WITH TIMEOUT
    snap_start = time.time()
    try:
        log_main("  \U0001F4F8 Requesting new snapshot from camera...")
        snap_result = await asyncio.wait_for(
            cam.snap_picture(),
            timeout=30  # 30 second timeout for snap request
        )

        snap_duration = time.time() - snap_start
        log_camera_performance(cam_name, "snap_picture", snap_duration, True)

        if isinstance(snap_result, dict):
            command_id = snap_result.get('id', 'unknown')
            state = snap_result.get('state_condition', 'unknown')
            log_main(f"  \u2705 Snapshot requested (ID: {command_id}, State: {state})")
        else:
            log_main(f"  \u2705 Snapshot requested")

        # WAIT LONGER FOR CAMERA TO PROCESS (increased from 3 to 8 seconds)
        log_main("  \u23F3 Waiting 8 seconds for camera to process snapshot...")
        await asyncio.sleep(8)

        # Refresh camera to get the new image
        refresh_start = time.time()
        await asyncio.wait_for(
            blink.refresh(force=True),
            timeout=20
        )
        refresh_duration = time.time() - refresh_start
        log_camera_performance(cam_name, "refresh_after_snap", refresh_duration, True)

    except asyncio.TimeoutError:
        snap_duration = time.time() - snap_start
        log_camera_performance(cam_name, "snap_picture", snap_duration, False)
        log_main(f"  \u26A0\uFE0F Snapshot request timed out for {cam_name}")
        log_camera(cam_name, f"TIMEOUT: Snapshot request exceeded 15 seconds")
    except Exception as e:
        snap_duration = time.time() - snap_start
        log_camera_performance(cam_name, "snap_picture", snap_duration, False)
        log_main(f"  \u26A0\uFE0F Snapshot request failed: {type(e).__name__}: {e}")
        log_camera(cam_name, f"ERROR: Snapshot request failed - {type(e).__name__}: {e}")

    # GET MEDIA WITH TIMEOUT
    media_start = time.time()
    try:
        response = await asyncio.wait_for(
            cam.get_media(),
            timeout=30  # 30 second timeout for download
        )

        if response.status == 200:
            image_bytes = await response.read()
            source = "get_media"
            media_duration = time.time() - media_start
            log_camera_performance(cam_name, "get_media", media_duration, True)
            log_main(f"  \u2705 Downloaded {len(image_bytes)} bytes in {media_duration:.2f}s")
        else:
            media_duration = time.time() - media_start
            log_camera_performance(cam_name, "get_media", media_duration, False)
            log_main(f"  \u274C HTTP {response.status}")
            log_camera(cam_name, f"ERROR: HTTP {response.status} from get_media")
    except asyncio.TimeoutError:
        media_duration = time.time() - media_start
        log_camera_performance(cam_name, "get_media", media_duration, False)
        log_main(f"  \u23F1\uFE0F Media download timed out for {cam_name}")
        log_camera(cam_name, f"TIMEOUT: Media download exceeded 30 seconds")
    except Exception as e:
        media_duration = time.time() - media_start
        log_camera_performance(cam_name, "get_media", media_duration, False)
        log_main(f"  \u274C Download failed: {e}")
        log_camera(cam_name, f"ERROR: Media download failed - {type(e).__name__}: {e}")

    # FALLBACK: Try thumbnail with timeout
    if not image_bytes or len(image_bytes) < 1000:
        thumb_start = time.time()
        try:
            thumb_response = await asyncio.wait_for(
                cam.get_thumbnail(),
                timeout=15
            )
            if thumb_response.status == 200:
                image_bytes = await thumb_response.read()
                source = "thumbnail"
                thumb_duration = time.time() - thumb_start
                log_camera_performance(cam_name, "get_thumbnail", thumb_duration, True)
                log_main(f"  \u26A0\uFE0F Using thumbnail ({len(image_bytes)} bytes)")
                log_camera(cam_name, f"FALLBACK: Using thumbnail instead of full image")
        except asyncio.TimeoutError:
            thumb_duration = time.time() - thumb_start
            log_camera_performance(cam_name, "get_thumbnail", thumb_duration, False)
            log_main(f"  \u23F1\uFE0F Thumbnail download timed out for {cam_name}")
            log_camera(cam_name, f"TIMEOUT: Thumbnail download exceeded 15 seconds")
        except Exception as e:
            thumb_duration = time.time() - thumb_start
            log_camera_performance(cam_name, "get_thumbnail", thumb_duration, False)
            log_main(f"  \u274C Thumbnail failed: {e}")
            log_camera(cam_name, f"ERROR: Thumbnail download failed - {type(e).__name__}: {e}")

    # REST OF THE SAVE LOGIC
    if not image_bytes or len(image_bytes) < 1000:
        placeholder = Image.new("RGB", (640, 480), color=(255, 0, 0))
        buffer = io.BytesIO()
        placeholder.save(buffer, format='JPEG')
        image_bytes = buffer.getvalue()
        source = "placeholder"
        log_main(f"  \u26A0\uFE0F No valid image data, using placeholder")
        log_camera(cam_name, f"WARNING: No valid image received, using red placeholder")

    try:
        # Verify image
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()
            log_main(f"  \u2705 Valid {img.format} image {img.size}")
        except Exception as e:
            log_main(f"  \u26A0\uFE0F Image validation failed: {e}")
            log_camera(cam_name, f"WARNING: Image validation failed - {e}")

        # Check if this image is a duplicate of the last saved image
        current_hash = hashlib.md5(image_bytes).hexdigest()

        # Get the most recent saved photo for comparison
        date_folders = sorted(cam_folder.glob("20*"), reverse=True)
        last_image_hash = None
        for date_folder in date_folders:
            existing_photos = sorted(date_folder.glob(f"{normalize_camera_name(cam_name)}_*.jpg"),
                                     key=lambda x: x.stat().st_mtime, reverse=True)
            if existing_photos:
                with open(existing_photos[0], 'rb') as f:
                    last_image_hash = hashlib.md5(f.read()).hexdigest()
                break

        if current_hash == last_image_hash:
            log_main(f"  \u26A0\uFE0F DUPLICATE IMAGE DETECTED - Camera may be offline/dead battery")
            log_camera(cam_name, f"WARNING: Duplicate image - camera not capturing new photos (battery dead?)")
            # Still save it but mark it
            source = source + "_DUPLICATE"

        # Save photo
        save_start = time.time()
        photo_path = camera_organizer.save_photo_to_date_folder(
            cam_folder,
            image_bytes,
            cam_name,
            datetime.now()
        )
        save_duration = time.time() - save_start

        if photo_path.exists():
            actual_size = photo_path.stat().st_size
            log_camera_performance(cam_name, "save_photo", save_duration, True)
            log_main(f"  \u2705 Saved: {photo_path.parent.name}/{photo_path.name} ({actual_size:,} bytes, {source})")
        else:
            log_camera_performance(cam_name, "save_photo", save_duration, False)
            log_main(f"  \u274C File not found after save!")
            log_camera(cam_name, f"ERROR: Photo file not found after save operation")

    except Exception as e:
        log_main(f"  \u274C Save error: {e}")
        log_camera(cam_name, f"ERROR: Failed to save photo - {type(e).__name__}: {e}")
        import traceback
        log_main(traceback.format_exc())

    # Log camera info to camera-specific log
    log_entry = (
        f"Temp: {cam.temperature}\u00B0F | Battery: {cam.battery} | "
        f"WiFi: {bars}/5 | Source: {source}"
    )
    log_camera(cam_name, log_entry)

    # Calculate total time for this camera
    total_duration = time.time() - start_time
    log_camera_performance(cam_name, "total_processing", total_duration, True)

    # CONSOLE OUTPUT - Brief summary only
    # print(f"\n--- {cam_name} ---")
    # print(f"Temperature: {cam.temperature}\u00B0F")
    # print(f"Battery: {cam.battery}")
    # print(f"WiFi: {bars}/5")
    # print(f"Source: {source}")
    # print(f"Processing Time: {total_duration:.2f}s")
    # print("----------------------\n")


# ---------------- Main Snapshot Function ---------------- #
async def take_snapshot(blink):
    """Take snapshots from all configured cameras"""
    cycle_start = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        log_main("Refreshing all cameras...")
        refresh_start = time.time()
        await asyncio.wait_for(blink.refresh(force=True), timeout=30)
        refresh_duration = time.time() - refresh_start
        log_performance(f"global_refresh | {refresh_duration:.2f}s | SUCCESS")
        log_main(f"Refresh complete in {refresh_duration:.2f}s")
    except asyncio.TimeoutError:
        refresh_duration = time.time() - refresh_start
        log_performance(f"global_refresh | {refresh_duration:.2f}s | TIMEOUT")
        log_main("\u26A0\uFE0F Camera refresh timed out after 30s")
    except Exception as e:
        log_main(f"Error refreshing blink: {e}")
        log_performance(f"global_refresh | ERROR: {e}")

    # PROCESS EACH CAMERA INDEPENDENTLY (don't let one failure affect others)
    successful = 0
    failed = 0

    for cam_name, cam in blink.cameras.items():
        if cam_name not in CAMERAS:
            log_main(f"Skipping {cam_name} (not in config)")
            continue

        # WRAP EACH CAMERA IN TRY/CATCH
        try:
            await process_single_camera(blink, cam_name, cam)
            successful += 1
        except Exception as e:
            failed += 1
            log_main(f"\u274C Error processing {cam_name}: {e}")
            log_camera(cam_name, f"CRITICAL ERROR: {type(e).__name__}: {e}")
            import traceback
            log_main(traceback.format_exc())
            # Continue to next camera instead of failing entire loop

    # Log cycle summary
    cycle_duration = time.time() - cycle_start
    log_main("=" * 60)
    log_main(f"Snapshot cycle complete: {successful} processed, {failed} failed")
    log_main(f"Total cycle time: {cycle_duration:.2f}s")
    log_main("=" * 60)
    log_performance(f"snapshot_cycle | {cycle_duration:.2f}s | Success:{successful} Failed:{failed}")


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

        # Main polling loop
        loop_count = 0
        while True:
            loop_count += 1
            loop_start = time.time()

            try:
                log_main(f"{'#' * 60}")
                log_main(f"POLLING CYCLE #{loop_count}")
                log_main(f"{'#' * 60}")

                # STEP 1: Refresh blink connection and save token
                token_start = time.time()
                try:
                    await asyncio.wait_for(blink.refresh(force=True), timeout=30)
                    await blink.save(TOKEN_FILE)
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | SUCCESS")
                except asyncio.TimeoutError:
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | TIMEOUT")
                    log_main("\u26A0\uFE0F Token refresh timed out, continuing anyway...")
                except Exception as e:
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | ERROR")
                    log_main(f"\u26A0\uFE0F Token refresh error: {e}")

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
                        reinit_start = time.time()
                        await asyncio.wait_for(blink.setup_post_verify(), timeout=30)
                        reinit_duration = time.time() - reinit_start
                        log_performance(f"camera_reinit | {reinit_duration:.2f}s | SUCCESS")
                        log_token(f"  Camera objects re-initialized successfully in {reinit_duration:.2f}s")
                    except asyncio.TimeoutError:
                        reinit_duration = time.time() - reinit_start
                        log_performance(f"camera_reinit | {reinit_duration:.2f}s | TIMEOUT")
                        log_token(f"  TIMEOUT re-initializing cameras after {reinit_duration:.2f}s")
                    except Exception as e:
                        log_token(f"  ERROR re-initializing cameras: {e}")
                        log_performance(f"camera_reinit | ERROR: {e}")

                # STEP 3: Take snapshot
                log_main("Starting snapshot cycle...")
                await take_snapshot(blink)

                # Log loop cycle time
                loop_duration = time.time() - loop_start
                log_performance(f"poll_cycle | {loop_duration:.2f}s | Cycle#{loop_count}")
                log_main(f"Poll cycle #{loop_count} completed in {loop_duration:.2f}s")

                # STEP 4: Wait for next interval
                await wait_until_next_interval(POLL_INTERVAL)

            except KeyboardInterrupt:
                log_main("Shutting down gracefully...")
                break
            except Exception as e:
                loop_duration = time.time() - loop_start
                log_performance(f"poll_cycle | {loop_duration:.2f}s | CRITICAL_ERROR")
                log_main(f"\u274C Critical error in polling loop: {e}")
                import traceback
                log_main(traceback.format_exc())
                log_main("Waiting 60 seconds before retry...")
                await asyncio.sleep(60)  # Longer wait on critical error


# ---------------- Script Entry ---------------- #
if __name__ == "__main__":
    CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    # STARTUP MESSAGES - Only show these on console
    # print("=" * 70)
    # print("BLINK WEBCAM SCRIPT STARTED")
    # print("=" * 70)
    # print(f"Log rotation enabled: keeps 5 days of history")
    # print(f"Photo retention: keeps {MAX_DAYS} days of photos per camera")
    # print(f"Poll interval: {POLL_INTERVAL // 60} minutes")
    # print(f"Configured cameras: {len(CAMERAS)}")
    # print(f"Duplicate detection: ENABLED")
    # print("=" * 70)
    # print(f"Main log: {get_current_log_file(MAIN_LOG_FOLDER, 'main')}")
    # print(f"Token log: {get_current_log_file(TOKEN_LOG_FOLDER, 'token')}")
    # print(f"Performance log: {get_current_log_file(PERF_LOG_FOLDER, 'performance')}")
    # print("=" * 70)
    # print()

    # Log to file (not console)
    log_main("=" * 70)
    log_main("BLINK WEBCAM SCRIPT STARTED")
    log_main("=" * 70)
    log_main(f"Log rotation enabled: keeps 5 days of history")
    log_main(f"Photo retention: keeps {MAX_DAYS} days of photos per camera")
    log_main(f"Poll interval: {POLL_INTERVAL // 60} minutes")
    log_main(f"Configured cameras: {len(CAMERAS)}")
    log_main(f"Duplicate detection: ENABLED")
    log_main("=" * 70)
    log_main(f"Main log: {get_current_log_file(MAIN_LOG_FOLDER, 'main')}")
    log_main(f"Token log: {get_current_log_file(TOKEN_LOG_FOLDER, 'token')}")
    log_main(f"Performance log: {get_current_log_file(PERF_LOG_FOLDER, 'performance')}")
    log_main("=" * 70)

    asyncio.run(poll_blink())