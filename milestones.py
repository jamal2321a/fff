import os
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
import json
import discord
from discord import app_commands
from discord.ext import tasks

from helpers import (
    get_player_data,
    get_player_battlelog,
    get_club_members,
    custom_emoji,
    custom_emoji1,
    custom_emoji2,
    custom_emoji3,
    custom_emoji4,
    custom_emoji5
)

from info import Ranks2, Boxes

# Load configuration from data.json
def load_config():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raise ValueError("❌ Missing or invalid data.json file")

config = load_config()
DISCORD_TOKEN = config.get("token")
BRAWL_API_KEY = config.get("BrawlStarsAPITOKEN")
CLUB_TAG = config.get("Club")
CHANNEL_ID = 1444110135386705953
POLL_SECONDS = config.get("POLL_SECONDS", 180)
GLOBAL_TRACKING_CHANNEL_ID = config.get("GLOBAL_TRACKING_CHANNEL_ID", 1444110135386705953)

if not all([DISCORD_TOKEN, CLUB_TAG, CHANNEL_ID, BRAWL_API_KEY]):
    raise ValueError("❌ Missing required configuration in data.json file")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_FILE2 = "data2.json"

# ----------------- Utility ----------------- #
def load_data2():
    try:
        with open(DATA_FILE2, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"Ranked": {}, "Trophies": {}, "GlobalTrophyLeader": 0, "LastTrophyBox": {}}

def save_data2(data2):
    with open(DATA_FILE2, "w") as f:
        json.dump(data2, f, indent=4)

# ----------------- Global Trophy Leader ----------------- #
async def get_global_trophy_leader():
    BASE_URL = "https://api.brawlstars.com/v1/"
    headers = {"Authorization": f"Bearer {BRAWL_API_KEY}"}
    url = f"{BASE_URL}rankings/global/players"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(f"⚠️ Global API request failed: {resp.status}")
                return 0
            rankings_data = await resp.json()
            if not rankings_data.get("items"):
                return 0
            
            top_player_tag = rankings_data["items"][0].get("tag")
            if not top_player_tag:
                return 0
            
            player_data = await get_player_data(top_player_tag)
            return player_data.get("trophies", 0) if player_data else 0

# ----------------- Ranked Table ----------------- #
async def update_ranked_table(members):
    data2 = load_data2()
    ranked = data2.setdefault("Ranked", {})
    
    current_tags = {m.get("tag") for m in members if m.get("tag")}
    
    for tag in list(ranked.keys()):
        if tag not in current_tags:
            ranked.pop(tag, None)
    
    for m in members:
        tag = m.get("tag")
        name = m.get("name", "Unknown")
        if not tag:
            continue
        
        battle_log = await get_player_battlelog(tag)
        if not battle_log:
            continue
        
        trophies = None
        for entry in battle_log:
            battle = entry.get("battle")
            if not battle or battle.get("type") != "soloRanked":
                continue
            
            teams = battle.get("teams", [])
            if not teams:
                continue
            
            found_trophies = None
            for team in teams:
                for player in team:
                    if player.get("tag") == tag:
                        found_trophies = player.get("brawler", {}).get("trophies", 0)
                        break
                if found_trophies is not None:
                    break
            
            if found_trophies is not None:
                trophies = found_trophies
                break
        
        if trophies is None:
            continue
        
        old_rank = ranked.get(tag, 0)
        new_rank = trophies
        
        if new_rank > old_rank:
            rank_file_id = 58000000 + (new_rank - 1)
            thumbnailurl = f"https://cdn.brawlify.com/ranked/tiered/{rank_file_id}.png"
            
            icon_id = m.get("icon", {}).get("id", 0)
            icon_url = f"https://cdn.brawlify.com/profile-icons/regular/{icon_id}.png"
            
            rank_name = Ranks2.get(new_rank, f"Rank {new_rank}")
            
            embed = discord.Embed(
                title=f"{name} Ranked Up!",
                description=f"{name} ranked up to **{rank_name}**",
                color=discord.Color.gold()
            )
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=thumbnailurl)
            
            channel = client.get_channel(GLOBAL_TRACKING_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
        
        ranked[tag] = max(old_rank, new_rank)
    
    save_data2(data2)
    print("✅ Ranked table updated.")

# ----------------- Trophies Table + Box Milestones ----------------- #
async def update_trophies_table(members):
    data2 = load_data2()
    trophies_table = data2.setdefault("Trophies", {})
    last_box_table = data2.setdefault("LastTrophyBox", {})
    global_trophy_leader = data2.setdefault("GlobalTrophyLeader", 0)
    
    current_global_best = await get_global_trophy_leader()
    
    is_season_reset = False
    # Detect season reset
    if current_global_best and global_trophy_leader:
        if global_trophy_leader - current_global_best >= 5000:
            is_season_reset = True
            print(f"🚨 Season Reset Detected! Old Global #1: {global_trophy_leader}, New: {current_global_best}")
            trophies_table.clear()
            last_box_table.clear()
    
    if current_global_best > global_trophy_leader or is_season_reset:
        data2["GlobalTrophyLeader"] = current_global_best
        print(f"✅ Updating GlobalTrophyLeader to {current_global_best}")
    
    current_tags = {m.get("tag") for m in members if m.get("tag")}
    
    # Remove missing players from tables
    for tag in list(trophies_table.keys()):
        if tag not in current_tags:
            trophies_table.pop(tag, None)
            last_box_table.pop(tag, None)
    
    for m in members:
        tag = m.get("tag")
        name = m.get("name", "Unknown")
        if not tag:
            continue
        
        player_data = await get_player_data(tag)
        if not player_data:
            continue
        
        brawlers = player_data.get("brawlers", [])
        current_brawler_trophies = {b.get("name", "Unknown"): b.get("trophies", 0) for b in brawlers}
        previous_brawler_trophies = trophies_table.get(tag, {})
        
        new_brawler_trophies = {}
        extra_trophies_sum = 0
        
        for bname, trophies in current_brawler_trophies.items():
            prev_trophies = previous_brawler_trophies.get(bname, 0)
            
            if trophies >= 1000:
                extra_trophies_sum += trophies - 1000
                
                # Check for new tier max (only if not season reset)
                if not is_season_reset and prev_trophies < 1000:
                    profile_icon_id = player_data.get("icon", {}).get("id", 0)
                    profile_icon_url = f"https://cdn.brawlify.com/profile-icons/regular/{profile_icon_id}.png"
                    
                    # Find brawler ID for thumbnail
                    brawler_obj = next((b for b in brawlers if b.get("name") == bname), None)
                    brawler_id = brawler_obj.get("id", 0) if brawler_obj else 0
                    brawler_icon_url = f"https://cdn.brawlify.com/brawlers/emoji/{brawler_id}.png"
                    
                    embed = discord.Embed(
                        title=f"{name} Got A New tier max!",
                        description=f"{name} reached **{bname}** Tier Max!!",
                        color=discord.Color.blue()
                    )
                    embed.set_author(name=name, icon_url=profile_icon_url)
                    embed.set_thumbnail(url=brawler_icon_url)
                    
                    channel = client.get_channel(GLOBAL_TRACKING_CHANNEL_ID)
                    if channel:
                        await channel.send(embed=embed)
                        print(f"✅ Sent tier max notification for {name} - {bname}")
            
            if is_season_reset:
                new_brawler_trophies[bname] = trophies
            else:
                new_brawler_trophies[bname] = max(prev_trophies, trophies)
        
        trophies_table[tag] = new_brawler_trophies
        
        profile_icon_id = player_data.get("icon", {}).get("id", 0)
        profile_icon_url = f"https://cdn.brawlify.com/profile-icons/regular/{profile_icon_id}.png"
        
        last_box_amount = last_box_table.get(tag, 0)
        
        # Trophy Box milestone check
        for box in Boxes:
            if box["amount"] == 0:
                continue
            
            if extra_trophies_sum >= box["amount"] > last_box_amount:
                # Extract emoji ID from format <:name:id>
                emoji_str = box["emojiid"]
                emoji_id = emoji_str.split(":")[-1].rstrip(">")
                
                embed = discord.Embed(
                    title=f"{name} Reached a Trophy Box!",
                    description=f"{name} got a **{box['name']}**!",
                    color=discord.Color.purple()
                )
                embed.set_author(name=name, icon_url=profile_icon_url)
                embed.set_thumbnail(url=f"https://cdn.discordapp.com/emojis/{emoji_id}.png")
                
                channel = client.get_channel(GLOBAL_TRACKING_CHANNEL_ID)
                if channel:
                    await channel.send(embed=embed)
                
                last_box_table[tag] = box["amount"]
    
    save_data2(data2)
    
    if is_season_reset:
        print("✅ Season reset detected: trophies and LastTrophyBox tables cleared and saved.")
    else:
        print("✅ Trophies table updated with 1000+ brawler check and Trophy Box milestones.")

# ----------------- Club Polling ----------------- #
async def poll_for_changes():
    await client.wait_until_ready()
    print("🟢 Club tracking started.")
    
    while not client.is_closed():
        print("🔄 Checking club members...")
        members = await get_club_members()
        
        if not members:
            print("⚠️ Could not fetch club members.")
            await asyncio.sleep(POLL_SECONDS)
            continue
        
        await update_ranked_table(members)
        await update_trophies_table(members)
        
        await asyncio.sleep(POLL_SECONDS)

# ----------------- Bot Startup ----------------- #
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    asyncio.create_task(poll_for_changes())

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)