"""
Blink_WebCam.py - Main Entry Point (Sequential Processing)
REVERTED: Back to one-at-a-time camera processing for reliability
"""

import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler
from datetime import datetime
from pathlib import Path
import json
import os
import sys
import warnings
import time

# Import custom modules
from log_rotation import LogRotator
from camera_organizer import CameraOrganizer
from camera_processor import CameraProcessor
from blink_utils import (
    normalize_camera_name,
    wifi_bars,
    get_current_log_file,
    schedule_midnight_cleanup,
    wait_until_next_interval,
    SuppressSpecificErrors
)

# Suppress warnings
warnings.filterwarnings("ignore", message=".*last_refresh.*")
sys.stderr = SuppressSpecificErrors(sys.stderr)

# ---------------- Configuration ---------------- #
TOKEN_FILE = "blink_token.json"
CONFIG_FILE = "blink_config.json"

# Load token
with open(TOKEN_FILE, "r") as f:
    token_data = json.load(f)

# Load config
if Path(CONFIG_FILE).exists():
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {
        "poll_interval": 300,
        "max_days": 7,
        "cameras": ["Front Door", "Tree Front Door", "Back Door", "Garage Door"]
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

POLL_INTERVAL = config.get("poll_interval", 300)
MAX_DAYS = config.get("max_days", 7)
CAMERAS = config.get("cameras", [])

ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"

CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FOLDER.mkdir(parents=True, exist_ok=True)

# Initialize modules
log_rotator = LogRotator(LOG_FOLDER, max_backups=5)
camera_organizer = CameraOrganizer(CAMERAS_DIR, max_days=MAX_DAYS)

MAIN_LOG_FOLDER = log_rotator.get_system_log_folder("main")
TOKEN_LOG_FOLDER = log_rotator.get_system_log_folder("token")
PERF_LOG_FOLDER = log_rotator.get_system_log_folder("performance")


# ---------------- Logging Functions ---------------- #
def log_main(msg: str):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(MAIN_LOG_FOLDER, "main")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


def log_token(msg: str):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(TOKEN_LOG_FOLDER, "token")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


def log_performance(msg: str):
    log_rotator.check_and_rotate_if_needed()
    log_file = get_current_log_file(PERF_LOG_FOLDER, "performance")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


def log_camera_performance(cam_name: str, operation: str, duration: float, success: bool = True):
    normalized_name = normalize_camera_name(cam_name)
    camera_log_folder = log_rotator.get_camera_log_folder(normalized_name)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = camera_log_folder / f"{normalized_name}_{date_str}.log"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | PERF | {operation} | {duration:.2f}s | {status}\n")

    log_performance(f"{cam_name} | {operation} | {duration:.2f}s | {status}")

    if duration > 30:
        log_main(f"WARNING SLOW OPERATION: {cam_name} - {operation} took {duration:.2f}s")


def log_camera(cam_name: str, msg: str):
    log_rotator.check_and_rotate_if_needed()
    normalized_name = normalize_camera_name(cam_name)
    camera_log_folder = log_rotator.get_camera_log_folder(normalized_name)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = camera_log_folder / f"{normalized_name}_{date_str}.log"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {msg}\n")


# ---------------- Initialize Camera Processor ---------------- #
camera_processor = CameraProcessor(
    camera_organizer=camera_organizer,
    log_main=log_main,
    log_camera=log_camera,
    log_camera_performance=log_camera_performance,
    normalize_camera_name=normalize_camera_name,
    wifi_bars=wifi_bars,
    duplicate_threshold=3
)


# ---------------- Main Snapshot Function (SEQUENTIAL) ---------------- #
async def take_snapshot(blink):
    """Take snapshots from all configured cameras (SEQUENTIAL PROCESSING)"""
    cycle_start = time.time()

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
        log_main("WARNING: Camera refresh timed out after 30s")
    except Exception as e:
        log_main(f"Error refreshing blink: {e}")
        log_performance(f"global_refresh | ERROR: {e}")

    log_main("=" * 60)
    log_main("STARTING SEQUENTIAL CAMERA PROCESSING")
    log_main("=" * 60)

    successful = 0
    failed = 0

    # Process cameras ONE AT A TIME
    for cam_name, cam in blink.cameras.items():
        if cam_name not in CAMERAS:
            log_main(f"Skipping {cam_name} (not in config)")
            continue
        
        try:
            result = await camera_processor.process_camera(blink, cam_name, cam, CAMERAS_DIR)
            
            if result.get("success"):
                successful += 1
            else:
                failed += 1
                
        except Exception as e:
            log_main(f"ERROR: Critical error processing {cam_name}: {e}")
            log_camera(cam_name, f"CRITICAL ERROR: {type(e).__name__}: {e}")
            failed += 1

    cycle_duration = time.time() - cycle_start
    log_main("=" * 60)
    log_main(f"Snapshot cycle complete: {successful} processed, {failed} failed")
    log_main(f"Total cycle time: {cycle_duration:.2f}s (SEQUENTIAL)")
    log_main("=" * 60)
    log_performance(f"snapshot_cycle_sequential | {cycle_duration:.2f}s | Success:{successful} Failed:{failed}")


# ---------------- Main Blink Polling ---------------- #
async def poll_blink():
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

        try:
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

        last_token_mtime = os.path.getmtime(TOKEN_FILE)

        log_rotator.start_midnight_rotation_thread()
        schedule_midnight_cleanup(camera_organizer, log_main)

        # Migrate photos on startup
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
                log_main(f"POLLING CYCLE #{loop_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                log_main(f"{'#' * 60}")

                # Refresh token
                token_start = time.time()
                try:
                    await asyncio.wait_for(blink.refresh(force=True), timeout=30)
                    await blink.save(TOKEN_FILE)
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | SUCCESS")
                except asyncio.TimeoutError:
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | TIMEOUT")
                    log_main("WARNING: Token refresh timed out, continuing anyway...")
                except Exception as e:
                    token_duration = time.time() - token_start
                    log_performance(f"token_refresh | {token_duration:.2f}s | ERROR")
                    log_main(f"WARNING: Token refresh error: {e}")

                # Check for token file changes
                current_token_mtime = os.path.getmtime(TOKEN_FILE)
                if current_token_mtime != last_token_mtime:
                    last_token_mtime = current_token_mtime

                    with open(TOKEN_FILE, "r") as f:
                        refreshed_token = json.load(f)

                    log_token(f"Token refreshed successfully")
                    log_token(f"  New token (first 20 chars): {refreshed_token.get('token', '')[:20]}...")
                    log_token(f"  Account ID: {refreshed_token.get('account_id')}")

                    try:
                        reinit_start = time.time()
                        await asyncio.wait_for(blink.setup_post_verify(), timeout=30)
                        reinit_duration = time.time() - reinit_start
                        log_performance(f"camera_reinit | {reinit_duration:.2f}s | SUCCESS")
                        log_token(f"  Camera objects re-initialized successfully in {reinit_duration:.2f}s")
                    except Exception as e:
                        log_token(f"  ERROR re-initializing cameras: {e}")
                        log_performance(f"camera_reinit | ERROR: {e}")

                # Take snapshot
                log_main("Starting snapshot cycle...")
                await take_snapshot(blink)

                loop_duration = time.time() - loop_start
                log_performance(f"poll_cycle | {loop_duration:.2f}s | Cycle#{loop_count}")
                log_main(f"Poll cycle #{loop_count} completed in {loop_duration:.2f}s")

                await wait_until_next_interval(POLL_INTERVAL)

            except KeyboardInterrupt:
                log_main("Shutting down gracefully...")
                break
            except Exception as e:
                loop_duration = time.time() - loop_start
                log_performance(f"poll_cycle | {loop_duration:.2f}s | CRITICAL_ERROR")
                log_main(f"ERROR: Critical error in polling loop: {e}")
                import traceback
                log_main(traceback.format_exc())
                log_main("Waiting 60 seconds before retry...")
                await asyncio.sleep(60)


# ---------------- Entry Point ---------------- #
if __name__ == "__main__":
    CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    log_main("=" * 70)
    log_main("BLINK WEBCAM SCRIPT STARTED (SEQUENTIAL PROCESSING)")
    log_main("=" * 70)
    log_main(f"Log rotation enabled: keeps 5 days of history")
    log_main(f"Photo retention: keeps {MAX_DAYS} days of photos per camera")
    log_main(f"Poll interval: {POLL_INTERVAL // 60} minutes")
    log_main(f"Configured cameras: {len(CAMERAS)}")
    log_main(f"Processing mode: SEQUENTIAL (one camera at a time)")
    log_main("=" * 70)

    asyncio.run(poll_blink())