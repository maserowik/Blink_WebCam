import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.helpers.util import BlinkURLHandler


async def setup_config():
    """Query Blink API for cameras and create configuration file"""

    TOKEN_FILE = "blink_token.json"
    CONFIG_FILE = "blink_config.json"

    # Check if token file exists
    if not Path(TOKEN_FILE).exists():
        print("❌ Error: blink_token.json not found!")
        print("Please run 'python blink_token.py' first to authenticate.")
        return

    # Load token
    print("Loading authentication token...")
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)

    print("Connecting to Blink API...\n")

    async with ClientSession() as session:
        blink = Blink(session=session)

        # Extract region
        host_url = token_data.get("host", "")
        region_id = host_url.replace("https://rest-", "").replace(".immedia-semi.com", "")

        # Setup authentication
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

            # Get list of cameras from API
            camera_list = list(blink.cameras.keys())

            if not camera_list:
                print("⚠️  No cameras found on your Blink account!")
                return

            print("=" * 60)
            print(f"✅ Found {len(camera_list)} camera(s):")
            print("=" * 60)
            for i, cam_name in enumerate(camera_list, 1):
                print(f"  {i}. {cam_name}")
            print("=" * 60)

            # Ask user which cameras to monitor
            print("\n📹 Camera Selection")
            print("-" * 60)
            print("Select cameras to monitor:")
            print("  [A] All cameras (default)")
            print("  [C] Choose specific cameras")

            choice = input("\nYour choice [A/C]: ").strip().upper()

            selected_cameras = []
            if choice == "C":
                print("\nEnter camera numbers to monitor (comma-separated)")
                print(f"Example: 1,3,4")
                selection = input("Camera numbers: ").strip()

                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    selected_cameras = [camera_list[i] for i in indices if 0 <= i < len(camera_list)]
                except:
                    print("Invalid selection, using all cameras...")
                    selected_cameras = camera_list
            else:
                selected_cameras = camera_list

            print(f"\n✅ Selected {len(selected_cameras)} camera(s):")
            for cam in selected_cameras:
                print(f"  • {cam}")

            # Get user location
            print("\n📍 Location Settings")
            print("-" * 60)
            print("Enter your location for weather display:")

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

            # 🔥 ADDITION: Geo-coordinate lookup (only modification)
            print("\n🌐 Looking up coordinates for radar map...")

            geocode_url = (
                f"https://nominatim.openstreetmap.org/search?"
                f"city={city}&state={state}&country=USA&format=json"
            )

            async with session.get(geocode_url, headers={"User-Agent": "BlinkRadar/1.0"}) as resp:
                data = await resp.json()

            if not data:
                print("⚠️ Could not determine GPS coordinates, using 0,0")
                lat, lon = 0.0, 0.0
            else:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                print(f"📍 Coordinates found → LAT: {lat}, LON: {lon}")

            # Get polling interval
            print("\n⏱️  Polling Interval")
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

            # Get max images per camera
            print("\n💾 Image Storage")
            print("-" * 60)
            print("Maximum images to keep per camera:")
            print(f"  At {poll_minutes} min intervals:")
            print(f"    • 1440 images = 1 day")
            print(f"    • 10080 images = 1 week (default)")
            print(f"    • 43200 images = 1 month")

            max_input = input("\nMax images [10080]: ").strip()
            max_images = int(max_input) if max_input else 10080

            # Calculate storage estimate
            days = (max_images * poll_minutes) / (60 * 24)
            print(f"\n📊 This will store approximately {days:.1f} days of history per camera")

            # Get carousel images setting
            print("\n🎠 Carousel Display")
            print("-" * 60)
            print("How many recent images to show in the web carousel?")
            print("  • 3 images = Minimal")
            print("  • 5 images = Default (recommended)")
            print("  • 10 images = Maximum")

            carousel_input = input("\nCarousel images [5]: ").strip()
            carousel_images = int(carousel_input) if carousel_input else 5

            if carousel_images < 1:
                carousel_images = 1
            elif carousel_images > 20:
                carousel_images = 20
                print(f"⚠️  Limited to maximum of 20 images")

            # Create configuration (updated only here)
            config = {
                "cameras": selected_cameras,
                "poll_interval": poll_interval,
                "max_images": max_images,
                "carousel_images": carousel_images,
                "location": {
                    "city": city,
                    "state": state,
                    "display": location,
                    "lat": lat,
                    "lon": lon
                }
            }

            # Save configuration
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            print("\n" + "=" * 60)
            print("✅ Configuration saved to blink_config.json")
            print("=" * 60)
            print(f"📹 Monitoring {len(selected_cameras)} camera(s)")
            print(f"📍 Location: {location}")
            print(f"🌐 Coordinates: {lat}, {lon}")
            print(f"⏱️  Snapshot interval: {poll_minutes} minutes")
            print(f"💾 Max images per camera: {max_images}")
            print(f"🎠 Carousel images: {carousel_images}")
            print("=" * 60)
            print("\n🚀 Ready to start! Run: python Blink_WebCam.py")

        except Exception as e:
            print(f"\n❌ Error connecting to Blink API: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("🎥 Blink Camera Configuration Setup")
    print("=" * 60)
    asyncio.run(setup_config())
