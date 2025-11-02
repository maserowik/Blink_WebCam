import asyncio
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from datetime import datetime
import json

# Config
TOKEN_FILE = "blink_token.json"
POLL_INTERVAL = 300  # 5 minutes in seconds


def wifi_bars(dbm):
    """Convert WiFi dBm to 0–5 bars"""
    if dbm is None:
        return 0
    elif dbm >= -50:
        return 5
    elif dbm >= -60:
        return 4
    elif dbm >= -70:
        return 3
    elif dbm >= -80:
        return 2
    elif dbm >= -90:
        return 1
    else:
        return 0


async def countdown(seconds):
    """Live countdown in console"""
    for remaining in range(seconds, 0, -1):
        print(f"\rWaiting {remaining} seconds for next snapshot...", end="")
        await asyncio.sleep(1)
    print("\rStarting next snapshot...               ")


async def poll_blink():
    # Load token
    with open(TOKEN_FILE, "r") as f:
        token = json.load(f)

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(token, session=session)

        urls = token.get("urls", {})
        blink.urls = urls
        blink.base_url = urls.get("base_url")
        blink.media_url = urls.get("media_url")

        # Start Blink and fetch initial data
        await blink.start()
        await blink.refresh()

        while True:
            # Refresh Blink data and token if needed
            await blink.refresh()
            await blink.save(TOKEN_FILE)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n==============================")
            print(f"📅 Snapshot at: {timestamp}")
            print("==============================\n")

            for name, cam in blink.cameras.items():
                bars = wifi_bars(cam.wifi_strength)
                print(f"--- {name} ---")
                print(f"Temperature: {cam.temperature}°F")
                print(f"Battery: {cam.battery}")
                print(f"WiFi: {bars}/5")
                print("----------------------")

            # Countdown until next snapshot
            await countdown(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(poll_blink())
