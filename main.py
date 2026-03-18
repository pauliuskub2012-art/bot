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
settings = {}  # {guild_id: {'staff_role': id, 'host_role': id, 'jail_role': id, 'jail_channel': id}}
active_leagues = {}

# --- EVENTS ---
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f'✅ MVSD Bot is online as {bot.user}')
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

# --- LEAGUE VIEW (FIXED THREADS) ---
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
        
        # FIX: Ensure Thread Creation
        if self.thread is None:
            try:
                # Bot creates a PRIVATE thread
                self.thread = await inter.channel.create_thread(
                    name=f"Match-{self.league_id}",
                    type=discord.ChannelType.private_thread
                )
                active_leagues[self.thread.id] = inter.message.id
                # Add the Host immediately
                host_member = await inter.guild.fetch_member(self.players[0])
                await self.thread.add_user(host_member)
            except Exception as e:
                print(f"Thread Error: {e}")
                return await inter.response.send_message("Missing 'Manage Threads' permission!", ephemeral=True)

        # Add the new player to the thread
        await self.thread.add_user(inter.user)
        
        spots = self.max_players - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(5, name="Spots Left", value=f"{spots}")

        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")
            await inter.message.edit(embed=embed, view=self)
            await self.thread.send(f"**Match Starting!**\nParticipants: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Check private thread: {self.thread.mention}", ephemeral=True)

# --- COMMANDS ---
@bot.tree.command(name="setup", description="Set staff and host roles")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction, staff_role: discord.Role, host_role: discord.Role):
    settings[interaction.guild.id] = {'staff_role': staff_role.id, 'host_role': host_role.id}
    await interaction.response.send_message(f"✅ Roles configured.")

@bot.tree.command(name="jail_setup", description="Automatically setup Jail role and channel")
@app_commands.checks.has_permissions(administrator=True)
async def jail_setup(interaction: discord.Interaction):
    guild = interaction.guild
    # 1. Create Jail Role
    jail_role = await guild.create_role(name="Jailed", color=discord.Color.darker_grey())
    # 2. Create Jail Channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        jail_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    jail_channel = await guild.create_text_channel("jail-cell", overwrites=overwrites)
    
    # Save to settings
    if guild.id not in settings: settings[guild.id] = {}
    settings[guild.id]['jail_role'] = jail_role.id
    settings[guild.id]['jail_channel'] = jail_channel.id
    
    await interaction.response.send_message(f"✅ Jail setup complete! Role: {jail_role.mention}, Channel: {jail_channel.mention}")

@bot.tree.command(name="leaguehost", description="Host an MVSD League")
async def leaguehost(interaction: discord.Interaction, format: str, type: str, perks: str, region: str):
    max_p = {"2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    league_id = random.randint(100000, 999999)
    now = datetime.datetime.now().strftime("%d %B %Y %H:%M")

    embed = discord.Embed(title="🎮 League Hosted", color=discord.Color.dark_grey())
    embed.description = f"**League ID: {league_id}**"
    embed.add_field(name="Match Format", value=f"`{format}`", inline=True)
    embed.add_field(name="Match Type", value=f"`{type}`", inline=True)
    embed.add_field(name="Perks", value=f"`{perks}`", inline=True)
    embed.add_field(name="Region", value=f"`{region}`", inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=f"{max_p - 1}", inline=True)
    embed.add_field(name="Hosted By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Active", inline=False)
    embed.add_field(name="Created", value=f"`{now}`", inline=False)
    
    view = JoinView(league_id, max_p, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

# --- MODERATION ---
@bot.command()
async def jail(ctx, member: discord.Member):
    role_id = settings.get(ctx.guild.id, {}).get('jail_role')
    role = ctx.guild.get_role(role_id)
    if role:
        await member.add_roles(role)
        await ctx.send(f"🔒 {member.mention} has been sent to jail.")

@bot.command()
async def unjail(ctx, member: discord.Member):
    role_id = settings.get(ctx.guild.id, {}).get('jail_role')
    role = ctx.guild.get_role(role_id)
    if role:
        await member.remove_roles(role)
        await ctx.send(f"🔓 {member.mention} has been released.")

if TOKEN: bot.run(TOKEN)

