"""
log_rotation.py - Log Rotation Module for Blink Camera System

This handles daily log cleanup keeping only the most recent days.
Logs are organized with dates in filenames:
  - logs/system/main/main_2025-12-28.log
  - logs/cameras/{camera-name}/{camera-name}_2025-12-28.log

FIXED: Now properly handles date-based log files instead of numbered backups
"""

from pathlib import Path
from datetime import datetime, timedelta
import threading
import time as time_module
import re


class LogRotator:
    """Manages log file cleanup with daily date-based files"""

    def __init__(self, log_folder: Path, max_backups: int = 5):
        """
        Initialize log rotator

        Args:
            log_folder: Path to logs directory
            max_backups: Number of days to keep (default: 5)
        """
        self.log_folder = Path(log_folder)
        self.max_backups = max_backups  # This is now "max_days"
        self.last_cleanup_date = datetime.now().date()

        # Create subdirectories for organization
        self.system_folder = self.log_folder / "system"
        self.cameras_folder = self.log_folder / "cameras"

        self.system_folder.mkdir(parents=True, exist_ok=True)
        self.cameras_folder.mkdir(parents=True, exist_ok=True)

    def get_system_log_folder(self, log_name: str) -> Path:
        """
        Get the folder for a system log (main, token, or performance)

        Args:
            log_name: 'main', 'token', 'performance', or 'webserver'

        Returns:
            Path to logs/system/{log_name}/
        """
        folder = self.system_folder / log_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def get_camera_log_folder(self, camera_name: str) -> Path:
        """
        Get the folder for a camera log

        Args:
            camera_name: Camera name (e.g., 'front-door')

        Returns:
            Path to logs/cameras/{camera_name}/
        """
        folder = self.cameras_folder / camera_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def cleanup_old_logs(self, folder: Path, base_name: str):
        """
        Remove log files older than max_backups days

        Example:
            Keeps: main_2025-12-28.log, main_2025-12-27.log, main_2025-12-26.log
            Deletes: main_2025-12-20.log (if older than 5 days)

        Args:
            folder: Folder containing log files
            base_name: Base name of log files (e.g., "main", "front-door")
        """
        if not folder.exists():
            return

        # Calculate cutoff date
        cutoff_date = datetime.now().date() - timedelta(days=self.max_backups)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        # Pattern: base_name_YYYY-MM-DD.log
        pattern = re.compile(rf'^{re.escape(base_name)}_(\d{{4}}-\d{{2}}-\d{{2}})\.log$')

        deleted_count = 0

        for log_file in folder.glob(f"{base_name}_*.log"):
            match = pattern.match(log_file.name)
            if match:
                date_str = match.group(1)

                # Compare date strings (YYYY-MM-DD format compares correctly)
                if date_str < cutoff_str:
                    try:
                        log_file.unlink()
                        deleted_count += 1
                        print(f"Deleted old log: {log_file.name}")
                    except Exception as e:
                        print(f"Error deleting {log_file.name}: {e}")

        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} old log(s) from {folder.name}")

    def cleanup_all_logs(self):
        """
        Cleanup old logs from all locations

        This runs at midnight and removes logs older than max_backups days
        """
        print("=" * 60)
        print(f"LOG CLEANUP - Removing logs older than {self.max_backups} days")
        print("=" * 60)

        total_deleted = 0

        # Cleanup system logs
        for log_name in ["main", "token", "performance", "webserver", "webserver-perf"]:
            folder = self.get_system_log_folder(log_name)
            if folder.exists():
                before_count = len(list(folder.glob("*.log")))
                self.cleanup_old_logs(folder, log_name)
                after_count = len(list(folder.glob("*.log")))
                deleted = before_count - after_count
                total_deleted += deleted

        # Cleanup camera logs
        if self.cameras_folder.exists():
            for camera_folder in self.cameras_folder.iterdir():
                if camera_folder.is_dir():
                    camera_name = camera_folder.name
                    before_count = len(list(camera_folder.glob("*.log")))
                    self.cleanup_old_logs(camera_folder, camera_name)
                    after_count = len(list(camera_folder.glob("*.log")))
                    deleted = before_count - after_count
                    total_deleted += deleted

        print(f"Total logs deleted: {total_deleted}")
        print("=" * 60)

        self.last_cleanup_date = datetime.now().date()

    def check_and_rotate_if_needed(self):
        """
        Check if it's past midnight and cleanup old logs if needed

        NOTE: We don't "rotate" - we just cleanup old dated files
        """
        current_date = datetime.now().date()

        if current_date > self.last_cleanup_date:
            self.cleanup_all_logs()
            return True
        return False

    def start_midnight_rotation_thread(self):
        """Start a background thread that checks for midnight cleanup"""

        def rotation_worker():
            while True:
                # Check every minute if we've crossed midnight
                self.check_and_rotate_if_needed()
                time_module.sleep(60)  # Check every minute

        thread = threading.Thread(target=rotation_worker, daemon=True)
        thread.start()
        print(f"Log cleanup scheduler started (keeps {self.max_backups} days of logs)")
        return thread

    def get_log_stats(self, folder_path: Path, log_name: str) -> dict:
        """
        Get statistics about dated log files

        Args:
            folder_path: Path to the folder containing the log
            log_name: Name of the log file base (without date/extension)

        Returns:
            Dictionary with log statistics
        """
        if not folder_path.exists():
            return {
                'log_name': log_name,
                'folder': folder_path,
                'total_files': 0,
                'total_size': 0,
                'total_lines': 0,
                'files': []
            }

        stats = {
            'log_name': log_name,
            'folder': folder_path,
            'total_files': 0,
            'total_size': 0,
            'total_lines': 0,
            'files': []
        }

        # Pattern: base_name_YYYY-MM-DD.log
        pattern = re.compile(rf'^{re.escape(log_name)}_(\d{{4}}-\d{{2}}-\d{{2}})\.log$')

        for log_file in sorted(folder_path.glob(f"{log_name}_*.log"), reverse=True):
            match = pattern.match(log_file.name)
            if match:
                file_size = log_file.stat().st_size
                file_lines = 0

                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        file_lines = sum(1 for _ in f)
                except:
                    pass

                stats['files'].append({
                    'name': log_file.name,
                    'date': match.group(1),
                    'size': file_size,
                    'lines': file_lines,
                    'modified': datetime.fromtimestamp(log_file.stat().st_mtime)
                })

                stats['total_files'] += 1
                stats['total_size'] += file_size
                stats['total_lines'] += file_lines

        return stats


def format_bytes(bytes_size: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


# Example usage and testing
if __name__ == "__main__":
    import sys

    # Configuration
    LOG_FOLDER = Path("logs")
    LOG_FOLDER.mkdir(exist_ok=True)

    # Create rotator
    rotator = LogRotator(LOG_FOLDER, max_backups=5)

    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        # Manual cleanup
        print("Performing manual log cleanup...")
        rotator.cleanup_all_logs()

    elif len(sys.argv) > 1 and sys.argv[1] == "--stats":
        # Show statistics
        print("\n" + "=" * 60)
        print("LOG STATISTICS")
        print("=" * 60)

        # System logs
        print("\nSYSTEM LOGS")
        print("-" * 60)
        for log_name in ["main", "token", "performance", "webserver", "webserver-perf"]:
            folder = rotator.get_system_log_folder(log_name)
            if folder.exists():
                stats = rotator.get_log_stats(folder, log_name)
                if stats['total_files'] > 0:
                    rel_path = folder.relative_to(LOG_FOLDER)
                    print(f"\n{rel_path}/")
                    print(f"  Files: {stats['total_files']}")
                    print(f"  Total size: {format_bytes(stats['total_size'])}")
                    print(f"  Total lines: {stats['total_lines']:,}")
                    print(f"  Files:")
                    for file_info in stats['files']:
                        print(f"    • {file_info['name']}: {format_bytes(file_info['size'])}, "
                              f"{file_info['lines']:,} lines")

        # Camera logs
        print("\nCAMERA LOGS")
        print("-" * 60)
        if rotator.cameras_folder.exists():
            camera_folders = [d for d in rotator.cameras_folder.iterdir() if d.is_dir()]

            for camera_folder in sorted(camera_folders):
                camera_name = camera_folder.name
                stats = rotator.get_log_stats(camera_folder, camera_name)

                if stats['total_files'] > 0:
                    rel_path = camera_folder.relative_to(LOG_FOLDER)
                    print(f"\n{rel_path}/")
                    print(f"  Files: {stats['total_files']}")
                    print(f"  Total size: {format_bytes(stats['total_size'])}")
                    print(f"  Total lines: {stats['total_lines']:,}")
                    print(f"  Files:")
                    for file_info in stats['files'][:5]:  # Show first 5
                        print(f"    • {file_info['name']}: {format_bytes(file_info['size'])}, "
                              f"{file_info['lines']:,} lines")
                    if len(stats['files']) > 5:
                        print(f"    ... and {len(stats['files']) - 5} more")

        print("\n" + "=" * 60)

    else:
        print("=" * 60)
        print("Log Rotation Module (Date-Based)")
        print("=" * 60)
        print(f"\nLog Organization:")
        print(f"  logs/system/main/main_YYYY-MM-DD.log")
        print(f"  logs/cameras/front-door/front-door_YYYY-MM-DD.log")
        print(f"\nRetention: {rotator.max_backups} days")
        print("\nUsage:")
        print("  python log_rotation.py --cleanup    # Manually cleanup old logs")
        print("  python log_rotation.py --stats      # Show log statistics")
        print("\nIntegration:")
        print("  from log_rotation import LogRotator")
        print("  rotator = LogRotator(LOG_FOLDER, max_backups=5)")
        print("  rotator.start_midnight_rotation_thread()")
        print("=" * 60)