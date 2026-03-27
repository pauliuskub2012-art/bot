import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, re
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

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
async def log_action(guild, message, title="Log"):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if not chan_id:
        return

    channel = guild.get_channel(chan_id)
    if not channel:
        return

    embed = discord.Embed(
        title=f"📌 {title}",
        description=message,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )

    await channel.send(embed=embed)

# --- SETUP COMMANDS (FIXED) ---
@bot.command()
@commands.has_permissions(manage_guild=True)
async def setup_logs(ctx, channel: discord.TextChannel):
    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["logs"] = channel.id
    await ctx.send(f"✅ Logs channel set to {channel.mention}")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setup_jail(ctx, role: discord.Role):
    server_settings.setdefault(ctx.guild.id, {})
    server_settings[ctx.guild.id]["jail"] = role.id
    await ctx.send(f"✅ Jail role set to {role.mention}")

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
        return await ctx.send("❌ Use .setup_jail first")

    await member.add_roles(role)
    await ctx.send(f"🚔 {member.mention} jailed")
    await log_action(ctx.guild, f"{ctx.author} jailed {member}", "Jail")

# --- WARN SYSTEM (FIXED) ---
@bot.command()
async def w(ctx, member: discord.Member, *, reason="No reason"):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    warns.setdefault(member.id, []).append(reason)

    await ctx.send(f"⚠️ {member.mention} warned ({len(warns[member.id])})")
    await log_action(ctx.guild, f"{ctx.author} warned {member} | {reason}", "Warn")

@bot.command()
async def unw(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)

    if member.id not in warns or not warns[member.id]:
        return await ctx.send("❌ No warns")

    warns[member.id].pop()
    await ctx.send(f"✅ Warn removed ({len(warns.get(member.id, []))})")

@bot.command(name="warns")
async def warns_cmd(ctx, member: discord.Member):
    user_warns = warns.get(member.id, [])
    if not user_warns:
        return await ctx.send("✅ No warns")

    msg = "\n".join([f"{i+1}. {w}" for i, w in enumerate(user_warns)])
    await ctx.send(f"⚠️ Warns for {member}:\n{msg}")

# --- RANK SYSTEM (FIXED SWITCHING) ---
@bot.tree.command(name="ranksetup", description="Set channel for PR ranking system")
async def ranksetup(inter: discord.Interaction, channel: discord.TextChannel):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("❌ No permission", ephemeral=True)

    server_settings.setdefault(inter.guild.id, {})["rank_channel"] = channel.id
    await inter.response.send_message("✅ Rank system configured", ephemeral=True)

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

    # REMOVE OLD PR ROLES
    remove_roles = [r for r in member.roles if r in pr_roles]
    if remove_roles:
        await member.remove_roles(*remove_roles)

    # ADD NEW
    await member.add_roles(new_role)

# --- LEAGUE SETUP ---
@bot.tree.command(name="leaguesetup", description="Set role required to host leagues")
async def leaguesetup(inter: discord.Interaction, role: discord.Role):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("❌ No permission", ephemeral=True)

    server_settings.setdefault(inter.guild.id, {})["league_role"] = role.id
    await inter.response.send_message(f"✅ League role set to {role.mention}", ephemeral=True)

# --- EMBED UPDATE (PROFESSIONAL + FIXED STATUS) ---
async def update_embed(guild, league_id):
    league = league_storage[league_id]
    msg = league["msg"]

    current = len(league["players"])
    max_p = league["max"]

    if league["status"] == "ended":
        status = "🔴 Ended"
    elif current >= max_p:
        status = "🔴 Full"
    else:
        status = "🟢 Looking"

    embed = discord.Embed(
        title="🎮 League Lobby",
        color=discord.Color.dark_green()
    )

    embed.add_field(name="🆔 League ID", value=f"`{league_id}` {status}", inline=False)
    embed.add_field(name="👥 Players", value=f"{current}/{max_p}", inline=True)
    embed.add_field(name="🌍 Region", value=league["region"], inline=True)
    embed.add_field(name="⚔️ Match Type", value=league["match_type"], inline=True)
    embed.add_field(name="✨ Perks", value=league["perks"], inline=True)
    embed.add_field(name="🔗 Access", value="Sent via DM 📩", inline=False)

    embed.set_footer(text="Click the button below to join")

    await msg.edit(embed=embed)

# --- JOIN BUTTON ---
class JoinView(discord.ui.View):
    def __init__(self, league_id):
        super().__init__(timeout=None)
        self.league_id = league_id

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button):
        league = league_storage[self.league_id]

        if league["status"] == "ended":
            return await inter.response.send_message("🔴 League ended", ephemeral=True)

        if inter.user.id in league["players"]:
            return await inter.response.send_message("Already joined", ephemeral=True)

        if len(league["players"]) >= league["max"]:
            league["status"] = "full"
            await update_embed(inter.guild, self.league_id)
            return await inter.response.send_message("🔴 League full", ephemeral=True)

        league["players"].append(inter.user.id)

        # FIXED STATUS LOGIC
        if len(league["players"]) >= league["max"]:
            league["status"] = "full"
        else:
            league["status"] = "looking"

        await update_embed(inter.guild, self.league_id)

        try:
            await inter.user.send(f"🎮 League {self.league_id}\n🔗 {league['link']}")
        except:
            pass

        await inter.response.send_message("✅ Joined! Check your DMs", ephemeral=True)

# --- LEAGUE HOST ---
@bot.tree.command(name="leaguehost", description="Create a new league lobby")
@app_commands.describe(
    format="1v1 / 2v2 / 3v3 / 4v4",
    perks="Enable perks?",
    match_type="Ranked / Casual / Tournament",
    region="EU / NA / etc",
    link="Private match link"
)
async def leaguehost(inter: discord.Interaction, format: str, perks: bool, match_type: str, region: str, link: str):

    settings = server_settings.get(inter.guild.id, {})
    role_id = settings.get("league_role")

    if role_id:
        role = inter.guild.get_role(role_id)
        if role not in inter.user.roles:
            return await inter.response.send_message("❌ You cannot host leagues", ephemeral=True)

    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}
    if format not in formats:
        return await inter.response.send_message("❌ Invalid format", ephemeral=True)

    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))
    msg = await inter.channel.send("⚙️ Creating league...")

    league_storage[league_id] = {
        "players":[inter.user.id],
        "max":formats[format],
        "status":"looking",
        "format":format,
        "match_type":match_type,
        "region":region,
        "perks":"Enabled" if perks else "Disabled",
        "link":link,
        "msg":msg
    }

    await update_embed(inter.guild, league_id)
    await msg.edit(view=JoinView(league_id))

    await inter.response.send_message(f"✅ League `{league_id}` created", ephemeral=True)

# --- END LEAGUE ---
@bot.tree.command(name="endleague", description="End a league")
async def endleague(inter: discord.Interaction, league_id: str):
    league = league_storage.get(league_id.upper())
    if not league:
        return await inter.response.send_message("❌ League not found", ephemeral=True)

    league["status"] = "ended"
    await update_embed(inter.guild, league_id.upper())

    await inter.response.send_message("🏁 League ended")

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="my boss vJ"
        )
    )

    print(f"✅ Logged in as {bot.user}")

keep_alive()
bot.run(TOKEN)
