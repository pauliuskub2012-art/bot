import discord
from discord import app_commands
from discord.ext import commands
import os, random, asyncio, datetime
from keep_alive import keep_alive

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- STORAGE ---
deleted_messages = {}
league_storage = {}
league_links = {}
server_settings = {}

# --- PERMISSION ---
def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        return ctx.author.guild_permissions.administrator or (
            staff_role_id and discord.utils.get(ctx.author.roles, id=staff_role_id)
        )
    return commands.check(predicate)

# --- EVENTS ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues"))
    keep_alive()
    await bot.tree.sync()
    print(f'✅ {bot.user} online!')

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    cid = message.channel.id
    if cid not in deleted_messages:
        deleted_messages[cid] = []
    deleted_messages[cid].insert(0, {
        "content": message.content,
        "author": str(message.author),
        "icon": str(message.author.display_avatar.url)
    })

# --- LEAGUE VIEW (NO THREADS) ---
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
            return await inter.response.send_message("You are already in!", ephemeral=True)

        self.players.append(inter.user.id)
        league_storage[self.league_id]["player_list"] = self.players

        # DM HOST
        try:
            host_user = await bot.fetch_user(self.host_id)
            await host_user.send(f"🔔 `{inter.user}` joined your league `{self.league_id}`.")
        except:
            pass

        # DM PLAYER LINK
        link = league_links.get(inter.message.id, "Host has not sent the link yet.")
        try:
            await inter.user.send(f"🎮 League `{self.league_id}`\nLink: {link}")
        except:
            pass

        # UPDATE EMBED
        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)

        embed.set_field_at(5, name="Players", value=f"{len(self.players)}/{self.max_p}", inline=True)
        embed.set_field_at(6, name="Spots Left", value=str(spots), inline=True)

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.orange()
            embed.set_field_at(8, name="Status", value="🟠 Ongoing", inline=False)
            league_storage[self.league_id]["status"] = "Ongoing"
            await inter.message.edit(embed=embed, view=None)
        else:
            await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined! Check your DMs.", ephemeral=True)

# --- COMMANDS ---

@bot.tree.command(name="leaguehost", description="Host a league")
async def leaguehost(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})

    if not inter.user.guild_permissions.administrator:
        if not any(role.id == settings.get('host_role') for role in inter.user.roles):
            return await inter.response.send_message("❌ Missing Host Role!", ephemeral=True)

    if settings.get('host_chan') and inter.channel_id != settings.get('host_chan'):
        return await inter.response.send_message(f"❌ Use <#{settings.get('host_chan')}>", ephemeral=True)

    max_p = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}.get(format, 4)
    league_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))

    embed = discord.Embed(title=f"🎮 {format} {type} League", color=discord.Color.green())
    embed.add_field(name="League ID", value=f"**{league_id}**", inline=False)
    embed.add_field(name="Format", value=format, inline=True)
    embed.add_field(name="Type", value=type, inline=True)
    embed.add_field(name="Perks", value=perks, inline=True)
    embed.add_field(name="Region", value=region, inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=str(max_p-1), inline=True)
    embed.add_field(name="Host", value=inter.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Recruiting", inline=False)

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

    # DM HOST FOR LINK
    try:
        await inter.user.send(f"📩 Send private server link for `{league_id}`")
        dm = await bot.wait_for(
            'message',
            check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel),
            timeout=180
        )
        league_links[msg.id] = dm.content
        await inter.user.send("✅ Link saved!")
    except:
        pass

@bot.tree.command(name="endleague", description="End a league")
async def endleague(inter: discord.Interaction):
    await inter.response.send_message("📩 Send League ID.", ephemeral=True)

    def check(m):
        return m.author.id == inter.user.id and m.channel == inter.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        league_id = msg.content.upper()

        if league_id not in league_storage:
            return await inter.followup.send("❌ ID not found!", ephemeral=True)

        data = league_storage[league_id]
        channel = bot.get_channel(data["channel_id"])
        main_msg = await channel.fetch_message(data["msg_id"])
        emb = main_msg.embeds[0]

        if data["status"] == "Recruiting":
            emb.color = discord.Color.red()
            emb.set_field_at(8, name="Status", value="❌ Cancelled")
            await main_msg.edit(embed=emb, view=None)
            await inter.followup.send(f"🚫 League `{league_id}` cancelled.")
        else:
            emb.color = discord.Color.light_grey()
            emb.set_field_at(8, name="Status", value="⚪ Ended")
            await main_msg.edit(embed=emb, view=None)

            await inter.followup.send("📩 Check DMs for result upload.")

            try:
                host = await bot.fetch_user(data["host_id"])
                await host.send(f"🏆 Send result screenshot for `{league_id}`")

                res = await bot.wait_for(
                    'message',
                    check=lambda m: m.author.id == data["host_id"] and m.attachments,
                    timeout=300
                )

                res_chan_id = server_settings.get(inter.guild.id, {}).get('res_chan')
                if res_chan_id:
                    res_chan = bot.get_channel(res_chan_id)
                    emb = discord.Embed(title=f"🏁 Results: {league_id}", color=discord.Color.blue())
                    emb.set_image(url=res.attachments[0].url)
                    emb.add_field(name="Players", value=" ".join([f"<@{p}>" for p in data['player_list']]))
                    await res_chan.send(content=" ".join([f"<@{p}>" for p in data['player_list']]), embed=emb)
            except:
                pass

        del league_storage[league_id]

    except asyncio.TimeoutError:
        await inter.followup.send("⏰ Timed out.", ephemeral=True)

# --- SETUP ---
@bot.tree.command(name="setupleagues")
@app_commands.checks.has_permissions(administrator=True)
async def setupleagues(inter: discord.Interaction, hosting_channel: discord.TextChannel, results_channel: discord.TextChannel, host_role: discord.Role):
    server_settings[inter.guild.id] = {
        "host_chan": hosting_channel.id,
        "res_chan": results_channel.id,
        "host_role": host_role.id
    }
    await inter.response.send_message("✅ Setup complete!", ephemeral=True)

# --- WHISPER ---
@bot.tree.command(name="whisper")
async def whisper(inter: discord.Interaction, player: discord.Member, message: str):
    try:
        await player.send(f"📩 {message}")
        await inter.response.send_message("✅ Sent!", ephemeral=True)
    except:
        await inter.response.send_message("❌ Failed to DM.", ephemeral=True)

# --- MODERATION ---
@bot.command()
@is_staff()
async def b(ctx, m: discord.Member, *, r="None"):
    await m.ban(reason=r)
    await ctx.send(f"✅ Banned {m}")

@bot.command()
@is_staff()
async def t(ctx, m: discord.Member, min: int):
    await m.timeout(datetime.timedelta(minutes=min))
    await ctx.send(f"✅ Muted {m}")

@bot.command()
@is_staff()
async def unt(ctx, m: discord.Member):
    await m.timeout(None)
    await ctx.send(f"✅ Unmuted {m}")

# --- RUN ---
if TOKEN:
    bot.run(TOKEN)
