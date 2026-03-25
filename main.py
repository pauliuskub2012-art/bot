import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- DATABASE ---
user_stats = {} # {uid: {stats, xp, bp_level, premium}}
server_settings = {} # {gid: {roles, shop: {role_id: price}, bp: {tier: reward}}}
league_storage = {}
league_links = {}

def get_stats(uid):
    if uid not in user_stats:
        user_stats[uid] = {
            'mmr': 1000, 'points': 0, 'coins': 100, 'xp': 0, 
            'bp_level': 1, 'premium': False, 'streak': 0, 'freeze': False
        }
    return user_stats[uid]

# --- BATTLEPASS LOGIC ---
def add_xp(uid, amount):
    s = get_stats(uid)
    s['xp'] += amount
    # Kas 100 XP - naujas lygis
    new_level = (s['xp'] // 100) + 1
    if new_level > s['bp_level']:
        s['bp_level'] = new_level
        return True
    return False

# --- SHOP & BATTLEPASS VIEWS ---
class ShopRoleView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Buy Role", style=discord.ButtonStyle.success, emoji="🏷️")
    async def buy_role(self, inter: discord.Interaction, button: discord.ui.Button):
        # Šis mygtukas atidaro sąrašą rolių, kurias nustatė adminas
        settings = server_settings.get(self.guild_id, {}).get('shop', {})
        if not settings: return await inter.response.send_message("Shop is empty!", ephemeral=True)
        
        options = []
        for r_id, price in settings.items():
            role = inter.guild.get_role(int(r_id))
            if role: options.append(discord.SelectOption(label=role.name, value=str(r_id), description=f"Price: {price} coins"))

        class RoleSelect(discord.ui.Select):
            def __init__(self, guild_id, shop_data):
                super().__init__(placeholder="Choose a role to buy...", options=options)
                self.guild_id = guild_id
                self.shop_data = shop_data

            async def callback(self, select_inter: discord.Interaction):
                role_id = int(self.values[0])
                price = self.shop_data[str(role_id)]
                s = get_stats(select_inter.user.id)
                
                if s['coins'] < price: return await select_inter.response.send_message("Not enough coins!", ephemeral=True)
                
                role = select_inter.guild.get_role(role_id)
                await select_inter.user.add_roles(role)
                s['coins'] -= price
                await select_inter.response.send_message(f"✅ Purchased {role.name}!", ephemeral=True)

        view = discord.ui.View(); view.add_item(RoleSelect(self.guild_id, settings))
        await inter.response.send_message("Select a role:", view=view, ephemeral=True)

# --- SLASH COMMANDS ---

@bot.tree.command(name="setupshoprole", description="Add a role to the coin shop")
@app_commands.checks.has_permissions(administrator=True)
async def setupshoprole(inter: discord.Interaction, role: discord.Role, price: int):
    gid = inter.guild.id
    if gid not in server_settings: server_settings[gid] = {}
    if 'shop' not in server_settings[gid]: server_settings[gid]['shop'] = {}
    
    server_settings[gid]['shop'][str(role.id)] = price
    await inter.response.send_message(f"✅ Added {role.name} to shop for {price} coins!")

@bot.tree.command(name="battlepass_setup", description="Set reward for a Battlepass tier")
@app_commands.checks.has_permissions(administrator=True)
async def bp_setup(inter: discord.Interaction, tier: int, reward_text: str, premium_reward: str):
    gid = inter.guild.id
    if gid not in server_settings: server_settings[gid] = {}
    if 'bp' not in server_settings[gid]: server_settings[gid]['bp'] = {}
    
    server_settings[gid]['bp'][tier] = {'free': reward_text, 'premium': premium_reward}
    await inter.response.send_message(f"✅ Tier {tier} setup complete!")

@bot.tree.command(name="battlepass", description="View your Battlepass progress")
async def battlepass(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    gid = inter.guild.id
    bp_data = server_settings.get(gid, {}).get('bp', {})
    
    emb = discord.Embed(title="🎫 MVSD BATTLEPASS", color=discord.Color.purple())
    emb.description = f"**Level:** {s['bp_level']} | **XP:** {s['xp'] % 100}/100\n**Premium:** {'✅ Yes' if s['premium'] else '❌ No'}"
    
    for tier in sorted(bp_data.keys())[:5]: # Rodom 5 artimiausius tierus
        data = bp_data[tier]
        status = "🎁" if s['bp_level'] >= tier else "🔒"
        prem_status = "💎" if s['premium'] and s['bp_level'] >= tier else "🔒"
        emb.add_field(name=f"Tier {tier}", value=f"Free: {status} {data['free']}\nPremium: {prem_status} {data['premium']}", inline=False)
    
    await inter.response.send_message(embed=emb)

@bot.tree.command(name="set_premium", description="Give Premium Battlepass to a user")
@app_commands.checks.has_permissions(administrator=True)
async def set_premium(inter: discord.Interaction, member: discord.Member, status: bool):
    get_stats(member.id)['premium'] = status
    await inter.response.send_message(f"✅ {member.name} premium set to {status}")

@bot.tree.command(name="shop", description="Open the league shop")
async def shop(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    emb = discord.Embed(title="🛒 MVSD League Shop", description=f"Your Balance: `💰 {s['coins']}`", color=discord.Color.gold())
    emb.add_field(name="🧊 Streak Freeze", value="Price: `150` coins", inline=True)
    await inter.response.send_message(embed=emb, view=ShopRoleView(inter.guild.id))

# --- UPDATED ENDLEAGUE (With XP) ---
@bot.tree.command(name="endleague", description="End match and award XP/Stats")
async def endleague(inter: discord.Interaction, id: str, winner_pings: str = ""):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("ID not found!", ephemeral=True)
    data = league_storage[id]
    
    if data["status"] == "Ongoing":
        winners = [int(p.strip('<@!> ')) for p in winner_pings.replace(',', ' ').split() if p.strip('<@!> ').isdigit()]
        for p_id in data['player_list']:
            s = get_stats(p_id)
            # Duodame XP už žaidimą
            level_up = add_xp(p_id, 25) # 25 XP už mačą
            if p_id in winners:
                add_xp(p_id, 25) # Papildomi 25 XP už laimėjimą
                s['coins'] += 20; s['mmr'] += 20
            else:
                s['mmr'] = max(0, s['mmr'] - 15)
            
            if level_up:
                try: 
                    u = await bot.fetch_user(p_id)
                    await u.send(f"🎉 **LEVEL UP!** You reached Battlepass Level {s['bp_level']}!")
                except: pass
        await inter.response.send_message(f"✅ League {id} ended. XP and Level ups processed!")
    
    if "thread_id" in data:
        t = bot.get_channel(data["thread_id"])
        if t: await t.delete()
    del league_storage[id]

# --- RE-ADD EVERYTHING ELSE ---
@bot.tree.command(name="hostleague")
async def hostleague(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    l_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))
    emb = discord.Embed(title=f"🎮 {format} {type} League", color=discord.Color.green())
    emb.add_field(name="ID", value=f"**{l_id}**", inline=False)
    emb.add_field(name="Status", value="🟢 Recruiting", inline=True)
    
    # Čia būtų tavo JoinView, kurį jau turėjome
    await inter.response.send_message(embed=emb)
    # ... (likusi hosting logika)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Battlepass & Shop"))
    keep_alive()
    await bot.tree.sync()
    print(f'✅ {bot.user} online!')

if TOKEN: bot.run(TOKEN)
