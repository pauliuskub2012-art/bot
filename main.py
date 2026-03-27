import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, asyncio, re
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# --- STORAGE ---
league_storage = {}
server_settings = {}
user_stats = {}
last_work = {}
weekly_activity = {}
warns = {}

# --- ECONOMY ---
def get_stats(uid):
    if uid not in user_stats:
        user_stats[uid] = {
            "coins": 100,
            "mmr": 1000,
            "wins": 0,
            "freeze": False,
            "insurance": False,
            "booster": False
        }
    return user_stats[uid]

# --- PERMS ---
def has_perm(ctx, perm):
    return getattr(ctx.author.guild_permissions, perm)

async def no_perm(ctx):
    await ctx.send("🚫 No permission.")

# --- LOGGING ---
def log_action(guild, message):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if chan_id:
        channel = bot.get_channel(chan_id)
        if channel:
            asyncio.create_task(channel.send(message))

@bot.command(help="Set logs channel")
async def setup_logs(ctx, channel: discord.TextChannel):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)

    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["logs"] = channel.id
    await ctx.send(f"📜 Logs set to {channel.mention}")

# --- JAIL SYSTEM ---
@bot.command(help="Set jail role")
async def setup_jail(ctx, role: discord.Role):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)

    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["jail"] = role.id

    await ctx.send(f"🚔 Jail role set to {role.mention}")
    log_action(ctx.guild, f"🚔 {ctx.author} set jail role {role.name}")

def get_jail_role(guild):
    role_id = server_settings.get(guild.id, {}).get("jail")
    return guild.get_role(role_id) if role_id else None

@bot.command(help="Jail a user")
async def jail(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    role = get_jail_role(ctx.guild)
    if not role:
        return await ctx.send("❌ Use .setup_jail first")

    await member.add_roles(role)
    await ctx.send(f"🚔 {member.mention} jailed")
    log_action(ctx.guild, f"🚔 {ctx.author} jailed {member}")

# --- RANK SYSTEM ---
@bot.tree.command(name="ranksetup", description="Set rank system channel and PR roles (PR1–PR10)")
async def ranksetup(inter: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("No permission", ephemeral=True)

    server_settings.setdefault(inter.guild.id, {})
    server_settings[inter.guild.id]["rank_channel"] = channel.id

    await inter.response.send_message("✅ Rank system configured", ephemeral=True)
    log_action(inter.guild, f"📊 {inter.user} set rank channel to {channel.name}")

# --- AUTO RANK HANDLER ---
@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot or not message.guild:
        return

    settings = server_settings.get(message.guild.id, {})
    if message.channel.id != settings.get("rank_channel"):
        return

    if not message.mentions:
        return

    member = message.mentions[0]
    match = re.search(r'PR\s*(\d+)', message.content.upper())

    if not match:
        return

    rank = int(match.group(1))
    if not (1 <= rank <= 10):
        return

    roles_to_remove = []
    new_role = None

    for role in message.guild.roles:
        if role.name.upper().startswith("PR"):
            try:
                num = int(role.name[2:])
                if 1 <= num <= 10:
                    roles_to_remove.append(role)
                    if num == rank:
                        new_role = role
            except:
                continue

    if not new_role:
        return

    await member.remove_roles(*[r for r in roles_to_remove if r in member.roles])
    await member.add_roles(new_role)

    log_action(message.guild, f"📊 {message.author} set {member} to PR{rank}")

# --- SHOP ---
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def buy(self, inter, item, price):
        s = get_stats(inter.user.id)
        if s["coins"] < price:
            return await inter.response.send_message("❌ Not enough coins", ephemeral=True)
        if s[item]:
            return await inter.response.send_message("Already active", ephemeral=True)

        s["coins"] -= price
        s[item] = True
        await inter.response.send_message(f"✅ {item} activated", ephemeral=True)

    @discord.ui.button(label="Freeze 🧊")
    async def freeze(self, i, b): await self.buy(i, "freeze", 150)

    @discord.ui.button(label="Insurance 🛡️")
    async def insurance(self, i, b): await self.buy(i, "insurance", 300)

    @discord.ui.button(label="Booster 🔥")
    async def booster(self, i, b): await self.buy(i, "booster", 500)

# --- LEAGUE JOIN VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id, link):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.link = link

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, btn):
        if inter.user.id in self.players:
            return await inter.response.send_message("Already joined", ephemeral=True)

        if len(self.players) >= self.max_p:
            return await inter.response.send_message("League full", ephemeral=True)

        self.players.append(inter.user.id)
        league_storage[self.league_id]["players"] = self.players

        try:
            embed = discord.Embed(title="League Joined", description=f"ID: {self.league_id}")
            embed.add_field(name="Link", value=self.link)
            await inter.user.send(embed=embed)
        except:
            pass

        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")
        await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("Joined", ephemeral=True)

# --- LEAGUE COMMANDS ---
@bot.tree.command(name="leaguehost", description="Host a league")
async def leaguehost(inter: discord.Interaction, format: str, perks: bool, match_type: str, region: str, link: str):
    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}

    if format not in formats:
        return await inter.response.send_message("Invalid format", ephemeral=True)

    max_p = formats[format]
    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))

    embed = discord.Embed(title=f"{format} | {match_type}")
    embed.add_field(name="ID", value=league_id)
    embed.add_field(name="Players", value=f"1/{max_p}")
    embed.add_field(name="Region", value=region)

    view = JoinView(league_id, max_p, inter.user.id, link)

    await inter.response.send_message(embed=embed, view=view)

    league_storage[league_id] = {"players":[inter.user.id]}
    log_action(inter.guild, f"🎮 {inter.user} hosted league {league_id}")

@bot.tree.command(name="endleague", description="End a league")
async def endleague(inter: discord.Interaction, league_id: str):
    league_id = league_id.upper()

    if league_id not in league_storage:
        return await inter.response.send_message("Not found", ephemeral=True)

    for p in league_storage[league_id]["players"]:
        s = get_stats(p)
        s["wins"] += 1
        s["coins"] += 20
        s["mmr"] += 10
        weekly_activity[p] = weekly_activity.get(p, 0) + 1

    del league_storage[league_id]
    await inter.response.send_message("🏁 League ended")

    log_action(inter.guild, f"🏁 {inter.user} ended league {league_id}")

@bot.tree.command(name="mvpannounce", description="Announce MVP")
async def mvpannounce(inter: discord.Interaction):
    if not weekly_activity:
        return await inter.response.send_message("No data", ephemeral=True)

    mvp = max(weekly_activity, key=weekly_activity.get)
    user = await bot.fetch_user(mvp)

    await inter.response.send_message(f"🌟 MVP: {user.mention}")
    weekly_activity.clear()

# --- MODERATION ---
@bot.command(help="Ban user")
async def b(ctx, member: discord.Member):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await member.ban()
    await ctx.send("Banned")
    log_action(ctx.guild, f"{ctx.author} banned {member}")

@bot.command(help="Kick user")
async def k(ctx, member: discord.Member):
    if not has_perm(ctx, "kick_members"):
        return await no_perm(ctx)

    await member.kick()
    await ctx.send("Kicked")
    log_action(ctx.guild, f"{ctx.author} kicked {member}")

@bot.command(help="Warn user")
async def w(ctx, member: discord.Member, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = warns.get(member.id, 0) + 1
    await ctx.send(f"Warned ({warns[member.id]})")
    log_action(ctx.guild, f"{ctx.author} warned {member}")

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")

keep_alive()
bot.run(TOKEN)
