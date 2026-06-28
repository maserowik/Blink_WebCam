# Changelog

All notable changes to Blink WebCam Monitor are documented here.

---

## [1.1.0] - 2026-06-28

### Fixed

- **Startup failure after power outage** -- thin client boots faster than
  router, leaving no network when the camera service starts. Fixed by adding
  an `ExecStartPre` ping gate to `blink-webcam.service` that loops on
  `ping 8.8.8.8` every 5 seconds until internet is reachable before allowing
  the Python process to launch. Also added `StartLimitIntervalSec=0` to
  prevent systemd from giving up on repeated restart attempts.

- **Camera service dying on startup network error** -- `Blink_Web_Cam.py`
  would call `return` and exit permanently if `setup_post_verify()` failed
  on first connect. Replaced with a `while True` retry loop that waits
  30 seconds and retries until the Blink cloud is reachable.

- **Weather widget stuck on "Service unavailable" after power outage** --
  `weather.js` fetched weather once on page load with no retry. If the
  fetch failed at boot (no network yet), the widget stayed in error state
  permanently. Fixed by adding a retry loop that retries every 30 seconds
  up to 10 times on failure, and a 30-minute polling interval to keep
  weather data fresh once recovered.

### Changed

- `Autostart/blink-webcam.service` updated with ping gate and
  `StartLimitIntervalSec=0`
- `README.md` updated with power outage notes in Autostart section
  and new Troubleshooting entry

---

## [1.0.0] - Initial Release

- Initial release of Blink WebCam Monitor
- Sequential camera snapshot polling via blinkpy
- Flask/Waitress web dashboard with camera carousel
- Tomorrow.io weather widget
- RainViewer + Mapbox animated radar
- NWS severe weather alerts
- NHC hurricane alerts
- Per-camera alert snooze
- Arm/disarm Blink system from dashboard
- Automatic photo and log retention/cleanup
