import json
import aiohttp

# ------------------ Load config from data.json ------------------ #

with open("data.json", "r") as f:
    config = json.load(f)

BRAWL_API_KEY = config.get("BrawlStarsAPITOKEN")
CLUB_TAG = config.get("Club")

if not BRAWL_API_KEY:
    raise ValueError("❌ Missing BrawlStarsAPITOKEN in data.json")
if not CLUB_TAG:
    raise ValueError("❌ Missing Club tag in data.json")

# Ensure club tag starts with #
if not CLUB_TAG.startswith("#"):
    CLUB_TAG = f"#{CLUB_TAG}"

# ------------------ Custom Emojis ------------------ #
# These must exist in your Discord server

custom_emoji = "<:51:1434593365642580111>"   # Tier Max's
custom_emoji1 = "<:tr:1434600700226048092>"  # Trophies
custom_emoji2 = "<:p11:1434611956211257466>" # Power 11's
custom_emoji3 = "<:3v3:1434627404273549342>" # 3v3 Wins
custom_emoji4 = "<:sd:1434627372065489018>"  # Showdown Wins
custom_emoji5 = "<:pl:1434701133980631060>"  # Power League

# ------------------ API Base ------------------ #

BASE_URL = "https://api.brawlstars.com/v1/"

async def fetch_api(path: str):
    """
    Fetches data from Brawl Stars API.
    Returns dict on success, None on failure.
    """
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {BRAWL_API_KEY}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"⚠️ API request failed: {resp.status} {text}")
                    return None
                return await resp.json()
    except Exception as e:
        print(f"⚠️ API request exception: {e}")
        return None

# ------------------ Player Helpers ------------------ #

async def get_player_data(player_tag: str):
    """
    Returns player data dict, or None if failed.
    """
    if not player_tag:
        return None
    tag = player_tag.replace("#", "%23")
    return await fetch_api(f"players/{tag}")

async def get_player_battlelog(player_tag: str):
    """
    Returns list of battle log entries, empty list if failed.
    """
    if not player_tag:
        return []
    tag = player_tag.replace("#", "%23")
    data = await fetch_api(f"players/{tag}/battlelog")
    if not data:
        return []
    return data.get("items", [])

# ------------------ Club Helpers ------------------ #

async def get_club_members():
    """
    Returns list of club members dicts, empty list if failed.
    """
    if not CLUB_TAG:
        print("⚠️ Club tag missing in data.json")
        return []

    tag = CLUB_TAG.replace("#", "%23")
    data = await fetch_api(f"clubs/{tag}/members")
    if not data:
        print("⚠️ Failed to fetch club members")
        return []

    members = data.get("items", [])
    if not isinstance(members, list):
        return []

    return members
