"""
blink_utils.py - Utility Functions Module
Common utility functions used throughout the application
"""

import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path


class SuppressSpecificErrors:
    """Suppress specific stderr messages"""
    def __init__(self, stderr):
        self.stderr = stderr
        self.suppress_patterns = [
            "Error calculating interval",
            "unsupported operand type(s) for -: 'NoneType' and 'int'"
        ]

    def write(self, text):
        if not any(pattern in text for pattern in self.suppress_patterns):
            self.stderr.write(text)

    def flush(self):
        self.stderr.flush()


def normalize_camera_name(cam_name: str) -> str:
    """Convert camera name to lowercase kebab-case"""
    return cam_name.lower().replace(" ", "-")


def wifi_bars(dbm: int | None) -> int:
    """Convert WiFi dBm to bar count (0-5)"""
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


async def wait_until_next_interval(interval_seconds: int):
    """Wait until the next aligned interval (0, 5, 10... minutes)"""
    now = datetime.now()
    interval_minutes = interval_seconds // 60
    minutes_to_wait = interval_minutes - (now.minute % interval_minutes)
    seconds_to_wait = minutes_to_wait * 60 - now.second
    if seconds_to_wait <= 0:
        return

    for remaining in range(seconds_to_wait, 0, -1):
        await asyncio.sleep(1)


def schedule_midnight_cleanup(camera_organizer, log_main):
    """Run cleanup once per day at midnight"""
    last_cleanup_date = datetime.now().date()

    def cleanup_worker():
        nonlocal last_cleanup_date
        while True:
            current_date = datetime.now().date()

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

            time.sleep(60)

    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    log_main("Midnight cleanup scheduler started")
    return thread