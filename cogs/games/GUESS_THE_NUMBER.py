import discord
import random
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

ALLOWED_ROLES = ["Game Master", "Moderator"]

class Guess_no(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        # Renamed for clarity as it now handles the entire game loop, not just hints.
        self.game_tasks = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("Guess_no cog is ready.")

    @app_commands.command(name="startguess", description="Starts the Guess the Number game")
    @app_commands.describe(
        max_number="The maximum number to guess.",
        duration="The duration of the game in seconds (e.g., 60)."
    )
    async def startguess(self, interaction: discord.Interaction, max_number: int, duration: int):
        guild_id = interaction.guild.id
        
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if guild_id in self.active_games:
            await interaction.response.send_message("❌ A game is already active in this server!", ephemeral=True)
            return
            
        if not (30 <= duration <= 600):
            await interaction.response.send_message("❌ Duration must be between 30 and 600 seconds.", ephemeral=True)
            return

        secret_number = random.randint(1, max_number)

        self.active_games[guild_id] = {
            "number": secret_number,
            "channel_id": interaction.channel.id,
            "players": set(),
            "max": max_number,
            "duration": duration,
            "winner_id": None, # To store the winner's ID
            "host_id": interaction.user.id,
            "host_name": interaction.user.name,
            "game_name": "Guess the Number",
            "stop_event": asyncio.Event() 
        }

        embed = discord.Embed(
            title="🎮 Guess the Number",
            description=f"Pick a number between `1` and `{max_number}`!\n\n"
                        f"The game will end in **{duration} seconds**.\n"
                        f"React with 🎯 to join the game.",
            color=discord.Color.blue()
        )
        embed.add_field(name="👥 Players Joined", value="*No one yet*", inline=False)
        embed.set_footer(text="Chat is paused for 10 seconds for fair gameplay.")
        
        await interaction.response.send_message(embed=embed)
        game_msg = await interaction.original_response()

        self.active_games[guild_id]["message_id"] = game_msg.id
        self.active_games[guild_id]["message_channel_id"] = game_msg.channel.id
        
        await game_msg.add_reaction("🎯")

        # Create the pause task
        self.bot.loop.create_task(self.pause_chat(interaction.channel, interaction.guild))

        # Start the main game loop task
        task = self.bot.loop.create_task(self.game_loop(guild_id))
        self.game_tasks[guild_id] = task

    async def pause_chat(self, channel, guild):
        if isinstance(channel, discord.TextChannel):
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite)
                await asyncio.sleep(10)
            finally:
                overwrite.send_messages = True
                await channel.set_permissions(guild.default_role, overwrite=overwrite)
                await channel.send("🔓 **The game has started! You can now guess the number!**")
        else:
            print("⚠️ Cannot pause chat in this channel type.")

    async def game_loop(self, guild_id):
        # Wait for the initial 10-second chat pause to end
        await asyncio.sleep(10)
        
        game = self.active_games.get(guild_id)
        if not game:
            return

        stop_event = game["stop_event"]
        channel = self.bot.get_channel(game["channel_id"])
        number = game["number"]
        max_num = game["max"]
        duration = game["duration"]
        
        if not channel:
            return

        # Calculate hint timings based on the total duration
        # First hint at 30% of the duration, second at 70%
        hint1_delay = duration * 0.3
        hint2_delay = duration * 0.4 # Time from hint 1 to hint 2
        final_delay = duration * 0.3 # Time from hint 2 to the end

        # --- Wait for Hint 1 ---
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=hint1_delay)
            return # Game was stopped early
        except asyncio.TimeoutError:
            if guild_id in self.active_games and not stop_event.is_set():
                mid = max_num // 2
                hint1 = discord.Embed(
                    title="🔍 Hint 1",
                    description=f"The number is **{'greater than' if number > mid else 'less than or equal to'} {mid}**.",
                    color=discord.Color.orange()
                )
                await channel.send(embed=hint1)

        # --- Wait for Hint 2 ---
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=hint2_delay)
            return # Game was stopped early
        except asyncio.TimeoutError:
            if guild_id in self.active_games and not stop_event.is_set():
                quarter = max_num // 4
                three_quarters = 3 * quarter
                desc = (
                    f"The number is **between {quarter} and {three_quarters}**." if quarter <= number <= three_quarters
                    else f"The number is **greater than {three_quarters}**." if number > three_quarters
                    else f"The number is **less than {quarter}**."
                )
                hint2 = discord.Embed(title="🔍 Hint 2", description=desc, color=discord.Color.orange())
                await channel.send(embed=hint2)

        # --- Wait for Game End ---
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=final_delay)
            return # Game was stopped early
        except asyncio.TimeoutError:
            if guild_id not in self.active_games:
                return

            game = self.active_games.get(guild_id) # Re-fetch state
            
            # --- Announce Winner Sequence ---
            # 1. Lock the channel
            lock_embed = discord.Embed(description="🔒 **Time's up! Locking channel to announce the winner...**", color=discord.Color.gold())
            await channel.send(embed=lock_embed)
            if isinstance(channel, discord.TextChannel):
                overwrite = channel.overwrites_for(channel.guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)
            
            await asyncio.sleep(3) # Brief pause for dramatic effect

            # 2. Announce the result
            winner_id = game.get("winner_id")
            if winner_id:
                winner_user = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
                final_embed = discord.Embed(
                    title="🎊 Game Over - We Have a Winner!",
                    description=f"{winner_user.mention} was the first to guess the number correctly! 🎯 It was `{number}`.",
                    color=discord.Color.green()
                )
            else:
                final_embed = discord.Embed(
                    title="⏰ Game Over",
                    description=f"No one guessed it in time. The number was `{number}`.",
                    color=discord.Color.red()
                )
            await channel.send(embed=final_embed)

            # 3. Clean up 
            message = await channel.fetch_message(game["message_id"])
            if message:
                await message.edit(content="🎯 **Game Over!**", embed=None)
            

            if guild_id in self.active_games:
                del self.active_games[guild_id]
            self.game_tasks.pop(guild_id, None)

    @app_commands.command(name="stopguess", description="Stops the ongoing Guess the Number game")
    async def stopguess(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if guild_id not in self.active_games:
            await interaction.response.send_message("❌ **No active game in this server.**", ephemeral=True)
            return

        game = self.active_games[guild_id]
        game["stop_event"].set()
        
        number = game["number"]

        task = self.game_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

        del self.active_games[guild_id]
        
        await interaction.response.send_message(f"🛑 **The game has been stopped. The number was `{number}`.**")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild:
            return

        guild_id = reaction.message.guild.id
        game = self.active_games.get(guild_id)

        if not game:
            return

        if reaction.message.id == game["message_id"] and reaction.emoji == "🎯":
            if user.id in game["players"]:
                return

            game["players"].add(user.id)

            players_list = list(game["players"])
            if len(players_list) > 10:
                displayed = [f"<@{uid}>" for uid in players_list[:10]]
                extra_count = len(players_list) - 10
                joined_display = "\n".join(displayed) + f"\n...and **{extra_count} more players**!"
            else:
                displayed = [f"<@{uid}>" for uid in players_list]
                joined_display = "\n".join(displayed) if displayed else "*No one yet*"

            embed = discord.Embed(
                title="🎮 Guess the Number",
                description=f"Guess a number between `1` and `{game['max']}`!\n\n"
                            f"The game will end in **{game['duration']} seconds**.",
                color=discord.Color.blue()
            )
            embed.add_field(name="👥 Players Joined", value=joined_display, inline=False)
            embed.set_footer(text="Chat is paused for 10 seconds for fair gameplay.")
            
            await reaction.message.edit(embed=embed)
            return

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        game = self.active_games.get(guild_id)

        if not game or message.channel.id != game["channel_id"]:
            return

        if message.author.id not in game["players"]:
            return 

        try:
            guess = int(message.content.strip())
        except ValueError:
            return 

        if not (1 <= guess <= game["max"]):
            return 

        if guess == game["number"]:
            # Only record the first person to guess correctly
            if game.get("winner_id") is None:
                game["winner_id"] = message.author.id
                # The game no longer ends here; it waits for the timer.

async def setup(bot):
    await bot.add_cog(Guess_no(bot))