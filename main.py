import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, re
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# --- STORAGE ---
league_storage = {}
server_settings = {}
weekly_activity = {}
warns = {}

# --- PERMS ---
def has_perm(ctx, perm):
    return getattr(ctx.author.guild_permissions, perm)

async def no_perm(ctx):
    await ctx.send("🚫 No permission.")

# --- LOGGING ---
async def log_action(guild, message, title="Action"):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if chan_id:
        channel = guild.get_channel(chan_id)
        if channel:
            embed = discord.Embed(
                title=title,
                description=message,
                color=discord.Color.blurple(),
                timestamp=datetime.datetime.utcnow()
            )
            await channel.send(embed=embed)

# --- SETUP ---
@bot.command()
async def setup_logs(ctx, channel: discord.TextChannel):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)
    server_settings.setdefault(ctx.guild.id, {})["logs"] = channel.id
    await ctx.send(f"📜 Logs set to {channel.mention}")

@bot.command()
async def setup_jail(ctx, role: discord.Role):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)
    server_settings.setdefault(ctx.guild.id, {})["jail"] = role.id
    await ctx.send(f"🚔 Jail role set to {role.mention}")

def get_jail_role(guild):
    role_id = server_settings.get(guild.id, {}).get("jail")
    return guild.get_role(role_id) if role_id else None

# --- JAIL ---
@bot.command()
async def jail(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)
    role = get_jail_role(ctx.guild)
    if not role:
        return await ctx.send("❌ Setup jail first")
    await member.add_roles(role)
    await ctx.send(f"🚔 {member.mention} jailed")

# --- RANK SYSTEM FIXED ---
@bot.tree.command(name="ranksetup")
async def ranksetup(inter: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("No permission", ephemeral=True)
    server_settings.setdefault(inter.guild.id, {})["rank_channel"] = channel.id
    await inter.response.send_message("✅ Rank setup done", ephemeral=True)

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
    match = re.search(r'\bPR\s*(\d+)\b', message.content.upper())
    if not match:
        return

    rank = int(match.group(1))
    if not (1 <= rank <= 10):
        return

    new_role = None
    pr_roles = []

    for role in message.guild.roles:
        if role.name.upper().startswith("PR"):
            pr_roles.append(role)
            try:
                if int(re.findall(r'\d+', role.name)[0]) == rank:
                    new_role = role
            except:
                continue

    if not new_role:
        return

    remove_roles = [r for r in member.roles if r in pr_roles]
    if remove_roles:
        await member.remove_roles(*remove_roles)

    await member.add_roles(new_role)

# --- LEAGUE ROLE SETUP ---
@bot.tree.command(name="leaguesetup", description="Set role required to host leagues")
async def leaguesetup(inter: discord.Interaction, role: discord.Role):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("❌ No permission", ephemeral=True)

    server_settings.setdefault(inter.guild.id, {})["league_role"] = role.id
    await inter.response.send_message(f"✅ League role set to {role.mention}", ephemeral=True)

# --- LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id):
        super().__init__(timeout=None)
        self.league_id = league_id

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button):
        league = league_storage.get(self.league_id)
        if not league:
            return await inter.response.send_message("❌ Not found", ephemeral=True)

        if league["status"] == "ended":
            return await inter.response.send_message("🔴 Ended", ephemeral=True)

        if inter.user.id in league["players"]:
            return await inter.response.send_message("Already joined", ephemeral=True)

        if len(league["players"]) >= league["max"]:
            league["status"] = "full"
            await update_embed(inter.guild, self.league_id)
            return await inter.response.send_message("🔴 Full", ephemeral=True)

        league["players"].append(inter.user.id)
        league["status"] = "ongoing" if len(league["players"]) < league["max"] else "full"

        await update_embed(inter.guild, self.league_id)
        await inter.response.send_message("✅ Joined", ephemeral=True)

async def update_embed(guild, league_id):
    league = league_storage[league_id]
    msg = league["msg"]

    status_map = {
        "looking": "🟢",
        "ongoing": "🟠",
        "full": "🔴",
        "ended": "🔴"
    }

    embed = discord.Embed(title="League", color=discord.Color.green())
    embed.add_field(name="ID", value=f"{league_id} {status_map[league['status']]}")
    embed.add_field(name="Players", value=f"{len(league['players'])}/{league['max']}")
    embed.add_field(name="Link", value=league["link"])

    await msg.edit(embed=embed)

# --- LEAGUE HOST ---
@bot.tree.command(name="leaguehost")
async def leaguehost(inter: discord.Interaction, format: str, link: str):
    settings = server_settings.get(inter.guild.id, {})
    role_id = settings.get("league_role")

    if role_id:
        role = inter.guild.get_role(role_id)
        if role not in inter.user.roles:
            return await inter.response.send_message("❌ No permission", ephemeral=True)

    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}
    if format not in formats:
        return await inter.response.send_message("❌ Invalid format", ephemeral=True)

    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))
    msg = await inter.channel.send("Creating league...")

    league_storage[league_id] = {
        "players":[inter.user.id],
        "max":formats[format],
        "status":"looking",
        "link":link,
        "msg":msg
    }

    await update_embed(inter.guild, league_id)
    await msg.edit(view=JoinView(league_id))

    await inter.response.send_message(f"✅ League {league_id} created", ephemeral=True)

# --- END LEAGUE ---
@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction, league_id: str):
    league = league_storage.get(league_id.upper())
    if not league:
        return await inter.response.send_message("❌ Not found", ephemeral=True)

    league["status"] = "ended"
    await update_embed(inter.guild, league_id)

    await inter.response.send_message("🏁 Ended")

# --- MOD COMMANDS ---
@bot.command()
async def b(ctx, member: discord.Member):
    await member.ban()
    await ctx.send("Banned")

@bot.command()
async def k(ctx, member: discord.Member):
    await member.kick()
    await ctx.send("Kicked")

@bot.command()
async def w(ctx, member: discord.Member):
    warns[member.id] = warns.get(member.id,0)+1
    await ctx.send("Warned")

@bot.command()
async def unw(ctx, member: discord.Member):
    warns[member.id] = max(0,warns.get(member.id,0)-1)
    await ctx.send("Unwarned")

@bot.command()
async def r(ctx, member: discord.Member, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if role:
        await member.add_roles(role)
        await ctx.send("Role added")

@bot.command()
async def unb(ctx, user: discord.User):
    await ctx.guild.unban(user)
    await ctx.send("Unbanned")

@bot.command()
async def t(ctx, member: discord.Member):
    await member.timeout(datetime.timedelta(minutes=10))
    await ctx.send("Timed out")

@bot.command()
async def unt(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send("Timeout removed")

@bot.command()
async def p(ctx, count: int):
    await ctx.channel.purge(limit=count)

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")

keep_alive()
bot.run(TOKEN)
