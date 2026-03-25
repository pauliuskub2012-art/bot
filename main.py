import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- SETTINGS ---
FREEZE_PRICE = 150  
DAILY_GOAL = 2      
DAILY_COINS = 50    
DAILY_MMR = 20      

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- DATABASE ---
user_stats = {} 
league_storage = {} 
league_links = {} 
server_settings = {} 
active_bets = {} # {league_id: {user_id: {'amount': 0, 'on_host': True}}}
deleted_messages = {}

# --- HELPERS ---
def get_stats(uid):
    today = str(datetime.date.today())
    if uid not in user_stats:
        user_stats[uid] = {
            'mmr': 1000, 'points': 0, 'wins': 0, 'played': 0, 'streak': 0, 
            'coins': 100, 'freeze': False, 'daily_count': 0, 
            'last_daily': today, 'weekly_pts': 0
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
        embed.set_field_at(1, name="Players", value=f"👤 `{len(self.players)}/{self.max_p}`", inline=True)
        
        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.orange()
            embed.set_field_at(2, name="Status", value="🟠 Ongoing (Bets Open!)", inline=True)
            league_storage[self.league_id]["status"] = "Ongoing"
            await inter.message.edit(embed=embed, view=None)
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! ID: `{self.league_id}`", ephemeral=True)
        try:
            link = league_links.get(inter.message.id, "No link provided.")
            await inter.user.send(f"🎮 **Joined League `{self.league_id}`**\nLink: {link}")
        except: pass

# --- SLASH COMMANDS ---

@bot.tree.command(name="setup_mvp", description="Set the channel where Weekly MVP will be announced")
@app_commands.checks.has_permissions(administrator=True)
async def setup_mvp(inter: discord.Interaction, channel: discord.TextChannel):
    if inter.guild.id not in server_settings: server_settings[inter.guild.id] = {}
    server_settings[inter.guild.id]['mvp_chan'] = channel.id
    await inter.response.send_message(f"✅ MVP announcements set to {channel.mention}!")

@bot.tree.command(name="pay", description="Send coins to another player")
async def pay(inter: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0: return await inter.response.send_message("Invalid amount!", ephemeral=True)
    sender = get_stats(inter.user.id)
    if sender['coins'] < amount: return await inter.response.send_message("Not enough coins!", ephemeral=True)
    
    receiver = get_stats(member.id)
    sender['coins'] -= amount
    receiver['coins'] += amount
    await inter.response.send_message(f"💸 Successfully paid `{amount}` coins to {member.mention}!")

@bot.tree.command(name="bet", description="Bet coins on the league winner")
async def bet(inter: discord.Interaction, league_id: str, amount: int, on_host_team: bool):
    league_id = league_id.upper()
    s = get_stats(inter.user.id)
    if amount <= 0 or s['coins'] < amount: return await inter.response.send_message("Invalid amount or no coins!", ephemeral=True)
    if league_id not in league_storage or league_storage[league_id]['status'] != "Ongoing":
        return await inter.response.send_message("Match not found or not in progress!", ephemeral=True)
    
    if league_id not in active_bets: active_bets[league_id] = {}
    active_bets[league_id][inter.user.id] = {'amount': amount, 'on_host': on_host_team}
    s['coins'] -= amount
    await inter.response.send_message(f"🎲 Bet `{amount}` coins on {'Host' if on_host_team else 'Opponents'}!")

@bot.tree.command(name="hostleague", description="Host a new match")
@app_commands.choices(format=[app_commands.Choice(name="1v1", value="1v1"), app_commands.Choice(name="2v2", value="2v2"), app_commands.Choice(name="3v3", value="3v3"), app_commands.Choice(name="4v4", value="4v4")])
async def hostleague(inter: discord.Interaction, format: app_commands.Choice[str], type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})
    if not inter.user.guild_permissions.administrator and not any(role.id == settings.get('host_role') for role in inter.user.roles):
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
        await inter.user.send(f"👋 ID: `{l_id}`. Reply with Server Link.")
        m = await bot.wait_for('message', check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel), timeout=180.0)
        league_links[msg.id] = m.content
        await inter.user.send("✅ Link saved!")
    except: pass

@bot.tree.command(name="endleague", description="End match and handle rewards")
async def endleague(inter: discord.Interaction, id: str, winner_pings: str = ""):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("❌ ID not found!", ephemeral=True)
    data = league_storage[id]
    
    if data["status"] == "Ongoing":
        winners = [int(p.strip('<@!> ')) for p in winner_pings.replace(',', ' ').split() if p.strip('<@!> ').isdigit()]
        host_won = data['host_id'] in winners

        # Award Stats
        for p_id in data['player_list']:
            s = get_stats(p_id); s['played'] += 1; s['daily_count'] += 1
            if p_id in winners:
                s['wins'] += 1; s['streak'] += 1; s['mmr'] += 20 + (s['streak'] * 2); s['coins'] += 15; s['weekly_pts'] += 50
            else:
                if s['freeze']: s['freeze'] = False
                else: s['streak'] = 0
                s['mmr'] = max(0, s['mmr'] - 15); s['weekly_pts'] += 10
        
        # Pay Bets
        if id in active_bets:
            for uid, bdata in active_bets[id].items():
                if bdata['on_host'] == host_won:
                    get_stats(uid)['coins'] += bdata['amount'] * 2
            del active_bets[id]

        await inter.response.send_message(f"✅ Match `{id}` archived. Bets paid!")
    else:
        await inter.response.send_message("❌ Cancelled.")

    if "thread_id" in data:
        t = bot.get_channel(data["thread_id"])
        if t: await t.delete()
    del league_storage[id]

@bot.tree.command(name="announce_mvp", description="Manually announce Weekly MVP")
@app_commands.checks.has_permissions(administrator=True)
async def announce_mvp(inter: discord.Interaction):
    if not user_stats: return await inter.response.send_message("No data!")
    mvp_id = max(user_stats, key=lambda x: user_stats[x]['weekly_pts'])
    mvp_data = user_stats[mvp_id]
    user = await bot.fetch_user(mvp_id)
    
    chan_id = server_settings.get(inter.guild.id, {}).get('mvp_chan')
    if not chan_id: return await inter.response.send_message("Setup MVP channel first!")
    
    chan = bot.get_channel(chan_id)
    emb = discord.Embed(title="🏆 WEEKLY MVP", description=f"The most valuable player of the week is {user.mention}!", color=discord.Color.gold())
    emb.add_field(name="Weekly Points", value=f"⭐ `{mvp_data['weekly_pts']}`")
    emb.set_thumbnail(url=user.display_avatar.url)
    await chan.send(embed=emb)
    
    # Reset weekly points
    for uid in user_stats: user_stats[uid]['weekly_pts'] = 0
    await inter.response.send_message("✅ MVP announced and points reset.")

@bot.tree.command(name="setup_all", description="Configure bot")
@app_commands.checks.has_permissions(administrator=True)
async def setup_all(inter: discord.Interaction, staff: discord.Role, host_role: discord.Role, host_ch: discord.TextChannel, res_ch: discord.TextChannel, jail: discord.Role):
    server_settings[inter.guild.id] = {'staff_role': staff.id, 'host_role': host_role.id, 'host_chan': host_ch.id, 'res_chan': res_ch.id, 'jail_role': jail.id}
    await inter.response.send_message("✅ Done!")

# --- START ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD MVP"))
    keep_alive()
    await bot.tree.sync()
    print(f'✅ {bot.user} online!')

if TOKEN: bot.run(TOKEN)
