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

# --- DATABASE (InMemory) ---
user_stats = {} # {user_id: {'wins': 0, 'played': 0, 'points': 0, 'karma': 100}}
league_storage = {} # {ID: {data}}
league_links = {} # {msg_id: link}
server_settings = {} # {guild_id: {staff_role, host_role, jail_role, host_chan, res_chan, rewards: {pts: role_id}}}
deleted_messages = {}

# --- HELPER FUNCTIONS ---
def get_stats(user_id):
    if user_id not in user_stats:
        user_stats[user_id] = {'wins': 0, 'played': 0, 'points': 0, 'karma': 100}
    return user_stats[user_id]

async def check_rewards(member, points):
    settings = server_settings.get(member.guild.id, {})
    rewards = settings.get('rewards', {})
    for p_limit, role_id in sorted(rewards.items(), reverse=True):
        if points >= p_limit:
            role = member.guild.get_role(role_id)
            if role and role not in member.roles:
                try: await member.add_roles(role)
                except: pass
            break

def is_staff():
    async def predicate(ctx):
        settings = server_settings.get(ctx.guild.id, {})
        staff_role_id = settings.get('staff_role')
        return ctx.author.guild_permissions.administrator or (staff_role_id and any(r.id == staff_role_id for r in ctx.author.roles))
    return commands.check(predicate)

# --- EVENTS ---
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MVSD Rankings"))
    keep_alive()
    try: await bot.tree.sync()
    except: pass
    print(f'✅ {bot.user} is online and ready!')

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    cid = message.channel.id
    if cid not in deleted_messages: deleted_messages[cid] = []
    deleted_messages[cid].insert(0, {"content": message.content, "author": str(message.author), "icon": str(message.author.display_avatar.url)})

# --- LEAGUE VIEW ---
class JoinView(discord.ui.View):
    def __init__(self, league_id, max_p, host_id):
        super().__init__(timeout=None)
        self.league_id, self.max_p, self.players, self.host_id = league_id, max_p, [host_id], host_id
        self.thread = None

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.green)
    async def join(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id in self.players:
            return await inter.response.send_message("You are already in!", ephemeral=True)
        
        self.players.append(inter.user.id)
        
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(name=f"match-{self.league_id}", type=discord.ChannelType.private_thread, invitational=False)
                league_storage[self.league_id]["thread_id"] = self.thread.id
                host_mem = inter.guild.get_member(self.host_id)
                if host_mem: await self.thread.add_user(host_mem)
            except: pass

        if self.thread: await self.thread.add_user(inter.user)
        league_storage[self.league_id]["player_list"] = self.players

        try:
            host_user = await bot.fetch_user(self.host_id)
            await host_user.send(f"🔔 `{inter.user.name}` joined your league `{self.league_id}`.")
        except: pass

        embed = inter.message.embeds[0]
        spots = self.max_p - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_p}")
        embed.set_field_at(5, name="Spots Left", value=str(spots))

        if len(self.players) >= self.max_p:
            button.disabled = True
            embed.color, embed.set_field_at(7, name="Status", value="🟠 Ongoing")
            league_storage[self.league_id]["status"] = "Ongoing"
            await inter.message.edit(embed=embed, view=None)
            if self.thread: await self.thread.send(f"📢 **START!** " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! Check DMs.", ephemeral=True)
        link = league_links.get(inter.message.id, "No link provided.")
        try: await inter.user.send(f"🎮 League ID: `{self.league_id}`\nServer Link: {link}")
        except: pass

# --- SLASH COMMANDS ---

@bot.tree.command(name="setupcommands", description="Set Staff and Jail roles")
@app_commands.checks.has_permissions(administrator=True)
async def setupcommands(inter: discord.Interaction, staff_role: discord.Role, jail_role: discord.Role):
    if inter.guild.id not in server_settings: server_settings[inter.guild.id] = {}
    server_settings[inter.guild.id].update({'staff_role': staff_role.id, 'jail_role': jail_role.id})
    await inter.response.send_message(f"✅ Roles saved!")

@bot.tree.command(name="setupleague", description="Set channels and host role")
@app_commands.checks.has_permissions(administrator=True)
async def setupleague(inter: discord.Interaction, hosting_channel: discord.TextChannel, results_channel: discord.TextChannel, host_role: discord.Role):
    if inter.guild.id not in server_settings: server_settings[inter.guild.id] = {}
    server_settings[inter.guild.id].update({'host_chan': hosting_channel.id, 'res_chan': results_channel.id, 'host_role': host_role.id})
    await inter.response.send_message(f"✅ League settings updated!")

@bot.tree.command(name="setup_rewards", description="Add auto-role reward for points")
@app_commands.checks.has_permissions(administrator=True)
async def setup_rewards(inter: discord.Interaction, points: int, role: discord.Role):
    settings = server_settings.setdefault(inter.guild.id, {})
    rewards = settings.setdefault('rewards', {})
    rewards[points] = role.id
    await inter.response.send_message(f"✅ Reward set: `{points}` pts -> {role.mention}")

@bot.tree.command(name="hostleague", description="Host a league match")
async def hostleague(inter: discord.Interaction, format: str, type: str, perks: str, region: str):
    settings = server_settings.get(inter.guild.id, {})
    if not inter.user.guild_permissions.administrator and not any(r.id == settings.get('host_role') for r in inter.user.roles):
        return await inter.response.send_message("❌ No Host Role!", ephemeral=True)
    if settings.get('host_chan') and inter.channel_id != settings.get('host_chan'):
        return await inter.response.send_message(f"❌ Host in <#{settings.get('host_chan')}>", ephemeral=True)

    max_p = {"1v1": 2, "2v2": 4, "3v3": 6, "4v4": 8}.get(format, 4)
    l_id = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))
    
    embed = discord.Embed(title=f"🎮 {format} {type} League", color=discord.Color.green())
    embed.add_field(name="League ID", value=f"**{l_id}**", inline=False)
    embed.add_field(name="Format", value=format, inline=True)
    embed.add_field(name="Type", value=type, inline=True)
    embed.add_field(name="Perks", value=perks, inline=True)
    embed.add_field(name="Region", value=region, inline=True)
    embed.add_field(name="Players", value=f"1/{max_p}", inline=True)
    embed.add_field(name="Spots Left", value=str(max_p-1), inline=True)
    embed.add_field(name="Host", value=inter.user.mention, inline=False)
    embed.add_field(name="Status", value="🟢 Recruiting", inline=False)
    
    view = JoinView(l_id, max_p, inter.user.id)
    await inter.response.send_message(embed=embed, view=view)
    msg = await inter.original_response()
    league_storage[l_id] = {"msg_id": msg.id, "channel_id": inter.channel_id, "host_id": inter.user.id, "status": "Recruiting", "player_list": [inter.user.id], "format": format, "type": type}
    
    try:
        await inter.user.send(f"👋 ID: `{l_id}`. Reply with Server Link.")
        m = await bot.wait_for('message', check=lambda m: m.author.id == inter.user.id and isinstance(m.channel, discord.DMChannel), timeout=180.0)
        league_links[msg.id] = m.content
        await inter.user.send("✅ Link saved!")
    except: pass

@bot.tree.command(name="endleague", description="End match and give points")
async def endleague(inter: discord.Interaction, id: str, winner_pings: str = None):
    id = id.upper()
    if id not in league_storage: return await inter.response.send_message("❌ ID not found!", ephemeral=True)
    data = league_storage[id]
    
    if data["status"] == "Ongoing":
        for p_id in data['player_list']:
            s = get_stats(p_id)
            s['played'] += 1; s['points'] += 10
            mem = inter.guild.get_member(p_id)
            if mem: await check_rewards(mem, s['points'])
        if winner_pings:
            for p in winner_pings.replace(',', ' ').split():
                clean = p.strip('<@!> ')
                if clean.isdigit():
                    s = get_stats(int(clean)); s['wins'] += 1; s['points'] += 20
                    mem = inter.guild.get_member(int(clean))
                    if mem: await check_rewards(mem, s['points'])

        await inter.response.send_message(f"✅ Match `{id}` ended. Pts awarded! Send screenshot to DM.")
        try:
            host = await bot.fetch_user(data["host_id"])
            await host.send(f"🏆 Match `{id}` screenshot needed.")
            m = await bot.wait_for('message', check=lambda m: m.author.id == data["host_id"] and m.attachments, timeout=300.0)
            res_chan = bot.get_channel(server_settings[inter.guild.id]['res_chan'])
            res_emb = discord.Embed(title=f"🏁 Result: {id}", color=discord.Color.blue())
            res_emb.set_image(url=m.attachments[0].url)
            res_emb.add_field(name="Format", value=data['format'])
            res_emb.add_field(name="Players", value=" ".join([f"<@{p}>" for p in data['player_list']]))
            await res_chan.send(content="Match Finished!", embed=res_emb)
        except: pass
    else:
        await inter.response.send_message(f"❌ Cancelled.")

    try:
        chan = bot.get_channel(data["channel_id"])
        msg = await chan.fetch_message(data["msg_id"])
        emb = msg.embeds[0]; emb.color = discord.Color.light_grey(); emb.set_field_at(7, name="Status", value="⚪ Ended")
        await msg.edit(embed=emb, view=None)
    except: pass
    if "thread_id" in data:
        t = bot.get_channel(data["thread_id"])
        if t: await t.delete()
    del league_storage[id]

@bot.tree.command(name="profile", description="Check player profile")
async def profile(inter: discord.Interaction, member: discord.Member = None):
    target = member or inter.user
    s = get_stats(target.id)
    emb = discord.Embed(title=f"📊 {target.name}", color=discord.Color.gold())
    emb.add_field(name="Points", value=s['points'], inline=True)
    emb.add_field(name="Wins", value=s['wins'], inline=True)
    emb.add_field(name="Karma", value=s['karma'], inline=True)
    await inter.response.send_message(embed=emb)

@bot.tree.command(name="leaderboard", description="Top 10 players")
async def leaderboard(inter: discord.Interaction):
    sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['points'], reverse=True)[:10]
    desc = "\n".join([f"**{i+1}.** <@{u}> - {s['points']} pts" for i, (u, s) in enumerate(sorted_users)])
    emb = discord.Embed(title="🏆 Leaderboard", description=desc or "Empty", color=discord.Color.blue())
    await inter.response.send_message(embed=emb)

@bot.tree.command(name="whisper", description="DM a player through the bot")
async def whisper(inter: discord.Interaction, player: discord.Member, message: str):
    if not inter.user.guild_permissions.administrator: return await inter.response.send_message("No permission", ephemeral=True)
    try:
        await player.send(f"📩 **Host Message:** {message}")
        await inter.response.send_message(f"✅ Sent to {player.name}", ephemeral=True)
    except: await inter.response.send_message("❌ DMs closed", ephemeral=True)

# --- PREFIX MODERATION ---
@bot.command()
@is_staff()
async def b(ctx, m: discord.Member, *, r="None"): await m.ban(reason=r); await ctx.send(f"✅ Banned {m}")

@bot.command()
@is_staff()
async def k(ctx, m: discord.Member, *, r="None"): await m.kick(reason=r); await ctx.send(f"✅ Kicked {m}")

@bot.command()
@is_staff()
async def t(ctx, m: discord.Member, min: int): await m.timeout(datetime.timedelta(minutes=min)); await ctx.send(f"✅ Muted {m}")

@bot.command()
@is_staff()
async def unt(ctx, m: discord.Member): await m.timeout(None); await ctx.send(f"✅ Unmuted {m}")

@bot.command()
@is_staff()
async def jail(ctx, m: discord.Member):
    rid = server_settings.get(ctx.guild.id, {}).get('jail_role')
    if rid: await m.add_roles(ctx.guild.get_role(rid)); await ctx.send(f"⚖️ Jailed {m}")

@bot.command()
@is_staff()
async def r(ctx, m: discord.Member, role: discord.Role): await m.add_roles(role); await ctx.send(f"✅ Added {role}")

@bot.command()
async def s(ctx, i: int = 1):
    data = deleted_messages.get(ctx.channel.id, [])
    if not data: return await ctx.send("No snipes.")
    msg = data[i-1]; e = discord.Embed(description=msg['content'], color=discord.Color.blue())
    e.set_author(name=msg['author'], icon_url=msg['icon']); await ctx.send(embed=e)

if TOKEN: bot.run(TOKEN)
