import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- NUSTATYMAI ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

# --- DUOMENŲ SAUGYKLA ---
deleted_messages = {}
active_leagues = {} # {thread_id: main_msg_id}
# Serverio nustatymai: {guild_id: {'staff_role': id, 'jail_role': id, 'jail_channel': id}}
server_settings = {}

# --- PAGALBINĖS FUNKCIJOS ---
def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        if ctx.author.guild_permissions.administrator: return True
        if staff_role_id and discord.utils.get(ctx.author.roles, id=staff_role_id): return True
        return False
    return commands.check(predicate)

# --- ĮVYKIAI ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD Leagues"))
    keep_alive()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Prisijungta: {bot.user}. Sinchronizuota {len(synced)} Slash komandų.")
    except Exception as e:
        print(f"❌ Sync Error: {e}")

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    if message.channel.id not in deleted_messages: deleted_messages[message.channel.id] = []
    deleted_messages[message.channel.id].insert(0, {
        "content": message.content,
        "author": str(message.author),
        "icon": str(message.author.display_avatar.url)
    })

# --- LYGŲ SISTEMA (JOIN BUTTON & SIDEBAR THREADS) ---
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
            return await inter.response.send_message("Tu jau esi lygos sąraše!", ephemeral=True)
        
        self.players.append(inter.user.id)
        embed = inter.message.embeds[0]
        
        # Sukuriame privačią giją šoniniame meniu
        if self.thread is None:
            self.thread = await inter.channel.create_thread(
                name=f"League-{self.league_id}",
                type=discord.ChannelType.private_thread
            )
            active_leagues[self.thread.id] = inter.message.id
            host = inter.guild.get_member(self.players[0])
            if host: await self.thread.add_user(host)

        await self.thread.add_user(inter.user)
        spots = self.max_p - len(self.players)
        
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_p}")
        embed.set_field_at(5, name="Spots Left", value=str(spots))

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Starting")
            await inter.message.edit(embed=embed, view=None) # Mygtukas dingsta
            await self.thread.send(f"**Match Starting!**\nPlayers: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Prisijungei! Gija: {self.thread.mention}", ephemeral=True)

# --- SLASH KOMANDOS ---
@bot.tree.command(name="hostleague")
async def hostleague(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    league_id = random.randint(1000, 9999)
    
    embed = discord.Embed(title=f"{format} {type} - {region}", color=discord.Color.blue())
    embed.add_field(name="Match Format", value=format, inline=True)
    embed.add_field(name="Match Type", value=type, inline=True)
    embed.add_field(name="Perks", value=perks, inline=True)
    embed.add_field(name="Region", value=region, inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=str(max_p-1), inline=True)
    embed.add_field(name="Hosted By", value=inter.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Active", inline=False)
    
    view = JoinView(league_id, max_p, inter.user.id)
    await inter.response.send_message(embed=embed, view=view)

@bot.tree.command(name="endleague")
async def endleague(inter: discord.Interaction):
    if not isinstance(inter.channel, discord.Thread):
        return await inter.response.send_message("Naudok šią komandą lygos gijoje!", ephemeral=True)

    if inter.channel.id in active_leagues:
        try:
            main_msg = await inter.channel.parent.fetch_message(active_leagues[inter.channel.id])
            embed = main_msg.embeds[0]
            embed.color = discord.Color.light_grey()
            embed.set_field_at(7, name="Status", value="⚪ Ended")
            await main_msg.edit(embed=embed, view=None)
        except: pass

    await inter.response.send_message("Lyga baigta. Gija bus ištrinta po 5s.")
    await asyncio.sleep(5)
    await inter.channel.delete()

@bot.tree.command(name="setupcommands")
@app_commands.checks.has_permissions(administrator=True)
async def setupcommands(inter: discord.Interaction, staff_role: discord.Role, jail_role: discord.Role, jail_channel: discord.TextChannel):
    server_settings[inter.guild.id] = {
        'staff_role': staff_role.id,
        'jail_role': jail_role.id,
        'jail_channel': jail_channel.id
    }
    await inter.response.send_message("✅ Moderacijos nustatymai išsaugoti!")

# --- PREFIX KOMANDOS (.) ---
@bot.command()
@is_staff()
async def b(ctx, member: discord.Member, *, reason="Nėra"):
    await member.ban(reason=reason); await ctx.send(f"✅ {member} užblokuotas.")

@bot.command()
@is_staff()
async def k(ctx, member: discord.Member, *, reason="Nėra"):
    await member.kick(reason=reason); await ctx.send(f"✅ {member} išmestas.")

@bot.command()
@is_staff()
async def t(ctx, member: discord.Member, minutes: int):
    await member.timeout(datetime.timedelta(minutes=minutes)); await ctx.send(f"✅ {member} nutildytas {minutes} min.")

@bot.command()
@is_staff()
async def p(ctx, amount: int):
    await ctx.channel.purge(limit=amount+1); await ctx.send(f"🗑 Išvalyta {amount} žinučių.", delete_after=3)

@bot.command()
async def s(ctx, index: int = 1):
    cid = ctx.channel.id
    if cid not in deleted_messages or not deleted_messages[cid]: return await ctx.send("Nėra ištrintų žinučių.")
    msg = deleted_messages[cid][index-1]
    emb = discord.Embed(description=msg['content'], color=discord.Color.orange())
    emb.set_author(name=msg['author'], icon_url=msg['icon'])
    await ctx.send(embed=emb)

@bot.command()
@is_staff()
async def jail(ctx, member: discord.Member):
    settings = server_settings.get(ctx.guild.id)
    if not settings: return await ctx.send("Pirmiausia naudok `/setupcommands`!")
    role = ctx.guild.get_role(settings['jail_role'])
    await member.add_roles(role); await ctx.send(f"⚖️ {member.mention} pasodintas į kalėjimą.")

@bot.command()
@is_staff()
async def unjail(ctx, member: discord.Member):
    settings = server_settings.get(ctx.guild.id)
    role = ctx.guild.get_role(settings['jail_role'])
    await member.remove_roles(role); await ctx.send(f"🔓 {member.mention} laisvas.")

# PALEIDIMAS
if TOKEN: bot.run(TOKEN)
