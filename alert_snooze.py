"""
alert_snooze.py - Per-Camera Alert Snooze Management

Manages snooze settings for camera alerts. When a camera is snoozed,
all alerts (battery, temperature, offline) are suppressed until snooze expires.

File location: /your-project/alert_snooze.py
"""

from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import Optional


class AlertSnooze:
    """Manages per-camera alert snooze settings"""

    def __init__(self, snooze_file: Path = Path("alert_snooze.json")):
        """
        Initialize alert snooze manager

        Args:
            snooze_file: Path to JSON file storing snooze settings
        """
        self.snooze_file = Path(snooze_file)
        self.snooze_data = self._load_snooze_data()

    def _load_snooze_data(self) -> dict:
        """Load snooze data from JSON file"""
        if self.snooze_file.exists():
            try:
                with open(self.snooze_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"\u26A0  Error loading snooze data: {e}")
                return {}
        return {}

    def _save_snooze_data(self):
        """Save snooze data to JSON file"""
        try:
            with open(self.snooze_file, "w") as f:
                json.dump(self.snooze_data, f, indent=4)
        except Exception as e:
            print(f"\u274C Error saving snooze data: {e}")

    def snooze_camera(self, camera_name: str, duration_minutes: int):
        """
        Snooze all alerts for a camera

        Args:
            camera_name: Normalized camera name (e.g., "front-door")
            duration_minutes: How long to snooze (in minutes)
        """
        snooze_until = datetime.now() + timedelta(minutes=duration_minutes)

        self.snooze_data[camera_name] = {
            "snoozed_until": snooze_until.isoformat()
        }

        self._save_snooze_data()

        print(f"\U0001F515 Snoozed {camera_name} until {snooze_until.strftime('%Y-%m-%d %I:%M %p')}")

    def snooze_all_cameras(self, camera_names: list, duration_minutes: int):
        """
        Snooze all cameras at once

        Args:
            camera_names: List of normalized camera names
            duration_minutes: How long to snooze (in minutes)
        """
        snooze_until = datetime.now() + timedelta(minutes=duration_minutes)

        for camera_name in camera_names:
            self.snooze_data[camera_name] = {
                "snoozed_until": snooze_until.isoformat()
            }

        self._save_snooze_data()

        print(f"\U0001F515 Snoozed {len(camera_names)} camera(s) until {snooze_until.strftime('%Y-%m-%d %I:%M %p')}")

    def unsnooze_camera(self, camera_name: str):
        """
        Remove snooze for a camera (alerts will resume immediately)

        Args:
            camera_name: Normalized camera name (e.g., "front-door")
        """
        if camera_name in self.snooze_data:
            del self.snooze_data[camera_name]
            self._save_snooze_data()
            print(f"\U0001F514 Unsnoozed {camera_name}")

    def unsnooze_all_cameras(self):
        """
        Remove snooze from all cameras
        """
        count = len(self.snooze_data)
        self.snooze_data = {}
        self._save_snooze_data()
        print(f"\U0001F514 Unsnoozed all cameras ({count} total)")

    def is_camera_snoozed(self, camera_name: str) -> bool:
        """
        Check if a camera is currently snoozed

        Args:
            camera_name: Normalized camera name (e.g., "front-door")

        Returns:
            True if camera is snoozed and snooze hasn't expired
        """
        if camera_name not in self.snooze_data:
            return False

        snooze_until_str = self.snooze_data[camera_name].get("snoozed_until")
        if not snooze_until_str:
            return False

        try:
            snooze_until = datetime.fromisoformat(snooze_until_str)
            now = datetime.now()

            if now >= snooze_until:
                # Snooze expired, auto-remove
                self.unsnooze_camera(camera_name)
                return False

            return True

        except Exception as e:
            print(f"\u26A0  Error checking snooze for {camera_name}: {e}")
            return False

    def are_all_cameras_snoozed(self, camera_names: list) -> bool:
        """
        Check if all cameras are currently snoozed

        Args:
            camera_names: List of normalized camera names

        Returns:
            True if ALL cameras are snoozed
        """
        if not camera_names:
            return False

        return all(self.is_camera_snoozed(cam) for cam in camera_names)

    def get_snooze_expiry(self, camera_name: str) -> Optional[datetime]:
        """
        Get the expiry time for a camera's snooze

        Args:
            camera_name: Normalized camera name (e.g., "front-door")

        Returns:
            datetime object of when snooze expires, or None if not snoozed
        """
        if not self.is_camera_snoozed(camera_name):
            return None

        snooze_until_str = self.snooze_data[camera_name].get("snoozed_until")
        if snooze_until_str:
            try:
                return datetime.fromisoformat(snooze_until_str)
            except:
                return None
        return None

    def get_all_snoozed_cameras(self) -> dict:
        """
        Get all currently snoozed cameras

        Returns:
            Dictionary mapping camera names to their snooze expiry times
        """
        snoozed = {}

        for camera_name in list(self.snooze_data.keys()):
            if self.is_camera_snoozed(camera_name):
                expiry = self.get_snooze_expiry(camera_name)
                if expiry:
                    snoozed[camera_name] = expiry

        return snoozed

    def cleanup_expired_snoozes(self):
        """Remove all expired snooze entries"""
        expired = []

        for camera_name in list(self.snooze_data.keys()):
            if not self.is_camera_snoozed(camera_name):
                expired.append(camera_name)

        if expired:
            print(f"\U0001F9F9 Cleaned up {len(expired)} expired snooze(s)")

    def get_snooze_status(self, camera_name: str) -> dict:
        """
        Get detailed snooze status for a camera

        Args:
            camera_name: Normalized camera name (e.g., "front-door")

        Returns:
            Dictionary with snooze status details
        """
        is_snoozed = self.is_camera_snoozed(camera_name)
        expiry = self.get_snooze_expiry(camera_name)

        status = {
            "camera_name": camera_name,
            "is_snoozed": is_snoozed,
            "snooze_until": None,
            "snooze_until_formatted": None,
            "snooze_until_full": None,
            "minutes_remaining": None
        }

        if is_snoozed and expiry:
            status["snooze_until"] = expiry.isoformat()
            status["snooze_until_formatted"] = expiry.strftime("%I:%M:%S %p")
            status["snooze_until_full"] = expiry.strftime("%m/%d/%Y %I:%M:%S %p")

            # Calculate minutes remaining
            now = datetime.now()
            minutes_remaining = int((expiry - now).total_seconds() / 60)
            status["minutes_remaining"] = max(0, minutes_remaining)

        return status


# Predefined snooze durations (in minutes)
SNOOZE_DURATIONS = {
    "30min": 30,
    "1hour": 60,
    "2hours": 120,
    "3hours": 180,
    "4hours": 240
}


def format_snooze_duration(minutes: int) -> str:
    """
    Format snooze duration in human-readable form

    Args:
        minutes: Duration in minutes

    Returns:
        Formatted string like "30 minutes", "1 hour", "2 hours"
    """
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"


# Example usage and testing
if __name__ == "__main__":
    import sys

    snooze_manager = AlertSnooze()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--snooze" and len(sys.argv) >= 4:
            # python alert_snooze.py --snooze front-door 60
            camera_name = sys.argv[2]
            duration = int(sys.argv[3])
            snooze_manager.snooze_camera(camera_name, duration)

        elif command == "--unsnooze" and len(sys.argv) >= 3:
            # python alert_snooze.py --unsnooze front-door
            camera_name = sys.argv[2]
            snooze_manager.unsnooze_camera(camera_name)

        elif command == "--status" and len(sys.argv) >= 3:
            # python alert_snooze.py --status front-door
            camera_name = sys.argv[2]
            status = snooze_manager.get_snooze_status(camera_name)

            print(f"\n\U0001F4F7 {status['camera_name']}")
            print("-" * 60)
            if status['is_snoozed']:
                print(f"  \U0001F515 SNOOZED until {status['snooze_until_full']}")
                print(f"  \u23F1  {status['minutes_remaining']} minutes remaining")
            else:
                print(f"  \U0001F514 ACTIVE (not snoozed)")

        elif command == "--list":
            # python alert_snooze.py --list
            print("\n" + "=" * 60)
            print("\U0001F515 SNOOZED CAMERAS")
            print("=" * 60)

            snoozed = snooze_manager.get_all_snoozed_cameras()

            if not snoozed:
                print("\n\u2139  No cameras are currently snoozed")
            else:
                for camera_name, expiry in snoozed.items():
                    status = snooze_manager.get_snooze_status(camera_name)
                    print(f"\n\U0001F4F7 {camera_name}")
                    print(f"  Until: {status['snooze_until_full']}")
                    print(f"  Remaining: {status['minutes_remaining']} minutes")

            print("\n" + "=" * 60)

        elif command == "--cleanup":
            # python alert_snooze.py --cleanup
            snooze_manager.cleanup_expired_snoozes()

        else:
            print("\u274C Invalid command")
            print("\nUsage:")
            print("  python alert_snooze.py --snooze <camera> <minutes>")
            print("  python alert_snooze.py --unsnooze <camera>")
            print("  python alert_snooze.py --status <camera>")
            print("  python alert_snooze.py --list")
            print("  python alert_snooze.py --cleanup")

    else:
        print("=" * 60)
        print("\U0001F515 Alert Snooze Manager")
        print("=" * 60)
        print("\nManages per-camera alert snooze settings.")
        print("\nPredefined durations:")
        for name, minutes in SNOOZE_DURATIONS.items():
            print(f"  \u2022 {name}: {format_snooze_duration(minutes)}")
        print("\nUsage:")
        print("  python alert_snooze.py --snooze front-door 60     # Snooze for 60 min")
        print("  python alert_snooze.py --unsnooze front-door      # Remove snooze")
        print("  python alert_snooze.py --status front-door        # Check status")
        print("  python alert_snooze.py --list                     # List all snoozed")
        print("  python alert_snooze.py --cleanup                  # Clean expired")
        print("\nIntegration:")
        print("  from alert_snooze import AlertSnooze")
        print("  snooze = AlertSnooze()")
        print("  if not snooze.is_camera_snoozed('front-door'):")
        print("      # Show alerts for this camera")
        print("=" * 60)