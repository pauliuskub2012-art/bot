import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import datetime
from keep_alive import keep_alive

# --- IMPROVED LEAGUE VIEW (SIDEBAR THREADS) ---
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
        
        # FIX: Creating thread in CHANNEL so it appears in the SIDEBAR
        if self.thread is None:
            try:
                self.thread = await inter.channel.create_thread(
                    name=f"Match-{self.league_id}",
                    type=discord.ChannelType.private_thread,
                    auto_archive_duration=60
                )
                # Track this league globally for the end command
                active_leagues[self.thread.id] = inter.message.id
                
                # Add the host (from the original interaction)
                host_member = inter.guild.get_member(self.players[0])
                if host_member:
                    await self.thread.add_user(host_member)
            except Exception as e:
                return await inter.response.send_message(f"Error creating sidebar thread: {e}", ephemeral=True)

        # Add the joining player
        await self.thread.add_user(inter.user)
        
        spots = self.max_players - len(self.players)
        embed.set_field_at(4, name="Players", value=f"{len(self.players)}/{self.max_players}")
        embed.set_field_at(5, name="Spots Left", value=f"{spots}")

        if len(self.players) >= self.max_players:
            button.disabled = True
            embed.color = discord.Color.red()
            embed.set_field_at(7, name="Status", value="🔴 Full / Match Starting")
            await inter.message.edit(embed=embed, view=self)
            await self.thread.send(f"**The match is starting!**\nParticipants: " + " ".join([f"<@{p}>" for p in self.players]))
        else:
            await inter.message.edit(embed=embed, view=self)
        
        await inter.response.send_message(f"✅ Joined! The private thread is now in the sidebar: {self.thread.mention}", ephemeral=True)

# --- END LEAGUE COMMAND ---
@bot.tree.command(name="endleague", description="Ends the league, updates status, and deletes the thread")
async def endleague(interaction: discord.Interaction):
    # Only allow in threads
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("Use this command INSIDE the league thread!", ephemeral=True)

    thread_id = interaction.channel.id
    if thread_id in active_leagues:
        msg_id = active_leagues[thread_id]
        try:
            # Find the original message to update status
            main_msg = await interaction.channel.parent.fetch_message(msg_id)
            embed = main_msg.embeds[0]
            embed.color = discord.Color.dark_grey()
            embed.set_field_at(7, name="Status", value="⚪ Ended")
            await main_msg.edit(embed=embed, view=None) # Remove buttons
            del active_leagues[thread_id]
        except:
            pass

    await interaction.response.send_message("League finished. This thread will be deleted in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

