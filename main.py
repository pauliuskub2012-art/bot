import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from datetime import timedelta
from keep_alive import keep_alive

# --- KONFIGŪRACIJA ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- SAUGYKLA ---
deleted_messages = {}
warnings = {}
# Saugo ryšį tarp gijos ID ir pagrindinės žinutės ID: {thread_id: message_id}
active_leagues = {}

# --- ĮVYKIAI ---
@bot.event
async def on_ready():
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

# --- LEAGUE VIEWS ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_players, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_players = max_players
        self.players = [host_id]
        self.thread = None
        self.main_msg = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("Tu jau čia!", ephemeral=True)
        
        self.players.append(inter.user.id)
        embed = inter.message.embeds[0]
        
        # Sukuriame privačią giją pirmo prisijungimo metu
        if self.thread is None:
            self.thread = await inter.message.create_thread(
                name=f"Match-{self.league_id}",
                type=discord.ChannelType.private_thread
            )
            # Įrašome giją į sekimo sąrašą
            active_leagues[self.thread.id] = inter.message.id
            # Pridedame hostą
            await self.thread.add_user(await inter.guild.fetch_member(self.players[0]))

        # Pridedame žaidėją į giją
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
        
        await inter.response.send_message(f"✅ Joined! Thread: {self.thread.mention}", ephemeral=True)

# --- SLASH KOMANDOS ---
@bot.tree.command(name="leaguehost", description="Host an MVSD League")
@app_commands.describe(format="Format", type="Swift/War", perks="Perks", region="Region")
@app_commands.choices(format=[
    app_commands.Choice(name="2v2", value="2v2"),
    app_commands.Choice(name="3v3", value="3v3"),
    app_commands.Choice(name="4v4", value="4v4")
], type=[
    app_commands.Choice(name="Swift", value="Swift"),
    app_commands.Choice(name="War", value="War")
], perks=[
    app_commands.Choice(name="Perks", value="Perks"),
    app_commands.Choice(name="No Perks", value="No Perks")
], region=[
    app_commands.Choice(name="EU", value="EU"),
    app_commands.Choice(name="ASIA", value="ASIA"),
    app_commands.Choice(name="NA", value="NA"),
    app_commands.Choice(name="AFRICA", value="AFRICA"),
    app_commands.Choice(name="AMERICA", value="AMERICA")
])
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

@bot.tree.command(name="endleague", description="End the league and close thread")
async def endleague(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("Naudok šią komandą match thread'e!", ephemeral=True)

    thread_id = interaction.channel.id
    if thread_id in active_leagues:
        msg_id = active_leagues[thread_id]
        try:
            # Surandame pagrindinę žinutę ir ją redaguojame
            parent_channel = interaction.channel.parent
            main_msg = await parent_channel.fetch_message(msg_id)
            embed = main_msg.embeds[0]
            embed.color = discord.Color.light_grey()
            embed.set_field_at(7, name="Status", value="🔴 Ended")
            
            # Išjungiame mygtukus
            await main_msg.edit(embed=embed, view=None)
            del active_leagues[thread_id]
        except:
            print("Nepavyko redaguoti pagrindinės žinutės.")

    await interaction.response.send_message("Lyga baigta. Gija bus ištrinta po 5s.")
    await asyncio.sleep(5)
    await interaction.channel.delete()

# --- MODERACIJA (.) ---
@bot.command()
@commands.has_permissions(manage_messages=True)
async def p(ctx, amount: int):
    """Ištrinti žinutes (Purge)"""
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Ištrinta {len(deleted)-1} žinučių.", delete_after=3)

@bot.command()
async def s(ctx, index: int = 1):
    """Snipe ištrintas žinutes"""
    cid = ctx.channel.id
    if cid not in deleted_messages or not deleted_messages[cid]: return await ctx.send("Nėra ką snipe.")
    data = deleted_messages[cid][index-1]
    embed = discord.Embed(description=data["content"] or "[No Text]", color=discord.Color.orange())
    embed.set_author(name=data["author"], icon_url=data["author_icon"])
    await ctx.send(embed=embed)

if TOKEN:
    bot.run(TOKEN)

