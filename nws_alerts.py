import requests
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

# ==================== CONSTANTS ====================
NWS_SCHEDULED_MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
NWS_API_TIMEOUT = 10  # seconds
NWS_MAX_RETRIES = 3
NWS_RETRY_DELAY = 5  # seconds


# ==================== THREAD-SAFE STATE ====================
class NWSAlertState:
    """Thread-safe state management for NWS alerts"""

    def __init__(self):
        self._lock = threading.Lock()
        self.alerts: List[str] = []
        self.last_check: datetime = datetime.min
        self.next_check: datetime = datetime.now()
        self.alert_active: bool = False

    def set_alerts(self, alerts: List[str]):
        with self._lock:
            self.alerts = alerts.copy()
            self.alert_active = len(alerts) > 0

    def get_alerts(self) -> List[str]:
        with self._lock:
            return self.alerts.copy()

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
def get_next_nws_check(now: datetime, alert_active: bool) -> datetime:
    """
    Calculate next NWS check time

    Args:
        now: Current datetime
        alert_active: Whether alerts are currently active

    Returns:
        Next check datetime
    """
    if alert_active:
        # Check every 2 minutes when alert is active
        return now + timedelta(minutes=2)
    else:
        # Check at next 5-minute mark
        current_minute = now.minute

        for m in NWS_SCHEDULED_MINUTES:
            if current_minute < m:
                return now.replace(minute=m, second=0, microsecond=0)

        # If past all scheduled minutes, go to next hour at :00
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_time


def get_nearest_5min_mark(now: datetime) -> datetime:
    """
    Get nearest 5-minute mark on or after now

    Args:
        now: Current datetime

    Returns:
        Nearest 5-minute mark datetime
    """
    for m in NWS_SCHEDULED_MINUTES:
        if now.minute <= m:
            return now.replace(minute=m, second=0, microsecond=0)

    # If past :55, go to next hour at :00
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


# ==================== NWS API FUNCTIONS ====================
def fetch_nws_alerts(zone: str) -> List[str]:
    """
    Fetch alerts from NWS API and extract descriptions

    Args:
        zone: NWS forecast zone (e.g., "PAZ021")

    Returns:
        List of alert description strings (truncated at first \\n\\n)
    """
    url = f"https://api.weather.gov/alerts/active?zone={zone}"
    headers = {"User-Agent": "BlinkWebCam/1.0"}

    for attempt in range(NWS_MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=NWS_API_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            alerts = data.get("features", [])

            # Extract and process descriptions (exact BetaBrite pattern)
            headlines = []
            for alert in alerts:
                props = alert.get("properties", {})
                desc = props.get("description", "")

                # Truncate at first \n\n
                if "\n\n" in desc:
                    desc = desc.split("\n\n")[0]

                # Replace remaining newlines with spaces
                desc = desc.replace("\n", " ").strip()

                if desc:
                    headlines.append(desc)

            return headlines

        except requests.exceptions.Timeout:
            if attempt < NWS_MAX_RETRIES - 1:
                time.sleep(NWS_RETRY_DELAY)
            else:
                raise Exception(f"NWS API timeout after {NWS_MAX_RETRIES} attempts")

        except requests.exceptions.RequestException as e:
            if attempt < NWS_MAX_RETRIES - 1:
                time.sleep(NWS_RETRY_DELAY)
            else:
                raise Exception(f"NWS API request failed: {e}")

    return []


def validate_nws_zone(zone: str) -> bool:
    """
    Validate NWS forecast zone

    Args:
        zone: NWS forecast zone (e.g., "PAZ021")

    Returns:
        True if zone is valid
    """
    if not zone or len(zone) != 6:
        return False

    # Check format: 3 letters + 3 digits
    if not zone[:3].isalpha() or not zone[3:].isdigit():
        return False

    # Validate against NWS API
    url = f"https://api.weather.gov/zones/forecast/{zone}"
    headers = {"User-Agent": "BlinkWebCam/1.0"}

    try:
        response = requests.get(url, headers=headers, timeout=NWS_API_TIMEOUT)
        return response.status_code == 200
    except:
        return False


# ==================== NWS ALERT CLASS ====================
class NWSAlerts:
    """NWS Alert monitoring and management"""

    def __init__(self, zone: str, log_function=None):
        """
        Initialize NWS alert monitor

        Args:
            zone: NWS forecast zone (e.g., "PAZ021")
            log_function: Optional logging function (called with message string)
        """
        self.zone = zone.upper()
        self.state = NWSAlertState()
        self.log = log_function if log_function else lambda msg: None
        self.shutdown_event = threading.Event()
        self.polling_thread = None

    def check_alerts(self) -> List[str]:
        """
        Check for active alerts (called by polling thread)

        Returns:
            List of alert description strings
        """
        now = datetime.now()
        self.state.set_last_check(now)

        try:
            self.log("Checking NWS API...")

            # Fetch alerts from NWS
            alerts = fetch_nws_alerts(self.zone)

            # Track state changes
            was_active = self.state.is_alert_active()
            is_active = len(alerts) > 0

            # Update state
            self.state.set_alerts(alerts)

            # Log results
            if is_active:
                if not was_active:
                    # Alert just appeared
                    self.log(f"ALERT DETECTED: {alerts[0][:100]}...")
                    self.log("Switching to 2-minute polling")
                else:
                    # Alert still active
                    self.log(f"Alert still active ({len(alerts)} alert{'s' if len(alerts) > 1 else ''})")
            else:
                if was_active:
                    # Alert just expired
                    self.log("Alert expired")
                    self.log("Returning to 5-minute schedule")
                else:
                    # No alerts
                    self.log("No active alerts")

            # Calculate next check time
            if is_active:
                next_check = get_next_nws_check(now, True)
            elif was_active and not is_active:
                # Just expired - go to nearest 5-min mark
                next_check = get_nearest_5min_mark(now)
                self.log(f"Next check: {next_check.strftime('%I:%M %p')} (nearest 5-min mark)")
            else:
                next_check = get_next_nws_check(now, False)

            self.state.set_next_check(next_check)

            if not (was_active and not is_active):
                self.log(f"Next check: {next_check.strftime('%I:%M %p')}")

            return alerts

        except Exception as e:
            self.log(f"ERROR: {e}")
            # Keep cached alerts on error
            return self.state.get_alerts()

    def get_alert_data(self) -> Dict:
        """
        Get current alert data for API response

        Returns:
            Dictionary with alert data
        """
        return {
            "alerts": self.state.get_alerts(),
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

        self.log(f"NWS polling thread started (Zone: {self.zone})")
        self.log("Configuration: 5-min schedule, 2-min when active")

    def stop_polling_thread(self):
        """Stop background polling thread"""
        self.shutdown_event.set()
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
        self.log("NWS polling thread stopped")

    def _polling_worker(self):
        """Background worker for NWS alert polling"""
        # Initial check
        self.check_alerts()

        while not self.shutdown_event.is_set():
            now = datetime.now()
            next_check = self.state.get_next_check()

            # Check if it's time for next poll
            if now >= next_check:
                self.check_alerts()

            # Sleep for 1 second before checking again
            time.sleep(1)


# ==================== STANDALONE TESTING ====================
if __name__ == "__main__":
    import sys


    def test_log(msg: str):
        """Simple logging for testing"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} | {msg}")


    if len(sys.argv) < 2:
        print("Usage: python nws_alerts.py <ZONE>")
        print("Example: python nws_alerts.py PAZ021")
        sys.exit(1)

    zone = sys.argv[1]

    print("=" * 60)
    print("NWS Alert Monitor - Testing Mode")
    print("=" * 60)
    print(f"Zone: {zone}")
    print()

    # Validate zone
    print("Validating zone...")
    if not validate_nws_zone(zone):
        print("ERROR: Invalid NWS forecast zone")
        sys.exit(1)
    print("Zone validated successfully")
    print()

    # Create monitor
    monitor = NWSAlerts(zone, log_function=test_log)

    # Start polling
    monitor.start_polling_thread()

    print("Monitoring for alerts... (Press Ctrl+C to stop)")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        monitor.stop_polling_thread()
        print("Shutdown complete")