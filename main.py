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

# --- PERMS ---
def has_perm(ctx, perm):
    return getattr(ctx.author.guild_permissions, perm)

async def no_perm(ctx):
    await ctx.send("🚫 No perms lil bro 😭")

# --- LOG SYSTEM ---
def log_action(guild, msg):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if chan_id:
        channel = bot.get_channel(chan_id)
        if channel:
            asyncio.create_task(channel.send(msg))

# --- AUTO SETUP LOGS ---
@bot.command()
async def setup_logs(ctx):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)

    channel = await ctx.guild.create_text_channel("bot-logs")

    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["logs"] = channel.id

    await ctx.send(f"📜 Logs created: {channel.mention}")

# --- AUTO SETUP JAIL ---
@bot.command()
async def setup_jail(ctx):
    if not has_perm(ctx, "manage_roles"):
        return await no_perm(ctx)

    role = await ctx.guild.create_role(name="Jailed")

    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
        role: discord.PermissionOverwrite(send_messages=True)
    }

    channel = await ctx.guild.create_text_channel("jail", overwrites=overwrites)

    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["jail_role"] = role.id
    server_settings[ctx.guild.id]["jail_channel"] = channel.id

    await ctx.send(f"🔒 Jail ready: {channel.mention}")

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

        try:
            await inter.user.send(f"👋 League `{self.league_id}`\n🔗 {self.link}")
        except:
            pass

        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")
        await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined", ephemeral=True)

# --- SLASH COMMANDS ---
@bot.tree.command(description="Open the shop")
async def shop(inter):
    s = get_stats(inter.user.id)
    await inter.response.send_message(
        embed=discord.Embed(title="🛒 Shop", description=f"Coins: {s['coins']}"),
        view=ShopView()
    )

@bot.tree.command(description="Earn coins")
async def work(inter):
    uid = inter.user.id
    now = datetime.datetime.now().timestamp()

    if uid in last_work and now - last_work[uid] < 1800:
        return await inter.response.send_message("⏳ Wait", ephemeral=True)

    earn = random.randint(25, 75)
    get_stats(uid)["coins"] += earn
    last_work[uid] = now

    await inter.response.send_message(f"💼 Earned {earn}")

@bot.tree.command(description="View profile")
async def profile(inter, user: discord.Member=None):
    user = user or inter.user
    s = get_stats(user.id)

    embed = discord.Embed(title=f"{user.name}")
    embed.add_field(name="Coins", value=s["coins"])
    embed.add_field(name="MMR", value=s["mmr"])
    embed.add_field(name="Wins", value=s["wins"])

    await inter.response.send_message(embed=embed)

@bot.tree.command(description="Leaderboard")
async def leaderboard(inter):
    top = sorted(user_stats.items(), key=lambda x: x[1]["mmr"], reverse=True)[:10]
    desc = ""

    for i, (uid, data) in enumerate(top, 1):
        user = await bot.fetch_user(uid)
        desc += f"{i}. {user.name} - {data['mmr']}\n"

    await inter.response.send_message(embed=discord.Embed(title="🏆 Leaderboard", description=desc))

# --- LEAGUE ---
@bot.tree.command(description="Host a league")
async def leaguehost(inter, format: str, perks: bool, match_type: str, region: str, link: str):
    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}

    if format not in formats:
        return await inter.response.send_message("Invalid format", ephemeral=True)

    max_p = formats[format]
    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))

    embed = discord.Embed(title=f"{format} | {match_type} | {'Perks' if perks else 'No Perks'}")
    embed.add_field(name="League ID", value=league_id)
    embed.add_field(name="Players", value=f"1/{max_p}")
    embed.add_field(name="Region", value=region.upper())

    view = JoinView(league_id, max_p, inter.user.id, link)
    await inter.response.send_message(embed=embed, view=view)

    league_storage[league_id] = {"players":[inter.user.id]}

@bot.tree.command(description="End a league")
async def endleague(inter, league_id: str):
    league_id = league_id.upper()

    if league_id not in league_storage:
        return await inter.response.send_message("Not found")

    data = league_storage[league_id]

    for p in data["players"]:
        s = get_stats(p)
        s["wins"] += 1
        s["coins"] += 20
        s["mmr"] += 10

    del league_storage[league_id]
    await inter.response.send_message("🏁 League ended")

# --- WARN ---
@bot.command()
async def w(ctx, member: discord.Member, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = warns.get(member.id, 0) + 1

    await ctx.send(f"⚠️ {member.mention} warned for **{reason}**")
    log_action(ctx.guild, f"{ctx.author} warned {member} | {reason} | total {warns[member.id]}")

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")

keep_alive()  # <--- PRIDĖKITE ČIA
bot.run(TOKEN)
