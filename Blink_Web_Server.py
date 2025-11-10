from flask import Flask, render_template, send_file, jsonify
from pathlib import Path
import json
from datetime import datetime

app = Flask(__name__)

# Configuration
CONFIG_FILE = "blink_config.json"
ROOT_DIR = Path(".")
CAMERAS_DIR = ROOT_DIR / "cameras"
LOG_FOLDER = ROOT_DIR / "logs"


def normalize_camera_name(cam_name: str) -> str:
    """Convert camera name to lowercase kebab-case"""
    return cam_name.lower().replace(" ", "-")


def wifi_bars(dbm: int | None) -> int:
    """Convert WiFi signal strength to bars"""
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


def get_config():
    """Read configuration file"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error reading config: {e}")
        return {
            "cameras": [],
            "carousel_images": 5,
            "location": {
                "city": "Bethel Park",
                "state": "PA"
            }
        }


def get_camera_data():
    """Read camera configuration and latest data"""
    try:
        config = get_config()
        cameras = config.get("cameras", [])
        carousel_images = config.get("carousel_images", 5)
        camera_data = []

        for cam_name in cameras:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name
            log_file = LOG_FOLDER / f"{normalized_name}.log"

            # Get latest N images (sorted by modification time, newest first)
            images = []
            if cam_folder.exists():
                all_images = sorted(
                    cam_folder.glob("*.jpg"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                images = [img.name for img in all_images[:carousel_images]]

            # Get latest log entry
            temp = "N/A"
            battery = "N/A"
            wifi = 0
            timestamp = "N/A"

            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        if lines:
                            last_line = lines[-1]
                            parts = last_line.split(" | ")
                            if len(parts) >= 4:
                                timestamp = parts[0]
                                for part in parts:
                                    if "Temp:" in part:
                                        temp_str = part.split("Temp:")[1].strip().split()[0]
                                        temp = temp_str.replace("°F", "").replace("Â°F", "")
                                        temp_clean = ""
                                        for char in temp:
                                            if char.isdigit() or char == '.' or char == '-':
                                                temp_clean += char
                                        temp = temp_clean if temp_clean else "N/A"
                                    elif "Battery:" in part:
                                        battery_str = part.split("Battery:")[1].strip()
                                        battery_parts = battery_str.split()
                                        battery = battery_parts[0] if battery_parts else "N/A"
                                    elif "WiFi:" in part:
                                        wifi_str = part.split("WiFi:")[1].strip()
                                        wifi_parts = wifi_str.split("/")
                                        try:
                                            wifi = int(wifi_parts[0])
                                        except:
                                            wifi = 0
                except Exception as e:
                    print(f"Error parsing log for {cam_name}: {e}")
                    pass

            camera_data.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "images": images,
                "temperature": temp,
                "battery": battery,
                "wifi": wifi,
                "timestamp": timestamp
            })

        return camera_data
    except Exception as e:
        print(f"Error reading camera data: {e}")
        return []


@app.route('/')
def index():
    """Main page with camera grid"""
    cameras = get_camera_data()
    config = get_config()
    location = config.get("location", {"city": "Bethel Park", "state": "PA"})
    return render_template('index.html', cameras=cameras, location=location)


@app.route('/api/cameras')
def api_cameras():
    """API endpoint for camera data"""
    cameras = get_camera_data()
    return jsonify(cameras)


@app.route('/api/location')
def api_location():
    """API endpoint for location data"""
    config = get_config()
    location = config.get("location", {"city": "Bethel Park", "state": "PA"})
    return jsonify(location)


@app.route('/image/<camera_name>/<image_name>')
def get_image(camera_name, image_name):
    """Serve camera images"""
    image_path = CAMERAS_DIR / camera_name / image_name
    if image_path.exists():
        return send_file(image_path, mimetype='image/jpeg')
    return "Image not found", 404


if __name__ == '__main__':
    print("=" * 60)
    print("🎥 Blink Camera Web Server")
    print("=" * 60)

    # Try to use Waitress if available
    try:
        from waitress import serve

        print("✅ Using Waitress production server")
        print("🌐 Server running at: http://localhost:5000")
        print("🌐 Network access: http://0.0.0.0:5000")
        print("=" * 60)
        print("Press Ctrl+C to stop the server")
        print("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=6, channel_timeout=120, backlog=128)
    except ImportError:
        print("⚠️  Waitress not found - using Flask development server")
        print("💡 For production use, install Waitress:")
        print("   pip install waitress")
        print("=" * 60)
        print("🌐 Server running at: http://localhost:5000")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=False)