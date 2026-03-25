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
league_storage = {} 
league_links = {}   
server_settings = {} 

# --- PERMISSION CHECKS ---
def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        if ctx.author.guild_permissions.administrator: return True
        if staff_role_id and discord.utils.get(ctx.author.roles, id=staff_role_id): return True
        return False
    return commands.check(predicate)

# --- EVENTS ---
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f'✅ {bot.user} is online!')
    keep_alive()
    try:
        await bot.tree.sync()
    except: pass

# --- LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id = league_id
        self.max_p = max_p
        self.players = [host_id]
        self.host_id = host_id
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(
                    name=f"match-{self.league_id}",
                    type=discord.ChannelType.private_thread,
                    invitational=False
                )
                if self.league_id in league_storage:
                    league_storage[self.league_id]["thread_id"] = self.thread.id
                host_mem = inter.guild.get_member(self.host_id)
                if host_mem: await self.thread.add_user(host_mem)
            except: pass

        self.players.append(inter.user.id)
        if self.thread: await self.thread.add_user(inter.user)
        
        # Save player list to storage for results
        league_storage[self.league_id]["player_list"] = self.players

        link = league_links.get(inter.message.id, "No link provided.")
        try:
            await inter.user.send(f"🎮 **League Joined!**\nID: `{self.league_id}`\nLink: {link}")
        except: pass

        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_p}")
        embed.set_field_at(5, name="Spots Left", value=str(spots))

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.orange() # Status: Ongoing
            embed.set_field_at(7, name="Status", value="🟠 Ongoing / Match Started")
            await inter.message.edit(embed=embed, view=None)
            if self.thread: await self.thread.send(f"📢 **MATCH STARTED!** Participants: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Check DMs.", ephemeral=True)

# --- SLASH COMMANDS ---
@bot.tree.command(name="setupleagues", description="Setup hosting, results, and host role")
@app_commands.checks.has_permissions(administrator=True)
async def setupleagues(inter: discord.Interaction, hosting_channel: discord.TextChannel, results_channel: discord.TextChannel, host_role: discord.Role):
    server_settings[inter.guild.id] = {
        'host_chan': hosting_channel.id,
        'res_chan': results_channel.id,
        'host_role': host_role.id
    }
    await inter.response.send_message("✅ League settings updated!")

@bot.tree.command(name="leaguehost", description="Host a league")
async def leaguehost(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})
    if not inter.user.guild_permissions.administrator and inter.user.id != settings.get('host_role'):
        if not any(role.id == settings.get('host_role') for role in inter.user.roles):
            return await inter.response.send_message("❌ Missing Host Role!", ephemeral=True)

    if settings.get('host_chan') and inter.channel_id != settings.get('host_chan'):
        return await inter.response.send_message(f"❌ Host in <#{settings.get('host_chan')}>", ephemeral=True)

    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    league_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))
    
    embed = discord.Embed(title=f"🎮 {format} {type} League", color=discord.Color.green())
    embed.add_field(name="League ID", value=f"**{league_id}**", inline=False)
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
    
    sent_msg = await inter.original_response()
    league_storage[league_id] = {
        "msg_id": sent_msg.id, 
        "channel_id": inter.channel_id, 
        "host_id": inter.user.id,
        "format": format,
        "type": type,
        "player_list": [inter.user.id]
    }
    
    try:
        await inter.user.send(f"👋 ID: `{league_id}`. Reply with Server Link.")
        msg = await bot.wait_for('message', check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel), timeout=300.0)
        league_links[sent_msg.id] = msg.content
        await inter.user.send("✅ Link saved!")
    except: pass

@bot.tree.command(name="endleague", description="End match via ID")
async def endleague(inter: discord.Interaction, id: str):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("❌ ID not found!", ephemeral=True)

    data = league_storage[id]
    
    # 1. Update Hosting Message
    try:
        channel = bot.get_channel(data["channel_id"])
        main_msg = await channel.fetch_message(data["msg_id"])
        emb = main_msg.embeds[0]
        emb.color = discord.Color.light_grey()
        emb.set_field_at(7, name="Status", value="⚪ Ended")
        await main_msg.edit(embed=emb, view=None)
    except: pass

    # 2. Post to Results Channel
    res_chan_id = server_settings.get(inter.guild.id, {}).get('res_chan')
    if res_chan_id:
        res_chan = bot.get_channel(res_chan_id)
        res_emb = discord.Embed(title="🏁 League Results", color=discord.Color.dark_grey())
        res_emb.add_field(name="League ID", value=id)
        res_emb.add_field(name="Format", value=data['format'])
        res_emb.add_field(name="Players", value=", ".join([f"<@{p}>" for p in data['player_list']]), inline=False)
        await res_chan.send(embed=res_emb)

    if "thread_id" in data:
        thread = bot.get_channel(data["thread_id"])
        if thread: await thread.delete()

    del league_storage[id]
    await inter.response.send_message(f"✅ League `{id}` ended and archived.")

@bot.tree.command(name="setupcommands", description="Setup staff and jail roles")
@app_commands.checks.has_permissions(administrator=True)
async def setupcommands(inter: discord.Interaction, staff_role: discord.Role, jail_role: discord.Role):
    server_settings[inter.guild.id] = {'staff_role': staff_role.id, 'jail_role': jail_role.id}
    await inter.response.send_message("✅ Roles saved!")

# --- PREFIX COMMANDS ---
@bot.command()
@is_staff()
async def b(ctx, m: discord.Member, *, r="None"): await m.ban(reason=r); await ctx.send(f"✅ Banned {m}")

@bot.command()
@is_staff()
async def t(ctx, m: discord.Member, min: int): await m.timeout(datetime.timedelta(minutes=min)); await ctx.send(f"✅ Muted {m} for {min}m")

@bot.command()
@is_staff()
async def unt(ctx, m: discord.Member): await m.timeout(None); await ctx.send(f"✅ Removed timeout for {m}")

@bot.command()
@is_staff()
async def jail(ctx, m: discord.Member):
    rid = server_settings.get(ctx.guild.id, {}).get('jail_role')
    if rid: await m.add_roles(ctx.guild.get_role(rid)); await ctx.send(f"⚖️ Jailed {m.mention}")

@bot.command()
async def s(ctx, i: int = 1):
    data = deleted_messages.get(ctx.channel.id, [])
    if not data: return await ctx.send("No snipes.")
    msg = data[i-1]
    e = discord.Embed(description=msg['content'], color=discord.Color.blue())
    e.set_author(name=msg['author'], icon_url=msg['icon'])
    await ctx.send(embed=e)

if TOKEN: bot.run(TOKEN)
