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

# --- EVENTS ---
@bot.event
async def on_ready():
    # SET BOT STATUS
    activity = discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    
    print(f'✅ MVSD Bot online as {bot.user}')
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

# --- LEAGUE VIEW (PRIVATE THREADS) ---
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
        
        # Create Private Thread on first join if not exists
        if self.thread is None:
            self.thread = await inter.message.create_thread(
                name=f"Match-{self.league_id}",
                type=discord.ChannelType.private_thread
            )
            # Add host manually
            host_user = await bot.fetch_user(self.players[0])
            await self.thread.add_user(host_user)

        # Add new player to thread
        await self.thread.add_user(inter.user)
        
        spots_left = self.max_players - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(5, name="Spots Left", value=f"{spots_left}")

        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")
            await inter.message.edit(embed=embed, view=self)
            await self.thread.send(f"**Match is starting!** Players: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Check private thread: {self.thread.mention}", ephemeral=True)

# --- SLASH COMMANDS ---
@bot.tree.command(name="hostleague", description="Host an MVSD League")
async def hostleague(interaction: discord.Interaction, format: str, type: str, perks: str, region: str):
    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 2)
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

# --- PREFIX COMMANDS (.) ---
@bot.command()
async def s(ctx, index: int = 1):
    channel_id = ctx.channel.id
    if channel_id not in deleted_messages or not deleted_messages[channel_id]:
        return await ctx.send("Nothing to snipe, lilbro 💀")
    if index < 1 or index > len(deleted_messages[channel_id]):
        return await ctx.send(f"Invalid page! Only {len(deleted_messages[channel_id])} saved.")

    data = deleted_messages[channel_id][index - 1]
    embed = discord.Embed(description=data["content"] or "[No Text]", color=discord.Color.orange())
    embed.set_author(name=data["author"], icon_url=data["author_icon"])
    embed.set_footer(text=f"Message {index}/{len(deleted_messages[channel_id])} • {data['time']}")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def cs(ctx):
    deleted_messages[ctx.channel.id] = []
    await ctx.send("✅ Sniped messages cleared!")

# --- START ---
if TOKEN:
    bot.run(TOKEN)

  
