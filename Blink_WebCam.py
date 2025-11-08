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
import time

# Suppress the specific blinkpy warning about last_refresh
warnings.filterwarnings("ignore", message=".*last_refresh.*")

# Redirect stderr to suppress blinkpy interval calculation errors
import io


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

# Load config (must exist - created by blink_config_setup.py)
if not Path(CONFIG_FILE).exists():
    print("=" * 60)
    print("❌ ERROR: blink_config.json not found!")
    print("=" * 60)
    print("You must run the configuration setup first:")
    print("  python blink_config_setup.py")
    print("=" * 60)
    sys.exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

POLL_INTERVAL = config.get("poll_interval", 300)  # seconds
MAX_IMAGES = config.get("max_images", 10080)
LOG_RETENTION_DAYS = config.get("log_retention_days", 5)
MAX_LOG_ENTRIES = config.get("max_log_entries", 1024)
CAMERAS = config.get("cameras", [])

ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

# Create directories
CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FOLDER.mkdir(parents=True, exist_ok=True)

MAIN_LOG_FILE = LOG_FOLDER / "main.log"
TOKEN_LOG_FILE = LOG_FOLDER / "token.log"


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


def log_main(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    try:
        with open(MAIN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"ERROR writing to main log: {e}")
    print(line.strip())


def log_token(msg: str):
    """Log token refresh events to dedicated token.log file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {msg}\n"
    try:
        with open(TOKEN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"ERROR writing to token log: {e}")
    # Also log to main log
    log_main(msg)


def get_camera_log_file(cam_name: str) -> Path:
    normalized_name = normalize_camera_name(cam_name)
    return LOG_FOLDER / f"{normalized_name}.log"


def safe_write_camera_log(log_file: Path, log_entry: str, max_retries: int = 3):
    """Write to camera log with retry logic and error handling"""
    for attempt in range(max_retries):
        try:
            # Open with explicit encoding and error handling
            with open(log_file, "a", encoding="utf-8", errors="replace") as f:
                f.write(log_entry)
                f.flush()  # Force write to disk
                os.fsync(f.fileno())  # Ensure OS writes to disk

            # Verify the write succeeded
            if log_file.exists() and log_file.stat().st_size > 0:
                return True
            else:
                raise IOError(f"Log file appears empty after write: {log_file}")

        except Exception as e:
            if attempt < max_retries - 1:
                log_main(f"⚠️ Retry {attempt + 1}/{max_retries} writing to {log_file.name}: {e}")
                time.sleep(0.2)  # Brief delay before retry
            else:
                log_main(f"❌ FAILED to write to {log_file.name} after {max_retries} attempts: {e}")
                # Try to diagnose the issue
                try:
                    if log_file.exists():
                        log_main(f"   File size: {log_file.stat().st_size} bytes")
                        log_main(f"   Permissions: {oct(log_file.stat().st_mode)}")
                except Exception as diag_error:
                    log_main(f"   Cannot diagnose: {diag_error}")
                return False
    return False


def trim_log(log_file: Path):
    if not log_file.exists():
        return

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        filtered_lines = []
        for line in lines:
            try:
                ts_str = line.split(" | ")[0]
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                if ts >= cutoff:
                    filtered_lines.append(line)
            except:
                continue

        filtered_lines = filtered_lines[-MAX_LOG_ENTRIES:]

        with open(log_file, "w", encoding="utf-8") as f:
            f.writelines(filtered_lines)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        log_main(f"Error trimming log {log_file.name}: {e}")


def ensure_camera_folder(cam_name: str) -> Path:
    normalized_name = normalize_camera_name(cam_name)
    cam_folder = CAMERAS_DIR / normalized_name
    cam_folder.mkdir(parents=True, exist_ok=True)
    return cam_folder


def trim_images(cam_folder: Path):
    files = sorted(cam_folder.glob("*.jpg"), key=os.path.getmtime)
    while len(files) > MAX_IMAGES:
        oldest = files.pop(0)
        oldest.unlink()
        log_main(f"Deleted old image: {oldest.name}")


async def countdown(seconds: int):
    for remaining in range(seconds, 0, -1):
        print(f"\rWaiting {remaining} seconds for next snapshot...", end="")
        await asyncio.sleep(1)
    print("\rStarting next snapshot...               ")


async def wait_until_next_interval(interval_seconds):
    """Wait until the next aligned interval (0, 5, 10… minutes) with live countdown"""
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


def load_current_token():
    """Load current token from file"""
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def has_token_changed(blink):
    """Check if token has changed compared to saved file"""
    saved_token_data = load_current_token()
    if not saved_token_data:
        return True

    # Compare the actual token values
    current_token = blink.auth.token
    current_refresh = blink.auth.refresh_token
    saved_token = saved_token_data.get("token")
    saved_refresh = saved_token_data.get("refresh_token")

    return (current_token != saved_token or current_refresh != saved_refresh)


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
        log_file = get_camera_log_file(cam_name)
        bars = wifi_bars(cam.wifi_strength)

        log_main(f"  Motion Enabled: {getattr(cam, 'motion_enabled', 'N/A')}")
        log_main(f"  Battery: {getattr(cam, 'battery', 'N/A')}")
        log_main(f"  Temperature: {getattr(cam, 'temperature', 'N/A')}")

        image_bytes = None
        source = "None"

        # ---------------- Method 1: Snap a fresh picture ---------------- #
        try:
            log_main("  Method 1: Calling snap_picture() for fresh image...")
            result = await cam.snap_picture()
            if isinstance(result, bytes) and len(result) > 1000:
                image_bytes = result
                source = "snap_picture"
                log_main(f"  ✓ snap_picture returned {len(image_bytes)} bytes")
            else:
                log_main(f"  ✗ snap_picture returned invalid data: {type(result)}")
        except Exception as e:
            log_main(f"  ✗ snap_picture error: {type(e).__name__}: {e}")

        # ---------------- Method 2: Use get_media() as fallback ---------------- #
        if not image_bytes:
            try:
                log_main("  Method 2: Calling get_media() as fallback...")
                response = await cam.get_media()
                if response.status == 200:
                    image_bytes = await response.read()
                    source = "get_media"
                    log_main(f"  ✓ get_media returned {len(image_bytes)} bytes")
                else:
                    log_main(f"  ✗ get_media returned non-200: {response.status}")
            except Exception as e:
                log_main(f"  ✗ get_media error: {type(e).__name__}: {e}")

        # ---------------- Method 3: Placeholder if both fail ---------------- #
        if not image_bytes:
            img_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_placeholder.jpg"
            img_path = cam_folder / img_name
            placeholder = Image.new("RGB", (640, 480), color=(255, 0, 0))
            placeholder.save(img_path)
            log_main(f"  ✗✗✗ FAILED: No image data, saved placeholder")
        else:
            img_name = f"{normalize_camera_name(cam_name)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            img_path = cam_folder / img_name
            try:
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                log_main(f"  ✓✓✓ SUCCESS: Saved {img_name} ({source}, {len(image_bytes)} bytes)")
            except Exception as e:
                log_main(f"  ✗ Error saving image: {e}")
                img_name = "error_" + img_name

        trim_images(cam_folder)

        # Log camera info with robust error handling
        log_entry = (
            f"{timestamp} | Temp: {cam.temperature}°F | Battery: {cam.battery} | "
            f"WiFi: {bars}/5 | Image: {img_name} | Source: {source} | "
            f"Motion Enabled: {getattr(cam, 'motion_enabled', 'N/A')}\n"
        )

        log_main(f"  📝 Writing to camera log: {log_file.name}")
        success = safe_write_camera_log(log_file, log_entry)
        if success:
            log_main(f"  ✓ Camera log updated successfully")
        else:
            log_main(f"  ✗ FAILED to update camera log!")

        trim_log(log_file)

        print(f"\n--- {cam_name} ---")
        print(f"Temperature: {cam.temperature}°F")
        print(f"Battery: {cam.battery}")
        print(f"WiFi: {bars}/5")
        print(f"Image: {img_name} ({source})")
        print(f"Log: {'✓' if success else '✗ FAILED'}")
        print("----------------------\n")


# ---------------- Main Blink Polling ---------------- #
async def poll_blink():
    # Load saved token data
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    async with ClientSession() as session:
        blink = Blink(session=session)

        # Extract the region code from the host URL (e.g., "u044" from "https://rest-u044.immedia-semi.com")
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

        # Initialize the URLs handler with just the region_id (e.g., "u044")
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

        # Startup snapshot
        await take_snapshot(blink)
        await wait_until_next_interval(POLL_INTERVAL)

        while True:
            try:
                await blink.refresh()

                # Check if token has actually changed
                if has_token_changed(blink):
                    # Save the updated token
                    await blink.save(TOKEN_FILE)

                    # Load the refreshed token to get details
                    with open(TOKEN_FILE, "r") as f:
                        refreshed_token = json.load(f)

                    # Log token refresh with details
                    log_token(f"Token refreshed successfully")
                    log_token(f"  New token (first 20 chars): {refreshed_token.get('token', '')[:20]}...")
                    log_token(f"  Account ID: {refreshed_token.get('account_id')}")
                    log_token(f"  Region: {refreshed_token.get('host')}")

                await take_snapshot(blink)
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
    asyncio.run(poll_blink())