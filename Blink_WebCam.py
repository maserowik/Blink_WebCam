import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
from PIL import Image

# ---------------- Configuration ---------------- #
CONFIG_FILE = "blink_token.json"

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

TOKEN_FILE = CONFIG_FILE
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
    with open(MAIN_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())


def get_camera_log_file(cam_name: str) -> Path:
    normalized_name = normalize_camera_name(cam_name)
    return LOG_FOLDER / f"{normalized_name}.log"


def trim_log(log_file: Path):
    if not log_file.exists():
        return
    with open(log_file, "r") as f:
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

    with open(log_file, "w") as f:
        f.writelines(filtered_lines)


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

        log_main(f"\n{'=' * 60}")
        log_main(f"Processing camera: {cam_name}")
        log_main(f"{'=' * 60}")

        cam_folder = ensure_camera_folder(cam_name)
        log_file = get_camera_log_file(cam_name)
        bars = wifi_bars(cam.wifi_strength)

        log_main(f"  Armed: {getattr(cam, 'armed', 'N/A')}")
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

        # Log camera info
        log_entry = (
            f"{timestamp} | Temp: {cam.temperature}°F | Battery: {cam.battery} | "
            f"WiFi: {bars}/5 | Image: {img_name} | Source: {source} | "
            f"Motion Enabled: {getattr(cam, 'motion_enabled', 'N/A')} | "
            f"Armed: {getattr(cam, 'armed', 'N/A')}\n"
        )
        with open(log_file, "a") as f:
            f.write(log_entry)
        trim_log(log_file)

        print(f"\n--- {cam_name} ---")
        print(f"Temperature: {cam.temperature}°F")
        print(f"Battery: {cam.battery}")
        print(f"WiFi: {bars}/5")
        print(f"Image: {img_name} ({source})")
        print("----------------------\n")


# ---------------- Main Blink Polling ---------------- #
async def poll_blink():
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(token_data, session=session)

        urls = token_data.get("urls", {})
        blink.urls = urls
        blink.base_url = urls.get("base_url")
        blink.media_url = urls.get("media_url")

        try:
            await blink.start()
            await blink.refresh()

            log_main("=" * 50)
            log_main("CAMERAS FOUND BY API:")
            for cam_name in blink.cameras.keys():
                log_main(f"  - '{cam_name}'")
            log_main("=" * 50)
            log_main(f"CAMERAS IN CONFIG: {CAMERAS}")
            log_main("=" * 50)

        except Exception as e:
            log_main(f"Error during Blink start/refresh: {e}")
            return

        last_token_mtime = os.path.getmtime(TOKEN_FILE)

        # Startup snapshot
        await take_snapshot(blink)
        await wait_until_next_interval(POLL_INTERVAL)

        while True:
            try:
                await blink.refresh()
                await blink.save(TOKEN_FILE)

                # Detect token refresh
                current_token_mtime = os.path.getmtime(TOKEN_FILE)
                if current_token_mtime != last_token_mtime:
                    last_token_mtime = current_token_mtime
                    log_main("Token refreshed successfully.")

                await take_snapshot(blink)
                await wait_until_next_interval(POLL_INTERVAL)

            except Exception as e:
                log_main(f"Error during polling loop: {e}")
                await asyncio.sleep(30)


# ---------------- Script Entry ---------------- #
if __name__ == "__main__":
    CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    log_main("Blink WebCam script started.")
    asyncio.run(poll_blink())