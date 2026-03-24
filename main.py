import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- BOT SETUP ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- STORAGE ---
deleted_messages = {}
active_leagues = {} 
server_settings = {}
warns = {}

# --- PERMISSION CHECK ---
def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        if ctx.author.guild_permissions.administrator:
            return True
        if staff_role_id and discord.utils.get(ctx.author.roles, id=staff_role_id):
            return True
        return False
    return commands.check(predicate)

# --- EVENTS ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues"))
    print(f'✅ {bot.user} is online!')
    keep_alive()
    await bot.tree.sync()

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    cid = message.channel.id
    if cid not in deleted_messages:
        deleted_messages[cid] = []
    deleted_messages[cid].insert(0, {
        "content": message.content,
        "author": str(message.author),
        "icon": str(message.author.display_avatar.url)
    })

# --- LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)

        self.players.append(inter.user.id)

        # --- CREATE PRIVATE THREAD ---
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(
                    name=f"match-{self.league_id}",
                    type=discord.ChannelType.private_thread,
                    auto_archive_duration=60,
                    invitable=False
                )

                active_leagues[self.thread.id] = inter.message.id

                # Add host + first joiner
                await self.thread.add_user(self.players[0])  # host
                await self.thread.add_user(inter.user)

                await self.thread.send(
                    f"🏆 **League ID: {self.league_id}**\n"
                    f"Host: <@{self.players[0]}>\n"
                    f"Waiting for more players..."
                )

            except Exception as e:
                return await inter.response.send_message(f"❌ Error creating thread: {e}", ephemeral=True)

        else:
            # Add new players to existing thread
            await self.thread.add_user(inter.user)

        # --- UPDATE EMBED ---
        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)

        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_p}")
        embed.set_field_at(5, name="Spots Left", value=str(spots))

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")

            await inter.message.edit(embed=embed, view=None)

            await self.thread.send(
                f"📢 **MATCH STARTING!**\nPlayers: " +
                " ".join([f"<@{p}>" for p in self.players])
            )
        else:
            await inter.message.edit(embed=embed, view=self)

        await inter.response.send_message(
            f"✅ Joined! Private thread created.",
            ephemeral=True
        )

# --- SLASH COMMANDS ---
@bot.tree.command(name="hostleague")
async def hostleague(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    league_id = random.randint(1000, 9999)

    embed = discord.Embed(title=f"🎮 {format} {type} - {region}", color=discord.Color.blue())
    embed.add_field(name="Format", value=format, inline=True)
    embed.add_field(name="Type", value=type, inline=True)
    embed.add_field(name="Perks", value=perks, inline=True)
    embed.add_field(name="Region", value=region, inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=str(max_p-1), inline=True)
    embed.add_field(name="Host", value=inter.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Recruiting", inline=False)

    view = JoinView(league_id, max_p, inter.user.id)
    await inter.response.send_message(embed=embed, view=view)

@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction):
    if not isinstance(inter.channel, discord.Thread):
        return await inter.response.send_message("Use this in the match thread!", ephemeral=True)

    if inter.channel.id in active_leagues:
        try:
            main_msg = await inter.channel.parent.fetch_message(active_leagues[inter.channel.id])
            emb = main_msg.embeds[0]
            emb.color = discord.Color.light_grey()
            emb.set_field_at(7, name="Status", value="⚪ Ended")
            await main_msg.edit(embed=emb, view=None)
        except:
            pass

    await inter.response.send_message("Match ended. Deleting thread...")
    await asyncio.sleep(3)
    await inter.channel.delete()

@bot.tree.command(name="setupcommands")
@app_commands.checks.has_permissions(administrator=True)
async def setupcommands(inter: discord.Interaction, staff_role: discord.Role, jail_role: discord.Role):
    server_settings[inter.guild.id] = {
        'staff_role': staff_role.id,
        'jail_role': jail_role.id
    }
    await inter.response.send_message("✅ Settings updated!")

# --- PREFIX COMMANDS ---
@bot.command()
@is_staff()
async def b(ctx, member: discord.Member, *, r="None"):
    await member.ban(reason=r)
    await ctx.send(f"✅ Banned {member}")

@bot.command()
@is_staff()
async def unb(ctx, user_id: int):
    await ctx.guild.unban(discord.Object(id=user_id))
    await ctx.send(f"✅ Unbanned {user_id}")

@bot.command()
@is_staff()
async def t(ctx, m: discord.Member, min: int):
    await m.timeout(datetime.timedelta(minutes=min))
    await ctx.send(f"✅ Muted {m} for {min}m")

@bot.command()
@is_staff()
async def unt(ctx, m: discord.Member):
    await m.timeout(None)
    await ctx.send(f"✅ Unmuted {m}")

@bot.command()
@is_staff()
async def w(ctx, m: discord.Member):
    warns[m.id] = warns.get(m.id, 0) + 1
    await ctx.send(f"⚠️ {m.mention} warned! Total: {warns[m.id]}")

@bot.command()
@is_staff()
async def unw(ctx, m: discord.Member):
    warns[m.id] = max(0, warns.get(m.id, 0) - 1)
    await ctx.send(f"✅ Warning removed for {m.mention}")

@bot.command()
@is_staff()
async def r(ctx, m: discord.Member, role: discord.Role):
    await m.add_roles(role)
    await ctx.send(f"✅ Given {role} to {m}")

@bot.command()
@is_staff()
async def p(ctx, amount: int):
    await ctx.channel.purge(limit=amount+1)

@bot.command()
@is_staff()
async def jail(ctx, m: discord.Member):
    rid = server_settings.get(ctx.guild.id, {}).get('jail_role')
    await m.add_roles(ctx.guild.get_role(rid))
    await ctx.send(f"⚖️ Jailed {m.mention}")

@bot.command()
async def s(ctx, i: int = 1):
    data = deleted_messages.get(ctx.channel.id, [])
    if not data:
        return await ctx.send("No snipes.")
    msg = data[i-1]
    e = discord.Embed(description=msg['content'], color=discord.Color.blue())
    e.set_author(name=msg['author'], icon_url=msg['icon'])
    await ctx.send(embed=e)

if TOKEN:
    bot.run(TOKEN)
