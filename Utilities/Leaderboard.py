# File: Leaderboard.py
import json
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio

# Import the new database manager
from database import DatabaseManager

load_dotenv()

LEADERBOARD_CHANNEL_ID = os.getenv('LEADERBOARD_CHANNEL_ID')
LAST_MESSAGE_FILE = os.path.join("Data", "last_leaderboard_messages.json")
MAX_LEADERBOARD_ENTRIES = 10

# Create the Data directory if it doesn't exist
os.makedirs("Data", exist_ok=True)

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseManager()
        self.last_leaderboard_messages = self._load_last_messages()

    def _load_last_messages(self):
        """Loads the last sent leaderboard message IDs for each channel."""
        if os.path.exists(LAST_MESSAGE_FILE):
            try:
                with open(LAST_MESSAGE_FILE, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {LAST_MESSAGE_FILE} is corrupted or empty. Starting with empty last messages.")
                return {}
        return {}

    def _save_last_messages(self):
        """Saves the last sent leaderboard message IDs to a JSON file."""
        with open(LAST_MESSAGE_FILE, "w") as f:
            json.dump(self.last_leaderboard_messages, f, indent=4)

    def set_last_leaderboard_message(self, channel_id, message_id):
        """Stores the ID of the last leaderboard message sent in a channel."""
        self.last_leaderboard_messages[str(channel_id)] = message_id
        self._save_last_messages()

    def get_last_leaderboard_message(self, channel_id):
        """Retrieves the ID of the last leaderboard message for a channel."""
        return self.last_leaderboard_messages.get(str(channel_id))

    @commands.command(name='leaderboard', help=f'Displays the recent winners leaderboard for this server.')
    async def display_leaderboard_command(self, ctx: commands.Context, channel: discord.TextChannel = None):
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        channel = channel or ctx.channel
        
        # Fetch the most recent winners for this guild from the database
        winners = self.db.get_recent_winners_for_guild(ctx.guild.id, limit=MAX_LEADERBOARD_ENTRIES)

        if not winners:
            await channel.send("ℹ️ The leaderboard is currently empty for this server.")
            return

        embed = discord.Embed(
            title="🏆 Recent Game Winners Leaderboard 🏆",
            description=f"Here are the last {len(winners)} players to win a game on this server!",
            color=discord.Color.gold()
        )

        for i, entry in enumerate(winners, 1):
            winner_display_name = entry['username']
            
            # Use guild.get_member() to get the member object if they are still in the server
            host_member = channel.guild.get_member(int(entry['host_id']))
            host_display_name = host_member.mention if host_member else entry['host_name']

            embed.add_field(
                name=f"#{i}. **{winner_display_name}**",
                value=(f"• Game: `{entry['game_name']}`\n"
                       f"• Hosted by: {host_display_name}\n"
                       f"• When: {entry['timestamp']}"),
                inline=False
            )

        leaderboard_msg = await channel.send(embed=embed)
        # Only track the last message if it's in the designated leaderboard channel
        if channel.id == int(LEADERBOARD_CHANNEL_ID):
            self.set_last_leaderboard_message(channel.id, leaderboard_msg.id)

    @commands.command(name='clearleaderboard', help='Resets the winners leaderboard for this server.')
    @commands.has_permissions(administrator=True)
    async def clear_leaderboard_command(self, ctx):
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        # Clear all winner records for the current guild from the database
        cleared = self.db.clear_leaderboard_for_guild(ctx.guild.id)
        
        if cleared:
            await ctx.send("✅ The recent winners leaderboard for this server has been cleared from the database.")
        else:
            await ctx.send("❌ An error occurred while trying to clear the leaderboard.")
        
        # Update the display after clearing
        leaderboard_channel = self.bot.get_channel(int(LEADERBOARD_CHANNEL_ID))
        if leaderboard_channel:
            await self.update_leaderboard_display(leaderboard_channel)

    async def update_leaderboard_display(self, channel: discord.TextChannel):
        """Updates the leaderboard message in a specific channel."""
        if not channel.guild:
            return

        # Fetch winners from the database
        winners = self.db.get_recent_winners_for_guild(channel.guild.id, limit=MAX_LEADERBOARD_ENTRIES)
        last_message_id = self.get_last_leaderboard_message(channel.id)

        embed = discord.Embed(
            title="🏆 Recent Game Winners Leaderboard 🏆",
            description=f"Here are the last {len(winners)} players to win a game on this server!",
            color=discord.Color.gold()
        )

        if not winners:
            embed.description = "The leaderboard is currently empty for this server."
        else:
            for i, entry in enumerate(winners, 1):
                winner_display_name = entry['username']
                
                host_member = channel.guild.get_member(int(entry['host_id']))
                host_display_name = host_member.mention if host_member else entry['host_name']

                embed.add_field(
                    name=f"#{i}. **{winner_display_name}**",
                    value=(f"• Game: `{entry['game_name']}`\n"
                           f"• Hosted by: {host_display_name}\n"
                           f"• When: {entry['timestamp']}"),
                    inline=False
                )

        try:
            if last_message_id:
                try:
                    message = await channel.fetch_message(last_message_id)
                    await message.edit(embed=embed)
                except discord.NotFound:
                    print("Old leaderboard message not found, sending a new one.")
                    new_msg = await channel.send(embed=embed)
                    self.set_last_leaderboard_message(channel.id, new_msg.id)
            else:
                new_msg = await channel.send(embed=embed)
                self.set_last_leaderboard_message(channel.id, new_msg.id)
        except Exception as e:
            print(f"Error updating leaderboard display: {e}")
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("Leaderboard cog is ready.")
        await asyncio.sleep(1) # Wait for bot to fully connect to guilds
        # Iterate through all guilds the bot is in and update their leaderboards
        for guild in self.bot.guilds:
            try:
                leaderboard_channel = guild.get_channel(int(LEADERBOARD_CHANNEL_ID))
                if leaderboard_channel:
                    await self.update_leaderboard_display(leaderboard_channel)
            except (ValueError, TypeError):
                print(f"Warning: LEADERBOARD_CHANNEL_ID is not a valid integer for guild {guild.name}.")
            except Exception as e:
                print(f"Error updating leaderboard for guild {guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))