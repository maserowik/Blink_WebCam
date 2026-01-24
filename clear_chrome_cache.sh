#!/bin/bash
# clear_chrome_cache.sh - Manually clear Chrome cache and restart browser
# Usage: bash clear_chrome_cache.sh

echo "=============================================="
echo "Chrome Cache Cleaner for Blink WebCam"
echo "=============================================="
echo ""

# Set display
export DISPLAY=:0

# Kill Chrome
echo "1. Stopping Chrome..."
pkill -9 chrome
pkill -9 chromium
sleep 2

# Clear cache directories
echo "2. Clearing cache directories..."

CHROME_CACHE="$HOME/.cache/google-chrome"
if [ -d "$CHROME_CACHE" ]; then
  echo "   - Removing: $CHROME_CACHE"
  rm -rf "$CHROME_CACHE"
fi

CHROME_PROFILE="$HOME/.config/google-chrome/Default"
if [ -d "$CHROME_PROFILE" ]; then
  echo "   - Clearing profile cache..."
  rm -rf "$CHROME_PROFILE/Cache" 2>/dev/null
  rm -rf "$CHROME_PROFILE/Code Cache" 2>/dev/null
  rm -rf "$CHROME_PROFILE/GPUCache" 2>/dev/null
  rm -rf "$CHROME_PROFILE/Service Worker" 2>/dev/null
  rm -rf "$CHROME_PROFILE/Application Cache" 2>/dev/null
fi

sleep 2

# Restart Chrome
echo "3. Restarting Chrome in kiosk mode..."
if command -v google-chrome &> /dev/null; then
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
    --disk-cache-dir=/dev/null \
    --disk-cache-size=1 \
    --media-cache-size=1 \
    --aggressive-cache-discard \
    --disable-cache \
    --disable-application-cache \
    --disable-offline-load-stale-cache \
    --disable-gpu-shader-disk-cache \
    --incognito \
    http://localhost:5000 &
elif command -v google-chrome-stable &> /dev/null; then
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
    --disk-cache-dir=/dev/null \
    --disk-cache-size=1 \
    --media-cache-size=1 \
    --aggressive-cache-discard \
    --disable-cache \
    --disable-application-cache \
    --disable-offline-load-stale-cache \
    --disable-gpu-shader-disk-cache \
    --incognito \
    http://localhost:5000 &
else
  echo "ERROR: Chrome not found!"
  exit 1
fi

sleep 3

echo ""
echo "=============================================="
echo "✓ Chrome cache cleared and restarted!"
echo "=============================================="
echo ""