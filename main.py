import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- STORAGE ---
deleted_messages = {}
guild_settings = {} # {guild_id: {'staff_role': id, 'jail_role': id}}
warnings = {} # {user_id: [reasons]}
active_leagues = {} # {thread_id: league_data}

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f'✅ MVSD Bot online as {bot.user}')
    keep_alive()
    await bot.tree.sync()

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    if message.channel.id not in deleted_messages:
        deleted_messages[message.channel.id] = []
    sniped_data = {"content": message.content, "author": message.author.name, "author_icon": str(message.author.display_avatar.url), "time": datetime.datetime.now().strftime("%H:%M:%S")}
    deleted_messages[message.channel.id].insert(0, sniped_data)
    if len(deleted_messages[message.channel.id]) > 20: deleted_messages[message.channel.id].pop()

# --- PERMISSION CHECK ---
@bot.check
async def check_permissions(ctx):
    if ctx.command.name in ['s']: return True # Public command
    staff_id = guild_settings.get(ctx.guild.id, {}).get('staff_role')
    if ctx.author.guild_permissions.administrator or (staff_id and discord.utils.get(ctx.author.roles, id=staff_id)):
        return True
    await ctx.send("You don't got perms lilbro 💀")
    return False

# --- SLASH COMMANDS ---
@bot.tree.command(name="setupcommands", description="Set the staff role")
@app_commands.checks.has_permissions(administrator=True)
async def setupcommands(interaction: discord.Interaction, staff_role: discord.Role, jail_role: discord.Role):
    guild_settings[interaction.guild.id] = {'staff_role': staff_role.id, 'jail_role': jail_role.id}
    await interaction.response.send_message(f"✅ Setup complete. Staff: {staff_role.name}, Jail Role: {jail_role.name}")

@bot.tree.command(name="hostleague", description="Host MVSD League")
async def hostleague(interaction: discord.Interaction, format: str, region: str):
    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 2)
    embed = discord.Embed(title=f"⚔️ {format} League - {region}", color=discord.Color.blue())
    embed.add_field(name="Players", value=f"1/{max_p}")
    
    # --- UPDATED LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_players, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_players = max_players
        self.players = [host_id]
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        embed = inter.message.embeds[0]
        
        # Updating fields to match your image exactly
        spots_left = self.max_players - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(5, name="Spots Left", value=f"{spots_left}")

        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")
            await inter.message.edit(embed=embed, view=self)
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! {spots_left} spots left.", ephemeral=True)

    embed = discord.Embed(title="🎮 League Hosted", color=discord.Color.dark_grey())
    embed.description = f"**League ID: {league_id}**"
    
    # Row 1 (Matching your image)
    embed.add_field(name="Match Format", value=f"`{format}`", inline=True)
    embed.add_field(name="Match Type", value=f"`{type}`", inline=True)
    embed.add_field(name="Perks", value=f"`{perks}`", inline=True)
    
    # Row 2 (Matching your image)
    embed.add_field(name="Region", value=f"`{region}`", inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=f"{max_p - 1}", inline=True)
    
    # Row 3 (Matching your image)
    embed.add_field(name="Hosted By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Active", inline=False)
    embed.add_field(name="Created", value=f"`{now}`", inline=False)
    
    embed.set_footer(text=f"League ID: {league_id}")

@bot.tree.command(name="hostleague", description="Host an MVSD League")
async def hostleague(interaction: discord.Interaction, format: str, type: str, perks: str, region: str):
    # ČIA TURI BŪTI TAVO EMBED KODAS (kurį rašėme anksčiau)
    
    # Šios eilutės PRIVALO turėti tarpus iš kairės:
    view = JoinView(league_id, max_p, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.command()
async def k(ctx, member: discord.Member, *, reason="No reason"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 Kicked {member.display_name}. Reason: {reason}")

@bot.command()
async def b(ctx, member: discord.Member, *, reason="No reason"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 Banned {member.display_name}. Reason: {reason}")

@bot.command()
async def r(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.find(lambda r: role_name.lower() in r.name.lower(), ctx.guild.roles)
    if role:
        if role in member.roles: await member.remove_roles(role)
        else: await member.add_roles(role)
        await ctx.send(f"✅ Updated role: {role.name}")

@bot.command()
async def m(ctx, member: discord.Member, time: str = "10m"):
    minutes = int(time[:-1]) if 'm' in time else 10
    await member.timeout(datetime.timedelta(minutes=minutes))
    await ctx.send(f"🔇 Muted {member.mention} for {time}.")

@bot.command()
async def jail(ctx, member: discord.Member):
    role_id = guild_settings.get(ctx.guild.id, {}).get('jail_role')
    role = ctx.guild.get_role(role_id)
    if role:
        await member.add_roles(role)
        await ctx.send(f"🔒 {member.mention} has been jailed.")

@bot.command()
async def unjail(ctx, member: discord.Member):
    role_id = guild_settings.get(ctx.guild.id, {}).get('jail_role')
    role = ctx.guild.get_role(role_id)
    if role:
        await member.remove_roles(role)
        await ctx.send(f"🔓 {member.mention} has been unjailed.")

@bot.command()
async def s(ctx, index: int = 1):
    cid = ctx.channel.id
    if cid not in deleted_messages or not deleted_messages[cid]: return await ctx.send("Nothing to snipe, lilbro 💀")
    data = deleted_messages[cid][index-1]
    embed = discord.Embed(description=data["content"], color=discord.Color.orange())
    embed.set_author(name=data["author"], icon_url=data["author_icon"])
    await ctx.send(embed=embed)

if TOKEN: bot.run(TOKEN)

  
