import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler

CONFIG_FILE = "blink_config.json"
TOKEN_FILE = "blink_token.json"


def get_input_with_default(prompt, default_value, value_type=str):
    """Get user input with existing value as default"""
    if default_value is not None:
        if value_type == bool:
            default_str = "Y" if default_value else "N"
            display_prompt = f"{prompt} [{default_str}]: "
        else:
            display_prompt = f"{prompt} [{default_value}]: "
    else:
        display_prompt = f"{prompt}: "

    user_input = input(display_prompt).strip()

    if not user_input and default_value is not None:
        return default_value

    if value_type == int:
        try:
            return int(user_input) if user_input else default_value
        except ValueError:
            print(f"\u26A0\uFE0F Invalid input, using default: {default_value}")
            return default_value
    elif value_type == bool:
        if user_input.upper() in ['Y', 'YES']:
            return True
        elif user_input.upper() in ['N', 'NO']:
            return False
        return default_value

    return user_input if user_input else default_value


async def setup_config():
    """Query Blink API for cameras and create configuration file"""

    # Load existing config if available
    existing_config = {}
    if Path(CONFIG_FILE).exists():
        print("=" * 60)
        print("\u25B6 Existing configuration found")
        print("  [V] View configuration")
        print("  [R] Re-run setup")
        choice = input("\nYour choice [V/R]: ").strip().upper()

        if choice == "V":
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                print("=" * 60)
                print("\u25B6 Configuration Summary")
                print("=" * 60)
                print("\u25B6 Cameras monitored:")
                for cam in config.get("cameras", []):
                    print(f"  \u2022 {cam}")
                poll_interval = config.get("poll_interval", 300)
                max_days = config.get("max_days", 7)
                max_images = int((max_days * 24 * 60) / (poll_interval // 60))
                print("\u23F1 Polling interval (seconds):", poll_interval)
                print("\u25A1 Max days:", max_days)
                print("\u25A1 Max images per camera (calculated):", max_images)
                print("\u25B6 Carousel images:", config.get("carousel_images", 5))
                loc = config.get("location", {})
                print("\u25A0 Location:", loc.get("display", "Unknown"))
                print("\u2600 Coordinates:", loc.get("lat", "N/A"), loc.get("lon", "N/A"))

                # Weather configuration
                weather = config.get("weather", {})
                print("\n\u25B6 WEATHER CONFIGURATION:")
                print(f"  Enabled: {weather.get('enabled', False)}")
                if weather.get('api_key'):
                    print(f"  Tomorrow.io API key: {weather['api_key'][:20]}...")

                radar = config.get("radar", {})
                print("\n\u25B6 RADAR CONFIGURATION:")
                print(f"  Enabled: {radar.get('enabled', False)}")
                print(f"  Animation frames: {radar.get('frames', 5)}")
                print(f"  Zoom level: {radar.get('zoom', 7)}")
                if radar.get('mapbox_token'):
                    print(f"  Mapbox token: {radar['mapbox_token'][:20]}...")

                print("=" * 60)
            except Exception as e:
                print("\u26A0\uFE0F Could not read configuration:", e)
            return
        elif choice == "R":
            print("\n\u25B6 Re-running setup...")
            print("\u25B6 Press Enter to keep existing values, or type new values\n")
            try:
                with open(CONFIG_FILE, "r") as f:
                    existing_config = json.load(f)
            except Exception as e:
                print("\u26A0\uFE0F Could not load existing config:", e)

    # Check Blink token
    if not Path(TOKEN_FILE).exists():
        print("\u274C Error: blink_token.json not found!")
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
                print("\u26A0\uFE0F No cameras found on your Blink account!")
                return

            print("=" * 60)
            print("\u2705 Found", len(camera_list), "camera(s):")
            print("=" * 60)
            for i, cam_name in enumerate(camera_list, 1):
                print(f"  {i}. {cam_name}")
            print("=" * 60)

            # --- Camera Selection ---
            print("\n\u25B6 Camera Selection")
            print("-" * 60)
            existing_cameras = existing_config.get("cameras", [])

            if existing_cameras:
                print("Current cameras monitored:")
                for cam in existing_cameras:
                    print(f"  \u2022 {cam}")
                print("\nChange camera selection?")
                print("  [N] No - keep current cameras (default)")
                print("  [A] All cameras")
                print("  [C] Choose specific cameras")
                choice = input("\nYour choice [N/A/C]: ").strip().upper()
            else:
                print("Select cameras to monitor:")
                print("  [A] All cameras (default)")
                print("  [C] Choose specific cameras")
                choice = input("\nYour choice [A/C]: ").strip().upper()

            selected_cameras = existing_cameras

            if choice == "C":
                print("\nEnter camera numbers to monitor (comma-separated), e.g., 1,3,4")
                selection = input("Camera numbers: ").strip()
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    selected_cameras = [camera_list[i] for i in indices if 0 <= i < len(camera_list)]
                except:
                    print("Invalid selection, using existing cameras...")
                    selected_cameras = existing_cameras if existing_cameras else camera_list
            elif choice == "A":
                selected_cameras = camera_list
            elif not choice and not existing_cameras:
                selected_cameras = camera_list

            print("\n\u2705 Selected Cameras:")
            for cam in selected_cameras:
                print(f"  \u2022 {cam}")

            # --- Location ---
            print("\n\u25A0 Location Settings")
            print("-" * 60)
            existing_loc = existing_config.get("location", {})

            city = get_input_with_default("City", existing_loc.get("city"))
            while not city:
                print("\u274C City cannot be empty!")
                city = input("City: ").strip()

            state = get_input_with_default("State (2-letter code, e.g., PA)", existing_loc.get("state"))
            while not state or len(state) != 2:
                print("\u274C Please enter a valid 2-letter state code!")
                state = input("State (2-letter code): ").strip().upper()

            location = f"{city}, {state}"
            print(f"\n\u2705 Location set to: {location}")

            # --- Geocode for coordinates ---
            location_changed = (city != existing_loc.get("city") or
                                state != existing_loc.get("state"))

            if location_changed or not existing_loc.get("lat"):
                print("\nLooking up coordinates...")
                geocode_url = f"https://nominatim.openstreetmap.org/search?city={city}&state={state}&country=USA&format=json"
                async with session.get(geocode_url, headers={"User-Agent": "BlinkRadar/1.0"}) as resp:
                    data = await resp.json()

                if not data:
                    print("\u26A0\uFE0F Could not determine GPS coordinates, using defaults")
                    lat, lon = 40.3267, -80.0171
                else:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    print(f"\u25B6 Coordinates found: LAT = {lat}, LON = {lon}")
            else:
                lat = existing_loc.get("lat", 40.3267)
                lon = existing_loc.get("lon", -80.0171)
                print(f"\u25B6 Using existing coordinates: LAT = {lat}, LON = {lon}")

            # --- Polling Interval ---
            print("\n\u25B6 Polling Interval")
            print("-" * 60)
            existing_poll = existing_config.get("poll_interval", 300) // 60
            print("How often should snapshots be taken?")
            print("  [1] Every 1 minute")
            print("  [5] Every 5 minutes (default)")
            print("  [10] Every 10 minutes")
            print("  [15] Every 15 minutes")
            print("  [30] Every 30 minutes")
            print("  [60] Every 60 minutes")
            poll_minutes = get_input_with_default("\nMinutes", existing_poll, int)
            poll_interval = poll_minutes * 60

            # --- Image Storage ---
            print("\n\u25B6 Image Storage")
            print("-" * 60)
            existing_days = existing_config.get("max_days", 7)
            print("How many days of images should be saved?")
            print("  1  = 1 day")
            print("  7  = 7 days (default)")
            print(" 14  = 14 days")
            print(" 30  = 30 days")
            max_days = get_input_with_default("\nDays", existing_days, int)
            max_images = int((max_days * 24 * 60) / poll_minutes)
            print("Estimated images per camera:", max_images)

            # --- Carousel ---
            print("\n\u25B6 Carousel Display")
            print("-" * 60)
            existing_carousel = existing_config.get("carousel_images", 5)
            print("How many recent images to show in the web carousel?")
            print("  3 images ")
            print("  5 images (default)")
            print(" 10 images ")
            carousel_images = get_input_with_default("\nCarousel images", existing_carousel, int)
            if carousel_images < 1:
                carousel_images = 1
            elif carousel_images > 20:
                carousel_images = 20
                print("\u26A0\uFE0F Limited to maximum of 20 images")

            # --- Tomorrow.io Weather API Configuration ---
            print("\n\u25B6 Tomorrow.io Weather API Configuration")
            print("-" * 60)
            existing_weather = existing_config.get("weather", {})

            print("Tomorrow.io provides accurate weather data for your location")
            print("Get your free API key at: https://www.tomorrow.io/weather-api/")
            print("Free tier: 500 calls/day (plenty for weather updates)")

            weather_config = {
                "enabled": True,
                "api_key": existing_weather.get("api_key", "")
            }

            weather_api_key = get_input_with_default("\nEnter Tomorrow.io API key",
                                                     weather_config["api_key"] if weather_config["api_key"] else None)
            while not weather_api_key:
                print("\u26A0\uFE0F Tomorrow.io API key is required for weather functionality")
                print("Get a free key at: https://www.tomorrow.io/weather-api/")
                weather_api_key = input("Enter Tomorrow.io API key: ").strip()

            weather_config["api_key"] = weather_api_key
            print("\u2705 Weather API configured successfully!")

            # --- Radar Configuration ---
            print("\n\u25B6 Weather Radar Configuration")
            print("-" * 60)
            existing_radar = existing_config.get("radar", {})

            print("Animated weather radar (uses RainViewer API)")
            print("Requires FREE Mapbox API key for base map")
            print("Get your free API key at: https://account.mapbox.com/")

            radar_config = {
                "enabled": True,
                "zoom": existing_radar.get("zoom", 7),
                "frames": existing_radar.get("frames", 5),
                "color": existing_radar.get("color", 2),
                "smooth": existing_radar.get("smooth", 1),
                "snow": existing_radar.get("snow", 1),
                "mapbox_token": existing_radar.get("mapbox_token", ""),
                "basemap_style": existing_radar.get("basemap_style", ""),
                "overlay_style": existing_radar.get("overlay_style", "")
            }

            mapbox_token = get_input_with_default("\nEnter Mapbox API token",
                                                  radar_config["mapbox_token"] if radar_config[
                                                      "mapbox_token"] else None)
            while not mapbox_token:
                print("\u26A0\uFE0F Mapbox API token is required for radar functionality")
                print("Get a free token at: https://account.mapbox.com/")
                mapbox_token = input("Enter Mapbox API token: ").strip()

            radar_config["mapbox_token"] = mapbox_token

            print("\n\u25B6 Radar Zoom Level")
            print("  4  = Continental view")
            print("  7  = Regional view (default)")
            print(" 10  = Local view")
            radar_config["zoom"] = get_input_with_default("\nZoom level", radar_config["zoom"], int)

            print("\n\u25B6 Animation Frames")
            print("Number of time steps to show (more = longer animation)")
            print("  3 frames = 30 minutes of history")
            print("  5 frames = 50 minutes of history (default)")
            print("  8 frames = 80 minutes of history")
            radar_config["frames"] = get_input_with_default("\nFrames", radar_config["frames"], int)

            # --- Custom Mapbox Styles (Advanced/Optional) ---
            print("\n\u25B6 Custom Mapbox Styles (Advanced - Optional)")
            print("-" * 60)
            print("Most users can skip this - default styles work great!")
            print("\nOnly customize if you want a different map appearance.")
            print("Examples: 'mapbox/dark-v11', 'mapbox/streets-v12', or your custom style")

            use_custom = input("\nUse custom Mapbox styles? [y/N]: ").strip().upper()

            if use_custom == 'Y':
                print("\nEnter style IDs (leave blank to use defaults):")
                basemap = get_input_with_default("  Base map style ID",
                                                 radar_config["basemap_style"] if radar_config[
                                                     "basemap_style"] else None)
                if basemap:
                    radar_config["basemap_style"] = basemap

                overlay = get_input_with_default("  Overlay style ID",
                                                 radar_config["overlay_style"] if radar_config[
                                                     "overlay_style"] else None)
                if overlay:
                    radar_config["overlay_style"] = overlay

                print("\u2705 Custom styles configured")
            else:
                print("\u2705 Using default Mapbox styles (recommended)")

            print("\n\u2705 Radar configured successfully!")

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
                    "lon": lon
                },
                "weather": weather_config,
                "radar": radar_config
            }

            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            print("\n" + "=" * 60)
            print("\u2705 Configuration saved to blink_config.json")
            print("=" * 60)
            print("\nConfiguration Summary:")
            print(f"  Cameras: {len(selected_cameras)}")
            print(f"  Poll interval: {poll_minutes} minutes")
            print(f"  Image retention: {max_days} days")
            print(f"  Carousel images: {carousel_images}")
            print(f"  Weather API: Tomorrow.io \u2713")
            print(f"  Radar enabled: {radar_config['enabled']}")
            if radar_config['enabled']:
                print(f"    Zoom: {radar_config['zoom']}")
                print(f"    Frames: {radar_config['frames']}")
                print(f"    Data source: RainViewer API")
                print(f"    Base map: Mapbox")
            print("=" * 60)

        except Exception as e:
            print("\u274C Error during Blink setup:", e)
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("\u25B6 Blink Camera Configuration Setup")
    print("=" * 60)
    asyncio.run(setup_config())