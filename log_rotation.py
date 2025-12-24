"""
log_rotation.py - Log Rotation Module for Blink Camera System

This handles daily log rotation with up to 5 days of history.
Logs are organized into folders:
  - logs/system/main/
  - logs/system/token/
  - logs/system/performance/
  - logs/cameras/{camera-name}/

File location: /your-project/log_rotation.py
"""

from pathlib import Path
from datetime import datetime, time
import shutil
import threading
import time as time_module


class LogRotator:
    """Manages log file rotation with daily cycles"""

    def __init__(self, log_folder: Path, max_backups: int = 5):
        """
        Initialize log rotator

        Args:
            log_folder: Path to logs directory
            max_backups: Number of backup logs to keep (default: 5)
        """
        self.log_folder = Path(log_folder)
        self.max_backups = max_backups
        self.last_rotation_date = datetime.now().date()

        # Create subdirectories for organization
        self.system_folder = self.log_folder / "system"
        self.cameras_folder = self.log_folder / "cameras"

        self.system_folder.mkdir(parents=True, exist_ok=True)
        self.cameras_folder.mkdir(parents=True, exist_ok=True)

    def get_system_log_folder(self, log_name: str) -> Path:
        """
        Get the folder for a system log (main, token, or performance)

        Args:
            log_name: 'main', 'token', or 'performance'

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

    def rotate_log(self, log_file: Path):
        """
        Rotate a single log file

        Example:
            system/main/main.log -> system/main/main.1.log
            cameras/front-door/front-door.log -> cameras/front-door/front-door.1.log

        Args:
            log_file: Path to the log file to rotate
        """
        if not log_file.exists():
            return

        # Get base name without extension and parent folder
        base_name = log_file.stem  # e.g., "front-door" or "main"
        extension = log_file.suffix  # e.g., ".log"
        parent_folder = log_file.parent

        # Rotate existing backups (oldest first)
        for i in range(self.max_backups, 0, -1):
            old_backup = parent_folder / f"{base_name}.{i}{extension}"

            if i == self.max_backups:
                # Delete oldest backup
                if old_backup.exists():
                    old_backup.unlink()
            else:
                # Shift backup to next number
                if old_backup.exists():
                    new_backup = parent_folder / f"{base_name}.{i + 1}{extension}"
                    shutil.move(str(old_backup), str(new_backup))

        # Move current log to .1
        first_backup = parent_folder / f"{base_name}.1{extension}"
        shutil.copy2(str(log_file), str(first_backup))

        # Clear current log file
        log_file.write_text("")

    def rotate_all_logs(self):
        """Rotate all .log files in all subdirectories (silent operation)"""
        # Find all .log files recursively
        log_files = []

        # Search in system folder and all camera folders
        for folder in [self.system_folder, self.cameras_folder]:
            if folder.exists():
                # Find all *.log files, excluding *.1.log, *.2.log, etc.
                for log_file in folder.rglob("*.log"):
                    if not any(log_file.stem.endswith(f".{i}") for i in range(1, self.max_backups + 1)):
                        log_files.append(log_file)

        if not log_files:
            return

        # Rotate each log file silently
        for log_file in log_files:
            try:
                self.rotate_log(log_file)
            except Exception as e:
                # Log error to main log file if it exists
                main_log = self.get_system_log_folder("main") / "main.log"
                if main_log.exists():
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(main_log, "a", encoding="utf-8") as f:
                        f.write(f"{timestamp} | ERROR | Log rotation failed for {log_file.name}: {e}\n")

        self.last_rotation_date = datetime.now().date()

        # Log completion to main log only
        main_log = self.get_system_log_folder("main") / "main.log"
        if main_log.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(main_log, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | Log rotation completed: {len(log_files)} files rotated\n")

    def check_and_rotate_if_needed(self):
        """Check if it's past midnight and rotate logs if needed"""
        current_date = datetime.now().date()

        if current_date > self.last_rotation_date:
            self.rotate_all_logs()
            return True
        return False

    def start_midnight_rotation_thread(self):
        """Start a background thread that checks for midnight rotation"""

        def rotation_worker():
            while True:
                # Check every minute if we've crossed midnight
                self.check_and_rotate_if_needed()
                time_module.sleep(60)  # Check every minute

        thread = threading.Thread(target=rotation_worker, daemon=True)
        thread.start()
        # Silently start - no console output
        return thread

    def get_log_stats(self, folder_path: Path, log_name: str) -> dict:
        """
        Get statistics about a log file and its backups

        Args:
            folder_path: Path to the folder containing the log
            log_name: Name of the log file (without extension)

        Returns:
            Dictionary with log statistics
        """
        stats = {
            'log_name': log_name,
            'folder': folder_path,
            'current_size': 0,
            'current_lines': 0,
            'backups': []
        }

        # Current log
        current_log = folder_path / f"{log_name}.log"
        if current_log.exists():
            stats['current_size'] = current_log.stat().st_size
            with open(current_log, 'r', encoding='utf-8', errors='ignore') as f:
                stats['current_lines'] = sum(1 for _ in f)

        # Backups
        for i in range(1, self.max_backups + 1):
            backup_log = folder_path / f"{log_name}.{i}.log"
            if backup_log.exists():
                stats['backups'].append({
                    'number': i,
                    'size': backup_log.stat().st_size,
                    'modified': datetime.fromtimestamp(backup_log.stat().st_mtime)
                })

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

    if len(sys.argv) > 1 and sys.argv[1] == "--rotate":
        # Manual rotation with verbose output
        print("\U0001F504 Performing manual log rotation...")

        # Find all .log files
        log_files = []
        for folder in [rotator.system_folder, rotator.cameras_folder]:
            if folder.exists():
                for log_file in folder.rglob("*.log"):
                    if not any(log_file.stem.endswith(f".{i}") for i in range(1, rotator.max_backups + 1)):
                        log_files.append(log_file)

        print(f"Found {len(log_files)} log files to rotate")

        # Rotate
        rotator.rotate_all_logs()

        print("✅ Rotation complete")

    elif len(sys.argv) > 1 and sys.argv[1] == "--stats":
        # Show statistics
        print("\n" + "=" * 60)
        print("\U0001F4CA LOG STATISTICS")
        print("=" * 60)

        # System logs
        print("\n\U0001F4C1 SYSTEM LOGS")
        print("-" * 60)
        for log_name in ["main", "token", "performance", "webserver"]:
            folder = rotator.get_system_log_folder(log_name)
            log_file = folder / f"{log_name}.log"
            if log_file.exists():
                stats = rotator.get_log_stats(folder, log_name)
                rel_path = folder.relative_to(LOG_FOLDER)
                print(f"\n\U0001F4C1 {rel_path}/{log_name}.log")
                print(f"   Current: {stats['current_lines']} lines, {format_bytes(stats['current_size'])}")

                if stats['backups']:
                    print(f"   Backups:")
                    for backup in stats['backups']:
                        print(f"      \u2022 {log_name}.{backup['number']}.log: "
                              f"{format_bytes(backup['size'])} "
                              f"(modified: {backup['modified'].strftime('%Y-%m-%d %H:%M')})")
                else:
                    print(f"   Backups: None")

        # Camera logs
        print("\n\U0001F4F9 CAMERA LOGS")
        print("-" * 60)
        if rotator.cameras_folder.exists():
            camera_folders = [d for d in rotator.cameras_folder.iterdir() if d.is_dir()]

            for camera_folder in sorted(camera_folders):
                camera_name = camera_folder.name
                log_file = camera_folder / f"{camera_name}.log"

                if log_file.exists():
                    stats = rotator.get_log_stats(camera_folder, camera_name)
                    rel_path = camera_folder.relative_to(LOG_FOLDER)
                    print(f"\n\U0001F4C1 {rel_path}/{camera_name}.log")
                    print(f"   Current: {stats['current_lines']} lines, {format_bytes(stats['current_size'])}")

                    if stats['backups']:
                        print(f"   Backups:")
                        for backup in stats['backups']:
                            print(f"      \u2022 {camera_name}.{backup['number']}.log: "
                                  f"{format_bytes(backup['size'])} "
                                  f"(modified: {backup['modified'].strftime('%Y-%m-%d %H:%M')})")
                    else:
                        print(f"   Backups: None")

        print("\n" + "=" * 60)

    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Create test logs
        print("\U0001F9EA Creating test log files...")

        # System logs (including performance)
        print("\n  Creating system logs:")
        for log_name in ["main", "token", "performance"]:
            folder = rotator.get_system_log_folder(log_name)
            log_file = folder / f"{log_name}.log"
            with open(log_file, "w") as f:
                for i in range(10):
                    f.write(f"2024-{i + 1:02d}-15 12:00:00 | Test {log_name} entry {i + 1}\n")
            rel_path = folder.relative_to(LOG_FOLDER)
            print(f"   \u2705 Created {rel_path}/{log_name}.log")

        # Camera logs
        print("\n  Creating camera logs:")
        camera_names = ["front-door", "back-door", "garage-door"]
        for camera_name in camera_names:
            folder = rotator.get_camera_log_folder(camera_name)
            log_file = folder / f"{camera_name}.log"
            with open(log_file, "w") as f:
                for i in range(10):
                    f.write(f"2024-{i + 1:02d}-15 12:00:00 | Test {camera_name} entry {i + 1}\n")
            rel_path = folder.relative_to(LOG_FOLDER)
            print(f"   \u2705 Created {rel_path}/{camera_name}.log")

        print("\n\U0001F504 Now rotating logs...")
        rotator.rotate_all_logs()

        print("\n\U0001F4CA Final state:")
        print("\n  System logs:")
        for log_name in ["main", "token", "performance"]:
            folder = rotator.get_system_log_folder(log_name)
            stats = rotator.get_log_stats(folder, log_name)
            print(f"    \u2022 {log_name}: {stats['current_lines']} lines, {len(stats['backups'])} backups")

        print("\n  Camera logs:")
        for camera_name in camera_names:
            folder = rotator.get_camera_log_folder(camera_name)
            stats = rotator.get_log_stats(folder, camera_name)
            print(f"    \u2022 {camera_name}: {stats['current_lines']} lines, {len(stats['backups'])} backups")

    else:
        print("=" * 60)
        print("\U0001F4DA Log Rotation Module")
        print("=" * 60)
        print("\nLog Organization:")
        print("  logs/")
        print("  \u251C\u2500\u2500 system/")
        print("  \u2502   \u251C\u2500\u2500 main/")
        print("  \u2502   \u2502   \u251C\u2500\u2500 main.log")
        print("  \u2502   \u2502   \u2514\u2500\u2500 main.1.log - main.5.log")
        print("  \u2502   \u251C\u2500\u2500 token/")
        print("  \u2502   \u2502   \u251C\u2500\u2500 token.log")
        print("  \u2502   \u2502   \u2514\u2500\u2500 token.1.log - token.5.log")
        print("  \u2502   \u2514\u2500\u2500 performance/")
        print("  \u2502       \u251C\u2500\u2500 performance.log")
        print("  \u2502       \u2514\u2500\u2500 performance.1.log - performance.5.log")
        print("  \u2514\u2500\u2500 cameras/")
        print("      \u251C\u2500\u2500 front-door/")
        print("      \u2502   \u251C\u2500\u2500 front-door.log")
        print("      \u2502   \u2514\u2500\u2500 front-door.1.log - front-door.5.log")
        print("      \u251C\u2500\u2500 back-door/")
        print("      \u2502   \u251C\u2500\u2500 back-door.log")
        print("      \u2502   \u2514\u2500\u2500 back-door.1.log - back-door.5.log")
        print("      \u2514\u2500\u2500 ...")
        print("\nUsage:")
        print("  python log_rotation.py --rotate    # Manually rotate all logs")
        print("  python log_rotation.py --stats     # Show log statistics")
        print("  python log_rotation.py --test      # Create test logs and rotate")
        print("\nIntegration:")
        print("  from log_rotation import LogRotator")
        print("  rotator = LogRotator(LOG_FOLDER)")
        print("  rotator.start_midnight_rotation_thread()")
        print("=" * 60)