import discord
from discord import app_commands
from discord.ext import commands
import os, random, asyncio, datetime
from keep_alive import keep_alive

# --- SETTINGS ---
FREEZE_PRICE = 150
INSURANCE_PRICE = 300
BOOSTER_PRICE = 500
WORK_COOLDOWN = 1800

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- STORAGE ---
league_storage = {}
league_links = {}
server_settings = {}
deleted_messages = {}
user_stats = {}
last_work = {}

# --- ECONOMY ---
def get_stats(uid):
    if uid not in user_stats:
        user_stats[uid] = {
            "coins": 100,
            "freeze": False,
            "insurance": False,
            "booster": False,
            "streak": 0,
            "mmr": 1000
        }
    return user_stats[uid]

# --- SHOP UI ---
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Freeze", style=discord.ButtonStyle.secondary, emoji="🧊")
    async def freeze(self, inter, btn):
        s = get_stats(inter.user.id)
        if s["coins"] < FREEZE_PRICE:
            return await inter.response.send_message("❌ Not enough coins", ephemeral=True)
        if s["freeze"]:
            return await inter.response.send_message("Already active", ephemeral=True)
        s["coins"] -= FREEZE_PRICE
        s["freeze"] = True
        await inter.response.send_message("🧊 Freeze activated", ephemeral=True)

    @discord.ui.button(label="Insurance", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def insurance(self, inter, btn):
        s = get_stats(inter.user.id)
        if s["coins"] < INSURANCE_PRICE:
            return await inter.response.send_message("❌ Not enough coins", ephemeral=True)
        if s["insurance"]:
            return await inter.response.send_message("Already active", ephemeral=True)
        s["coins"] -= INSURANCE_PRICE
        s["insurance"] = True
        await inter.response.send_message("🛡️ Insurance ready", ephemeral=True)

    @discord.ui.button(label="Booster", style=discord.ButtonStyle.success, emoji="🔥")
    async def booster(self, inter, btn):
        s = get_stats(inter.user.id)
        if s["coins"] < BOOSTER_PRICE:
            return await inter.response.send_message("❌ Not enough coins", ephemeral=True)
        if s["booster"]:
            return await inter.response.send_message("Already active", ephemeral=True)
        s["coins"] -= BOOSTER_PRICE
        s["booster"] = True
        await inter.response.send_message("🔥 Booster ready", ephemeral=True)

# --- JOIN VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.host_id = host_id

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("Already joined!", ephemeral=True)

        self.players.append(inter.user.id)
        league_storage[self.league_id]["player_list"] = self.players

        # DM host
        try:
            host = await bot.fetch_user(self.host_id)
            await host.send(f"🔔 {inter.user} joined `{self.league_id}`")
        except: pass

        # DM player link
        link = league_links.get(inter.message.id, "No link yet.")
        try:
            await inter.user.send(f"🎮 League `{self.league_id}`\nLink: {link}")
        except: pass

        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)

        embed.set_field_at(5, name="Players", value=f"{len(self.players)}/{self.max_p}")
        embed.set_field_at(6, name="Spots Left", value=str(spots))

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.orange()
            embed.set_field_at(8, name="Status", value="🟠 Ongoing")
            league_storage[self.league_id]["status"] = "Ongoing"
            await inter.message.edit(embed=embed, view=None)
        else:
            await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined! Check DMs.", ephemeral=True)

# --- COMMANDS ---

@bot.tree.command(name="shop")
async def shop(inter: discord.Interaction):
    s = get_stats(inter.user.id)
    embed = discord.Embed(title="🛒 Shop", description=f"Coins: {s['coins']}")
    await inter.response.send_message(embed=embed, view=ShopView())

@bot.tree.command(name="work")
async def work(inter: discord.Interaction):
    uid = inter.user.id
    now = datetime.datetime.now().timestamp()

    if uid in last_work and now - last_work[uid] < WORK_COOLDOWN:
        return await inter.response.send_message("⏳ Wait before working again", ephemeral=True)

    earn = random.randint(25, 75)
    get_stats(uid)["coins"] += earn
    last_work[uid] = now

    await inter.response.send_message(f"💼 Earned {earn} coins")

@bot.tree.command(name="leaguehost")
async def leaguehost(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})

    if not inter.user.guild_permissions.administrator:
        if not any(role.id == settings.get('host_role') for role in inter.user.roles):
            return await inter.response.send_message("❌ Missing Host Role!", ephemeral=True)

    max_p = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}.get(format, 4)
    league_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))

    embed = discord.Embed(title=f"{format} {type}", color=discord.Color.green())
    embed.add_field(name="League ID", value=league_id, inline=False)
    embed.add_field(name="Players", value=f"1/{max_p}")
    embed.add_field(name="Spots Left", value=str(max_p-1))
    embed.add_field(name="Status", value="🟢 Recruiting")

    view = JoinView(league_id, max_p, inter.user.id)
    await inter.response.send_message(embed=embed, view=view)
    msg = await inter.original_response()

    league_storage[league_id] = {
        "msg_id": msg.id,
        "channel_id": inter.channel_id,
        "host_id": inter.user.id,
        "player_list": [inter.user.id],
        "status": "Recruiting"
    }

    # DM for link
    try:
        await inter.user.send(f"Send private server link for `{league_id}`")
        dm = await bot.wait_for('message',
            check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel),
            timeout=180)
        league_links[msg.id] = dm.content
    except: pass

@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction):
    await inter.response.send_message("Send League ID", ephemeral=True)

    def check(m):
        return m.author.id == inter.user.id and m.channel == inter.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        league_id = msg.content.upper()

        if league_id not in league_storage:
            return await inter.followup.send("❌ Not found", ephemeral=True)

        data = league_storage[league_id]

        # rewards
        for p in data["player_list"]:
            s = get_stats(p)
            reward = 20

            if s["booster"]:
                reward *= 2
                s["booster"] = False

            s["coins"] += reward
            s["mmr"] += 10

        await inter.followup.send(f"✅ `{league_id}` ended. Rewards given.")

        del league_storage[league_id]

    except asyncio.TimeoutError:
        await inter.followup.send("⏰ Timeout", ephemeral=True)

# --- SETUP ---
@bot.tree.command(name="setupleagues")
@app_commands.checks.has_permissions(administrator=True)
async def setupleagues(inter: discord.Interaction, hosting_channel: discord.TextChannel, results_channel: discord.TextChannel, host_role: discord.Role):
    server_settings[inter.guild.id] = {
        "host_chan": hosting_channel.id,
        "res_chan": results_channel.id,
        "host_role": host_role.id
    }
    await inter.response.send_message("✅ Setup done", ephemeral=True)

# --- RUN ---
@bot.event
async def on_ready():
    keep_alive()
    await bot.tree.sync()
    print("Bot ready")

if TOKEN:
    bot.run(TOKEN)
