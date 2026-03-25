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

# --- DATABASE (InMemory) ---
user_stats = {} # {uid: {stats, xp, bp_level, premium, weekly_pts}}
server_settings = {} # {gid: {staff, jail, host_ch, res_ch, mvp_ch, shop: {}, bp: {}}}
league_storage = {}
league_links = {}
deleted_messages = {}

# --- HELPERS ---
def get_stats(uid):
    if uid not in user_stats:
        user_stats[uid] = {
            'mmr': 1000, 'points': 0, 'coins': 100, 'xp': 0, 
            'bp_level': 1, 'premium': False, 'streak': 0, 'freeze': False, 'weekly_pts': 0
        }
    return user_stats[uid]

def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        return ctx.author.guild_permissions.administrator or (staff_role_id and any(r.id == staff_role_id for r in ctx.author.roles))
    return commands.check(predicate)

# --- BATTLEPASS & REWARDS LOGIC ---
async def process_xp(guild, user_id, amount):
    s = get_stats(user_id)
    s['xp'] += amount
    new_level = (s['xp'] // 100) + 1
    
    if new_level > s['bp_level']:
        s['bp_level'] = new_level
        # Tikriname prizus
        settings = server_settings.get(guild.id, {})
        bp_data = settings.get('bp', {}).get(new_level)
        
        if bp_data:
            reward = bp_data['free']
            if s['premium']: reward += f" & Premium: {bp_data['premium']}"
            
            # Pranešimas į rezultatų/pranešimų kanalą
            chan_id = settings.get('res_chan')
            if chan_id:
                chan = guild.get_channel(chan_id)
                emb = discord.Embed(title="🆙 BATTLEPASS LEVEL UP!", color=discord.Color.purple())
                emb.description = f"Congratulations <@{user_id}>! You reached **Tier {new_level}**.\n**Reward:** {reward}"
                await chan.send(content=f"<@{user_id}>", embed=emb)

# --- VIEWS ---
class ShopView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Buy Role", style=discord.ButtonStyle.success, emoji="🏷️")
    async def buy_role(self, inter: discord.Interaction, button: discord.ui.Button):
        settings = server_settings.get(self.guild_id, {}).get('shop', {})
        if not settings: return await inter.response.send_message("Shop is empty!", ephemeral=True)
        
        options = [discord.SelectOption(label=inter.guild.get_role(int(rid)).name, value=rid, description=f"Price: {pr} coins") 
                   for rid, pr in settings.items() if inter.guild.get_role(int(rid))]

        class RoleDropdown(discord.ui.Select):
            def __init__(self, shop_data):
                super().__init__(placeholder="Choose a role...", options=options)
                self.shop_data = shop_data
            async def callback(self, d_inter: discord.Interaction):
                rid = self.values[0]; price = self.shop_data[rid]; s = get_stats(d_inter.user.id)
                if s['coins'] < price: return await d_inter.response.send_message("Not enough coins!", ephemeral=True)
                s['coins'] -= price; await d_inter.user.add_roles(d_inter.guild.get_role(int(rid)))
                await d_inter.response.send_message(f"✅ Purchased!", ephemeral=True)

        view = discord.ui.View(); view.add_item(RoleDropdown(settings))
        await inter.response.send_message("Select role:", view=view, ephemeral=True)

# --- SLASH COMMANDS ---

@bot.tree.command(name="setup_all")
@app_commands.checks.has_permissions(administrator=True)
async def setup_all(inter: discord.Interaction, staff: discord.Role, host: discord.Role, host_ch: discord.TextChannel, res_ch: discord.TextChannel, jail: discord.Role, mvp_ch: discord.TextChannel):
    server_settings[inter.guild.id] = {'staff_role': staff.id, 'host_role': host.id, 'host_chan': host_ch.id, 'res_chan': res_ch.id, 'jail_role': jail.id, 'mvp_chan': mvp_ch.id, 'shop': {}, 'bp': {}}
    await inter.response.send_message("✅ Global Setup Complete!")

@bot.tree.command(name="battlepass_setup")
@app_commands.checks.has_permissions(administrator=True)
async def bp_setup(inter: discord.Interaction, tier: int, free_reward: str, premium_reward: str):
    settings = server_settings.get(inter.guild.id, {})
    if 'bp' not in settings: settings['bp'] = {}
    settings['bp'][tier] = {'free': free_reward, 'premium': premium_reward}
    await inter.response.send_message(f"✅ Tier {tier} rewards set!")

@bot.tree.command(name="setupshoprole")
@app_commands.checks.has_permissions(administrator=True)
async def setupshoprole(inter: discord.Interaction, role: discord.Role, price: int):
    settings = server_settings.get(inter.guild.id, {})
    settings['shop'][str(role.id)] = price
    await inter.response.send_message(f"✅ Added {role.name} to shop for {price} coins!")

@bot.tree.command(name="battlepass")
async def battlepass(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    bp_data = server_settings.get(inter.guild.id, {}).get('bp', {})
    emb = discord.Embed(title="🎫 MVSD BATTLEPASS", color=discord.Color.purple())
    emb.description = f"Level: **{s['bp_level']}** | XP: `{s['xp'] % 100}/100` | Premium: {'✅' if s['premium'] else '❌'}"
    for t in sorted(bp_data.keys())[:5]:
        d = bp_data[t]; status = "🎁" if s['bp_level'] >= t else "🔒"
        emb.add_field(name=f"Tier {t}", value=f"Free: {status} {d['free']}\nPrem: {status if s['premium'] else '🔒'} {d['premium']}", inline=False)
    await inter.response.send_message(embed=emb)

@bot.tree.command(name="announce_mvp")
@app_commands.checks.has_permissions(administrator=True)
async def announce_mvp(inter: discord.Interaction):
    if not user_stats: return await inter.response.send_message("No data!")
    mvp_id = max(user_stats, key=lambda x: user_stats[x]['weekly_pts'])
    user = await bot.fetch_user(mvp_id); chan_id = server_settings.get(inter.guild.id, {}).get('mvp_chan')
    if not chan_id: return await inter.response.send_message("Setup MVP channel first!")
    chan = bot.get_channel(chan_id)
    emb = discord.Embed(title="🏆 WEEKLY MVP", description=f"The MVP is {user.mention}!", color=discord.Color.gold())
    emb.set_thumbnail(url=user.display_avatar.url); await chan.send(embed=emb)
    for uid in user_stats: user_stats[uid]['weekly_pts'] = 0
    await inter.response.send_message("✅ MVP Announced!")

@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction, id: str, winner_pings: str = ""):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("❌ ID not found!", ephemeral=True)
    data = league_storage[id]
    if data["status"] == "Ongoing":
        winners = [int(p.strip('<@!> ')) for p in winner_pings.replace(',', ' ').split() if p.strip('<@!> ').isdigit()]
        for p_id in data['player_list']:
            s = get_stats(p_id); await process_xp(inter.guild, p_id, 50) # 50 XP už žaidimą
            if p_id in winners:
                s['coins'] += 30; s['mmr'] += 20; s['weekly_pts'] += 100
                await process_xp(inter.guild, p_id, 50) # Papildomi 50 XP laimėjus
            else:
                s['mmr'] = max(0, s['mmr'] - 15); s['weekly_pts'] += 20
        await inter.response.send_message(f"✅ League {id} ended. XP & Rewards processed!")
    if "thread_id" in data:
        t = bot.get_channel(data["thread_id"])
        if t: await t.delete()
    del league_storage[id]

# --- PREFIX MODERATION ---
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
async def jail(ctx, m: discord.Member):
    rid = server_settings.get(ctx.guild.id, {}).get('jail_role')
    if rid: await m.add_roles(ctx.guild.get_role(rid)); await ctx.send(f"⚖️ Jailed {m}")

# --- RUN ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD Rankings"))
    keep_alive(); await bot.tree.sync(); print(f'✅ {bot.user} online!')

if TOKEN: bot.run(TOKEN)
