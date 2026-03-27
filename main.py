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
    await ctx.send("🚫 You don't have permission.")

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
            embed = discord.Embed(title="👋 League Joined!", description=f"ID: {self.league_id}")
            embed.add_field(name="Link", value=self.link)
            await inter.user.send(embed=embed)
        except:
            pass

        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")
        await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined", ephemeral=True)

# --- SLASH COMMANDS ---
@bot.tree.command(description="Open shop")
async def shop(inter):
    s = get_stats(inter.user.id)
    await inter.response.send_message(
        embed=discord.Embed(title="🛒 Shop", description=f"Coins: {s['coins']}"),
        view=ShopView()
    )

@bot.tree.command(description="Work for coins")
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

    embed = discord.Embed(title=user.name)
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

    await inter.response.send_message(embed=discord.Embed(title="🏆", description=desc))

# --- MODERATION ---
@bot.command(help="Ban user")
async def b(ctx, member: discord.Member):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await member.ban()
    await ctx.send("🔨 Banned")
    log_action(ctx.guild, f"{ctx.author} banned {member}")

@bot.command(help="Kick user")
async def k(ctx, member: discord.Member):
    if not has_perm(ctx, "kick_members"):
        return await no_perm(ctx)

    await member.kick()
    await ctx.send("👢 Kicked")
    log_action(ctx.guild, f"{ctx.author} kicked {member}")

@bot.command(help="Timeout user")
async def t(ctx, member: discord.Member, time: int):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    await member.timeout(datetime.timedelta(seconds=time))
    await ctx.send("⏳ Timed out")
    log_action(ctx.guild, f"{ctx.author} timed out {member}")

@bot.command(help="Remove timeout")
async def unt(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    await member.timeout(None)
    await ctx.send("✅ Timeout removed")
    log_action(ctx.guild, f"{ctx.author} removed timeout {member}")

@bot.command(help="Warn user")
async def w(ctx, member: discord.Member, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = warns.get(member.id, 0) + 1
    await ctx.send(f"⚠️ Warned ({warns[member.id]})")
    log_action(ctx.guild, f"{ctx.author} warned {member}")

@bot.command(help="Clear warns")
async def unw(ctx, member: discord.Member):
    warns[member.id] = 0
    await ctx.send("✅ Cleared warns")

@bot.command(help="Purge messages")
async def p(ctx, amount: int):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Deleted {amount}", delete_after=2)

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")

keep_alive()
bot.run(TOKEN)
