import discord
from discord import app_commands
import json
import asyncio
import aiohttp
import os
import math
from datetime import datetime, timedelta, timezone
import aiohttp
import asyncio
import requests
from datetime import date
# NOTE: Assumed 'info.py' contains required variables like Boxes, Ranks, Brawlers, etc.
# These variables are crucial for the create_profile_embed function.
from info import Boxes, Ranks, brawlers_with_emojiid, records, Brawlers, upgrade_costs, COINS_PER_STARPOWER, COINS_PER_GADGET, fame 
# Import the tracking bot module
import milestones
# ----------------------------
# Load / Save JSON
# ----------------------------
def load_data():
    """Loads the bot configuration and cache data from data.json."""
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("data.json not found. Creating a default structure.")
        # Return a base structure if the file is missing to prevent crash on startup
        return {
            "token": "",
            "ClubStatChannel": "0",
            "Club": "",
            "UpdateTime": "180",
            "DailyUpdate": str(date.today()),
            "club_cache": {}
        }
    except json.JSONDecodeError:
        print("Error decoding data.json. Check file content.")
        return {}

def save_data(data):
    """Saves the bot configuration and cache data to data.json."""
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ----------------------------
# Config
# ----------------------------
TOKEN = data["token"]
CLUBSTATS_CHANNEL_ID = int(data["ClubStatChannel"])

# NEW CHANNEL ID FOR JOIN/LEAVE NOTIFICATIONS (Replace with your actual ID)
# NOTE: The provided ID '1434373001285210124' is used as an example, ensure it's correct.
JOIN_LEAVE_CHANNEL_ID = 1434373001285210124 
CLUB_TAG = data["Club"].replace("#", "").upper()
UPDATE_TIME = int(data.get("UpdateTime", 180))

# API URLs
ClubImageAPI = f"https://api.brawltools.net/clubs/{CLUB_TAG}/image?option=2&quality=high"
PlayerImageAPI = "https://api.brawltools.net/players/{tag}/image?option=8&quality=high"
PlayerAPI = "https://api.brawltools.net/players/"
ClubAPI = f"https://api.brawltools.net/clubs/{CLUB_TAG}"

# ----------------------------
# Discord client
# ----------------------------
intents = discord.Intents.default()
# Intents are required for member-related events, which is critical for club tracking
intents.members = True 
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Configuration Loading ---
# Load data.json to get the API Token
config_data = load_data()
BRAWL_API_TOKEN = config_data.get("BrawlStarsAPITOKEN")
GLOBAL_LEADERBOARD_CHANNEL_ID = 1435006603882659860
if not BRAWL_API_TOKEN:
    print("⚠️ 'BrawlStarsAPITOKEN' not found in data.json. Global summary will fail.")

# --- GLOBAL LEADERBOARD SUMMARY --- #

async def post_global_leaderboard_summary(client):
    """
    Fetches the lowest trophy amount for every Brawler 
    and posts a summary in a single unified style.
    """
    await client.wait_until_ready()
    print("🌍 Global leaderboard tracker started.")

    token = data.get("BrawlStarsAPITOKEN")
    if not token:
        print("⚠️ 'BrawlStarsAPITOKEN' not found in data.json.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    brawler_emoji_map = {b["name"]: f"<:b:{b['emojiid']}>" for b in brawlers_with_emojiid}

    while not client.is_closed():
        EST = timezone(timedelta(hours=-5))
        now = datetime.now(EST)
        today_str = now.strftime("%Y-%m-%d")

        if data.get("GlobalSentToday", {}).get("date") == today_str:
            await asyncio.sleep(600)
            continue

        print(f"🌍 Starting daily global fetch...")

        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.brawlstars.com/v1/brawlers", headers=headers) as resp:
                if resp.status != 200:
                    await asyncio.sleep(600)
                    continue
                api_brawlers = (await resp.json()).get("items", [])

            leaderboard_data = []
            for b in api_brawlers:
                bid = b.get("id")
                name = b.get("name", "").upper()
                url = f"https://api.brawlstars.com/v1/rankings/global/brawlers/{bid}"
                try:
                    async with session.get(url, headers=headers) as r:
                        if r.status == 200:
                            players = (await r.json()).get("items", [])
                            if players:
                                trophies = players[-1].get("trophies", 0)
                                leaderboard_data.append((name, trophies))
                except:
                    continue
                await asyncio.sleep(0.05)

        if leaderboard_data:
            leaderboard_data.sort(key=lambda x: x[1], reverse=True)

            # Reverting to your original formatting style
            formatted_lines = []
            for idx, (name, trophies) in enumerate(leaderboard_data, start=1):
                emoji = brawler_emoji_map.get(name, "")
                # Using the trophy emoji from your original script
                formatted_lines.append(f"{idx}. {emoji} {name} — <:tr:1449145784313581764>{trophies}")

            channel = client.get_channel(GLOBAL_LEADERBOARD_CHANNEL_ID)
            if channel:
                # Joining lines back into a single block
                full_text = "\n".join(formatted_lines)
                
                # Using your original 3900 character limit chunking
                # This keeps the sections much larger (usually only 2 blocks)
                def chunk_text(text, limit=3900):
                    chunks = []
                    current = ""
                    for line in text.splitlines():
                        if len(current) + len(line) + 1 > limit:
                            chunks.append(current)
                            current = line
                        else:
                            current += ("\n" if current else "") + line
                    if current: chunks.append(current)
                    return chunks

                chunks = chunk_text(full_text)
                day = now.strftime("%B %d, %Y")

                for i, chunk in enumerate(chunks):
                    embed = discord.Embed(
                        # Restoring the original Blue color and Title
                        title=f"🌍 Global Leaderboard Trophies Lows — {day}" if i == 0 else "",
                        description=chunk,
                        color=discord.Color.blue(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    await channel.send(embed=embed)
                
                data["GlobalSentToday"] = {"date": today_str}
                save_data(data)

        await asyncio.sleep(600)

# ----------------------------
# Player data fetch
# ----------------------------
def get_playerdata(tag):
    """Fetches full player profile data from the API."""
    tag = tag.replace("#", "").upper()
    url = PlayerAPI + tag
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        print(f"Error fetching player data for {tag}: {e}")
        return None

# ----------------------------
# Daily club image task
# ----------------------------
async def send_club_image_task():
    """Periodically sends a club image update to the designated channel."""
    await client.wait_until_ready()
    channel = client.get_channel(CLUBSTATS_CHANNEL_ID)
    if channel is None:
        print("Channel not found or bot has no access (CLUBSTATS_CHANNEL_ID)")
        return

    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            today_str = str(date.today())
            if data.get("DailyUpdate") != today_str:
                data["DailyUpdate"] = today_str
                save_data(data)

                try:
                    async with session.get(ClubImageAPI) as resp:
                        if resp.status != 200:
                            print(f"Failed to download image: {resp.status}")
                            await asyncio.sleep(UPDATE_TIME)
                            continue
                        image_data = await resp.read()

                    filename = "club_image.png"
                    with open(filename, "wb") as f:
                        f.write(image_data)

                    await channel.send(file=discord.File(filename))
                    os.remove(filename)
                except Exception as e:
                    print("Error sending club image:", e)

            await asyncio.sleep(UPDATE_TIME)

# ----------------------------
# Helpers
# ----------------------------
def get_player_box(amount):
    """Determines the trophy road box based on season trophies."""
    best_box = None
    for box in Boxes:
        if amount >= box["amount"]:
            best_box = box
    return best_box

def get_rank_by_id(rank_id):
    """Retrieves rank details based on rank ID."""
    for rank in Ranks:
        if rank["id"] == rank_id:
            return rank
    return None

def get_fame_tier(famepoints):
    """Calculates and formats the player's fame tier."""
    if famepoints == 0:
        return "? No Fame"

    temp_famepoints = famepoints
    for tier in fame:
        total_points_for_tier = tier["points_per_level"] * tier["levels"]
        if temp_famepoints < total_points_for_tier:
            level = (temp_famepoints // tier["points_per_level"]) + 1
            if level > tier["levels"]:
                level = tier["levels"]
            roman = ["I", "II", "III"][level - 1]
            return f"{tier['emojiid']} {tier['name']} {roman}"
        temp_famepoints -= total_points_for_tier

    # If beyond all tiers
    last_tier = fame[-1]
    return f"{last_tier['emojiid']} {last_tier['name']} III"

def calculate_costs(owned_brawlers):
    """Calculates the total coins and power points needed to max all 97 brawlers."""
    total_coins_needed = 0
    total_pp_needed = 0
    
    # Tracking progress for the embed
    total_starpowers_owned = 0
    total_gadgets_owned = 0
    owned_count = len(owned_brawlers)
    
    # 1. Calculate costs for brawlers the player HAS unlocked
    for b in owned_brawlers:
        current_power = b["power"]
        
        # Power Level Costs: Check every upgrade step
        for upgrade in upgrade_costs:
            # If current power is 1, it needs the upgrade where "from" is 1
            if current_power <= upgrade["from"]:
                total_coins_needed += upgrade["coins"]
                total_pp_needed += upgrade["power_points"]
        
        total_starpowers_owned += len(b.get("starPowers", []))
        total_gadgets_owned += len(b.get("gadgets", []))

    # 2. Calculate costs for brawlers NOT YET unlocked
    # These are assumed to be Level 1 with nothing.
    unowned_count = Brawlers - owned_count
    
    if unowned_count > 0:
        # Sum of a full Level 1 -> 11 journey
        full_upgrade_coins = sum(u["coins"] for u in upgrade_costs)
        full_upgrade_pp = sum(u["power_points"] for u in upgrade_costs)
        
        total_coins_needed += (full_upgrade_coins * unowned_count)
        total_pp_needed += (full_upgrade_pp * unowned_count)

    # 3. Calculate Star Power and Gadget costs for the WHOLE account
    # Every brawler (97) should have 2 SPs and 2 Gadgets.
    total_sp_possible = Brawlers * 2
    total_gadgets_possible = Brawlers * 2
    
    missing_sp = total_sp_possible - total_starpowers_owned
    missing_gadgets = total_gadgets_possible - total_gadgets_owned
    
    total_coins_needed += (missing_sp * COINS_PER_STARPOWER) 
    total_coins_needed += (missing_gadgets * COINS_PER_GADGET)
    
    return total_coins_needed, total_pp_needed, total_starpowers_owned, total_gadgets_owned


# Function to create the player profile embed (reused for join/leave)
def create_profile_embed(pdata: dict, player_tag: str, event_type: str = None):
    """
    Creates the Discord embed for a player profile.
    
    :param pdata: The player data dictionary (pdata["data"] for /profile, or the club member object for join/leave).
    :param player_tag: The player's tag (e.g., "#PQR234").
    :param event_type: "JOINED", "LEFT", or None for base /profile command.
    """
    
    if event_type is not None: 
        # Called from club_api_poll_task (Join/Leave). pdata is the club member object.
        # We need to fetch the full player data to get stats like 3v3 victories, etc.
        name = pdata["name"]
        
        # Fetch full player data for detailed stats
        tag_data = get_playerdata(player_tag)
        if not tag_data or not tag_data.get("data"):
            return discord.Embed(
                title=f"⚠️ {name} ({player_tag}) {event_type}", 
                description="Could not load full profile data for detailed stats.", 
                color=discord.Color.red() if event_type == "LEFT" else discord.Color.green()
            )
        
        # Overwrite pdata with the full nested data for stats calculation
        pdata = tag_data["data"]
        
    else:
        # Called from /profile. pdata is the nested 'data' object.
        name = pdata["name"]

    # --- Data Extraction & Calculation ---
    trophies = pdata["trophies"]
    fav_brawler = pdata["favouriteBrawler"]
    icon_id = pdata["icon"]["id"]
    famepoints = pdata.get("famePoints", 0)
    brawlers = pdata["brawlers"]
    
    total_coins_needed, total_pp_needed, total_starpowers, total_gadgets = calculate_costs(brawlers)

    count_1000_plus = sum(1 for b in brawlers if b["trophies"] >= 1000)
    count_p11 = sum(1 for b in brawlers if b["power"] >= 11)
    solo = pdata["soloVictories"]
    duo = pdata["duoVictories"]
    RankElo = pdata["rankedPoints"]
    RankNumber = pdata["ranked"]
    HighestRankElo = pdata["highestRankedPoints"]
    HighestRankNumber = pdata["highestRanked"]
    playtime = pdata["playedHours"]
    prestiges = pdata["prestige"]
    recordRank = pdata["recordRank"]
    recordPoints = pdata["recordPoints"]
    brawler_count = len(pdata["brawlers"])
    
    season_trophies = 0
    for b in pdata["brawlers"]:
        hst = b.get("highestSeasonTrophies", 0)
        if hst > 1000:
            season_trophies += (hst - 1000)

    rank = get_rank_by_id(RankNumber)
    highestrank = get_rank_by_id(HighestRankNumber)
    box = get_player_box(season_trophies)

    total_gears_owned = sum(len(b.get("gears", [])) for b in pdata["brawlers"])
    
    fame_display = get_fame_tier(famepoints)

    # Top brawler icon
    fav_brawler_icon = f"https://cdn.brawlify.com/brawlers/emoji/{fav_brawler}.png"
    profile_icon_url = f"https://cdn.brawlify.com/profile-icons/regular/{icon_id}.png"

    # --- EMBED Setup ---
    
    if event_type == "JOINED":
        author_name = f"✅ {name} JOINED the Club! ({player_tag})"
        color = discord.Color.green()
    elif event_type == "LEFT":
        author_name = f"❌ {name} LEFT the Club! ({player_tag})"
        color = discord.Color.red()
    else:
        author_name = f"{name}'s Profile ({player_tag})"
        color = discord.Color.green()


    embed = discord.Embed(
        color=color,
        description=(
            "\n\u200b\n"
            f"**TROPHIES**\n\n"
            f"<:tr:1449145784313581764> **Trophies:** {trophies}\n"
            f"<:51:1449145889179570349> **Tier Max's:** {count_1000_plus}\n"
            f"{box['emojiid']} **Season Trophies:** {season_trophies}\n"
            f"<:BS_Prestige2:1449167208789049384> **Prestiges:** {prestiges}\n\n"
            f"**PROGRESSION**\n\n"
            f"<:eyJwYXRoIjoic3VwZXJjZWxsXC9maWxl:1449146235616231454> **Brawlers:** {brawler_count}/{Brawlers}\n"
            f"<:p111:1449146020763140126> **Power 11's:** {count_p11}\n"
            f"<:gadgeet:1449185766876905675> **Gadgets:** {total_gadgets}/{Brawlers*2}\n"
            f"<:starpwer:1449185761030311997> **Starpowers:** {total_starpowers}/{Brawlers*2}\n"
            f"<:gear_base_empty:1449189230617301012> **Gears:** {total_gears_owned}/{Brawlers*6}\n\n"
            f"**INFO**\n\n"
            f"{records[recordRank]} **Record:** {recordPoints}\n"
            f"**{fame_display}**\n"
            f"<:pin_sandclock:1449164376987664454> **Playtime:** {playtime}h\n\n"
            f"**COST TO MAX**\n\n"
            f"<:icon_gold_coin:1449195153918005421> {total_coins_needed}\n"
            f"<:Power_Points:1449195161249779866> {total_pp_needed}\n\n"
            f"\u200b"
        )
    )

    embed.add_field(
        name="<:rd:1449159742155915304> **Rank:**",
        value=f"{rank['emojiid']} {RankElo}",
        inline=True
    )

    embed.add_field(
        name="<:rd:1449159742155915304> **Highest Rank:**",
        value=f"{highestrank['emojiid']} {HighestRankElo}",
        inline=True
    )

    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(
        name="<:3v3:1449146236690108538> **3v3 Victories:**",
        value=f"{pdata['3vs3Victories']}",
        inline=True
    )

    embed.add_field(
        name="<:image1:1449146237885485210> **Showdown Victories:**",
        value=f"{solo + duo}",
        inline=True
    )

    embed.set_author(name=author_name, icon_url=fav_brawler_icon)
    embed.set_thumbnail(url=profile_icon_url)
    
    return embed


# ----------------------------
# /profile command
# ----------------------------
@tree.command(name="profile", description="Get a Brawl Stars player image or embed")
@app_commands.describe(
    playertag="The player's tag (with or without #)",
    format="Type 'image' to get the full player card image"
)
async def profile(interaction: discord.Interaction, playertag: str, format: str = None):
    await interaction.response.defer()
    tag = playertag.replace("#", "").upper()

    # ---- IMAGE MODE ----
    if format and format.lower() == "image":
        api_url = PlayerImageAPI.format(tag=tag)
        filename = f"player_{tag}.png"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ API error: `{resp.status}`")
                        return
                    img = await resp.read()
            with open(filename, "wb") as f:
                f.write(img)
            await interaction.followup.send(file=discord.File(filename))
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return  # Stop here

    pdata = get_playerdata(tag)
    if not pdata or not pdata.get("data"):
        await interaction.followup.send("❌ Failed to load player data. Tag might be incorrect or API unavailable.")
        return

    embed = create_profile_embed(pdata["data"], player_tag=f"#{tag}")
    await interaction.followup.send(embed=embed)


@tree.command(
    name="megapig",
    description="Shows the current Mega Pig participation for all club members."
)
async def megapig(interaction: discord.Interaction):
    import math
    await interaction.response.defer()

    club_cache = data.get("club_cache")
    if not club_cache or not club_cache.get("data"):
        await interaction.followup.send("❌ Club data cache is empty or invalid.")
        return

    club_data = club_cache["data"]
    members_list = club_data.get("members", [])

    participating_members = []
    for member in members_list:
        mega = member.get("megaPig")
        if mega:
            participating_members.append({
                "name": member["name"],
                "wins": mega.get("wins", 0),
                "tickets_left": mega.get("ticketsLeft", 0)
            })

    if not participating_members:
        await interaction.followup.send("❌ No members have Mega Pig data yet.")
        return

    # Sort by wins (descending)
    participating_members.sort(key=lambda m: m["wins"], reverse=True)

    # 1. Determine the character count of the longest "Name + Rank"
    max_label_len = 0
    for i, m in enumerate(participating_members, start=1):
        label_text = f"#{i} {m['name']}"
        if len(label_text) > max_label_len:
            max_label_len = len(label_text)
    
    # 2. Set target position (longest name + 2 extra spaces)
    target_pos = max_label_len + 2

    leaderboard_lines = []
    for i, member in enumerate(participating_members, start=1):
        label_text = f"#{i} {member['name']}"
        
        # 3. Calculate how many "En Spaces" are needed
        # We use \u2002 because Discord won't shrink it like a normal space
        spaces_needed = target_pos - len(label_text)
        wide_spacing = "\u2002" * spaces_needed
        
        line = (
            f"{label_text}{wide_spacing}"
            f"<:tk:1454321218261090538> {member['tickets_left']}  "
            f"<:wn:1454321226066563208> {member['wins']}"
        )
        leaderboard_lines.append(line)

    # ---------- Embed Construction ----------
    embed = discord.Embed(
        title="<:mp:1454321208794288180> Mega Pig Participation",
        color=0xF5A623
    )

    chunk = ""
    chunks = []
    for line in leaderboard_lines:
        if len(chunk) + len(line) + 1 > 1024:
            chunks.append(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        chunks.append(chunk)

    total_wins = club_data.get("megaPig", {}).get("totalWins", 0)
    total_played = club_data.get("megaPig", {}).get("totalPlayed", 0)
    
    embed.add_field(name="<:wn:1454321226066563208> **Total Wins:**", value=total_wins, inline=True)
    embed.add_field(name="<:tk:1454321218261090538> **Total Played:**", value=total_played, inline=True)

    for idx, part in enumerate(chunks):
        field_name = "📊 Members" if idx == 0 else "\u200b"
        embed.add_field(name=field_name, value=part, inline=False)

    num = total_wins / 16
    stage = min(math.floor(num), 5)
    sd = stage * 4

    embed.add_field(name="<:mp:1454321208794288180> Stage:", value=f"{stage}/5", inline=True)
    embed.add_field(name="<:sd:1454330224316649705> Reward:", value=sd, inline=True)

    await interaction.followup.send(embed=embed)






# ----------------------------
# Club API polling task (RAW SAVE & JOIN/LEAVE TRACKING)
# ----------------------------
async def club_api_poll_task():
    """Periodically fetches club data and checks for join/leave events."""
    await client.wait_until_ready()
    
    join_leave_channel = client.get_channel(JOIN_LEAVE_CHANNEL_ID)
    if join_leave_channel is None:
        print("Channel not found or bot has no access (JOIN_LEAVE_CHANNEL_ID)")
        return

    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                async with session.get(ClubAPI) as resp:
                    if resp.status != 200:
                        print(f"[CLUB API] HTTP {resp.status}")
                        await asyncio.sleep(UPDATE_TIME)
                        continue

                    club_json = await resp.json()
                    new_members_list = club_json.get("data", {}).get("members", [])
                    new_member_tags = {member["tag"] for member in new_members_list}

                    # Get old member list from cache
                    old_club_cache = data.get("club_cache", {})
                    old_members_list = old_club_cache.get("data", {}).get("members", [])
                    old_member_tags = {member["tag"] for member in old_members_list}
                    
                    # Map tags to full member data for easy access
                    old_members_map = {member["tag"]: member for member in old_members_list}
                    new_members_map = {member["tag"]: member for member in new_members_list}

                    # Tracking Logic only runs if there was an old cache
                    if old_member_tags:
                        
                        # --- MEMBERS WHO JOINED ---
                        joined_tags = new_member_tags - old_member_tags
                        for tag in joined_tags:
                            member_data = new_members_map[tag]
                            # Fetch full player data and send JOINED embed
                            joined_embed = create_profile_embed(member_data, player_tag=tag, event_type="JOINED")
                            await join_leave_channel.send(embed=joined_embed)
                            print(f"[CLUB API] Detected JOIN: {member_data['name']} ({tag})")


                        # --- MEMBERS WHO LEFT ---
                        left_tags = old_member_tags - new_member_tags
                        for tag in left_tags:
                            member_data = old_members_map[tag] # Use old data to get name/tag
                            
                            # Send LEFT embed 
                            try:
                                left_embed = create_profile_embed(member_data, player_tag=tag, event_type="LEFT")
                                await join_leave_channel.send(embed=left_embed)

                            except Exception as e:
                                # Fallback if profile API fails for the left member
                                embed = discord.Embed(
                                    title=f"❌ {member_data.get('name', 'Unknown Player')} LEFT the Club!",
                                    description=f"Tag: `{tag}`\nClub Role: **{member_data.get('role', 'unknown').capitalize()}**\nTrophies: **{member_data.get('trophies', '?')}**",
                                    color=discord.Color.red()
                                )
                                await join_leave_channel.send(embed=embed)
                                print(f"[CLUB API] Error sending detailed LEFT notification for {tag}: {e}")

                            print(f"[CLUB API] Detected LEFT: {member_data.get('name', 'Unknown Player')} ({tag})")


                    # SAVE NEW CACHE (MUST BE DONE AFTER ALL CHECKS)
                    data["club_cache"] = club_json
                    save_data(data)

                    member_count = len(new_members_list)
                    print(f"[CLUB API] Cached RAW club data ({member_count} members). Join/Leave check complete.")

            except Exception as e:
                print("[CLUB API] Exception:", e)

            await asyncio.sleep(UPDATE_TIME)



# ----------------------------
# Events
# ----------------------------
@client.event
async def on_ready():
    """Event fired when the bot is ready and connected to Discord."""
    await tree.sync()
    print(f"Logged in as {client.user} (slash commands synced!)")

@client.event
async def setup_hook():
    """Sets up the asynchronous tasks when the bot starts."""
    client.loop.create_task(send_club_image_task())
    client.loop.create_task(club_api_poll_task())
    client.loop.create_task(post_global_leaderboard_summary(client))

# ----------------------------
# Run bot
# ----------------------------
if __name__ == "__main__":
    if TOKEN:
        # Run both bots concurrently
        loop = asyncio.get_event_loop()
        
        # Start the main bot (700 line script)
        loop.create_task(client.start(TOKEN))
        
        # Start the milestones tracking bot
        loop.create_task(milestones.client.start(milestones.DISCORD_TOKEN))
        
        # Keep the loop running
        loop.run_forever()
    else:
        print("Bot token is missing. Please check the 'token' field in data.json.")