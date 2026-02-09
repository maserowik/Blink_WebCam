"""
nhc_alerts.py - National Hurricane Center Alert Monitoring

Monitors NHC for active Atlantic basin hurricanes.
Checks at scheduled hours: 5 AM, 11 AM, 5 PM, 11 PM

File location: /your-project/nhc_alerts.py
"""

import requests
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional
import json


# ==================== CONSTANTS ====================
NHC_SCHEDULED_HOURS = [5, 11, 17, 23]
NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC_API_TIMEOUT = 10  # seconds
NHC_MAX_RETRIES = 3
NHC_RETRY_DELAY = 5  # seconds


# ==================== THREAD-SAFE STATE ====================
class NHCAlertState:
    """Thread-safe state management for NHC alerts"""

    def __init__(self):
        self._lock = threading.Lock()
        self.hurricane_names: List[str] = []
        self.last_check: datetime = datetime.min
        self.next_check: datetime = datetime.now()
        self.alert_active: bool = False

    def set_hurricanes(self, names: List[str]):
        with self._lock:
            self.hurricane_names = names.copy()
            self.alert_active = len(names) > 0

    def get_hurricanes(self) -> List[str]:
        with self._lock:
            return self.hurricane_names.copy()

    def set_last_check(self, check_time: datetime):
        with self._lock:
            self.last_check = check_time

    def get_last_check(self) -> datetime:
        with self._lock:
            return self.last_check

    def set_next_check(self, check_time: datetime):
        with self._lock:
            self.next_check = check_time

    def get_next_check(self) -> datetime:
        with self._lock:
            return self.next_check

    def is_alert_active(self) -> bool:
        with self._lock:
            return self.alert_active


# ==================== SCHEDULING FUNCTIONS ====================
def get_next_nhc_check(now: datetime) -> datetime:
    """
    Calculate next NHC check time (next scheduled hour: 5, 11, 17, 23)

    Args:
        now: Current datetime

    Returns:
        Next check datetime
    """
    current_hour = now.hour

    # Find next scheduled hour today
    next_hours = [h for h in NHC_SCHEDULED_HOURS if h > current_hour]

    if next_hours:
        # Next scheduled hour is today
        next_hour = next_hours[0]
        return now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    else:
        # Next scheduled hour is tomorrow (first hour of the day)
        next_hour = NHC_SCHEDULED_HOURS[0]
        next_day = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        
        # Add one day
        from datetime import timedelta
        return next_day + timedelta(days=1)


def should_check_nhc(now: datetime, last_check: datetime) -> bool:
    """
    Check if it's time for NHC update (5, 11, 17, 23)

    Args:
        now: Current datetime
        last_check: Last check datetime

    Returns:
        True if should check now
    """
    # Must be at a scheduled hour
    if now.hour not in NHC_SCHEDULED_HOURS:
        return False

    # Must be within first 5 minutes of the hour
    if now.minute >= 5:
        return False

    # Must not have checked this hour yet today
    if last_check.hour == now.hour and last_check.date() == now.date():
        return False

    return True


# ==================== NHC API FUNCTIONS ====================
def fetch_nhc_hurricanes() -> List[str]:
    """
    Fetch Atlantic basin hurricanes from NHC API

    Returns:
        List of hurricane names (e.g., ["Idalia", "Franklin"])
    """
    headers = {"User-Agent": "BlinkWebCam/1.0"}

    for attempt in range(NHC_MAX_RETRIES):
        try:
            response = requests.get(NHC_URL, headers=headers, timeout=NHC_API_TIMEOUT)
            response.raise_for_status()

            data = response.json()

            # Filter for Atlantic basin hurricanes only
            hurricanes = [
                s for s in data.get("activeStorms", [])
                if s.get("classification", "") == "HU" 
                and s.get("id", "").lower().startswith("al")
            ]

            # Extract hurricane names
            names = [h.get("name") for h in hurricanes if h.get("name")]

            return names

        except requests.exceptions.Timeout:
            if attempt < NHC_MAX_RETRIES - 1:
                time.sleep(NHC_RETRY_DELAY)
            else:
                raise Exception(f"NHC API timeout after {NHC_MAX_RETRIES} attempts")

        except requests.exceptions.RequestException as e:
            if attempt < NHC_MAX_RETRIES - 1:
                time.sleep(NHC_RETRY_DELAY)
            else:
                raise Exception(f"NHC API request failed: {e}")

    return []


# ==================== NHC ALERT CLASS ====================
class NHCAlerts:
    """NHC Alert monitoring and management"""

    def __init__(self, log_function=None):
        """
        Initialize NHC alert monitor

        Args:
            log_function: Optional logging function (called with message string)
        """
        self.state = NHCAlertState()
        self.log = log_function if log_function else lambda msg: None
        self.shutdown_event = threading.Event()
        self.polling_thread = None

    def check_hurricanes(self) -> List[str]:
        """
        Check for active Atlantic basin hurricanes (called by polling thread)

        Returns:
            List of hurricane names
        """
        now = datetime.now()
        self.state.set_last_check(now)

        try:
            self.log("Checking NHC API...")

            # Fetch hurricanes from NHC
            names = fetch_nhc_hurricanes()

            # Track state changes
            was_active = self.state.is_alert_active()
            is_active = len(names) > 0

            # Update state
            self.state.set_hurricanes(names)

            # Log results
            if is_active:
                if not was_active:
                    # Hurricane just appeared
                    self.log(f"HURRICANE DETECTED: {', '.join(names)}")
                else:
                    # Hurricane still active
                    self.log(f"Hurricane(s) still active: {', '.join(names)}")
            else:
                if was_active:
                    # Hurricane ended/moved
                    self.log("No active Atlantic hurricanes")
                else:
                    # No hurricanes
                    self.log("No active Atlantic hurricanes")

            # Calculate next check time
            next_check = get_next_nhc_check(now)
            self.state.set_next_check(next_check)
            self.log(f"Next check: {next_check.strftime('%I:%M %p')}")

            return names

        except Exception as e:
            self.log(f"ERROR: {e}")
            # Keep cached hurricanes on error
            return self.state.get_hurricanes()

    def get_alert_data(self) -> Dict:
        """
        Get current hurricane data for API response

        Returns:
            Dictionary with hurricane data
        """
        return {
            "hurricanes": self.state.get_hurricanes(),
            "alert_active": self.state.is_alert_active(),
            "last_check": self.state.get_last_check().isoformat(),
            "next_check": self.state.get_next_check().isoformat()
        }

    def start_polling_thread(self):
        """Start background polling thread"""
        if self.polling_thread and self.polling_thread.is_alive():
            self.log("Polling thread already running")
            return

        self.shutdown_event.clear()
        self.polling_thread = threading.Thread(target=self._polling_worker, daemon=True)
        self.polling_thread.start()

        self.log("NHC polling thread started")
        self.log(f"Configuration: Check at {NHC_SCHEDULED_HOURS}")

    def stop_polling_thread(self):
        """Stop background polling thread"""
        self.shutdown_event.set()
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
        self.log("NHC polling thread stopped")

    def _polling_worker(self):
        """Background worker for NHC hurricane polling"""
        # Initial check if we're at a scheduled hour
        now = datetime.now()
        if should_check_nhc(now, self.state.get_last_check()):
            self.check_hurricanes()
        else:
            # Calculate next check
            next_check = get_next_nhc_check(now)
            self.state.set_next_check(next_check)
            self.log(f"Next NHC check: {next_check.strftime('%I:%M %p')}")

        while not self.shutdown_event.is_set():
            now = datetime.now()
            
            # Check if it's time for scheduled poll
            if should_check_nhc(now, self.state.get_last_check()):
                self.check_hurricanes()

            # Sleep for 1 minute before checking again
            time.sleep(60)


# ==================== STANDALONE TESTING ====================
if __name__ == "__main__":
    import sys


    def test_log(msg: str):
        """Simple logging for testing"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} | {msg}")


    print("=" * 60)
    print("NHC Alert Monitor - Testing Mode")
    print("=" * 60)
    print()

    # Create monitor
    monitor = NHCAlerts(log_function=test_log)

    # Manual check
    print("Running manual hurricane check...")
    hurricanes = monitor.check_hurricanes()

    if hurricanes:
        print(f"\n✓ Active Atlantic Hurricanes: {', '.join(hurricanes)}")
    else:
        print("\n✓ No active Atlantic hurricanes")

    print()

    # Start polling if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--monitor":
        monitor.start_polling_thread()

        print("Monitoring for hurricanes... (Press Ctrl+C to stop)")
        print()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            monitor.stop_polling_thread()
            print("Shutdown complete")
    else:
        print("To start continuous monitoring, run:")
        print("  python nhc_alerts.py --monitor")
