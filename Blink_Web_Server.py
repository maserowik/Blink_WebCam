from flask import Flask, render_template, send_file, jsonify
from pathlib import Path
import json
from datetime import datetime

app = Flask(__name__)

# Configuration
CONFIG_FILE = "blink_token.json"
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


def get_camera_data():
    """Read camera configuration and latest data"""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        cameras = config.get("cameras", [])
        camera_data = []

        for cam_name in cameras:
            normalized_name = normalize_camera_name(cam_name)
            cam_folder = CAMERAS_DIR / normalized_name
            log_file = LOG_FOLDER / f"{normalized_name}.log"

            # Get latest image
            latest_image = None
            if cam_folder.exists():
                images = sorted(cam_folder.glob("*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)
                if images:
                    latest_image = images[0].name

            # Get latest log entry
            temp = "N/A"
            battery = "N/A"
            wifi = 0
            timestamp = "N/A"

            if log_file.exists():
                try:
                    with open(log_file, "r") as f:
                        lines = f.readlines()
                        if lines:
                            last_line = lines[-1]
                            parts = last_line.split(" | ")
                            if len(parts) >= 4:
                                timestamp = parts[0]
                                for part in parts:
                                    if "Temp:" in part:
                                        temp = part.split("Temp:")[1].strip().split()[0]
                                    elif "Battery:" in part:
                                        battery = part.split("Battery:")[1].strip().split()[0]
                                    elif "WiFi:" in part:
                                        wifi = part.split("WiFi:")[1].strip().split("/")[0]
                except:
                    pass

            camera_data.append({
                "name": cam_name,
                "normalized_name": normalized_name,
                "image": latest_image,
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
    return render_template('index.html', cameras=cameras)


@app.route('/api/cameras')
def api_cameras():
    """API endpoint for camera data"""
    cameras = get_camera_data()
    return jsonify(cameras)


@app.route('/image/<camera_name>/<image_name>')
def get_image(camera_name, image_name):
    """Serve camera images"""
    image_path = CAMERAS_DIR / camera_name / image_name
    if image_path.exists():
        return send_file(image_path, mimetype='image/jpeg')
    return "Image not found", 404


if __name__ == '__main__':
    print("Starting Blink Camera Web Server...")
    print("Open your browser to: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)