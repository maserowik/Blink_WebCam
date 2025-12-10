import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler

CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"


async def get_radar_station_from_api(lat, lon, session):
    """Get radar station from Weather.gov API"""
    try:
        url = f"https://api.weather.gov/points/{lat},{lon}"
        headers = {"User-Agent": "BlinkRadar/1.0"}
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['properties']['radarStation']
            else:
                print("⚠️ Weather.gov API returned status", resp.status)
                return "KPBZ"
    except Exception as e:
        print("⚠️ Could not determine radar station:", e)
        return "KPBZ"


async def setup_config():
    """Query Blink API for cameras and create configuration file"""

    # Check if config exists
    if Path(CONFIG_FILE).exists():
        print("=" * 60)
        print("▶ Existing configuration found")
        print("  [V] View configuration")
        print("  [R] Re-run setup")
        choice = input("\nYour choice [V/R]: ").strip().upper()

        if choice == "V":
            # Load and print summary
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                print("=" * 60)
                print("▶ Configuration Summary")
                print("=" * 60)
                print("▶ Cameras monitored:")
                for cam in config.get("cameras", []):
                    print(f"  • {cam}")
                poll_interval = config.get("poll_interval", 300)
                max_days = config.get("max_days", 7)
                max_images = int((max_days * 24 * 60) / (poll_interval // 60))
                print("⏱ Polling interval (seconds):", poll_interval)
                print("□ Max days:", max_days)
                print("□ Max images per camera (calculated):", max_images)
                print("▶ Carousel images:", config.get("carousel_images", 5))
                loc = config.get("location", {})
                print("■ Location:", loc.get("display", "Unknown"))
                print("☀ Coordinates:", loc.get("lat", "N/A"), loc.get("lon", "N/A"))
                print("▶ Radar Station:", loc.get("radar_station", "KPBZ"))

                # Radar configuration
                radar = config.get("radar", {})
                print("\n▶ RADAR CONFIGURATION:")
                print(f"  Enabled: {radar.get('enabled', False)}")
                print(f"  Animation frames: {radar.get('frames', 5)}")
                print(f"  Zoom level: {radar.get('zoom', 7)}")
                if radar.get('mapbox_token'):
                    print(f"  Mapbox token: {radar['mapbox_token'][:20]}...")

                print("=" * 60)
            except Exception as e:
                print("⚠️ Could not read configuration:", e)
            return
        elif choice == "R":
            print("\n▶ Re-running setup...\n")

    # Check Blink token
    if not Path(TOKEN_FILE).exists():
        print("❌ Error: blink_token.json not found!")
        print("Please run 'python blink_token.py' first to authenticate.")
        return

    print("Loading authentication token...")
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    print("Connecting to Blink API...\n")

    async with ClientSession() as session:
        blink = Blink(session=session)

        host_url = token_data.get("host", "")
        region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")

        blink.auth = Auth({}, session=session, no_prompt=True)
        blink.auth.region_id = region_id
        blink.auth.host = host_url
        blink.auth.token = token_data.get("token")
        blink.auth.refresh_token = token_data.get("refresh_token")
        blink.auth.client_id = token_data.get("client_id")
        blink.auth.account_id = token_data.get("account_id")
        blink.auth.user_id = token_data.get("user_id")
        blink.urls = BlinkURLHandler(region_id)

        try:
            await blink.setup_post_verify()

            camera_list = list(blink.cameras.keys())
            if not camera_list:
                print("⚠️ No cameras found on your Blink account!")
                return

            print("=" * 60)
            print("✅ Found", len(camera_list), "camera(s):")
            print("=" * 60)
            for i, cam_name in enumerate(camera_list, 1):
                print(f"  {i}. {cam_name}")
            print("=" * 60)

            # --- Camera Selection ---
            print("\n▶ Camera Selection")
            print("-" * 60)
            print("Select cameras to monitor:")
            print("  [A] All cameras (default)")
            print("  [C] Choose specific cameras")
            choice = input("\nYour choice [A/C]: ").strip().upper()
            selected_cameras = []
            if choice == "C":
                print("\nEnter camera numbers to monitor (comma-separated), e.g., 1,3,4")
                selection = input("Camera numbers: ").strip()
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    selected_cameras = [camera_list[i] for i in indices if 0 <= i < len(camera_list)]
                except:
                    print("Invalid selection, using all cameras...")
                    selected_cameras = camera_list
            else:
                selected_cameras = camera_list

            print("\n✅ Selected Cameras:")
            for cam in selected_cameras:
                print(f"  • {cam}")

            # --- Location ---
            print("\n■ Location Settings")
            print("-" * 60)
            city = input("City: ").strip()
            while not city:
                print("❌ City cannot be empty!")
                city = input("City: ").strip()

            state = input("State (2-letter code, e.g., PA): ").strip().upper()
            while not state or len(state) != 2:
                print("❌ Please enter a valid 2-letter state code!")
                state = input("State (2-letter code, e.g., PA): ").strip().upper()

            location = f"{city}, {state}"
            print(f"\n✅ Location set to: {location}")

            # --- Geocode and radar ---
            print("\nLooking up coordinates for radar map...")
            geocode_url = f"https://nominatim.openstreetmap.org/search?city={city}&state={state}&country=USA&format=json"
            async with session.get(geocode_url, headers={"User-Agent": "BlinkRadar/1.0"}) as resp:
                data = await resp.json()

            if not data:
                print("⚠️ Could not determine GPS coordinates, using defaults")
                lat, lon = 40.3267, -80.0171
                radar_station = "KPBZ"
            else:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                print(f"▶ Coordinates found: LAT = {lat}, LON = {lon}")

                # Get radar station from Weather.gov API
                print("Looking up nearest radar station...")
                radar_station = await get_radar_station_from_api(lat, lon, session)
                print(f"▶ Radar station selected: {radar_station}")

            # --- Polling Interval ---
            print("\n▶ Polling Interval")
            print("-" * 60)
            print("How often should snapshots be taken?")
            print("  [1] Every 1 minute")
            print("  [5] Every 5 minutes (default)")
            print("  [10] Every 10 minutes")
            print("  [15] Every 15 minutes")
            print("  [30] Every 30 minutes")
            print("  [60] Every 60 minutes")
            poll_input = input("\nMinutes [5]: ").strip()
            poll_minutes = int(poll_input) if poll_input else 5
            poll_interval = poll_minutes * 60

            # --- Image Storage ---
            print("\n▶ Image Storage")
            print("-" * 60)
            print("How many days of images should be saved?")
            print("  1  = 1 day")
            print("  7  = 7 days (default)")
            print(" 14  = 14 days")
            print(" 30  = 30 days")
            days_input = input("\nDays [7]: ").strip()
            max_days = int(days_input) if days_input else 7
            max_images = int((max_days * 24 * 60) / poll_minutes)
            print("Estimated images per camera:", max_images)

            # --- Carousel ---
            print("\n▶ Carousel Display")
            print("-" * 60)
            print("How many recent images to show in the web carousel?")
            print("  3 images ")
            print("  5 images (default)")
            print(" 10 images ")
            carousel_input = input("\nCarousel images [5]: ").strip()
            carousel_images = int(carousel_input) if carousel_input else 5
            if carousel_images < 1:
                carousel_images = 1
            elif carousel_images > 20:
                carousel_images = 20
                print("⚠️ Limited to maximum of 20 images")

            # --- Radar Configuration (automatically enabled) ---
            print("\n▶ Weather Radar Configuration")
            print("-" * 60)
            print("Animated weather radar will be enabled ")
            print("You need a FREE Mapbox API key to use radar")
            print("Get your free API key at: https://account.mapbox.com/")
            print("Sign up and create an access token with default scopes")

            radar_config = {
                "enabled": True,  # Always enabled now
                "zoom": 7,
                "frames": 5,
                "color": 2,
                "smooth": 1,
                "snow": 1,
                "mapbox_token": "",
                "basemap_style": "",
                "overlay_style": ""
            }

            mapbox_token = input("\nEnter Mapbox API token (required): ").strip()
            while not mapbox_token:
                print("⚠️ Mapbox API token is required for radar functionality")
                print("Get a free token at: https://account.mapbox.com/")
                mapbox_token = input("Enter Mapbox API token: ").strip()

            radar_config["mapbox_token"] = mapbox_token

            print("\n▶ Radar Zoom Level")
            print("  4  = Continental view")
            print("  7  = Regional view (default)")
            print(" 10  = Local view")
            zoom_input = input("\nZoom level [7]: ").strip()
            radar_config["zoom"] = int(zoom_input) if zoom_input else 7

            print("\n▶ Animation Frames")
            print("Number of time steps to show (more = longer animation)")
            print("  3 frames = 30 minutes of history")
            print("  5 frames = 50 minutes of history (default)")
            print("  8 frames = 80 minutes of history")
            frames_input = input("\nFrames [5]: ").strip()
            radar_config["frames"] = int(frames_input) if frames_input else 5

            print("\n▶ Custom Mapbox Styles (optional)")
            print("Leave blank to use default styles")
            print("Example: 'username/style-id' or 'mapbox/dark-v11'")

            basemap = input("\nBase map style (dark map, no labels) [blank for default]: ").strip()
            if basemap:
                radar_config["basemap_style"] = basemap

            overlay = input("Overlay style (transparent, labels only) [blank for default]: ").strip()
            if overlay:
                radar_config["overlay_style"] = overlay

            print("\n✅ Radar configured successfully!")

            # --- Save Config ---
            config = {
                "cameras": selected_cameras,
                "poll_interval": poll_interval,
                "max_days": max_days,
                "carousel_images": carousel_images,
                "location": {
                    "city": city,
                    "state": state,
                    "display": location,
                    "lat": lat,
                    "lon": lon,
                    "radar_station": radar_station
                },
                "radar": radar_config
            }

            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            print("\n" + "=" * 60)
            print("✅ Configuration saved to blink_config.json")
            print("=" * 60)
            print("\nConfiguration Summary:")
            print(f"  Cameras: {len(selected_cameras)}")
            print(f"  Poll interval: {poll_minutes} minutes")
            print(f"  Image retention: {max_days} days")
            print(f"  Carousel images: {carousel_images}")
            print(f"  Radar enabled: {radar_config['enabled']}")
            print(f"    Zoom: {radar_config['zoom']}")
            print(f"    Frames: {radar_config['frames']}")
            print("=" * 60)

        except Exception as e:
            print("❌ Error during Blink setup:", e)
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("▶ Blink Camera Configuration Setup")
    print("=" * 60)
    asyncio.run(setup_config())