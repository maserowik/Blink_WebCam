"""
camera_processor.py - Camera Processing Module
Handles individual camera snapshot processing with retry logic and error handling
"""

import asyncio
import time
import io
import hashlib
from datetime import datetime
from PIL import Image
from pathlib import Path


class CameraProcessor:
    """Handles processing snapshots for individual cameras"""
    
    def __init__(self, camera_organizer, log_main, log_camera, log_camera_performance, 
                 normalize_camera_name, wifi_bars, duplicate_threshold=3):
        self.camera_organizer = camera_organizer
        self.log_main = log_main
        self.log_camera = log_camera
        self.log_camera_performance = log_camera_performance
        self.normalize_camera_name = normalize_camera_name
        self.wifi_bars = wifi_bars
        self.duplicate_threshold = duplicate_threshold
    
    def ensure_camera_folder(self, cam_name: str, cameras_dir: Path) -> Path:
        """Create and return camera folder"""
        normalized_name = self.normalize_camera_name(cam_name)
        cam_folder = cameras_dir / normalized_name
        cam_folder.mkdir(parents=True, exist_ok=True)
        return cam_folder
    
    async def refresh_camera_state(self, cam, cam_name: str):
        """Force refresh camera state before snapshot"""
        try:
            self.log_main("  Refreshing camera state before snapshot...")
            await asyncio.wait_for(cam.async_update(), timeout=10)
        except asyncio.TimeoutError:
            self.log_main("  WARNING: Camera state refresh timed out")
        except Exception as e:
            self.log_main(f"  WARNING: Camera state refresh failed: {e}")
    
    async def request_snapshot_with_retry(self, cam, cam_name: str, max_retries=2):
        """Request snapshot with retry logic"""
        snap_start = time.time()
        snap_success = False

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.log_main(f"  Retry {attempt}/{max_retries} for snapshot...")
                    await asyncio.sleep(5)
                
                self.log_main("  Requesting new snapshot from camera...")
                snap_result = await asyncio.wait_for(
                    cam.snap_picture(),
                    timeout=30
                )

                snap_duration = time.time() - snap_start
                self.log_camera_performance(cam_name, "snap_picture", snap_duration, True)

                if isinstance(snap_result, dict):
                    command_id = snap_result.get('id', 'unknown')
                    state = snap_result.get('state_condition', 'unknown')
                    self.log_main(f"  Snapshot requested (ID: {command_id}, State: {state})")
                else:
                    self.log_main(f"  Snapshot requested")
                
                snap_success = True
                break

            except asyncio.TimeoutError:
                snap_duration = time.time() - snap_start
                self.log_camera_performance(cam_name, "snap_picture", snap_duration, False)
                self.log_main(f"  WARNING: Snapshot request timed out (attempt {attempt + 1}/{max_retries})")
                self.log_camera(cam_name, f"TIMEOUT: Snapshot request exceeded 30 seconds (attempt {attempt + 1})")
                
                if attempt == max_retries - 1:
                    self.log_main(f"  ERROR: All snapshot attempts failed for {cam_name}")
            
            except Exception as e:
                snap_duration = time.time() - snap_start
                self.log_camera_performance(cam_name, "snap_picture", snap_duration, False)
                self.log_main(f"  WARNING: Snapshot request failed: {type(e).__name__}: {e}")
                self.log_camera(cam_name, f"ERROR: Snapshot request failed - {type(e).__name__}: {e}")
                
                if attempt == max_retries - 1:
                    self.log_main(f"  ERROR: All snapshot attempts failed for {cam_name}")

        return snap_success
    
    async def download_image(self, cam, cam_name: str):
        """Download image with fallback to thumbnail"""
        image_bytes = None
        source = "None"
        
        # Try get_media first
        media_start = time.time()
        try:
            response = await asyncio.wait_for(cam.get_media(), timeout=30)

            if response.status == 200:
                image_bytes = await response.read()
                source = "get_media"
                media_duration = time.time() - media_start
                self.log_camera_performance(cam_name, "get_media", media_duration, True)
                self.log_main(f"  Downloaded {len(image_bytes)} bytes in {media_duration:.2f}s")
            else:
                media_duration = time.time() - media_start
                self.log_camera_performance(cam_name, "get_media", media_duration, False)
                self.log_main(f"  ERROR: HTTP {response.status}")
                self.log_camera(cam_name, f"ERROR: HTTP {response.status} from get_media")
        except asyncio.TimeoutError:
            media_duration = time.time() - media_start
            self.log_camera_performance(cam_name, "get_media", media_duration, False)
            self.log_main(f"  Timeout: Media download timed out for {cam_name}")
            self.log_camera(cam_name, f"TIMEOUT: Media download exceeded 30 seconds")
        except Exception as e:
            media_duration = time.time() - media_start
            self.log_camera_performance(cam_name, "get_media", media_duration, False)
            self.log_main(f"  ERROR: Download failed: {e}")
            self.log_camera(cam_name, f"ERROR: Media download failed - {type(e).__name__}: {e}")

        # Fallback to thumbnail
        if not image_bytes or len(image_bytes) < 1000:
            thumb_start = time.time()
            try:
                thumb_response = await asyncio.wait_for(cam.get_thumbnail(), timeout=15)
                if thumb_response.status == 200:
                    image_bytes = await thumb_response.read()
                    source = "thumbnail"
                    thumb_duration = time.time() - thumb_start
                    self.log_camera_performance(cam_name, "get_thumbnail", thumb_duration, True)
                    self.log_main(f"  WARNING: Using thumbnail ({len(image_bytes)} bytes)")
                    self.log_camera(cam_name, f"FALLBACK: Using thumbnail instead of full image")
            except asyncio.TimeoutError:
                thumb_duration = time.time() - thumb_start
                self.log_camera_performance(cam_name, "get_thumbnail", thumb_duration, False)
                self.log_main(f"  Timeout: Thumbnail download timed out for {cam_name}")
                self.log_camera(cam_name, f"TIMEOUT: Thumbnail download exceeded 15 seconds")
            except Exception as e:
                thumb_duration = time.time() - thumb_start
                self.log_camera_performance(cam_name, "get_thumbnail", thumb_duration, False)
                self.log_main(f"  ERROR: Thumbnail failed: {e}")
                self.log_camera(cam_name, f"ERROR: Thumbnail download failed - {type(e).__name__}: {e}")
        
        # Final fallback - placeholder
        if not image_bytes or len(image_bytes) < 1000:
            placeholder = Image.new("RGB", (640, 480), color=(255, 0, 0))
            buffer = io.BytesIO()
            placeholder.save(buffer, format='JPEG')
            image_bytes = buffer.getvalue()
            source = "placeholder"
            self.log_main(f"  WARNING: No valid image data, using placeholder")
            self.log_camera(cam_name, f"WARNING: No valid image received, using red placeholder")
        
        return image_bytes, source
    
    def check_duplicate(self, image_bytes: bytes, cam_folder: Path, cam_name: str):
        """Check if image is duplicate using 60-second cutoff"""
        current_hash = hashlib.md5(image_bytes).hexdigest()
        
        date_folders = sorted(cam_folder.glob("20*"), reverse=True)
        last_image_hash = None
        comparison_photo_name = None
        now = datetime.now()
        cutoff_time = now.timestamp() - 60
        
        for date_folder in date_folders:
            existing_photos = sorted(
                date_folder.glob(f"{self.normalize_camera_name(cam_name)}_*.jpg"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            for photo in existing_photos:
                try:
                    if photo.stat().st_mtime > cutoff_time:
                        continue
                    
                    with open(photo, 'rb') as f:
                        last_image_hash = hashlib.md5(f.read()).hexdigest()
                    comparison_photo_name = photo.name
                    break
                except Exception as e:
                    self.log_camera(cam_name, f"Error reading photo for duplicate check: {e}")
            
            if last_image_hash:
                break
        
        dup_count_file = cam_folder / ".duplicate_count"
        dup_count = int(dup_count_file.read_text()) if dup_count_file.exists() else 0
        
        is_duplicate = False
        if last_image_hash and current_hash == last_image_hash:
            dup_count += 1
            dup_count_file.write_text(str(dup_count))
            is_duplicate = True

            if dup_count >= self.duplicate_threshold:
                self.log_main(f"  WARNING: Snapshot unchanged for {dup_count} consecutive cycles")
                self.log_camera(cam_name, f"WARNING: Camera may not be capturing new images - {dup_count} duplicates in a row")
            else:
                self.log_main(f"  INFO: Image identical to previous capture (compared with {comparison_photo_name})")

        elif last_image_hash:
            dup_count_file.write_text("0")
            self.log_main(f"  OK: Image is unique (compared with {comparison_photo_name})")

        else:
            dup_count_file.write_text("0")
            self.log_main(f"  INFO: No previous photos to compare (first run or new camera)")
        
        return is_duplicate
    
    async def process_camera(self, blink, cam_name: str, cam, cameras_dir: Path):
        """Main camera processing function"""
        start_time = time.time()

        self.log_main(f"{'=' * 60}")
        self.log_main(f"Processing camera: {cam_name}")
        self.log_main(f"{'=' * 60}")

        cam_folder = self.ensure_camera_folder(cam_name, cameras_dir)
        bars = self.wifi_bars(cam.wifi_strength)

        self.log_main(f"  Battery: {getattr(cam, 'battery', 'N/A')}")
        self.log_main(f"  Temperature: {getattr(cam, 'temperature', 'N/A')}")
        self.log_main(f"  WiFi Signal: {getattr(cam, 'wifi_strength', 'N/A')} dBm ({bars}/5 bars)")

        # Refresh camera state
        await self.refresh_camera_state(cam, cam_name)
        
        # Request snapshot with retry
        snap_success = await self.request_snapshot_with_retry(cam, cam_name)
        
        if not snap_success:
            self.log_main(f"  WARNING: Proceeding with last available image for {cam_name}")
        
        # Wait for camera to process
        self.log_main("  Waiting 12 seconds for camera to process snapshot...")
        await asyncio.sleep(12)
        
        # Refresh to get new image
        refresh_start = time.time()
        try:
            await asyncio.wait_for(blink.refresh(force=True), timeout=20)
            refresh_duration = time.time() - refresh_start
            self.log_camera_performance(cam_name, "refresh_after_snap", refresh_duration, True)
        except asyncio.TimeoutError:
            refresh_duration = time.time() - refresh_start
            self.log_camera_performance(cam_name, "refresh_after_snap", refresh_duration, False)
            self.log_main(f"  WARNING: Refresh after snap timed out")
        except Exception as e:
            self.log_main(f"  WARNING: Refresh error: {e}")
        
        # Download image
        image_bytes, source = await self.download_image(cam, cam_name)
        
        # Verify image
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()
            self.log_main(f"  Valid {img.format} image {img.size}")
        except Exception as e:
            self.log_main(f"  WARNING: Image validation failed: {e}")
            self.log_camera(cam_name, f"WARNING: Image validation failed - {e}")
        
        # Check for duplicates
        is_duplicate = self.check_duplicate(image_bytes, cam_folder, cam_name)
        if is_duplicate:
            source = source + "_DUPLICATE"
        
        # Save photo
        save_start = time.time()
        photo_path = self.camera_organizer.save_photo_to_date_folder(
            cam_folder,
            image_bytes,
            cam_name,
            datetime.now()
        )
        save_duration = time.time() - save_start

        if photo_path.exists():
            actual_size = photo_path.stat().st_size
            self.log_camera_performance(cam_name, "save_photo", save_duration, True)
            self.log_main(f"  Saved: {photo_path.parent.name}/{photo_path.name} ({actual_size:,} bytes, {source})")
        else:
            self.log_camera_performance(cam_name, "save_photo", save_duration, False)
            self.log_main(f"  ERROR: File not found after save!")
            self.log_camera(cam_name, f"ERROR: Photo file not found after save operation")
        
        # Save status
        self.save_camera_status(cam, cam_folder, cam_name, photo_path)
        
        # Log summary
        log_entry = f"Temp: {cam.temperature} | Battery: {cam.battery} | WiFi: {bars}/5 | Source: {source}"
        self.log_camera(cam_name, log_entry)

        total_duration = time.time() - start_time
        self.log_camera_performance(cam_name, "total_processing", total_duration, True)

        return {
            "camera": cam_name,
            "success": True,
            "duration": total_duration
        }
    
    def save_camera_status(self, cam, cam_folder: Path, cam_name: str, photo_path: Path):
        """Save camera status to JSON file"""
        import json
        
        status_data = {
            "temperature": str(cam.temperature) if hasattr(cam, 'temperature') else "N/A",
            "battery": str(cam.battery) if hasattr(cam, 'battery') else "N/A",
            "wifi_strength": cam.wifi_strength if hasattr(cam, 'wifi_strength') else None,
            "last_updated": datetime.now().isoformat(),
            "last_photo": photo_path.name if photo_path and photo_path.exists() else None
        }
        
        status_file = cam_folder / "status.json"
        temp_status_file = cam_folder / "status.json.tmp"
        
        try:
            cam_folder.mkdir(parents=True, exist_ok=True)
            with open(temp_status_file, 'w') as f:
                json.dump(status_data, f, indent=2)
            temp_status_file.replace(status_file)
            self.log_main(f"  Status updated: {status_file.name}")
        except Exception as e:
            self.log_main(f"  WARNING: Error updating status file: {e}")
            self.log_camera(cam_name, f"ERROR: Failed to update status.json - {e}")
            
            if temp_status_file.exists():
                try:
                    temp_status_file.unlink()
                except:
                    pass