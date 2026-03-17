from keep_alive import keep_alive
import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import json
from datetime import datetime, timedelta
import random
import string
import re
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive


# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance with '!' and '.' prefix
bot = commands.Bot(command_prefix=['!', '.'], intents=intents)
deleted_messages = {} # Saugo žinutes pagal kanalus

@bot.event
async def on_message_delete(message):
    if message.author.bot: return # Ignoruoti botus
    
    if message.channel.id not in deleted_messages:
        deleted_messages[message.channel.id] = []
    
    # Pridedame žinutę į sąrašo pradžią
    sniped_data = {
        "content": message.content,
        "author": message.author.name,
        "author_icon": str(message.author.display_avatar.url),
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }
    deleted_messages[message.channel.id].insert(0, sniped_data)
    
    # Saugome tik paskutines 20 ištrintų žinučių tame kanale
    if len(deleted_messages[message.channel.id]) > 20:
        deleted_messages[message.channel.id].pop()

class JoinView(discord.ui.View):
    def __init__(self, league_id, max_players, host):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_players = max_players
        self.players = [host.id]
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You're already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        
        # Update Embed count
        embed = inter.message.embeds[0]
        embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(2, name="Spots Left", value=f"{self.max_players - len(self.players)}")

        # Create Private Thread on first join
        if self.thread is None:
            # Create a PRIVATE thread (type=discord.ChannelType.private_thread)
            self.thread = await inter.message.create_thread(
                name=f"League-{self.league_id}",
                type=discord.ChannelType.private_thread
            )
            # Add Host automatically
            await self.thread.add_user(inter.message.interaction.user)

        # Add the person who clicked "Join" to the private thread
        await self.thread.add_user(inter.user)
        
        # Check if Full
        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(5, name="Status", value="🔴 Full / Match Starting", inline=False)
            await inter.message.edit(embed=embed, view=self)
            await self.thread.send(f"**Match is Starting!**\nPlayers: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Check the private thread: {self.thread.mention}", ephemeral=True)

# ========== IN-MEMORY STORAGE ==========

# League storage: keyed by league_id
leagues = {}

# Guild settings: keyed by guild_id
guild_settings = {}

# Stores original roles for jailed users: {guild_id: {user_id: [role_ids]}}
jail_store = {}

# Active Guess The Number games: {channel_id: {'number': int, 'prize': str}}
gtn_games = {}

# Warning storage: {guild_id: {user_id: [{'reason': str, 'mod': str, 'ts': str}]}}
warnings = {}

# Guesser points: {guild_id: {user_id: int}}
guesser_points = {}

# Active guesser games: {channel_id: {'type': 'map'|'weapon', 'answer': str, 'aliases': [str], 'image': str}}
active_guesser = {}

# ── MVSD Guesser Data ──────────────────────────────────────────────────────────
# Replace image URLs with actual hosted images (Discord CDN, Imgur, etc.)

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- MVSD DATABASE (Maps & Weapons) ---
# Replace the 'image' URLs with actual MVSD screenshot links
MAPS_DATA = {
    'Refinery': {'image': 'https://i.imgur.com/placeholder1.png', 'aliases': ['ref']},
    'Clown': {'image': 'https://i.imgur.com/placeholder2.png', 'aliases': ['clown']},
    'Library': {'image': 'https://i.imgur.com/placeholder3.png', 'aliases': ['lib']},
    'Barn': {'image': 'https://i.imgur.com/placeholder4.png', 'aliases': []},
    'Ship': {'image': 'https://i.imgur.com/placeholder5.png', 'aliases': []},
}

WEAPONS_DATA = {
    'Winx': {'image': 'https://i.imgur.com/placeholder6.png', 'aliases': ['winx set']},
    'Mermaid': {'image': 'https://i.imgur.com/placeholder7.png', 'aliases': ['mermaid']},
    'Celestial': {'image': 'https://i.imgur.com/placeholder8.png', 'aliases': []},
    'Dragonfire': {'image': 'https://i.imgur.com/placeholder9.png', 'aliases': ['df']},
}

class JoinView(discord.ui.View):
    def __init__(self, max_players, host_id):
        super().__init__(timeout=None)
        self.max_players = max_players
        self.players = [host_id]

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        
            @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        
        # Svarbu: visos šios eilutės turi turėti lygiai 8 tarpus kairėje
        if len(self.players) >= self.max_players:
            button.disabled = True
            # Čia turi būti tavo gijų kūrimo logika
            await inter.response.send_message("League is full! Starting...", ephemeral=True)
        else:
            await inter.response.send_message("Joined!", ephemeral=True)

        else:
            embed = inter.message.embeds[0]
            embed.set_field_at(1, name="Players", value=f"{len(self.players)}/{self.max_players}")
            await inter.message.edit(embed=embed, view=self)
            
            await inter.response.send_message("Joined!", ephemeral=True)

@bot.command()
async def s(ctx, index: int = 1):
    """Show deleted messages. Usage: .s 1, .s 2 etc."""
    channel_id = ctx.channel.id
    if channel_id not in deleted_messages or not deleted_messages[channel_id]:
        return await ctx.send("There are no deleted messages in this channel, lilbro 💀")

    # Patikriname, ar puslapis egzistuoja
    if index < 1 or index > len(deleted_messages[channel_id]):
        return await ctx.send(f"Invalid page! Only {len(deleted_messages[channel_id])} messages saved.")

    data = deleted_messages[channel_id][index - 1]
    
    embed = discord.Embed(description=data["content"] or "[No Text Content]", color=discord.Color.orange())
    embed.set_author(name=data["author"], icon_url=data["author_icon"])
    embed.set_footer(text=f"Message {index}/{len(deleted_messages[channel_id])} • Deleted at {data['time']}")
    
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def cs(ctx):
    """Clear all sniped messages in the channel."""
    if ctx.channel.id in deleted_messages:
        deleted_messages[ctx.channel.id] = []
        await ctx.send("✅ Sniped messages history cleared!")
    else:
        await ctx.send("Nothing to clear, lilbro 💀")

# --- GUESSER GAMES ---
@bot.tree.command(name="guessmap", description="Start an MVSD map guessing game")
async def guessmap(interaction: discord.Interaction):
    map_name, data = random.choice(list(MAPS_DATA.items()))
    embed = discord.Embed(title="🖼️ Guess the MVSD Map!", description="You have 60 seconds. Use `.hints` for help!")
    embed.set_image(url=data)
    await interaction.response.send_message(embed=embed)

    def check(m):
        return m.channel == interaction.channel and m.content.lower() in ([map_name.lower()] + data['aliases'])

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        await msg.add_reaction("✅")
        await interaction.followup.send(f"🎉 **{msg.author.name}** guessed it! It was **{map_name}**!")
    except asyncio.TimeoutError:
        await interaction.followup.send(f"⏰ Time's up! The map was **{map_name}**.")

def get_guild_settings(guild_id: int) -> dict:
    """Return settings for a guild, creating defaults if needed."""
    if guild_id not in guild_settings:
        guild_settings[guild_id] = {
            'mod_role_id': None,
            'league_channel_id': None,
            'host_role_id': None,
            'ping_role_id': None,
            'event_role_id': None,
            'mod_log_channel_id': None,
        }
    return guild_settings[guild_id]


def parse_duration(duration_str: str):
    """Parse duration string (e.g., '10m', '1h', '2d') to seconds."""
    match = re.match(r'(\d+)([mhd])', duration_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {'m': 60, 'h': 3600, 'd': 86400}[unit]


def generate_league_id() -> str:
    """Generate a unique 6-digit league ID."""
    return ''.join(random.choices(string.digits, k=6))


def user_has_mod_role(member: discord.Member, settings: dict) -> bool:
    """Return True if member has the configured mod role (or is admin)."""
    if member.guild_permissions.administrator:
        return True
    mod_role_id = settings.get('mod_role_id')
    if mod_role_id is None:
        return True  # No restriction set — anyone can use
    return any(r.id == mod_role_id for r in member.roles)


def user_has_host_role(member: discord.Member, settings: dict) -> bool:
    """Return True if member has the configured host role (or is admin)."""
    if member.guild_permissions.administrator:
        return True
    host_role_id = settings.get('host_role_id')
    if host_role_id is None:
        return True  # No restriction set — anyone can host
    return any(r.id == host_role_id for r in member.roles)


def user_has_event_role(member: discord.Member, settings: dict) -> bool:
    """Return True if member has the Event Manager role, host role, or is admin."""
    if member.guild_permissions.administrator:
        return True
    event_role_id = settings.get('event_role_id')
    host_role_id  = settings.get('host_role_id')
    member_role_ids = {r.id for r in member.roles}
    if event_role_id and event_role_id in member_role_ids:
        return True
    if host_role_id and host_role_id in member_role_ids:
        return True
    # If neither role is configured, allow anyone
    if event_role_id is None and host_role_id is None:
        return True
    return False


# ========== PERMISSION DENIED REPLIES ==========

NO_PERMS_MESSAGES = [
    "You don't got perms lilbro 💀",
    "Nice try, but you're not the boss here! 😭",
    "Bro really thought he was staff 💀",
    "The audacity... No. ❌",
    "Dream on champ, you ain't got the clearance 🤣",
    "Who gave you the confidence to try that? 😂",
    "Lmaooo not you thinking you're staff 💀",
    "You wildin. No perms, no power. 🚫",
]

def no_perms_reply() -> str:
    return random.choice(NO_PERMS_MESSAGES)


# ========== MOD LOG HELPER ==========

LOG_COLORS = {
    'Warning':  discord.Color.yellow(),
    'Timeout':  discord.Color.orange(),
    'Kick':     discord.Color.from_rgb(255, 100, 0),
    'Ban':      discord.Color.red(),
    'Jail':     discord.Color.dark_gray(),
    'Unjail':   discord.Color.green(),
    'Purge':    discord.Color.blurple(),
}

async def send_mod_log(guild: discord.Guild, action: str, fields: dict):
    """Send a professional embed to the configured mod-logs channel."""
    settings = get_guild_settings(guild.id)
    log_channel_id = settings.get('mod_log_channel_id')
    if not log_channel_id:
        return
    channel = guild.get_channel(log_channel_id)
    if not channel:
        return

    color = LOG_COLORS.get(action, discord.Color.blurple())
    action_icons = {
        'Warning': '⚠️', 'Timeout': '⏱️', 'Kick': '👟',
        'Ban': '🔨', 'Jail': '🔒', 'Unjail': '🔓', 'Purge': '🗑️',
    }
    icon = action_icons.get(action, '📋')

    embed = discord.Embed(
        title=f'{icon} {action}',
        color=color,
        timestamp=datetime.utcnow()
    )
    for name, value in fields.items():
        embed.add_field(name=name, value=str(value), inline=True)
    embed.set_footer(text='MVSD Mod Logs')
    await channel.send(embed=embed)


# ========== LEAGUE EMBED ==========

class JoinLeagueView(discord.ui.View):
    def __init__(self, league_id: str):
        super().__init__(timeout=None)
        self.league_id = league_id
        # Unique custom_id per league so Discord can route interactions correctly
        btn = discord.ui.Button(
            label='🎮 Join League',
            style=discord.ButtonStyle.green,
            custom_id=f'join_league_{league_id}'
        )
        btn.callback = self.join_callback
        self.add_item(btn)

    async def join_callback(self, interaction: discord.Interaction):
        league = leagues.get(self.league_id)

        if not league:
            await interaction.response.send_message('League not found.', ephemeral=True)
            return

        if league['status'] in ('Full', 'Ended'):
            await interaction.response.send_message(
                f'This league is currently **{league["status"]}** and is no longer accepting players.',
                ephemeral=True
            )
            return

        # Prevent duplicate joins
        if interaction.user.id in league['joined_users']:
            await interaction.response.send_message('You have already joined this league.', ephemeral=True)
            return

        # Create thread on first join, reuse afterwards
        if not league['thread_id']:
            channel = bot.get_channel(league['channel_id'])
            message = await channel.fetch_message(league['message_id'])
            thread = await message.create_thread(name=f"🎮 League {self.league_id} – Match Thread")
            league['thread_id'] = thread.id
        else:
            thread = bot.get_channel(league['thread_id'])

        await thread.add_user(interaction.user)
        league['joined_users'].add(interaction.user.id)
        league['current_players'] += 1

        is_full = league['current_players'] >= league['max_players']
        await update_league_embed(self.league_id, is_full)

        await interaction.response.send_message(
            f'✅ You joined the league! Head to {thread.mention}.', ephemeral=True
        )


STATUS_DISPLAY = {
    'Active': '🟢 Active',
    'Full':   '🔴 Full / Match Starting',
    'Ended':  '🔴 Ended',
}

STATUS_COLOR = {
    'Active': discord.Color.blue(),
    'Full':   discord.Color.red(),
    'Ended':  discord.Color.greyple(),
}


async def update_league_embed(league_id: str, is_full: bool = False):
    """Rebuild and edit the league embed, removing the button when full or ended."""
    league = leagues.get(league_id)
    if not league:
        return

    if is_full:
        league['status'] = 'Full'

    color = STATUS_COLOR.get(league['status'], discord.Color.blue())
    embed = build_league_embed(league_id, league, color)
    closed = league['status'] in ('Full', 'Ended')

    try:
        channel = bot.get_channel(league['channel_id'])
        message = await channel.fetch_message(league['message_id'])
        await message.edit(embed=embed, view=None if closed else JoinLeagueView(league_id))
    except Exception as e:
        print(f"[embed update error] {e}")


def build_league_embed(league_id: str, league: dict, color: discord.Color) -> discord.Embed:
    spots_left = max(0, league['max_players'] - league['current_players'])
    embed = discord.Embed(
        title='🎮 League Hosted',
        description=f'League ID: **{league_id}**',
        color=color
    )
    embed.add_field(name='Match Format', value=league['format'], inline=True)
    embed.add_field(name='Match Type',   value=league['type'],   inline=True)
    embed.add_field(name='Perks',        value=league['perks'],  inline=True)
    embed.add_field(name='Region',       value=league['region'], inline=True)
    embed.add_field(name='Players',      value=f"{league['current_players']}/{league['max_players']}", inline=True)
    embed.add_field(name='Spots Left',   value=str(spots_left),  inline=True)
    embed.add_field(name='Hosted By',    value=f"<@{league['host']}>", inline=False)
    embed.add_field(name='Status',       value=STATUS_DISPLAY.get(league['status'], league['status']), inline=False)
    embed.add_field(name='Created',      value=f"<t:{league['created']}:f>", inline=False)
    embed.set_footer(text=f'League ID: {league_id}')
    return embed


# ========== EVENTS ==========

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('MVSD League Bot is ready!')
    print('------')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Error syncing commands: {e}')


@bot.event
async def on_message(message: discord.Message):
    # Always process prefix commands first
    await bot.process_commands(message)

    # Ignore bots and DMs
    if message.author.bot or not message.guild:
        return

    # ── GTN game check ──
    game = gtn_games.get(message.channel.id)
    if game:
        guess_str = message.content.strip()
        if guess_str.isdigit():
            guess = int(guess_str)
            if guess == game['number']:
                prize = game['prize']
                # Remove game before any await so no double-trigger
                del gtn_games[message.channel.id]

                await message.reply(
                    f'🎉 Congrats! {message.author.mention} guessed the number '
                    f'(**{game["number"]}**)! Open a ticket to claim your **{prize}**!'
                )
                # Lock the channel
                try:
                    await message.channel.set_permissions(
                        message.guild.default_role,
                        send_messages=False,
                        reason='GTN game ended — correct number guessed'
                    )
                    await message.channel.send('🔒 This channel has been locked. GTN game over!')
                except Exception as e:
                    print(f'[gtn lock error] {e}')

    # ── Guesser game check ──
    guesser_game = active_guesser.get(message.channel.id)
    if guesser_game:
        guess = message.content.strip().lower()
        answer = guesser_game['answer'].lower()
        aliases = [a.lower() for a in guesser_game['aliases']]
        if guess == answer or guess in aliases:
            game_type = guesser_game['type']
            correct_name = guesser_game['answer']
            del active_guesser[message.channel.id]

            # Award point
            guild_pts = guesser_points.setdefault(message.guild.id, {})
            guild_pts[message.author.id] = guild_pts.get(message.author.id, 0) + 1
            total_pts = guild_pts[message.author.id]

            embed = discord.Embed(
                title='✅ Correct Guess!',
                description=f'{message.author.mention} got it right!',
                color=discord.Color.green()
            )
            embed.add_field(name='Answer',       value=correct_name,      inline=True)
            embed.add_field(name='Points Earned', value='+1 🏆',          inline=True)
            embed.add_field(name='Total Points',  value=str(total_pts),   inline=True)
            await message.reply(embed=embed)


# ========== UTILITY COMMANDS ==========

@bot.command(name='ping')
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f'Pong! MVSD League Bot is online. Latency: {latency}ms')


@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync_cmd(ctx):
    """Sync all slash commands to this guild."""
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f'✅ Synced {len(synced)} slash command(s) to this server.')
    except Exception as e:
        await ctx.send(f'❌ Sync failed: {e}')

@sync_cmd.error
async def sync_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ You need Administrator permission to sync commands.')


@bot.command(name='leagueinfo')
async def leagueinfo(ctx):
    embed = discord.Embed(
        title='MVSD League Information',
        description='Official MVSD Competitive League',
        color=discord.Color.blue()
    )
    embed.add_field(name='Match Format', value='5v5 Competitive', inline=False)
    embed.add_field(name='Region',       value='North America',   inline=False)
    embed.add_field(name='Players',      value='64 Active Players', inline=False)
    embed.add_field(name='Status',       value='🟢 Active & Accepting Registrations', inline=False)
    embed.set_footer(text='MVSD League Bot | Type !help for more commands')
    await ctx.send(embed=embed)


# ========== SETUP SLASH COMMANDS ==========

@bot.tree.command(name='setupcommands', description='Set which role can use moderation and league hosting commands')
@app_commands.describe(role='The role that will be granted access to mod and host commands')
@app_commands.default_permissions(administrator=True)
async def setupcommands(interaction: discord.Interaction, role: discord.Role):
    settings = get_guild_settings(interaction.guild_id)
    settings['mod_role_id'] = role.id

    embed = discord.Embed(
        title='⚙️ Commands Setup',
        description=f'Moderation and `/hostleague` commands are now restricted to {role.mention}.',
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f'Set by {interaction.user}')
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='setupleague', description='Configure league hosting settings for this server')
@app_commands.describe(
    channel='Channel where /hostleague embeds are posted (defaults to current channel)',
    host_role='Role allowed to host leagues (bot creates "League Host" if not provided)',
    ping_role='Role that gets pinged when a new league is created'
)
@app_commands.default_permissions(administrator=True)
async def setupleague(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    host_role: Optional[discord.Role] = None,
    ping_role: Optional[discord.Role] = None
):
    settings = get_guild_settings(interaction.guild_id)

    # Channel — default to current
    league_channel = channel or interaction.channel
    settings['league_channel_id'] = league_channel.id

    # Host role — create if not provided
    if host_role is None:
        existing = discord.utils.get(interaction.guild.roles, name='League Host')
        if existing:
            host_role = existing
        else:
            try:
                host_role = await interaction.guild.create_role(
                    name='League Host',
                    color=discord.Color.gold(),
                    reason='Created by /setupleague'
                )
            except Exception as e:
                await interaction.response.send_message(f'❌ Could not create League Host role: {e}', ephemeral=True)
                return

    settings['host_role_id'] = host_role.id

    # Ping role — optional
    if ping_role:
        settings['ping_role_id'] = ping_role.id
    else:
        settings['ping_role_id'] = None

    embed = discord.Embed(
        title='⚙️ League Setup Complete',
        color=discord.Color.blurple()
    )
    embed.add_field(name='League Channel', value=league_channel.mention, inline=False)
    embed.add_field(name='Host Role',      value=host_role.mention,      inline=False)
    embed.add_field(name='Ping Role',      value=ping_role.mention if ping_role else 'None', inline=False)
    embed.set_footer(text=f'Set by {interaction.user}')
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='setupevents', description='Set the Event Manager role for hosting leagues and GTN games')
@app_commands.describe(role='Role that can use /hostleague, /hostgtn, and .endgtn')
@app_commands.default_permissions(administrator=True)
async def setupevents(interaction: discord.Interaction, role: discord.Role):
    settings = get_guild_settings(interaction.guild_id)
    settings['event_role_id'] = role.id

    embed = discord.Embed(
        title='⚙️ Event Manager Setup',
        description=(
            f'{role.mention} has been set as the **Event Manager** role.\n\n'
            f'Members with this role can now use:\n'
            f'• `/hostleague` — Host a league\n'
            f'• `/hostgtn` — Start a Guess The Number game\n'
            f'• `.endgtn` — Manually end a GTN game'
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f'Set by {interaction.user}')
    await interaction.response.send_message(embed=embed)


# ========== LEAGUE HOSTING ==========

@bot.tree.command(name='hostleague', description='Host a new league')
@app_commands.describe(
    format='Match Format (1v1, 2v2, 3v3, 4v4)',
    type='Match Type (Swift/War)',
    perks='Perks enabled (Yes/No)',
    region='Region (e.g. North America, Europe)',
    max_players='Maximum number of players (1–8)'
)
async def hostleague(
    interaction: discord.Interaction,
    format: str,
    type: str,
    perks: str,
    region: str,
    max_players: int
):
    settings = get_guild_settings(interaction.guild_id)

    # Check event/host role permission
    if not user_has_event_role(interaction.user, settings):
        await interaction.response.send_message(no_perms_reply(), ephemeral=True)
        return

    # Always post in the channel where the command is typed
    channel = interaction.channel

    league_id = generate_league_id()
    created_ts = int(datetime.now().timestamp())

    leagues[league_id] = {
        'host': interaction.user.id,
        'format': format,
        'type': type,
        'perks': perks,
        'region': region,
        'max_players': max_players,
        'current_players': 1,                          # host counts as first player
        'joined_users': {interaction.user.id},         # host pre-joined
        'channel_id': channel.id,
        'message_id': None,
        'thread_id': None,
        'status': 'Active',
        'created': created_ts,
    }

    embed = build_league_embed(league_id, leagues[league_id], discord.Color.blue())

    # Always respond in the channel where the command was written
    await interaction.response.send_message(embed=embed, view=JoinLeagueView(league_id))
    msg = await interaction.original_response()

    leagues[league_id]['message_id'] = msg.id

    # Create the match thread immediately and add the host
    try:
        thread = await msg.create_thread(name=f"🎮 League {league_id} – Match Thread")
        leagues[league_id]['thread_id'] = thread.id
        await thread.add_user(interaction.user)
        await thread.send(f'👋 {interaction.user.mention} has opened this league. Players who join will appear here.')
    except Exception as e:
        print(f"[hostleague thread create error] {e}")

    # Send ping as a separate follow-up message so it actually notifies
    ping_role_id = settings.get('ping_role_id')
    if ping_role_id:
        try:
            await channel.send(f'<@&{ping_role_id}> — A new league has been created! Check the embed above to join.')
        except Exception as e:
            print(f"[hostleague ping error] {e}")


def find_league_by_thread(thread_id: int):
    """Return (league_id, league) for the league whose thread matches, or (None, None)."""
    for lid, league in leagues.items():
        if league.get('thread_id') == thread_id:
            return lid, league
    return None, None


def find_latest_active_league_in_channel(channel_id: int, host_id: int = None):
    """Return (league_id, league) for the most recent active league in a channel.
    Optionally filter by host_id."""
    candidates = [
        (lid, l) for lid, l in leagues.items()
        if l['channel_id'] == channel_id
        and l['status'] == 'Active'
        and (host_id is None or l['host'] == host_id)
    ]
    if not candidates:
        return None, None
    # Most recently created
    return max(candidates, key=lambda x: x[1]['created'])


@bot.tree.command(name='endleague', description='End a league you hosted (use in the channel or inside the match thread)')
@app_commands.describe(league_id='League ID to end (optional – auto-detected if omitted)')
async def endleague(interaction: discord.Interaction, league_id: Optional[str] = None):
    settings = get_guild_settings(interaction.guild_id)
    channel  = interaction.channel
    in_thread = isinstance(channel, discord.Thread)

    # --- Resolve which league to end ---
    if league_id:
        league = leagues.get(league_id)
        lid = league_id
        if not league:
            await interaction.response.send_message(f'❌ League `{league_id}` not found.', ephemeral=True)
            return
    elif in_thread:
        lid, league = find_league_by_thread(channel.id)
        if not league:
            await interaction.response.send_message(
                '❌ This thread is not linked to any active league.', ephemeral=True
            )
            return
    else:
        # Main channel — find latest active league hosted by this user here
        lid, league = find_latest_active_league_in_channel(channel.id, interaction.user.id)
        if not league:
            # Admins/mods: try any active league in this channel
            if user_has_mod_role(interaction.user, settings):
                lid, league = find_latest_active_league_in_channel(channel.id)
        if not league:
            await interaction.response.send_message(
                '❌ No active league found. Provide a `league_id` or run this inside the match thread.',
                ephemeral=True
            )
            return

    # --- Permission check ---
    is_host = league['host'] == interaction.user.id
    is_mod  = user_has_mod_role(interaction.user, settings)
    if not is_host and not is_mod:
        await interaction.response.send_message(
            '❌ Only the league host or a staff member can end this league.', ephemeral=True
        )
        return

    if league['status'] == 'Ended':
        await interaction.response.send_message(f'❌ League `{lid}` is already ended.', ephemeral=True)
        return

    # --- End the league ---
    league['status'] = 'Ended'
    await update_league_embed(lid)

    # Respond before deleting (Discord needs a response within 3s)
    await interaction.response.send_message(f'✅ League `{lid}` has been ended.', ephemeral=True)

    if league.get('thread_id'):
        try:
            thread = bot.get_channel(league['thread_id'])
            if thread:
                if in_thread:
                    # Send a farewell then delete the thread entirely
                    await thread.send('🔴 This league has ended. Deleting this thread...')
                    await thread.delete()
                else:
                    # Called from main channel — just lock and archive
                    await thread.send('🔴 This league has ended. The thread is now closed.')
                    await thread.edit(archived=True, locked=True)
        except Exception as e:
            print(f"[endleague thread error] {e}")


# ========== GUESS THE NUMBER ==========

@bot.tree.command(name='hostgtn', description='Start a Guess The Number game in a channel')
@app_commands.describe(
    channel='Channel to unlock and run the GTN game in',
    prize='Prize for the winner',
    number='The number to guess (1–1000). Leave blank for a random number.',
    ping_role='Role to ping when the game starts'
)
async def hostgtn(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    prize: str,
    number: Optional[int] = None,
    ping_role: Optional[discord.Role] = None
):
    settings = get_guild_settings(interaction.guild_id)

    # Check event/host role permission
    if not user_has_event_role(interaction.user, settings):
        await interaction.response.send_message(no_perms_reply(), ephemeral=True)
        return

    # Validate or generate number
    if number is None:
        number = random.randint(1, 1000)
    elif not (1 <= number <= 1000):
        await interaction.response.send_message('❌ Number must be between 1 and 1000.', ephemeral=True)
        return

    # Prevent two games in the same channel
    if channel.id in gtn_games:
        await interaction.response.send_message(
            f'❌ A GTN game is already running in {channel.mention}.', ephemeral=True
        )
        return

    # Unlock the channel for @everyone
    try:
        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=True,
            reason=f'GTN game started by {interaction.user}'
        )
    except Exception as e:
        await interaction.response.send_message(f'❌ Could not unlock channel: {e}', ephemeral=True)
        return

    # Register the game
    gtn_games[channel.id] = {'number': number, 'prize': prize}

    # Build the embed — always appears in the provided channel
    embed = discord.Embed(
        title='🎮 Guess The Number — GTN Started!',
        description=f'Guess the number between **1 and 1000** to win **{prize}**!',
        color=discord.Color.gold()
    )
    embed.add_field(name='Prize', value=prize,                    inline=True)
    embed.add_field(name='Host',  value=interaction.user.mention, inline=True)
    embed.set_footer(text='Type your guess in this channel. First correct guess wins!')

    ping_content = ping_role.mention if ping_role else None
    await channel.send(content=ping_content, embed=embed)

    await interaction.response.send_message(
        f'✅ GTN game started in {channel.mention}!', ephemeral=True
    )
    print(f'[GTN] Game started in #{channel.name} (guild: {interaction.guild.name}) — answer: {number}')


@bot.command(name='endgtn')
async def endgtn(ctx, channel: discord.TextChannel = None):
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_event_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    target = channel or ctx.channel

    if target.id not in gtn_games:
        await ctx.send(f'❌ No active GTN game found in {target.mention}.')
        return

    game = gtn_games.pop(target.id)

    # Lock the channel
    try:
        await target.set_permissions(
            ctx.guild.default_role,
            send_messages=False,
            reason=f'GTN game ended by moderator {ctx.author}'
        )
    except Exception as e:
        await ctx.send(f'⚠️ Could not lock {target.mention}: {e}')

    embed = discord.Embed(
        title='🔒 GTN Event Ended',
        description=f'The Guess The Number game has been ended by a moderator.',
        color=discord.Color.red()
    )
    embed.add_field(name='Prize',      value=game['prize'],          inline=True)
    embed.add_field(name='Ended By',   value=ctx.author.mention,     inline=True)
    embed.add_field(name='Answer Was', value=str(game['number']),    inline=True)
    embed.set_footer(text='This channel has been locked.')
    await target.send(embed=embed)

    if target.id != ctx.channel.id:
        await ctx.send(f'✅ GTN game in {target.mention} has been ended and the channel locked.')


# ========== MODERATION COMMANDS ==========

@bot.command(name='t')
async def timeout_user(ctx, user: discord.Member, duration: str):
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send('❌ Invalid duration. Use formats like: `10m`, `1h`, `2d`.')
        return
    if seconds > 2419200:
        await ctx.send('❌ Timeout duration cannot exceed 28 days.')
        return

    try:
        await user.timeout(timedelta(seconds=seconds), reason=f'Timed out by {ctx.author}')
        await ctx.send(f'✅ {user.mention} has been timed out for **{duration}**.')
        await send_mod_log(ctx.guild, 'Timeout', {
            'Target':    user.mention,
            'Moderator': ctx.author.mention,
            'Duration':  duration,
            'Channel':   ctx.channel.mention,
        })
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


def find_best_role(guild: discord.Guild, query: str) -> discord.Role | None:
    """Find the best matching role using word-prefix matching.
    e.g. query 't mod' matches 'Trial Moderator' because 't' → Trial, 'mod' → Moderator."""
    query_parts = query.lower().split()
    best_role = None
    best_score = -1

    for role in guild.roles:
        if role.is_default():
            continue
        role_words = role.name.lower().split()

        # Count how many query parts prefix-match at least one word in the role name
        score = 0
        for q in query_parts:
            if any(w.startswith(q) for w in role_words):
                score += 1

        # Bonus: exact full-name match wins immediately
        if role.name.lower() == query.lower():
            return role

        if score > best_score:
            best_score = score
            best_role = role

    return best_role if best_score > 0 else None


@bot.command(name='r')
async def manage_role(ctx, user: discord.Member, *, query: str):
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    role = find_best_role(ctx.guild, query)
    if role is None:
        await ctx.send(f'❌ No role found matching **"{query}"**.')
        return

    try:
        if role in user.roles:
            await user.remove_roles(role, reason=f'Role removed by {ctx.author}')
            await ctx.send(f'✅ Removed {role.mention} from {user.mention}.')
        else:
            await user.add_roles(role, reason=f'Role added by {ctx.author}')
            await ctx.send(f'✅ Added {role.mention} to {user.mention}. *(matched: "{role.name}")*')
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


@bot.command(name='unt')
async def untimeout_user(ctx, user: discord.Member):
    """Remove a timeout from a user."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return
    try:
        await user.timeout(None, reason=f'Timeout removed by {ctx.author}')
        await ctx.send(f'✅ Timeout removed from {user.mention}.')
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


@bot.command(name='k')
async def kick_user(ctx, user: discord.Member, *, reason: str = 'No reason provided'):
    """Kick a user from the server."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return
    try:
        await user.kick(reason=f'Kicked by {ctx.author}: {reason}')
        await ctx.send(f'✅ {user.mention} has been kicked. Reason: {reason}')
        await send_mod_log(ctx.guild, 'Kick', {
            'Target':    f'{user} ({user.id})',
            'Moderator': ctx.author.mention,
            'Reason':    reason,
            'Channel':   ctx.channel.mention,
        })
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


@bot.command(name='b')
async def ban_user(ctx, user: discord.Member, *, reason: str = 'No reason provided'):
    """Ban a user from the server."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return
    try:
        await user.ban(reason=f'Banned by {ctx.author}: {reason}', delete_message_days=0)
        await ctx.send(f'✅ {user.mention} has been banned. Reason: {reason}')
        await send_mod_log(ctx.guild, 'Ban', {
            'Target':    f'{user} ({user.id})',
            'Moderator': ctx.author.mention,
            'Reason':    reason,
            'Channel':   ctx.channel.mention,
        })
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


# ========== JAIL SYSTEM ==========

@bot.command(name='setup_jail')
@commands.has_permissions(administrator=True)
async def setup_jail(ctx):
    """Create the Jailed role and #jail-cell channel with locked permissions."""
    guild = ctx.guild

    # --- Create or find the Jailed role ---
    jailed_role = discord.utils.get(guild.roles, name='Jailed')
    if jailed_role is None:
        jailed_role = await guild.create_role(
            name='Jailed',
            color=discord.Color.dark_gray(),
            reason='Jail system setup'
        )

    # Deny Send Messages / View Channels on every existing channel
    for channel in guild.channels:
        try:
            await channel.set_permissions(
                jailed_role,
                send_messages=False,
                read_messages=False,
                add_reactions=False,
                reason='Jail system: lock all channels for Jailed role'
            )
        except Exception:
            pass

    # --- Create or find the #jail-cell channel ---
    jail_channel = discord.utils.get(guild.text_channels, name='jail-cell')
    if jail_channel is None:
        # Everyone can't see it; only Jailed role can
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            jailed_role: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                add_reactions=False
            ),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        jail_channel = await guild.create_text_channel(
            'jail-cell',
            overwrites=overwrites,
            reason='Jail system setup'
        )
    else:
        # Update existing channel permissions
        await jail_channel.set_permissions(
            jailed_role,
            read_messages=True,
            send_messages=True,
            add_reactions=False
        )
        await jail_channel.set_permissions(
            guild.default_role,
            read_messages=False
        )

    settings = get_guild_settings(guild.id)
    settings['jailed_role_id'] = jailed_role.id
    settings['jail_channel_id'] = jail_channel.id

    await ctx.send(
        f'✅ Jail system ready! Role: {jailed_role.mention} | Channel: {jail_channel.mention}'
    )

@setup_jail.error
async def setup_jail_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ You need Administrator permission to run setup_jail.')


@bot.command(name='jail')
async def jail_user(ctx, user: discord.Member, *, reason: str = 'No reason provided'):
    """Jail a user: save their roles, strip them, and assign the Jailed role."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    jailed_role_id = settings.get('jailed_role_id')
    if not jailed_role_id:
        await ctx.send('❌ Jail system not set up. Run `.setup_jail` first.')
        return

    jailed_role = ctx.guild.get_role(jailed_role_id)
    if not jailed_role:
        await ctx.send('❌ Jailed role not found. Run `.setup_jail` again.')
        return

    # Save all non-managed, non-everyone roles so we can restore them later
    saved_roles = [r for r in user.roles if not r.is_default() and not r.managed]
    guild_jail = jail_store.setdefault(ctx.guild.id, {})
    guild_jail[user.id] = [r.id for r in saved_roles]

    try:
        await user.remove_roles(*saved_roles, reason=f'Jailed by {ctx.author}: {reason}')
        await user.add_roles(jailed_role, reason=f'Jailed by {ctx.author}: {reason}')

        jail_channel_id = settings.get('jail_channel_id')
        jail_channel = ctx.guild.get_channel(jail_channel_id) if jail_channel_id else None

        await ctx.send(
            f'🔒 {user.mention} has been jailed. Reason: {reason}'
            + (f' | {jail_channel.mention}' if jail_channel else '')
        )
        await send_mod_log(ctx.guild, 'Jail', {
            'Target':    user.mention,
            'Moderator': ctx.author.mention,
            'Reason':    reason,
            'Channel':   ctx.channel.mention,
        })
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


@bot.command(name='unjail')
async def unjail_user(ctx, user: discord.Member):
    """Unjail a user: remove the Jailed role and restore their original roles."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    jailed_role_id = settings.get('jailed_role_id')
    if not jailed_role_id:
        await ctx.send('❌ Jail system not set up. Run `.setup_jail` first.')
        return

    jailed_role = ctx.guild.get_role(jailed_role_id)

    guild_jail = jail_store.get(ctx.guild.id, {})
    saved_role_ids = guild_jail.pop(user.id, [])
    roles_to_restore = [ctx.guild.get_role(rid) for rid in saved_role_ids]
    roles_to_restore = [r for r in roles_to_restore if r is not None]

    try:
        if jailed_role and jailed_role in user.roles:
            await user.remove_roles(jailed_role, reason=f'Unjailed by {ctx.author}')
        if roles_to_restore:
            await user.add_roles(*roles_to_restore, reason=f'Roles restored after unjail by {ctx.author}')
        await ctx.send(f'🔓 {user.mention} has been unjailed and their roles have been restored.')
        await send_mod_log(ctx.guild, 'Unjail', {
            'Target':    user.mention,
            'Moderator': ctx.author.mention,
            'Channel':   ctx.channel.mention,
        })
    except Exception as e:
        await ctx.send(f'❌ Error: {e}')


# ========== WARNING SYSTEM ==========

@bot.command(name='w')
async def warn_user(ctx, user: discord.Member, *, reason: str = 'No reason provided'):
    """Warn a user and log it."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    guild_warns = warnings.setdefault(ctx.guild.id, {})
    user_warns  = guild_warns.setdefault(user.id, [])
    entry = {
        'reason': reason,
        'mod':    str(ctx.author),
        'ts':     datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
    }
    user_warns.append(entry)
    total = len(user_warns)

    embed = discord.Embed(
        title='⚠️ Warning Issued',
        color=discord.Color.yellow()
    )
    embed.add_field(name='User',         value=user.mention,         inline=True)
    embed.add_field(name='Moderator',    value=ctx.author.mention,   inline=True)
    embed.add_field(name='Total Warns',  value=str(total),           inline=True)
    embed.add_field(name='Reason',       value=reason,               inline=False)
    embed.set_footer(text=entry['ts'])
    await ctx.send(embed=embed)

    await send_mod_log(ctx.guild, 'Warning', {
        'Target':       user.mention,
        'Moderator':    ctx.author.mention,
        'Reason':       reason,
        'Total Warns':  str(total),
        'Channel':      ctx.channel.mention,
    })


@bot.command(name='unw')
async def unwarn_user(ctx, user: discord.Member, count: int = 1):
    """Remove N most-recent warnings from a user."""
    settings = get_guild_settings(ctx.guild.id)
    if not user_has_mod_role(ctx.author, settings):
        await ctx.send(no_perms_reply())
        return

    if count < 1:
        await ctx.send('❌ Count must be at least 1.')
        return

    guild_warns = warnings.get(ctx.guild.id, {})
    user_warns  = guild_warns.get(user.id, [])

    if not user_warns:
        await ctx.send(f'ℹ️ {user.mention} has no warnings to remove.')
        return

    removed  = min(count, len(user_warns))
    del user_warns[-removed:]
    remaining = len(user_warns)

    embed = discord.Embed(
        title='🗑️ Warning(s) Removed',
        color=discord.Color.green()
    )
    embed.add_field(name='User',           value=user.mention,         inline=True)
    embed.add_field(name='Moderator',      value=ctx.author.mention,   inline=True)
    embed.add_field(name='Removed',        value=str(removed),         inline=True)
    embed.add_field(name='Warns Remaining', value=str(remaining),      inline=True)
    embed.set_footer(text=datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'))
    await ctx.send(embed=embed)


# ========== MOD LOGS SETUP ==========

@bot.command(name='mod_logs_setup')
@commands.has_permissions(administrator=True)
async def mod_logs_setup(ctx):
    """Create or find the #mod-logs channel and register it."""
    guild = ctx.guild
    existing = discord.utils.get(guild.text_channels, name='mod-logs')

    if existing:
        channel = existing
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        # Grant access to the configured mod role if set
        settings = get_guild_settings(guild.id)
        mod_role_id = settings.get('mod_role_id')
        if mod_role_id:
            mod_role = guild.get_role(mod_role_id)
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)

        channel = await guild.create_text_channel(
            'mod-logs',
            overwrites=overwrites,
            topic='Automated moderation logs — do not delete.',
            reason='Created by .mod_logs_setup'
        )

    settings = get_guild_settings(guild.id)
    settings['mod_log_channel_id'] = channel.id

    embed = discord.Embed(
        title='📋 Mod Logs Ready',
        description=(
            f'Mod logs are now being sent to {channel.mention}.\n\n'
            f'**Auto-logged actions:**\n'
            f'⚠️ Warnings • ⏱️ Timeouts • 👟 Kicks\n'
            f'🔨 Bans • 🔒 Jail/Unjail • 🗑️ Purge'
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f'Set up by {ctx.author}')
    await ctx.send(embed=embed)

@mod_logs_setup.error
async def mod_logs_setup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ You need Administrator permission to run .mod_logs_setup.')


# ========== PURGE ==========

@bot.tree.command(name='purge', description='Bulk-delete messages in a channel')
@app_commands.describe(amount='Number of messages to delete (1–100)')
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    settings = get_guild_settings(interaction.guild_id)
    if not user_has_mod_role(interaction.user, settings):
        await interaction.response.send_message(no_perms_reply(), ephemeral=True)
        return

    if not (1 <= amount <= 100):
        await interaction.response.send_message('❌ Amount must be between 1 and 100.', ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)

    await interaction.followup.send(
        f'✅ Deleted **{len(deleted)}** message(s).', ephemeral=True
    )
    await send_mod_log(interaction.guild, 'Purge', {
        'Moderator': interaction.user.mention,
        'Channel':   interaction.channel.mention,
        'Deleted':   str(len(deleted)),
    })


# ========== MVSD GUESSER ==========

@bot.tree.command(name='guessmap', description='Start a map guessing game — type the map name to win a point!')
async def guessmap(interaction: discord.Interaction):
    if interaction.channel.id in active_guesser:
        await interaction.response.send_message('❌ A guessing game is already running in this channel.', ephemeral=True)
        return

    name, data = random.choice(list(MAPS_DATA.items()))
    active_guesser[interaction.channel.id] = {
        'type':    'map',
        'answer':  name,
        'aliases': data['aliases'],
        'image':   data['image'],
    }

    embed = discord.Embed(
        title='🗺️ MVSD Map Guesser',
        description='Which map is this? Type the name in chat — first correct answer wins **+1 point**!',
        color=discord.Color.blurple()
    )
    embed.set_image(url=data['image'])
    embed.set_footer(text='Type the map name exactly. Aliases accepted.')
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='guessweapon', description='Start a weapon skin guessing game — type the name to win a point!')
async def guessweapon(interaction: discord.Interaction):
    if interaction.channel.id in active_guesser:
        await interaction.response.send_message('❌ A guessing game is already running in this channel.', ephemeral=True)
        return

    name, data = random.choice(list(WEAPONS_DATA.items()))
    active_guesser[interaction.channel.id] = {
        'type':    'weapon',
        'answer':  name,
        'aliases': data['aliases'],
        'image':   data['image'],
    }

    embed = discord.Embed(
        title='🔪 MVSD Weapon Guesser',
        description='What skin is this? Type the name in chat — first correct answer wins **+1 point**!',
        color=discord.Color.orange()
    )
    embed.set_image(url=data['image'])
    embed.set_footer(text='Type the skin name exactly. Aliases accepted.')
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='value', description='Check the current trading value of an MVSD skin')
@app_commands.describe(skin_name='Name of the skin to look up')
async def value(interaction: discord.Interaction, skin_name: str):
    key = skin_name.strip().lower()

    # Exact match first, then partial
    result = VALUES_DATA.get(key)
    if result is None:
        result = next((v for k, v in VALUES_DATA.items() if key in k or k in key), None)
        matched_name = next((k for k in VALUES_DATA if key in k or key in k), skin_name)
    else:
        matched_name = key

    if result is None:
        known = '\n'.join(f'• {k.title()}' for k in VALUES_DATA)
        await interaction.response.send_message(
            f'❌ **"{skin_name}"** is not in the value list yet.\n\n**Known items:**\n{known}',
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title='💰 MVSD Skin Value',
        color=discord.Color.gold()
    )
    embed.add_field(name='Skin',  value=matched_name.title(), inline=True)
    embed.add_field(name='Value', value=result,               inline=True)
    embed.set_footer(text='Values are estimates and may fluctuate with market trends.')
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='guesser_lb', description='Show the top players on the MVSD Guesser leaderboard')
async def guesser_lb(interaction: discord.Interaction):
    guild_pts = guesser_points.get(interaction.guild_id, {})

    if not guild_pts:
        await interaction.response.send_message('📊 No points have been earned yet. Start a game with `/guessmap` or `/guessweapon`!', ephemeral=True)
        return

    sorted_pts = sorted(guild_pts.items(), key=lambda x: x[1], reverse=True)[:10]

    medals = ['🥇', '🥈', '🥉']
    lines = []
    for i, (uid, pts) in enumerate(sorted_pts):
        member = interaction.guild.get_member(uid)
        name = member.display_name if member else f'Unknown ({uid})'
        icon = medals[i] if i < 3 else f'`#{i+1}`'
        lines.append(f'{icon} **{name}** — {pts} pt{"s" if pts != 1 else ""}')

    embed = discord.Embed(
        title='🏆 MVSD Guesser Leaderboard',
        description='\n'.join(lines),
        color=discord.Color.gold()
    )
    embed.set_footer(text='Points earned from /guessmap and /guessweapon')
    await interaction.response.send_message(embed=embed)


def main():
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print('Error: DISCORD_TOKEN environment variable not set.')
        return
        
    keep_alive()
    bot.run(token)


if __name__ == '__main__':
    main()

