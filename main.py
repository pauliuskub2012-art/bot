import discord
from discord.ext import commands
from discord import app_commands
import os, random, datetime, asyncio, re
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
async def log_action(guild, message, title="Action"):
    chan_id = server_settings.get(guild.id, {}).get("logs")
    if chan_id:
        channel = bot.get_channel(chan_id)
        if channel:
            embed = discord.Embed(title=title, description=message, color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
            await channel.send(embed=embed)

# --- HELP COMMAND ---
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📜 Help", color=discord.Color.blue())
    for cmd in bot.commands:
        if cmd.hidden:
            continue
        embed.add_field(name=f".{cmd.name}", value=cmd.help or "No description", inline=False)
    await ctx.send(embed=embed)

# --- SETUP COMMANDS ---
@bot.command(help="Set logs channel")
async def setup_logs(ctx, channel: discord.TextChannel):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)
    server_settings.setdefault(ctx.guild.id, {})["logs"] = channel.id
    await ctx.send(f"📜 Logs set to {channel.mention}")

@bot.command(help="Set jail role")
async def setup_jail(ctx, role: discord.Role):
    if not has_perm(ctx, "manage_guild"):
        return await no_perm(ctx)
    server_settings.setdefault(ctx.guild.id, {})["jail"] = role.id
    await ctx.send(f"🚔 Jail role set to {role.mention}")
    await log_action(ctx.guild, f"{ctx.author.mention} set jail role {role.name}", "Jail Setup")

def get_jail_role(guild):
    role_id = server_settings.get(guild.id, {}).get("jail")
    return guild.get_role(role_id) if role_id else None

# --- JAIL SYSTEM ---
@bot.command(help="Jail a user")
async def jail(ctx, member: discord.Member):
    if not has_perm(ctx, "moderate_members"):
        return await no_perm(ctx)
    role = get_jail_role(ctx.guild)
    if not role:
        return await ctx.send("❌ Use .setup_jail first")
    await member.add_roles(role)
    await ctx.send(f"🚔 {member.mention} jailed")
    await log_action(ctx.guild, f"{ctx.author.mention} jailed {member.mention}", "Jail")

# --- RANK SYSTEM ---
@bot.tree.command(name="ranksetup", description="Set rank channel where messages like '@user PR6' update roles silently")
async def ranksetup(inter: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("No permission", ephemeral=True)
    server_settings.setdefault(inter.guild.id, {})["rank_channel"] = channel.id
    await inter.response.send_message("✅ Rank system configured", ephemeral=True)
    await log_action(inter.guild, f"{inter.user.mention} set rank channel to {channel.mention}", "Rank Setup")

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
        name = role.name.upper()
        if name.startswith("PR"):
            try:
                num = int(name.replace("PR", ""))
                if 1 <= num <= 10:
                    pr_roles.append(role)
                    if num == rank:
                        new_role = role
            except:
                continue
    if not new_role:
        return
    remove_roles = [r for r in pr_roles if r in member.roles]
    if remove_roles:
        await member.remove_roles(*remove_roles)
    await member.add_roles(new_role)
    await log_action(message.guild, f"{message.author.mention} set {member.mention} to PR{rank}", "Rank Update")

# --- LEAGUE SYSTEM ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id, link):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.link = link
        self.closed = False  # League status

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, btn):
        if self.closed:
            return await inter.response.send_message("❌ League has ended.", ephemeral=True)
        if inter.user.id in self.players:
            return await inter.response.send_message("Already joined", ephemeral=True)
        if len(self.players) >= self.max_p:
            return await inter.response.send_message("League full", ephemeral=True)
        self.players.append(inter.user.id)
        league_storage[self.league_id]["players"] = self.players
        await inter.response.send_message("✅ Joined", ephemeral=True)

    def close_league(self):
        self.closed = True
        for item in self.children:
            item.disabled = True

# --- LEAGUE COMMANDS ---
@bot.tree.command(name="leaguehost", description="Host a league")
async def leaguehost(inter: discord.Interaction, format: str, perks: bool, match_type: str, region: str, link: str):
    formats = {"1v1":2,"2v2":4,"3v3":6,"4v4":8}
    if format not in formats:
        return await inter.response.send_message("Invalid format", ephemeral=True)
    max_p = formats[format]
    league_id = "".join(random.choice("ABC123XYZ") for _ in range(6))
    view = JoinView(league_id, max_p, inter.user.id, link)
    embed = discord.Embed(title=f"{format} | {match_type}", color=discord.Color.green())
    embed.add_field(name="ID", value=league_id)
    embed.add_field(name="Players", value=f"1/{max_p}")
    embed.add_field(name="Region", value=region)
    msg = await inter.response.send_message(embed=embed, view=view)
    league_storage[league_id] = {"players":[inter.user.id], "view": view, "message": msg}

    await log_action(inter.guild, f"{inter.user.mention} hosted league {league_id}", "League Host")

@bot.tree.command(name="endleague", description="End league and reward players")
async def endleague(inter: discord.Interaction, league_id: str):
    league_id = league_id.upper()
    if league_id not in league_storage:
        return await inter.response.send_message("❌ League not found", ephemeral=True)
    
    # Update weekly activity
    for p in league_storage[league_id]["players"]:
        weekly_activity[p] = weekly_activity.get(p, 0) + 1
    
    # Close league so buttons can't be clicked
    view = league_storage[league_id].get("view")
    if view:
        view.close_league()
        msg = league_storage[league_id].get("message")
        if msg:
            try:
                await msg.edit(view=view)
            except:
                pass
    
    del league_storage[league_id]
    await inter.response.send_message("🏁 League ended. No more joins allowed.")
    await log_action(inter.guild, f"{inter.user.mention} ended league {league_id}", "League End")

@bot.tree.command(name="mvpannounce", description="Announce most active player")
async def mvpannounce(inter: discord.Interaction):
    if not weekly_activity:
        return await inter.response.send_message("No data", ephemeral=True)
    mvp = max(weekly_activity, key=weekly_activity.get)
    user = await bot.fetch_user(mvp)
    await inter.response.send_message(f"🌟 MVP: {user.mention}")
    weekly_activity.clear()
    await log_action(inter.guild, f"MVP announced: {user.mention}", "MVP")

# --- MODERATION ---
@bot.command(help="Ban user")
async def b(ctx, member: discord.Member):
    if not has_perm(ctx, "ban_members"):
        return await no_perm(ctx)
    await member.ban()
    await ctx.send("🔨 Banned")
    await log_action(ctx.guild, f"{ctx.author.mention} banned {member.mention}", "Ban")

@bot.command(help="Kick user")
async def k(ctx, member: discord.Member):
    if not has_perm(ctx, "kick_members"):
        return await no_perm(ctx)
    await member.kick()
    await ctx.send("👢 Kicked")
    await log_action(ctx.guild, f"{ctx.author.mention} kicked {member.mention}", "Kick")

# --- REST OF COMMANDS (WARN, UNWARN, ROLES, TIMEOUT, PURGE) ---
# The previous commands remain the same as in your last code
# (w, unw, r, unb, t, unt, p)

# --- READY ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready")
keep_alive()
bot.run(TOKEN)
