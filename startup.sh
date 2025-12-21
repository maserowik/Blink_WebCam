#!/bin/bash
# ===============================================
# Blink Kiosk startup script: webcam + web server + Chrome kiosk
# ===============================================

# Start the webcam Python script
/home/beta-blink/Blink_WebCam/.blink/bin/python3 /home/beta-blink/Blink_WebCam/Blink_WebCam.py &

# Start the Flask web server
/home/beta-blink/Blink_WebCam/.blink/bin/python3 /home/beta-blink/Blink_WebCam/Blink_Web_Server.py &

# Give both scripts a few seconds to initialize
sleep 5

# Launch Chromium/Chrome in full-screen kiosk mode
# Ensure DISPLAY is set for the graphical session
export DISPLAY=:0
/usr/bin/google-chrome --kiosk http://wyse-beta-blink:5000 \
    --noerrdialogs --disable-infobars --disable-session-crashed-bubble &
