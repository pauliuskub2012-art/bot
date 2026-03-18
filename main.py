import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from datetime import timedelta
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- STORAGE ---
deleted_messages = {}
# Settings: {guild_id: {'staff_role': id, 'host_role': id}}
settings = {}
# League tracking: {thread_id: main_message_id}
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
    sniped_data = {
        "content": message.content,
        "author": message.author.name,
        "author_icon": str(message.author.display_avatar.url),
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }
    deleted_messages[message.channel.id].insert(0, sniped_data)
    if len(deleted_messages[message.channel.id]) > 20:
        deleted_messages[message.channel.id].pop()

# --- PERMISSION CHECKS ---
def is_staff():
    async def predicate(ctx):
        guild_id = ctx.guild.id
        staff_role_id = settings.get(guild_id, {}).get('staff_role')
        if ctx.author.guild_permissions.administrator: return True
        if staff_role_id and discord.utils.get(ctx.author.roles, id=staff_role_id): return True
        await ctx.send("You don't got perms lilbro 💀")
        return False
    return commands.check(predicate)

# --- LEAGUE VIEWS ---
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
        
        # Create Private Thread if it doesn't exist
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(
                    name=f"Match-{self.league_id}",
                    type=discord.ChannelType.private_thread,
                    auto_archive_duration=60
                )
                active_leagues[self.thread.id] = inter.message.id
                # Add the host
                host_member = await inter.guild.fetch_member(self.players[0])
                await self.thread.add_user(host_member)
            except Exception as e:
                return await inter.response.send_message(f"Error creating thread: {e}", ephemeral=True)

        # Add the joining player
        await self.thread.add_user(inter.user)
        
        spots_left = self.max_players - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(5, name="Spots Left", value=f"{spots_left}")

        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")
            await inter.message.edit(embed=embed, view=self)
            await self.thread.send(f"**Match Starting!** Players: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Private thread: {self.thread.mention}", ephemeral=True)

# --- SETUP COMMANDS ---
@bot.tree.command(name="setup", description="Configure bot roles")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction, staff_role: discord.Role, host_role: discord.Role):
    settings[interaction.guild.id] = {
        'staff_role': staff_role.id,
        'host_role': host_role.id
    }
    await interaction.response.send_message(f"✅ Setup complete!\nStaff: {staff_role.mention}\nHosts: {host_role.mention}")

# --- LEAGUE COMMANDS ---
@bot.tree.command(name="leaguehost", description="Host an MVSD League")
async def leaguehost(interaction: discord.Interaction, format: str, type: str, perks: str, region: str):
    # Permission Check
    guild_id = interaction.guild.id
    host_role_id = settings.get(guild_id, {}).get('host_role')
    if not interaction.user.guild_permissions.administrator:
        if not host_role_id or not discord.utils.get(interaction.user.roles, id=host_role_id):
            return await interaction.response.send_message("Only League Hosts can do this!", ephemeral=True)

    max_p = {"2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    league_id = random.randint(100000, 999999)
    now = datetime.datetime.now().strftime("%d %B %Y %H:%M")

    embed = discord.Embed(title="🎮 League Hosted", color=discord.Color.dark_grey())
    embed.description = f"**League ID: {league_id}**"
    embed.add_field(name="Format", value=f"`{format}`", inline=True)
    embed.add_field(name="Type", value=f"`{type}`", inline=True)
    embed.add_field(name="Perks", value=f"`{perks}`", inline=True)
    embed.add_field(name="Region", value=f"`{region}`", inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=f"{max_p - 1}", inline=True)
    embed.add_field(name="Hosted By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Active", inline=False)
    embed.add_field(name="Created", value=f"`{now}`", inline=False)
    
    view = JoinView(league_id, max_p, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="endleague", description="End league and close private thread")
async def endleague(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("Use this inside the league thread!", ephemeral=True)

    thread_id = interaction.channel.id
    if thread_id in active_leagues:
        msg_id = active_leagues[thread_id]
        try:
            main_msg = await interaction.channel.parent.fetch_message(msg_id)
            embed = main_msg.embeds[0]
            embed.color = discord.Color.light_grey()
            embed.set_field_at(7, name="Status", value="🔴 Ended")
            await main_msg.edit(embed=embed, view=None)
            del active_leagues[thread_id]
        except: pass

    await interaction.response.send_message("League ended. Thread deleting in 5s...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

# --- PREFIX MODERATION (.) ---
@bot.command()
@is_staff()
async def p(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Purged {amount} messages.", delete_after=3)

@bot.command()
async def s(ctx, index: int = 1):
    cid = ctx.channel.id
    if cid not in deleted_messages or not deleted_messages[cid]: return await ctx.send("Nothing to snipe.")
    data = deleted_messages[cid][index-1]
    embed = discord.Embed(description=data["content"] or "[Media]", color=discord.Color.orange())
    embed.set_author(name=data["author"], icon_url=data["author_icon"])
    await ctx.send(embed=embed)

if TOKEN:
    bot.run(TOKEN)
