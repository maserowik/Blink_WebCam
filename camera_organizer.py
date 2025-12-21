"""
camera_organizer.py - Camera Photo Organization Module

Manages camera photo storage in date-organized folders:
  cameras/{camera-name}/YYYY-MM-DD/photo.jpg

Features:
- Organizes photos into daily folders
- Automatic cleanup of old photos based on max_days retention
- Migration support for flat photo structure to date folders

File location: /your-project/camera_organizer.py
"""

from pathlib import Path
from datetime import datetime, timedelta
import re
import shutil


class CameraOrganizer:
    """Manages camera photo organization and retention"""

    def __init__(self, cameras_dir: Path, max_days: int = 7):
        """
        Initialize camera organizer

        Args:
            cameras_dir: Path to cameras directory
            max_days: Number of days to retain photos (default: 7)
        """
        self.cameras_dir = Path(cameras_dir)
        self.max_days = max_days

    def get_date_folder(self, camera_folder: Path, date: datetime) -> Path:
        """
        Get the date folder for a camera

        Args:
            camera_folder: Path to camera folder
            date: Date for the folder

        Returns:
            Path to YYYY-MM-DD folder
        """
        date_str = date.strftime("%Y-%m-%d")
        date_folder = camera_folder / date_str
        date_folder.mkdir(parents=True, exist_ok=True)
        return date_folder

    def save_photo_to_date_folder(
        self,
        camera_folder: Path,
        image_bytes: bytes,
        camera_name: str,
        timestamp: datetime
    ) -> Path:
        """
        Save a photo to the appropriate date folder

        Args:
            camera_folder: Path to camera folder
            image_bytes: Image data
            camera_name: Camera name (for filename)
            timestamp: Photo timestamp

        Returns:
            Path to saved photo
        """
        # Get date folder
        date_folder = self.get_date_folder(camera_folder, timestamp)

        # Create filename: camera-name_YYYYMMDD_HHMMSS.jpg
        normalized_name = camera_name.lower().replace(" ", "-")
        filename = f"{normalized_name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
        photo_path = date_folder / filename

        # Save photo
        with open(photo_path, "wb") as f:
            f.write(image_bytes)

        return photo_path

    def get_all_date_folders(self, camera_folder: Path) -> list:
        """
        Get all date folders for a camera (sorted newest first)

        Args:
            camera_folder: Path to camera folder

        Returns:
            List of (date_str, folder_path) tuples
        """
        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        date_folders = []

        if not camera_folder.exists():
            return []

        for item in camera_folder.iterdir():
            if item.is_dir() and date_pattern.match(item.name):
                date_folders.append((item.name, item))

        # Sort by date (newest first)
        date_folders.sort(key=lambda x: x[0], reverse=True)
        return date_folders

    def cleanup_old_photos(self, camera_folder: Path) -> dict:
        """
        Remove photos older than max_days

        Args:
            camera_folder: Path to camera folder

        Returns:
            Dictionary with cleanup stats
        """
        if not camera_folder.exists():
            return {"deleted_folders": 0, "deleted_photos": 0}

        cutoff_date = datetime.now() - timedelta(days=self.max_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        deleted_folders = 0
        deleted_photos = 0

        date_folders = self.get_all_date_folders(camera_folder)

        for date_str, folder_path in date_folders:
            if date_str < cutoff_str:
                # Count photos before deletion
                photos = list(folder_path.glob("*.jpg"))
                deleted_photos += len(photos)

                # Delete folder
                shutil.rmtree(folder_path)
                deleted_folders += 1

        return {
            "deleted_folders": deleted_folders,
            "deleted_photos": deleted_photos,
            "camera": camera_folder.name
        }

    def cleanup_all_cameras(self) -> list:
        """
        Cleanup old photos from all cameras

        Returns:
            List of cleanup stats for each camera
        """
        if not self.cameras_dir.exists():
            return []

        stats = []

        for camera_folder in self.cameras_dir.iterdir():
            if camera_folder.is_dir():
                cleanup_result = self.cleanup_old_photos(camera_folder)
                if cleanup_result["deleted_folders"] > 0:
                    stats.append(cleanup_result)

        return stats

    def migrate_flat_photos_to_date_folder(self, camera_folder: Path) -> dict:
        """
        Migrate photos from flat structure to date folders

        Moves photos like:
          cameras/front-door/photo.jpg
        To:
          cameras/front-door/YYYY-MM-DD/photo.jpg

        Args:
            camera_folder: Path to camera folder

        Returns:
            Dictionary with migration stats
        """
        if not camera_folder.exists():
            return {"migrated": 0, "errors": 0}

        migrated = 0
        errors = 0

        # Find all .jpg files directly in camera folder (not in subfolders)
        flat_photos = [
            f for f in camera_folder.glob("*.jpg")
            if f.is_file()
        ]

        for photo in flat_photos:
            try:
                # Extract date from filename: camera-name_YYYYMMDD_HHMMSS.jpg
                match = re.search(r'_(\d{8})_(\d{6})\.jpg$', photo.name)

                if match:
                    date_str = match.group(1)  # YYYYMMDD
                    date = datetime.strptime(date_str, "%Y%m%d")
                else:
                    # Use file modification time as fallback
                    date = datetime.fromtimestamp(photo.stat().st_mtime)

                # Get destination date folder
                date_folder = self.get_date_folder(camera_folder, date)
                dest_path = date_folder / photo.name

                # Move photo
                shutil.move(str(photo), str(dest_path))
                migrated += 1

            except Exception as e:
                print(f"  \u26A0\uFE0F Error migrating {photo.name}: {e}")
                errors += 1

        return {
            "camera": camera_folder.name,
            "migrated": migrated,
            "errors": errors
        }

    def migrate_all_cameras(self) -> list:
        """
        Migrate all cameras from flat to date folder structure

        Returns:
            List of migration stats for each camera
        """
        if not self.cameras_dir.exists():
            return []

        stats = []

        for camera_folder in self.cameras_dir.iterdir():
            if camera_folder.is_dir():
                result = self.migrate_flat_photos_to_date_folder(camera_folder)
                if result["migrated"] > 0 or result["errors"] > 0:
                    stats.append(result)

        return stats

    def get_camera_stats(self, camera_folder: Path) -> dict:
        """
        Get statistics for a camera

        Args:
            camera_folder: Path to camera folder

        Returns:
            Dictionary with camera stats
        """
        if not camera_folder.exists():
            return {
                "camera": camera_folder.name,
                "total_photos": 0,
                "total_size_mb": 0,
                "date_folders": 0,
                "oldest_date": None,
                "newest_date": None
            }

        date_folders = self.get_all_date_folders(camera_folder)
        total_photos = 0
        total_size = 0

        for date_str, folder_path in date_folders:
            photos = list(folder_path.glob("*.jpg"))
            total_photos += len(photos)
            total_size += sum(p.stat().st_size for p in photos)

        oldest_date = date_folders[-1][0] if date_folders else None
        newest_date = date_folders[0][0] if date_folders else None

        return {
            "camera": camera_folder.name,
            "total_photos": total_photos,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "date_folders": len(date_folders),
            "oldest_date": oldest_date,
            "newest_date": newest_date
        }

    def get_all_camera_stats(self) -> list:
        """
        Get statistics for all cameras

        Returns:
            List of stats dictionaries
        """
        if not self.cameras_dir.exists():
            return []

        stats = []

        for camera_folder in self.cameras_dir.iterdir():
            if camera_folder.is_dir():
                camera_stats = self.get_camera_stats(camera_folder)
                stats.append(camera_stats)

        return stats


# Example usage and testing
if __name__ == "__main__":
    import sys

    # Configuration
    CAMERAS_DIR = Path("cameras")
    MAX_DAYS = 7

    # Create organizer
    organizer = CameraOrganizer(CAMERAS_DIR, max_days=MAX_DAYS)

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--migrate":
            # Migrate flat photos to date folders
            print("=" * 60)
            print("\U0001F4E6 MIGRATING PHOTOS TO DATE FOLDERS")
            print("=" * 60)

            stats = organizer.migrate_all_cameras()

            if not stats:
                print("\n\u2139\uFE0F No photos to migrate")
            else:
                for result in stats:
                    print(f"\n\U0001F4F9 {result['camera']}")
                    print(f"  \u2705 Migrated: {result['migrated']} photos")
                    if result['errors'] > 0:
                        print(f"  \u26A0\uFE0F Errors: {result['errors']}")

            print("\n" + "=" * 60)

        elif command == "--cleanup":
            # Cleanup old photos
            print("=" * 60)
            print(f"\U0001F9F9 CLEANING UP PHOTOS OLDER THAN {MAX_DAYS} DAYS")
            print("=" * 60)

            stats = organizer.cleanup_all_cameras()

            if not stats:
                print("\n\u2139\uFE0F No old photos to cleanup")
            else:
                total_folders = 0
                total_photos = 0

                for result in stats:
                    print(f"\n\U0001F4F9 {result['camera']}")
                    print(f"  \U0001F5D1\uFE0F Deleted: {result['deleted_folders']} folder(s)")
                    print(f"  \U0001F5D1\uFE0F Deleted: {result['deleted_photos']} photo(s)")
                    total_folders += result['deleted_folders']
                    total_photos += result['deleted_photos']

                print("\n" + "-" * 60)
                print(f"Total: {total_folders} folder(s), {total_photos} photo(s) deleted")

            print("=" * 60)

        elif command == "--stats":
            # Show camera statistics
            print("=" * 60)
            print("\U0001F4CA CAMERA STATISTICS")
            print("=" * 60)

            stats = organizer.get_all_camera_stats()

            if not stats:
                print("\n\u2139\uFE0F No cameras found")
            else:
                for camera_stats in stats:
                    print(f"\n\U0001F4F9 {camera_stats['camera']}")
                    print(f"  \U0001F4F8 Photos: {camera_stats['total_photos']}")
                    print(f"  \U0001F4BE Size: {camera_stats['total_size_mb']} MB")
                    print(f"  \U0001F4C1 Date folders: {camera_stats['date_folders']}")
                    if camera_stats['oldest_date']:
                        print(f"  \U0001F4C5 Oldest: {camera_stats['oldest_date']}")
                    if camera_stats['newest_date']:
                        print(f"  \U0001F4C5 Newest: {camera_stats['newest_date']}")

            print("\n" + "=" * 60)

        else:
            print("\u274C Invalid command")
            print("\nUsage:")
            print("  python camera_organizer.py --migrate   # Move flat photos to date folders")
            print("  python camera_organizer.py --cleanup   # Remove old photos")
            print("  python camera_organizer.py --stats     # Show camera statistics")

    else:
        print("=" * 60)
        print("\U0001F4C1 Camera Photo Organizer")
        print("=" * 60)
        print(f"\nOrganizes photos into date folders:")
        print(f"  cameras/{{camera-name}}/YYYY-MM-DD/photo.jpg")
        print(f"\nRetention: {MAX_DAYS} days")
        print("\nUsage:")
        print("  python camera_organizer.py --migrate   # Move flat photos to date folders")
        print("  python camera_organizer.py --cleanup   # Remove old photos")
        print("  python camera_organizer.py --stats     # Show camera statistics")
        print("\nIntegration:")
        print("  from camera_organizer import CameraOrganizer")
        print("  organizer = CameraOrganizer(CAMERAS_DIR, max_days=7)")
        print("  organizer.save_photo_to_date_folder(cam_folder, image_bytes, cam_name, datetime.now())")
        print("  organizer.cleanup_all_cameras()")
        print("=" * 60)