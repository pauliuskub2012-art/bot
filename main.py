import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, asyncio
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

# --- PERM CHECK ---
def has_perm(ctx, perm):
    return getattr(ctx.author.guild_permissions, perm)

async def no_perm(ctx):
    await ctx.send("🚫 You don't have permission to use this command.")

# --- LOGGING ---
def log_action(guild, message):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if chan_id:
        channel = bot.get_channel(chan_id)
        if channel:
            asyncio.create_task(channel.send(message))

@bot.command(help="Set a logs channel for moderation actions")
async def setup_logs(ctx, channel: discord.TextChannel):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)

    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["logs"] = channel.id

    await ctx.send(f"📜 Logs channel set to {channel.mention}")

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

    @discord.ui.button(label="Freeze 🧊", style=discord.ButtonStyle.blurple)
    async def freeze(self, i, b): await self.buy(i, "freeze", 150)

    @discord.ui.button(label="Insurance 🛡️", style=discord.ButtonStyle.green)
    async def insurance(self, i, b): await self.buy(i, "insurance", 300)

    @discord.ui.button(label="Booster 🔥", style=discord.ButtonStyle.red)
    async def booster(self, i, b): await self.buy(i, "booster", 500)

# --- JOIN VIEW ---
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

        # DM LINK
        try:
            embed = discord.Embed(
                title="👋 League Joined!",
                description=f"**ID:** `{self.league_id}`",
                color=0x00ffcc
            )
            embed.add_field(name="Server Link", value=self.link)
            await inter.user.send(embed=embed)
        except:
            pass

        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")
        await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined", ephemeral=True)

# --- SLASH COMMANDS ---
@bot.tree.command(name="shop", description="Open the shop to buy perks")
async def shop(inter):
    s = get_stats(inter.user.id)
    await inter.response.send_message(
        embed=discord.Embed(title="🛒 Shop", description=f"Coins: {s['coins']}"),
        view=ShopView()
    )

@bot.tree.command(name="work", description="Work to earn coins (30 min cooldown)")
async def work(inter):
    uid = inter.user.id
    now = datetime.datetime.now().timestamp()

    if uid in last_work and now - last_work[uid] < 1800:
        return await inter.response.send_message("⏳ You need to wait before working again.", ephemeral=True)

    earn = random.randint(25, 75)
    get_stats(uid)["coins"] += earn
    last_work[uid] = now

    await inter.response.send_message(f"💼 You earned {earn} coins!")

@bot.tree.command(name="profile", description="Check your or another user's profile")
async def profile(inter, user: discord.Member=None):
    user = user or inter.user
    s = get_stats(user.id)

    embed = discord.Embed(title=f"{user.name}")
    embed.add_field(name="Coins", value=s["coins"])
    embed.add_field(name="MMR", value=s["mmr"])
    embed.add_field(name="Wins", value=s["wins"])

    await inter.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show top 10 players by MMR")
async def leaderboard(inter):
    top = sorted(user_stats.items(), key=lambda x: x[1]["mmr"], reverse=True)[:10]
    desc = ""

    for i, (uid, data) in enumerate(top, 1):
        user = await bot.fetch_user(uid)
        desc += f"{i}. {user.name} - {data['mmr']}\n"

    await inter.response.send_message(embed=discord.Embed(title="🏆 Leaderboard", description=desc))

@bot.tree.command(name="leaguehost", description="Host a new league")
async def leaguehost(inter, format: str, perks: bool, match_type: str, region: str, link: str):
    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}

    if format not in formats:
        return await inter.response.send_message("Invalid format", ephemeral=True)

    max_p = formats[format]
    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))

    embed = discord.Embed(
        title=f"{format} | {match_type} | {'Perks' if perks else 'No Perks'}",
        color=0x00ffcc
    )
    embed.add_field(name="League ID", value=league_id)
    embed.add_field(name="Players", value=f"1/{max_p}")
    embed.add_field(name="Region", value=region.upper())

    view = JoinView(league_id, max_p, inter.user.id, link)

    await inter.response.send_message(embed=embed, view=view)

    league_storage[league_id] = {
        "players":[inter.user.id],
        "host":inter.user.id
    }

@bot.tree.command(name="endleague", description="End a league and reward players")
async def endleague(inter, league_id: str):
    league_id = league_id.upper()

    if league_id not in league_storage:
        return await inter.response.send_message("League not found.")

    data = league_storage[league_id]

    for p in data["players"]:
        s = get_stats(p)
        s["wins"] += 1
        s["coins"] += 20
        s["mmr"] += 10
        weekly_activity[p] = weekly_activity.get(p, 0) + 1

    del league_storage[league_id]
    await inter.response.send_message("🏁 League ended")

@bot.tree.command(name="mvpannounce", description="Announce weekly MVP")
async def mvpannounce(inter):
    if not weekly_activity:
        return await inter.response.send_message("No activity data yet.")

    mvp = max(weekly_activity, key=weekly_activity.get)
    user = await bot.fetch_user(mvp)

    await inter.response.send_message(f"🌟 MVP: {user.mention}")
    weekly_activity.clear()

# --- PREFIX MODERATION COMMANDS ---
@bot.command(help="Add or remove a role from a user")
async def r(ctx, member: discord.Member, *, role_name):
    if not has_perm(ctx, "manage_roles"):
        return await no_perm(ctx)

    role = discord.utils.find(lambda r: role_name.lower() in r.name.lower(), ctx.guild.roles)
    if not role:
        return await ctx.send("Role not found")

    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send("❌ Removed")
        log_action(ctx.guild, f"❌ {ctx.author} removed role {role.name} from {member}")
    else:
        await member.add_roles(role)
        await ctx.send("✅ Added")
        log_action(ctx.guild, f"✅ {ctx.author} added role {role.name} to {member}")

@bot.command(help="Timeout a user for a certain number of seconds")
async def t(ctx, member: discord.Member, time: int, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    await member.timeout(datetime.timedelta(seconds=time))
    await ctx.send(f"⏳ {member.mention} timed out for {time} seconds")
    log_action(ctx.guild, f"⏳ {ctx.author} timed out {member} for {time}s | Reason: {reason}")

@bot.command(help="Remove timeout from a user")
async def unt(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    await member.timeout(None)
    await ctx.send("✅ Timeout removed")
    log_action(ctx.guild, f"✅ {ctx.author} removed timeout from {member}")

@bot.command(help="Ban a user")
async def b(ctx, member: discord.Member):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await member.ban()
    await ctx.send("🔨 Banned")
    log_action(ctx.guild, f"🔨 {ctx.author} banned {member}")

@bot.command(help="Unban a user")
async def unb(ctx, user: discord.User):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await ctx.guild.unban(user)
    await ctx.send("✅ Unbanned")
    log_action(ctx.guild, f"✅ {ctx.author} unbanned {user}")

@bot.command(help="Kick a user")
async def k(ctx, member: discord.Member):
    if not has_perm(ctx, "kick_members"):
        return await no_perm(ctx)

    await member.kick()
    await ctx.send("👢 Kicked")
    log_action(ctx.guild, f"👢 {ctx.author} kicked {member}")

@bot.command(help="Purge messages in a channel")
async def p(ctx, amount: int):
    if not has_perm(ctx, "manage_messages"):
        return await no_perm(ctx)

    await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Deleted {amount}", delete_after=2)
    log_action(ctx.guild, f"🧹 {ctx.author} deleted {amount} messages in {ctx.channel.mention}")

@bot.command(help="Warn a user")
async def w(ctx, member: discord.Member, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = warns.get(member.id, 0) + 1
    await ctx.send(f"⚠️ {member.mention} warned for **{reason}**")
    log_action(ctx.guild,
        f"⚠️ {ctx.author} warned {member} | Reason: {reason} | Total warns: {warns[member.id]}"
    )

@bot.command(help="Clear warns of a user")
async def unw(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = 0
    await ctx.send("✅ Warns cleared")
    log_action(ctx.guild, f"✅ {ctx.author} cleared warns for {member}")

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")
keep_alive()
bot.run(TOKEN)
