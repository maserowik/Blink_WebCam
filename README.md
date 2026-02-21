# Blink WebCam Monitor

A self-hosted, real-time camera surveillance dashboard for Blink cameras. Automatically takes snapshots on a configurable schedule and displays them in a web browser with weather, radar, NWS weather alerts, and NHC hurricane alerts.

![Dashboard](https://img.shields.io/badge/status-stable-brightgreen)

---

## Table of Contents

1. [What This Does](#what-this-does)
2. [Hardware Requirements](#hardware-requirements)
3. [Software Requirements](#software-requirements)
4. [System Preparation](#system-preparation)
5. [Python Environment Setup](#python-environment-setup)
6. [Installing Dependencies](#installing-dependencies)
7. [Blink Authentication](#blink-authentication)
8. [Configuration](#configuration)
9. [Running Manually](#running-manually)
10. [Autostart on Boot](#autostart-on-boot)
11. [API Keys](#api-keys)
12. [File Structure](#file-structure)
13. [Restarting the Services](#restarting-the-services)
14. [Troubleshooting](#troubleshooting)

---

## What This Does

- Connects to your Blink camera account and takes snapshots from all configured cameras on a schedule (default every 5 minutes)
- Stores photos organized by camera and date
- Serves a local web dashboard showing live camera images, temperature, battery, and WiFi signal for each camera
- Displays current weather conditions via Tomorrow.io API
- Shows animated weather radar via RainViewer + Mapbox
- Shows National Weather Service (NWS) severe weather alerts for your area
- Shows National Hurricane Center (NHC) Atlantic hurricane alerts
- Supports arm/disarm of your Blink system from the dashboard
- Supports per-camera alert snoozing
- Automatically cleans up old photos and logs based on configurable retention settings
- Designed to run 24/7 on a dedicated thin client or low-power PC with a display

---

## Hardware Requirements

- Any Linux PC or thin client (tested on a Dell Wyse thin client)
- At least 2GB RAM
- At least 8GB storage (more if using long photo retention)
- A display connected to the machine (for the kiosk browser)
- Network connection (wired recommended for stability)
- One or more Blink cameras already set up and working in the official Blink app

---

## Software Requirements

- Ubuntu 22.04 or 24.04 (or compatible Debian-based Linux)
- Python 3.10 or higher
- Google Chrome browser
- Git

---

## System Preparation

### Step 1 — Update your system

Open a terminal and run:

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 2 — Install required system packages

```bash
sudo apt install -y python3 python3-pip python3-venv git curl wget unclutter
```

- `python3-venv` — creates isolated Python environments
- `unclutter` — hides the mouse cursor in kiosk mode
- `git` — for cloning the repository

### Step 3 — Install Google Chrome

Chrome is not in the default Ubuntu repositories. Install it manually:

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
```

Verify Chrome installed correctly:

```bash
google-chrome --version
```

You should see something like `Google Chrome 120.0.0.0`.

---

## Python Environment Setup

### Step 4 — Clone the repository

Navigate to your home directory and clone the project:

```bash
cd ~
git clone https://github.com/maserowik/Blink_WebCam.git
cd Blink_WebCam
```

### Step 5 — Create a Python virtual environment

This keeps all project dependencies isolated from your system Python:

```bash
python3 -m venv .blink
```

This creates a hidden folder called `.blink` inside the project directory.

### Step 6 — Activate the virtual environment

```bash
source .blink/bin/activate
```

Your terminal prompt will change to show `(.blink)` at the start. You must always activate the virtual environment before running any project commands.

---

## Installing Dependencies

### Step 7 — Install Python packages

With the virtual environment active, install all required packages:

```bash
pip install -r requirements.txt
```

This installs:
- `blinkpy` — communicates with the Blink API
- `Flask` — the web server
- `waitress` — production-grade WSGI server for Flask
- `requests` — HTTP requests for weather and alert APIs
- `pillow` — image processing and validation
- `python-dateutil` — date handling utilities

---

## Blink Authentication

You need to authenticate with your Blink account once to generate a token file. This token is saved locally and reused automatically — you will not need to log in again unless the token expires.

### Step 8 — Run the authentication script

With the virtual environment active:

```bash
python3 blink_token.py
```

You will be prompted for:
- Your Blink account email address
- Your Blink account password
- A two-factor authentication (2FA) code sent to your email or phone

After successful authentication, a file called `blink_token.json` will be created in the project directory. This file contains your access credentials — **do not share it or commit it to version control** (it is already in `.gitignore`).

The script will also list all cameras found on your account, for example:

```
✔ Found sync module: My Home
  📷 Front Door
  📷 Back Door
  📷 Garage Door
```

---

## Configuration

### Step 9 — Run the configuration setup script

```bash
python3 blink_config_setup.py
```

This interactive script will guide you through all settings. If a `blink_config.json` already exists it will show your current settings and let you keep or change each one.

You will be asked for:

**Cameras**
Select which cameras from your account to monitor. You can monitor all of them or choose specific ones.

**Location**
Enter your city and 2-letter state code (e.g. `Pittsburgh` and `PA`). The script will automatically look up your GPS coordinates for weather and radar.

**Polling Interval**
How often snapshots are taken. Options are 1, 5, 10, 15, 30, or 60 minutes. The default is 5 minutes.

**Image Retention**
How many days of photos to keep per camera. The default is 7 days. Older photos are automatically deleted.

**Carousel Images**
How many recent images to show in the web dashboard carousel per camera. Default is 5.

**Tomorrow.io Weather API Key**
Required for weather display. See [API Keys](#api-keys) below for instructions on getting a free key.

**Mapbox API Token**
Required for the animated radar map. See [API Keys](#api-keys) below for instructions.

**NWS Alerts Zone**
Optional. The National Weather Service forecast zone for your area (e.g. `PAZ021` for Pittsburgh). Find yours at https://www.weather.gov/ — enter your location and look for the zone code on your forecast page.

**NHC Hurricane Alerts**
Optional. Monitors the National Hurricane Center for active Atlantic basin hurricanes. Checks at 5 AM, 11 AM, 5 PM, and 11 PM daily.

After completing setup, a `blink_config.json` file is saved in the project directory.

---

## Running Manually

You can run the two components manually to test everything is working before setting up autostart.

### Step 10 — Activate the virtual environment (if not already active)

```bash
cd ~/Blink_WebCam
source .blink/bin/activate
```

### Step 11 — Start the camera service

This service polls your Blink cameras on the configured schedule and saves snapshots:

```bash
python3 Blink_WebCam.py &
```

The `&` runs it in the background. You should see log output beginning with:

```
BLINK WEBCAM SCRIPT STARTED (SEQUENTIAL PROCESSING)
```

### Step 12 — Wait a few seconds then start the web server

```bash
sleep 5
python3 Blink_Web_Server.py &
```

### Step 13 — Open the dashboard in Chrome

```bash
DISPLAY=:0 google-chrome --kiosk \
  --start-fullscreen \
  --window-position=0,0 \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --noerrdialogs \
  --disk-cache-dir=/tmp/chrome-cache \
  --aggressive-cache-discard \
  --incognito \
  http://localhost:5000 > /dev/null 2>&1 &
```

The dashboard should appear on screen within a few seconds. If you are on a different machine on the same network, you can also open it in any browser at:

```
http://<IP-OF-YOUR-MACHINE>:5000
```

To find your machine's IP address:

```bash
hostname -I
```

---

## Autostart on Boot

There are two autostart methods included. Choose one.

### Option A — systemd services (recommended for headless or server use)

Two service files are included in the `Autostart/` folder.

Copy them to the systemd directory:

```bash
sudo cp Autostart/blink-webcam.service /etc/systemd/system/
sudo cp Autostart/blink-webserver.service /etc/systemd/system/
```

Reload systemd and enable the services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable blink-webcam.service
sudo systemctl enable blink-webserver.service
sudo systemctl start blink-webcam.service
sudo systemctl start blink-webserver.service
```

Check that both are running:

```bash
sudo systemctl status blink-webcam.service blink-webserver.service
```

Both should show `Active: active (running)`.

**Note:** The systemd services do not launch Chrome. Use this option if you want the Python services to autostart and access the dashboard from another device on your network.

---

### Option B — startup.sh (recommended for kiosk/display use)

The `startup.sh` script starts both Python services AND launches Chrome in kiosk mode. This is designed for a dedicated thin client with a display.

Make the script executable:

```bash
chmod +x ~/Blink_WebCam/startup.sh
```

To run it automatically on login, add it to your desktop autostart. For LXDE/LXQt (common on thin clients):

```bash
mkdir -p ~/.config/autostart
```

Create a file called `~/.config/autostart/blink-webcam.desktop` with the following contents:

```ini
[Desktop Entry]
Type=Application
Name=Blink WebCam
Exec=bash /home/YOUR-USERNAME/Blink_WebCam/startup.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

Replace `YOUR-USERNAME` with your actual Linux username.

Alternatively, add it to crontab to run on reboot:

```bash
crontab -e
```

Add this line at the bottom:

```
@reboot bash /home/YOUR-USERNAME/Blink_WebCam/startup.sh
```

The startup script accepts optional arguments:
- `--no-delay` or `-n` — skip the 60-second boot wait
- `--delay 30` or `-d 30` — use a custom delay in seconds
- `--message-delay 30` or `-m 30` — show a dialog countdown before starting

---

## API Keys

### Tomorrow.io (Weather)

1. Go to https://www.tomorrow.io/weather-api/
2. Click **Get Free API Key** and create an account
3. After logging in, your API key is shown on the dashboard
4. The free tier allows 500 calls per day which is more than enough

### Mapbox (Radar Map Base Layer)

1. Go to https://account.mapbox.com/
2. Create a free account
3. After logging in, your default public token is shown on the Tokens page
4. Copy the token — it starts with `pk.`
5. The free tier is generous and sufficient for personal use

### NWS Zone (Weather Alerts)

No API key required. You just need your forecast zone code.

1. Go to https://www.weather.gov/
2. Enter your city/zip in the forecast search
3. On your local forecast page, look at the URL — it will contain your zone (e.g. `PAZ021`)
4. Alternatively, go to https://alerts.weather.gov/ and browse to find your zone

---

## File Structure

```
Blink_WebCam/
├── Blink_WebCam.py          # Main camera polling service
├── Blink_Web_Server.py      # Flask web server
├── blink_token.py           # One-time Blink authentication
├── blink_config_setup.py    # Interactive configuration wizard
├── camera_processor.py      # Snapshot capture and image handling
├── camera_organizer.py      # Photo storage and cleanup
├── alert_snooze.py          # Per-camera alert snooze management
├── blink_utils.py           # Shared utility functions
├── log_rotation.py          # Log file management
├── nws_alerts.py            # NWS weather alert polling
├── nhc_alerts.py            # NHC hurricane alert polling
├── requirements.txt         # Python dependencies
├── startup.sh               # Full kiosk startup script
├── clear_chrome_cache.sh    # Utility to clear Chrome cache
├── Autostart/
│   ├── blink-webcam.service     # systemd service for camera poller
│   ├── blink-webserver.service  # systemd service for web server
│   └── startup.sh               # Copy of startup script
├── templates/
│   └── index.html           # Dashboard HTML template
├── static/
│   ├── css/
│   │   └── style.css        # Dashboard stylesheet
│   └── js/
│       ├── main.js          # Core app logic, theme, arm toggle
│       ├── camera.js        # Camera carousel management
│       ├── camera-refresh.js # Background camera data refresh
│       ├── weather.js       # Weather widget
│       ├── radar.js         # Animated radar widget
│       ├── nws-alerts.js    # NWS alert widget
│       ├── nhc-alerts.js    # NHC hurricane alert widget
│       └── snooze.js        # Alert snooze functionality
├── cameras/                 # Auto-created — stores camera photos
│   └── {camera-name}/
│       └── YYYY-MM-DD/
│           └── photo.jpg
├── logs/                    # Auto-created — stores log files
│   ├── system/
│   │   ├── main/
│   │   ├── token/
│   │   ├── performance/
│   │   ├── webserver/
│   │   └── nws-alerts/
│   └── cameras/
│       └── {camera-name}/
├── blink_token.json         # Auto-created — Blink credentials (keep private)
├── blink_config.json        # Auto-created — your configuration
└── alert_snooze.json        # Auto-created — snooze state
```

---

## Restarting the Services

If you need to restart the Python services (for example after making code changes) without rebooting:

```bash
pkill -f Blink_WebCam.py
pkill -f Blink_Web_Server.py

cd ~/Blink_WebCam
source .blink/bin/activate
python3 Blink_WebCam.py &
sleep 5
python3 Blink_Web_Server.py &
```

To refresh Chrome without rebooting, first install xdotool:

```bash
sudo apt install xdotool -y
```

Then send F5 to the Chrome window:

```bash
DISPLAY=:0 xdotool key F5
```

---

## Troubleshooting

### The dashboard shows no images

- Check that `Blink_WebCam.py` is running: `pgrep -f Blink_WebCam.py`
- Check the main log for errors: `tail -f logs/system/main/main_$(date +%Y-%m-%d).log`
- Verify your token is still valid by running `python3 blink_token.py` again

### The web page won't load

- Check that `Blink_Web_Server.py` is running: `pgrep -f Blink_Web_Server.py`
- Make sure port 5000 is not blocked by a firewall
- Try accessing it directly: `curl http://localhost:5000`

### Weather is not showing

- Verify your Tomorrow.io API key is correct in `blink_config.json`
- Check you have not exceeded the 500 calls/day free tier limit
- Check the webserver log: `tail -f logs/system/webserver/webserver_$(date +%Y-%m-%d).log`

### Radar is not showing

- Verify your Mapbox token is correct in `blink_config.json`
- Make sure the token starts with `pk.`
- Open the browser developer console (F12) and look for errors

### NWS alerts are never showing

- Verify your zone code is correct (e.g. `PAZ021`)
- Test it manually: `curl "https://api.weather.gov/alerts/active?zone=PAZ021"`
- If the response has `features: []` there are simply no active alerts for your zone

### Chrome won't start in kiosk mode

- Make sure `DISPLAY=:0` is set
- Verify Chrome is installed: `google-chrome --version`
- Check if another Chrome instance is already running: `pgrep -f chrome`
- If so, kill it first: `pkill -f chrome`

### Blink token expired

Re-run the authentication script:

```bash
cd ~/Blink_WebCam
source .blink/bin/activate
python3 blink_token.py
```

Then restart the camera service:

```bash
pkill -f Blink_WebCam.py
python3 Blink_WebCam.py &
```

### Disk space filling up

Reduce `max_days` in your config by re-running `python3 blink_config_setup.py`. You can also manually trigger a cleanup:

```bash
python3 camera_organizer.py --cleanup
```

---

## Notes

- All photo data and logs stay entirely on your local machine — nothing is uploaded anywhere except the API calls to Blink, Tomorrow.io, and the public NWS/NHC/RainViewer APIs
- The `blink_token.json` and `blink_config.json` files are excluded from version control via `.gitignore` — never commit them
- The camera service and web server are two separate processes intentionally — the camera poller runs independently of whether anyone is viewing the dashboard
