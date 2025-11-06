import asyncio
import json
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError


def get_user_input():
    """Prompt user for camera names."""
    # Get camera names
    cameras = []
    print("\nEnter camera names (type 'done' when finished):")
    while True:
        camera_name = input("Camera name: ").strip()
        if camera_name.lower() == 'done':
            break
        if camera_name:
            cameras.append(camera_name)

    return cameras


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

    # Save the credentials
    token_file = "blink_token.json"

    # Get user input for cameras
    cameras = get_user_input()

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

    # Display available cameras
    if cameras:
        print(f"\n✓ Found {len(cameras)} camera(s):")
        for name in cameras:
            print(f"  - {name}")
    else:
        print("\n⚠ No cameras found on your account")

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
    finally:
        # Ensure the session is closed in case of an error
        if session and isinstance(session, ClientSession) and not session.closed:
            asyncio.run(session.close())
