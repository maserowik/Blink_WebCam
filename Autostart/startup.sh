#!/bin/bash
# Startup script for Blink WebCam
# Designed to run on Wyse Thin Client with Google Chrome
# Can be started from autostart or crontab:
# @reboot bash /home/beta-blink/Blink_WebCam/startup.sh

# Change to script directory
cd "$HOME"/Blink_WebCam || exit

# Set display if not set
if [ "$DISPLAY" = "" ]; then
  export DISPLAY=:0
fi

# Wait for system to fully boot
MSG="echo Waiting 60 seconds before starting"
DELAY="sleep 60"
if [ "$1" = "-n" ] || [ "$1" = "--no-delay" ]; then
  echo "Skipping delay"
  MSG=""
  DELAY=""
  shift
fi
if [ "$1" = "-d" ] || [ "$1" = "--delay" ]; then
  MSG="echo Waiting $2 seconds before starting"
  DELAY="sleep $2"
  shift
  shift
fi
if [ "$1" = "-m" ] || [ "$1" = "--message-delay" ]; then
  MSG="echo Waiting $2 seconds for response"
  DELAY='zenity --question --title "Blink WebCam" --ok-label=Now --cancel-label=Cancel --timeout '$2' --text "Starting Blink WebCam in '$2' seconds" >/dev/null 2>&1'
  shift
  shift
fi

$MSG
eval "$DELAY"
if [ $? -eq 1 ]; then
  echo "Blink WebCam Cancelled"
  exit 0
fi

# Show startup message (if zenity available)
which zenity >/dev/null 2>&1
if [ $? -eq 0 ]; then
  zenity --info --timeout 3 --text "Starting Blink WebCam..." >/dev/null 2>&1 &
fi

# Disable screen blanking
echo "Disabling screen blanking..."
xset s off
xset -dpms
xset s noblank

# Hide mouse cursor
pgrep unclutter >/dev/null 2>&1
if [ $? -eq 1 ]; then
  which unclutter >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    unclutter >/dev/null 2>&1 &
  fi
fi

# Virtual environment
echo "Activating virtual environment..."
if [ -d ".blink" ]; then
  source .blink/bin/activate || exit
elif [ -d "venv" ]; then
  source venv/bin/activate || exit
else
  echo "Virtual environment not found!"
  exit 1
fi

# Start Camera Service
echo "Checking for Blink Camera service..."
pgrep -f Blink_WebCam.py >/dev/null
if [ $? -eq 1 ]; then
  echo "Starting Blink Camera Service..."
  python3 Blink_WebCam.py &
else
  echo "Blink Camera Service already running"
fi

# Wait for camera service to initialize
sleep 5

# Start Web Server
echo "Checking for Blink Web Server..."
pgrep -f Blink_Web_Server.py >/dev/null
if [ $? -eq 1 ]; then
  echo "Starting Blink Web Server..."
  python3 Blink_Web_Server.py &
else
  echo "Blink Web Server already running"
fi

# Wait for web server to be ready
echo "Waiting for web server to be ready..."
sleep 10

# Open Google Chrome browser in kiosk mode
echo "Checking for Google Chrome browser..."
if command -v google-chrome &> /dev/null; then
  echo "Opening Google Chrome in kiosk mode..."
  google-chrome --kiosk \
    --start-fullscreen \
    --window-position=0,0 \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --noerrdialogs \
    --disable-suggestions-service \
    --disable-translate \
    --disable-save-password-bubble \
    --disable-features=TranslateUI \
    --disk-cache-dir=/tmp \
    --aggressive-cache-discard \
    http://localhost:5000 &
elif command -v google-chrome-stable &> /dev/null; then
  echo "Opening Google Chrome (stable) in kiosk mode..."
  google-chrome-stable --kiosk \
    --start-fullscreen \
    --window-position=0,0 \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --noerrdialogs \
    --disable-suggestions-service \
    --disable-translate \
    --disable-save-password-bubble \
    --disable-features=TranslateUI \
    --disk-cache-dir=/tmp \
    --aggressive-cache-discard \
    http://localhost:5000 &
else
  echo "ERROR: Google Chrome not found!"
  echo "Please install Google Chrome"
  exit 1
fi

echo ""
echo "Blink WebCam startup complete!"
echo "Access from other devices: http://192.168.55.40:5000"
echo ""
