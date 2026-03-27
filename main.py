import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, asyncio

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# --- STORAGE ---
league_storage = {}
server_settings = {}
warns = {}

# --- PERMISSION CHECK ---
def has_perm(ctx, perm):
    if getattr(ctx.author.guild_permissions, perm):
        return True
    return False

def no_perm(ctx):
    return ctx.send("🚫 No perms lil bro 😭")

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
            await inter.user.send(f"👋 **League ID:** `{self.league_id}`\n🔗 {self.link}")
        except:
            pass

        # UPDATE COUNT
        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_p}")
        await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message("✅ Joined league", ephemeral=True)

# --- LEAGUE HOST ---
@bot.tree.command(name="leaguehost")
async def leaguehost(inter: discord.Interaction,
                    format: str,
                    perks: bool,
                    match_type: str,
                    region: str,
                    link: str):

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
        "host":inter.user.id,
        "link":link
    }

# --- END LEAGUE ---
@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction, league_id: str):

    league_id = league_id.upper()

    if league_id not in league_storage:
        return await inter.response.send_message("Not found")

    del league_storage[league_id]
    await inter.response.send_message("🏁 League ended")

# ---------------- MODERATION ----------------

@bot.command()
async def setup_logs(ctx, channel: discord.TextChannel):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)

    server_settings[ctx.guild.id] = {"logs": channel.id}
    await ctx.send("✅ Logs set")

def log(ctx, msg):
    chan_id = server_settings.get(ctx.guild.id, {}).get("logs")
    if chan_id:
        chan = bot.get_channel(chan_id)
        asyncio.create_task(chan.send(msg))

# ROLE TOGGLE
@bot.command()
async def r(ctx, member: discord.Member, *, role_name):

    if not has_perm(ctx, "manage_roles"):
        return await no_perm(ctx)

    role = discord.utils.find(lambda r: role_name.lower() in r.name.lower(), ctx.guild.roles)

    if not role:
        return await ctx.send("Role not found")

    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"❌ Removed {role.name}")
        log(ctx, f"{ctx.author} removed {role.name} from {member}")
    else:
        await member.add_roles(role)
        await ctx.send(f"✅ Added {role.name}")
        log(ctx, f"{ctx.author} added {role.name} to {member}")

# TIMEOUT
@bot.command()
async def t(ctx, member: discord.Member, time: int, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    until = datetime.timedelta(seconds=time)
    await member.timeout(until, reason=reason)

    await ctx.send(f"⏳ Timed out {member}")
    log(ctx, f"{member} timed out for {time}s | {reason}")

@bot.command()
async def unt(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    await member.timeout(None)
    await ctx.send("✅ Timeout removed")

# BAN / UNBAN
@bot.command()
async def b(ctx, member: discord.Member):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await member.ban()
    await ctx.send("🔨 Banned")
    log(ctx, f"{member} banned")

@bot.command()
async def unb(ctx, user: discord.User):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)

    await ctx.guild.unban(user)
    await ctx.send("✅ Unbanned")

# KICK
@bot.command()
async def k(ctx, member: discord.Member):
    if not has_perm(ctx, "kick_members"):
        return await no_perm(ctx)

    await member.kick()
    await ctx.send("👢 Kicked")

# PURGE
@bot.command()
async def p(ctx, amount: int):
    if not has_perm(ctx, "manage_messages"):
        return await no_perm(ctx)

    await ctx.channel.purge(limit=amount)
    msg = await ctx.send(f"🧹 Deleted {amount}")
    await asyncio.sleep(2)
    await msg.delete()

# WARNS
@bot.command()
async def w(ctx, member: discord.Member, *, reason="None"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns.setdefault(member.id, 0)
    warns[member.id] += 1

    await ctx.send(f"⚠️ Warned ({warns[member.id]})")
    log(ctx, f"{member} warned | total {warns[member.id]}")

@bot.command()
async def unw(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns[member.id] = 0
    await ctx.send("✅ Warns cleared")

# JAIL SYSTEM
@bot.command()
async def setup_jail(ctx, role: discord.Role, channel: discord.TextChannel):
    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["jail_role"] = role.id
    server_settings[ctx.guild.id]["jail_chan"] = channel.id
    await ctx.send("🔒 Jail setup done")

@bot.command()
async def j(ctx, member: discord.Member, time: int=None):
    if not has_perm(ctx, "manage_roles"):
        return await no_perm(ctx)

    role_id = server_settings.get(ctx.guild.id, {}).get("jail_role")
    role = ctx.guild.get_role(role_id)

    await member.add_roles(role)
    await ctx.send("🔒 Jailed")

    if time:
        await asyncio.sleep(time)
        await member.remove_roles(role)

@bot.command()
async def unj(ctx, member: discord.Member):
    role_id = server_settings.get(ctx.guild.id, {}).get("jail_role")
    role = ctx.guild.get_role(role_id)

    await member.remove_roles(role)
    await ctx.send("🔓 Unjailed")

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")

bot.run(TOKEN)
