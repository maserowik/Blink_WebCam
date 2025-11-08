import asyncio
import json
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError


async def start():
    """Setup Blink authentication and save credentials"""
    # Create a session
    session = ClientSession()
    # Initialize Blink with the session
    blink = Blink(session=session)

    try:
        # Start will prompt for username and password
        await blink.start()
    except BlinkTwoFARequiredError:
        # If 2FA is required, prompt for it
        await blink.prompt_2fa()

    print("\n🔍 Discovering cameras...")

    # Refresh to get camera data
    await blink.refresh()

    # Get all cameras from all sync modules
    cameras = []
    camera_info = {}

    for sync_name, sync_module in blink.sync.items():
        print(f"\n✓ Found sync module: {sync_name}")
        for camera_name, camera in sync_module.cameras.items():
            cameras.append(camera_name)
            camera_info[camera_name] = {
                "sync_module": sync_name,
                "camera_id": getattr(camera, 'camera_id', None),
                "name": camera.name,
                "armed": getattr(camera, 'arm', None),
                "motion_enabled": getattr(camera, 'motion_enabled', None),
                "battery": getattr(camera, 'battery', None),
                "temperature": getattr(camera, 'temperature', None)
            }
            print(f"  📹 {camera_name}")
            print(f"     - Armed: {getattr(camera, 'arm', 'Unknown')}")
            print(f"     - Motion detection: {getattr(camera, 'motion_enabled', 'Unknown')}")
            if hasattr(camera, 'battery'):
                print(f"     - Battery: {camera.battery}")

    # Save the credentials
    token_file = "blink_token.json"

    # Prepare data to save
    data = {
        "device_id": "Blinkpy",
        "token": blink.auth.token,
        "refresh_token": blink.auth.refresh_token,
        "host": blink.urls.base_url,
        "client_id": blink.client_id,
        "account_id": blink.account_id,
        "user_id": blink.user_id,
        "cameras": cameras,
        "camera_info": camera_info,
        "urls": {
            "base_url": "https://rest.prod.immedia-semi.com",
            "media_url": "https://rest-prod.immedia-semi.com"
        }
    }

    # Save data to JSON file
    with open(token_file, "w") as f:
        json.dump(data, f, indent=4)

    print(f"\n✓ Credentials saved to {token_file}")
    print(f"✓ Setup complete!")

    # Display summary
    if cameras:
        print(f"\n✓ Successfully configured {len(cameras)} camera(s)")
    else:
        print("\n⚠ No cameras found on your account")
        print("   Make sure your cameras are set up in the Blink app first")

    # Close the session
    await session.close()
    return session


if __name__ == "__main__":
    session = None
    try:
        session = asyncio.run(start())
        print("\n✓ Authentication successful!")
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Ensure the session is closed in case of an error
        if session and isinstance(session, ClientSession) and not session.closed:
            asyncio.run(session.close())