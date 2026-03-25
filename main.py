import discord
from discord import app_commands
from discord.ext import commands
import os, random, asyncio, datetime
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# --- STORAGE ---
league_storage = {}
league_links = {}
server_settings = {}
user_stats = {}
last_work = {}
bets = {}
weekly_activity = {}

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
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.host_id = host_id

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, btn):
        if inter.user.id in self.players:
            return await inter.response.send_message("Already joined", ephemeral=True)

        self.players.append(inter.user.id)
        league_storage[self.league_id]["player_list"] = self.players

        # DM link
        link = league_links.get(inter.message.id, "No link yet")
        try:
            await inter.user.send(f"🎮 `{self.league_id}`\n{link}")
        except:
            pass

        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")

        await inter.message.edit(embed=embed, view=self)
        await inter.response.send_message("Joined!", ephemeral=True)

# --- COMMANDS ---

@bot.tree.command(name="shop", description="Open shop to buy items")
async def shop(inter):
    s = get_stats(inter.user.id)
    await inter.response.send_message(
        embed=discord.Embed(title="🛒 Shop", description=f"Coins: {s['coins']}"),
        view=ShopView()
    )

@bot.tree.command(name="work", description="Earn coins (cooldown applies)")
async def work(inter):
    uid = inter.user.id
    now = datetime.datetime.now().timestamp()

    if uid in last_work and now - last_work[uid] < 1800:
        return await inter.response.send_message("⏳ Wait before working again", ephemeral=True)

    earn = random.randint(25, 75)
    get_stats(uid)["coins"] += earn
    last_work[uid] = now

    await inter.response.send_message(f"💼 Earned {earn} coins")

@bot.tree.command(name="profile", description="View stats")
async def profile(inter, user: discord.Member = None):
    user = user or inter.user
    s = get_stats(user.id)

    embed = discord.Embed(title=f"{user.name}'s Profile")
    embed.add_field(name="Coins", value=s["coins"])
    embed.add_field(name="MMR", value=s["mmr"])
    embed.add_field(name="Wins", value=s["wins"])

    await inter.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Top players by MMR")
async def leaderboard(inter):
    top = sorted(user_stats.items(), key=lambda x: x[1]["mmr"], reverse=True)[:10]
    desc = ""

    for i, (uid, data) in enumerate(top, 1):
        user = await bot.fetch_user(uid)
        desc += f"{i}. {user.name} - {data['mmr']}\n"

    await inter.response.send_message(embed=discord.Embed(title="🏆 Leaderboard", description=desc))

@bot.tree.command(name="leaguehost", description="Host a league")
async def leaguehost(inter, format: str):
    max_p = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}.get(format, 4)
    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))

    embed = discord.Embed(title=f"{format} League")
    embed.add_field(name="League ID", value=league_id)
    embed.add_field(name="Players", value=f"1/{max_p}")

    view = JoinView(league_id, max_p, inter.user.id)
    await inter.response.send_message(embed=embed, view=view)
    msg = await inter.original_response()

    league_storage[league_id] = {
        "msg_id": msg.id,
        "channel_id": inter.channel_id,
        "host_id": inter.user.id,
        "player_list": [inter.user.id]
    }

    try:
        await inter.user.send(f"Send link for `{league_id}`")
        dm = await bot.wait_for("message",
            check=lambda m: m.author == inter.user and isinstance(m.channel, discord.DMChannel),
            timeout=120)
        league_links[msg.id] = dm.content
    except:
        pass

@bot.tree.command(name="endleague", description="End league and upload screenshots")
async def endleague(inter):
    await inter.response.send_message("Send League ID", ephemeral=True)

    msg = await bot.wait_for("message", check=lambda m: m.author == inter.user, timeout=60)
    league_id = msg.content.upper()

    if league_id not in league_storage:
        return await inter.followup.send("Not found")

    data = league_storage[league_id]
    host = await bot.fetch_user(data["host_id"])

    await host.send(f"📸 Send screenshots for `{league_id}` (send multiple, then stop)")

    screenshots = []
    try:
        while True:
            m = await bot.wait_for("message", timeout=120, check=lambda x: x.author.id == data["host_id"])
            if m.attachments:
                screenshots.extend(m.attachments)
            else:
                break
    except:
        pass

    # send to results channel
    chan_id = server_settings.get(inter.guild.id, {}).get("res_chan")
    if chan_id:
        chan = bot.get_channel(chan_id)
        for att in screenshots:
            emb = discord.Embed(title=f"{league_id} Result")
            emb.set_image(url=att.url)
            await chan.send(embed=emb)

    # rewards + MVP tracking
    for p in data["player_list"]:
        s = get_stats(p)
        s["wins"] += 1
        s["coins"] += 20
        s["mmr"] += 10
        weekly_activity[p] = weekly_activity.get(p, 0) + 1

    del league_storage[league_id]
    await inter.followup.send("League ended + results posted")

@bot.tree.command(name="mvpsetup", description="Set MVP channel")
async def mvpsetup(inter, channel: discord.TextChannel):
    server_settings.setdefault(inter.guild.id, {})
    server_settings[inter.guild.id]["mvp_chan"] = channel.id
    await inter.response.send_message("MVP channel set", ephemeral=True)

@bot.tree.command(name="mvpannounce", description="Announce MVP")
async def mvpannounce(inter):
    if not weekly_activity:
        return await inter.response.send_message("No data")

    mvp = max(weekly_activity, key=weekly_activity.get)
    user = await bot.fetch_user(mvp)

    chan_id = server_settings.get(inter.guild.id, {}).get("mvp_chan")
    if chan_id:
        chan = bot.get_channel(chan_id)
        await chan.send(f"🌟 MVP: {user.mention} with {weekly_activity[mvp]} wins!")

    weekly_activity.clear()
    await inter.response.send_message("MVP announced")

@bot.tree.command(name="setupleagues", description="Set results channel")
async def setupleagues(inter, results_channel: discord.TextChannel):
    server_settings.setdefault(inter.guild.id, {})
    server_settings[inter.guild.id]["res_chan"] = results_channel.id
    await inter.response.send_message("Setup done")

# --- ALIVE CHAT SYSTEM ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    # 🔥 REPLY WHEN PINGED
    if bot.user in message.mentions:
        content = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not content:
            reply = "👀 You called?"
        else:
            reply = content.capitalize()

        await message.reply(reply)
        return

    # 🎲 RANDOM CHAT (5%)
    if random.randint(1, 100) <= 5:
        await message.channel.send(random.choice([
            "👀 I'm watching...",
            "🎮 Queue up!",
            "💰 Try /work",
            "🏆 Someone farming wins?"
        ]))

# --- READY ---
@bot.event
async def on_ready():
    keep_alive()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="My boss vJ")
    )
    await bot.tree.sync()
    print("Bot is alive.")

bot.run(TOKEN)
