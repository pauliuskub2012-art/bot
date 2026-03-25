import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- SETTINGS & BALANCE ---
FREEZE_PRICE = 150  
DAILY_GOAL = 2      
DAILY_COINS = 50    
DAILY_MMR = 20      

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- DATABASE (InMemory) ---
user_stats = {} 
league_storage = {} 
league_links = {} 
server_settings = {} 
deleted_messages = {}

# --- HELPERS ---
def get_stats(uid):
    today = str(datetime.date.today())
    if uid not in user_stats:
        user_stats[uid] = {
            'mmr': 1000, 'points': 0, 'wins': 0, 'played': 0, 'streak': 0, 
            'coins': 100, 'freeze': False, 'daily_count': 0, 
            'last_daily': today
        }
    if user_stats[uid]['last_daily'] != today:
        user_stats[uid]['daily_count'] = 0
        user_stats[uid]['last_daily'] = today
    return user_stats[uid]

def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        return ctx.author.guild_permissions.administrator or (staff_role_id and any(r.id == staff_role_id for r in ctx.author.roles))
    return commands.check(predicate)

# --- LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id, self.max_p, self.players, self.host_id = league_id, max_p, [host_id], host_id
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(name=f"match-{self.league_id}", type=discord.ChannelType.private_thread, invitational=False)
                league_storage[self.league_id]["thread_id"] = self.thread.id
                host_mem = inter.guild.get_member(self.host_id)
                if host_mem: await self.thread.add_user(host_mem)
            except: pass

        if self.thread: await self.thread.add_user(inter.user)
        league_storage[self.league_id]["player_list"] = self.players

        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)
        embed.set_field_at(1, name="Players", value=f"👤 `{len(self.players)}/{self.max_p}`", inline=True)
        
        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.orange()
            embed.set_field_at(2, name="Status", value="🟠 Ongoing", inline=True)
            league_storage[self.league_id]["status"] = "Ongoing"
            await inter.message.edit(embed=embed, view=None)
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! ID: `{self.league_id}`", ephemeral=True)
        try:
            link = league_links.get(inter.message.id, "Not provided.")
            await inter.user.send(f"🎮 **League Joined!**\nID: `{self.league_id}`\nLink: {link}")
        except: pass

# --- SLASH COMMANDS ---

@bot.tree.command(name="setup_all", description="Configure all bot roles and channels")
@app_commands.checks.has_permissions(administrator=True)
async def setup_all(inter: discord.Interaction, staff_role: discord.Role, host_role: discord.Role, host_chan: discord.TextChannel, res_chan: discord.TextChannel, jail_role: discord.Role):
    server_settings[inter.guild.id] = {'staff_role': staff_role.id, 'host_role': host_role.id, 'host_chan': host_chan.id, 'res_chan': res_chan.id, 'jail_role': jail_role.id}
    await inter.response.send_message("✅ Settings saved!", ephemeral=True)

@bot.tree.command(name="hostleague", description="Host a new match")
@app_commands.choices(format=[app_commands.Choice(name="1v1", value="1v1"), app_commands.Choice(name="2v2", value="2v2"), app_commands.Choice(name="3v3", value="3v3"), app_commands.Choice(name="4v4", value="4v4")])
async def hostleague(inter: discord.Interaction, format: app_commands.Choice[str], type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})
    if not inter.user.guild_permissions.administrator and not any(r.id == settings.get('host_role') for r in inter.user.roles):
        return await inter.response.send_message("❌ Missing Host Role!", ephemeral=True)
    
    f_val = format.value
    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(f_val, 4)
    l_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))
    
    emb = discord.Embed(title=f"🎮 {f_val} {type} League", color=discord.Color.green())
    emb.add_field(name="ID", value=f"**{l_id}**", inline=False)
    emb.add_field(name="Players", value=f"👤 `1/{max_p}`", inline=True)
    emb.add_field(name="Status", value="🟢 Recruiting", inline=True)
    emb.add_field(name="Host", value=inter.user.mention, inline=False)
    
    view = JoinView(l_id, max_p, inter.user.id)
    await inter.response.send_message(embed=emb, view=view)
    msg = await inter.original_response()
    league_storage[l_id] = {"msg_id": msg.id, "channel_id": inter.channel_id, "host_id": inter.user.id, "status": "Recruiting", "player_list": [inter.user.id], "format": f_val}
    
    try:
        await inter.user.send(f"👋 ID: `{l_id}`. Reply with Private Server Link.")
        m = await bot.wait_for('message', check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel), timeout=180.0)
        league_links[msg.id] = m.content
        await inter.user.send("✅ Link saved!")
    except: pass

@bot.tree.command(name="endleague", description="End match and award MMR")
async def endleague(inter: discord.Interaction, id: str, winner_pings: str = ""):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("❌ ID not found!", ephemeral=True)
    data = league_storage[id]
    
    if data["status"] == "Ongoing":
        winners = [int(p.strip('<@!> ')) for p in winner_pings.replace(',', ' ').split() if p.strip('<@!> ').isdigit()]
        for p_id in data['player_list']:
            s = get_stats(p_id); s['played'] += 1; s['daily_count'] += 1
            if s['daily_count'] == DAILY_GOAL: s['coins'] += DAILY_COINS; s['mmr'] += DAILY_MMR
            if p_id in winners:
                s['wins'] += 1; s['streak'] += 1; s['mmr'] += 20 + (s['streak'] * 2); s['coins'] += 15
            else:
                if s['freeze']: s['freeze'] = False; await inter.channel.send(f"🧊 <@{p_id}> used **Freeze**!")
                else: s['streak'] = 0
                s['mmr'] = max(0, s['mmr'] - 15)
        await inter.response.send_message(f"✅ Match `{id}` ended.")
    else:
        await inter.response.send_message("❌ Match cancelled.")

    if "thread_id" in data:
        t = bot.get_channel(data["thread_id"])
        if t: await t.delete()
    del league_storage[id]

@bot.tree.command(name="shop", description="League store")
async def shop(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    emb = discord.Embed(title="🛒 Shop", description=f"Your Balance: `{s['coins']}`", color=discord.Color.gold())
    emb.add_field(name="🧊 Streak Freeze", value=f"Price: `{FREEZE_PRICE}` Coins\nProtect your win streak.")
    await inter.response.send_message(embed=emb)

@bot.tree.command(name="buy_freeze", description="Buy a streak freeze")
async def buy_freeze(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    if s['coins'] < FREEZE_PRICE: return await inter.response.send_message("❌ Not enough coins!", ephemeral=True)
    s['coins'] -= FREEZE_PRICE; s['freeze'] = True
    await inter.response.send_message("🧊 Freeze purchased!")

@bot.tree.command(name="profile", description="Check stats")
async def profile(inter: discord.Interaction, member: discord.Member = None):
    t = member or inter.user; s = get_stats(t.id)
    emb = discord.Embed(title=f"📊 {t.name}", color=discord.Color.blue())
    emb.add_field(name="MMR", value=s['mmr']); emb.add_field(name="Streak", value=s['streak'])
    emb.add_field(name="Coins", value=s['coins']); await inter.response.send_message(embed=emb)

@bot.tree.command(name="leaderboard", description="Top 10 players")
async def leaderboard(inter: discord.Interaction):
    sorted_u = sorted(user_stats.items(), key=lambda x: x[1]['mmr'], reverse=True)[:10]
    desc = "\n".join([f"**{i+1}.** <@{u}> - `{s['mmr']}` MMR" for i, (u, s) in enumerate(sorted_u)])
    await inter.response.send_message(embed=discord.Embed(title="🏆 Leaderboard", description=desc or "None", color=discord.Color.gold()))

@bot.tree.command(name="manage_coins", description="Add/Remove coins (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def manage_coins(inter: discord.Interaction, member: discord.Member, amount: int):
    s = get_stats(member.id); s['coins'] += amount
    await inter.response.send_message(f"✅ Updated {member.name}'s balance to `{s['coins']}`.")

# --- PREFIX COMMANDS (.) ---
@bot.command()
@is_staff()
async def b(ctx, m: discord.Member, *, r="None"): await m.ban(reason=r); await ctx.send(f"✅ Banned {m}")

@bot.command()
@is_staff()
async def k(ctx, m: discord.Member, *, r="None"): await m.kick(reason=r); await ctx.send(f"✅ Kicked {m}")

@bot.command()
@is_staff()
async def t(ctx, m: discord.Member, min: int): await m.timeout(datetime.timedelta(minutes=min)); await ctx.send(f"✅ Muted {m}")

@bot.command()
@is_staff()
async def unt(ctx, m: discord.Member): await m.timeout(None); await ctx.send(f"✅ Unmuted {m}")

@bot.command()
@is_staff()
async def jail(ctx, m: discord.Member):
    rid = server_settings.get(ctx.guild.id, {}).get('jail_role')
    if rid: await m.add_roles(ctx.guild.get_role(rid)); await ctx.send(f"⚖️ Jailed {m}")

@bot.command()
async def s(ctx, i: int = 1):
    data = deleted_messages.get(ctx.channel.id, [])
    if not data: return await ctx.send("No snipes.")
    msg = data[i-1]; e = discord.Embed(description=msg['content'], color=discord.Color.red())
    e.set_author(name=msg['author'], icon_url=msg['icon']); await ctx.send(embed=e)

# --- RUN ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Leagues"))
    keep_alive()
    await bot.tree.sync()
    print(f'✅ {bot.user} online!')

if TOKEN: bot.run(TOKEN)
