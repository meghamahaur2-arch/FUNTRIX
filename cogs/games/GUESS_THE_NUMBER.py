import discord
import random
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
load_dotenv()
LEADERBOARD_CHANNEL_ID = int(os.getenv('LEADERBOARD_CHANNEL_ID'))
PRIVATE_CHANNEL_ID = int(os.getenv('PRIVATE_CHANNEL_ID'))

ALLOWED_ROLES = ["Game Master", "Moderator"]

class Guess_no(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        self.hint_tasks = {}
        self.leaderboard_cog = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("Guess_no cog is ready.")
        await self.bot.wait_until_ready()
        self.leaderboard_cog = self.bot.get_cog('Leaderboard')
        if self.leaderboard_cog:
            print("Leaderboard cog found and linked to Guess_no cog.")
        else:
            print("WARNING: Leaderboard cog not found. Leaderboard functions will not work for Guess the Number.")

    @app_commands.command(name="startguess", description="Starts the Guess the Number game")
    @app_commands.describe(max_number="The maximum number to guess")
    async def startguess(self, interaction: discord.Interaction, max_number: int):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if interaction.channel.id in self.active_games:
            await interaction.response.send_message("**A game is already active in this channel!**", ephemeral=True)
            return

        secret_number = random.randint(1, max_number)

        embed = discord.Embed(
            title="🎮 Guess the Number",
            description=f"Pick a number between `1` and `{max_number}`!\n\n",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎯 Join the Game", value="React with 🎯 to join in.", inline=False)
        embed.add_field(name="Game Paused", value="Chat is paused for 10 seconds for fair gameplay.", inline=False)
        embed.add_field(name="👥 Players Joined", value="*No one yet*", inline=False)

        await interaction.response.send_message(embed=embed)
        game_msg = await interaction.original_response()

        self.active_games[interaction.channel.id] = {
            "number": secret_number,
            "players": set(),
            "message": game_msg,
            "max": max_number,
            "host_id": interaction.user.id,
            "host_name": interaction.user.name,
            "game_name": "Guess the Number"
        }

        await game_msg.add_reaction("🎯")

        if isinstance(interaction.channel, discord.TextChannel):
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            try:
                overwrite.send_messages = False
                await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                await asyncio.sleep(10)
            finally:
                overwrite.send_messages = True
                await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        else:
            await interaction.followup.send("⚠️ Cannot pause chat in this channel type.", ephemeral=True)

        await interaction.followup.send("🔓 **The game has started! You can now guess the number!**")

        task = self.bot.loop.create_task(self.send_hints(interaction.channel.id, secret_number, max_number, interaction.channel))
        self.hint_tasks[interaction.channel.id] = task

    async def send_hints(self, channel_id, number, max_num, channel):
        await asyncio.sleep(10) 
        if channel_id not in self.active_games:
            return

        mid = max_num // 2
        hint1 = discord.Embed(
            title="🔍 Hint 1",
            description=f"The number is **{'greater than' if number > mid else 'less than or equal to'} {mid}**.",
            color=discord.Color.orange()
        )
        await channel.send(embed=hint1)

        await asyncio.sleep(40) 
        if channel_id not in self.active_games:
            return

        quarter = max_num // 4
        three_quarters = 3 * quarter
        desc = (
            f"The number is **between {quarter} and {three_quarters}**."
            if quarter <= number <= three_quarters
            else (
                f"The number is **greater than {three_quarters}**."
                if number > three_quarters
                else f"The number is **less than {quarter}**."
            )
        )

        hint2 = discord.Embed(title="🔍 Hint 2", description=desc, color=discord.Color.orange())
        await channel.send(embed=hint2)

        await asyncio.sleep(90) 
        if channel_id in self.active_games:
            game = self.active_games[channel_id]
            final_hint = discord.Embed(
                title="⏰ Game Over",
                description=f"No one guessed it in time. The number was `{game['number']}`.",
                color=discord.Color.red()
            )
            await channel.send(embed=final_hint)

            await game["message"].edit(content="❌ **Game Ended! No one guessed the number.**", embed=None)
            del self.active_games[channel_id]
            self.hint_tasks.pop(channel_id, None)

    @app_commands.command(name="stopguess", description="Stops the ongoing Guess the Number game")
    async def stopguess(self, interaction: discord.Interaction):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if interaction.channel.id not in self.active_games:
            await interaction.response.send_message("❌ **No active game in this channel.**", ephemeral=True)
            return

        number = self.active_games[interaction.channel.id]["number"]

        task = self.hint_tasks.pop(interaction.channel.id, None)
        if task and not task.done():
            task.cancel()

        await self.active_games[interaction.channel.id]["message"].edit(content="🛑 **Game stopped.**", embed=None)
        del self.active_games[interaction.channel.id]
        await interaction.response.send_message(f"🛑 **The game has been stopped. The number was `{number}`.**")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild:
            return

        for channel_id, game in self.active_games.items():
            if reaction.message.id == game["message"].id and reaction.emoji == "🎯":
                if user.id in game["players"]:
                    return

                game["players"].add(user.id)
                joined_mentions = "\n".join(f"<@{uid}>" for uid in game["players"])

                embed = discord.Embed(
                    title="🎮 Guess the Number",
                    description=f"Guess a number between `1` and `{game['max']}`!",
                    color=discord.Color.blue()
                )
                embed.add_field(name="🎯 Join the Game", value="Only those who react can play.", inline=False)
                embed.add_field(name="Game Paused", value="Chat is paused for 10 seconds for fair gameplay.", inline=False)
                embed.add_field(name="👥 Players Joined", value=joined_mentions, inline=False)

                await game["message"].edit(embed=embed)
                return

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        if channel_id not in self.active_games:
            return

        game = self.active_games[channel_id]

        if message.author.id not in game["players"]:
            return 

        try:
            guess = int(message.content.strip())
        except ValueError:
            return 

        if not (1 <= guess <= game["max"]):
            return 

        if channel_id not in self.active_games:
            return 

        if guess == game["number"]:
            if channel_id not in self.active_games:
                return 

            if self.leaderboard_cog:
                if any(str(w['user_id']) == str(message.author.id) for w in self.leaderboard_cog.get_recent_winners()):
                    await message.channel.send(f"Hey {message.author.mention}, you've recently won a game and are already on the leaderboard! Let others have a chance! 🥳", delete_after=10)
                    return
            else:
                await message.channel.send("⚠️ Leaderboard system is not available for winner tracking.", delete_after=10)
                
            await message.add_reaction("🎉")
            embed = discord.Embed(
                title="🎊 We Have a Winner!",
                description=f"{message.author.mention} guessed the number correctly! 🎯 It was `{game['number']}`.",
                color=discord.Color.green()
            )
            await message.channel.send(embed=embed)

            if self.leaderboard_cog:
                self.leaderboard_cog.add_recent_winner(
                    user_id=message.author.id,
                    username=message.author.name,
                    game_name=game["game_name"],
                    host_id=game["host_id"],
                    host_name=game["host_name"]
                )
                
                await self.leaderboard_cog.update_leaderboard_displa(message.channel)

                if self.leaderboard_cog.is_leaderboard_full():
                    await self.handle_leaderboard_full(message.guild, message.channel, game["host_id"], game["host_name"])

            task = self.hint_tasks.pop(channel_id, None)
            if task and not task.done():
                task.cancel() 

            await game["message"].edit(content="🎯 **Game Over: We have a winner!**", embed=None)
            del self.active_games[channel_id]

    async def handle_leaderboard_full(self, guild: discord.Guild, game_channel: discord.TextChannel, host_id: int, host_name: str):
        if not self.leaderboard_cog:
            await game_channel.send("⚠️ Leaderboard system is not available, cannot finalize game actions.")
            return

        await game_channel.send(embed=discord.Embed(
            title="🎉 LEADERBOARD IS FULL! 🎉",
            description="We have 10 winners! Check the official leaderboard channel!",
            color=discord.Color.gold()
        ))

        leaderboard_channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        private_channel = self.bot.get_channel(PRIVATE_CHANNEL_ID)

        if leaderboard_channel:
            await self.leaderboard_cog.update_leaderboard_display(leaderboard_channel)
            await leaderboard_channel.send(
                "**Congratulations to all the winners!**\n"
                "🔄 **The leaderboard has been reset for the next set of champions!**"
            )
        else:
            print(f"Error: Leaderboard channel with ID {LEADERBOARD_CHANNEL_ID} not found.")
            await game_channel.send("⚠️ Could not find the dedicated leaderboard channel for final announcement.")

        if private_channel:
            host_user = self.bot.get_user(host_id) or await self.bot.fetch_user(host_id)
            if host_user:
                role_name = await self.leaderboard_cog._winners_role_logic(
                    private_channel, self.bot, lambda m: m.author == host_user and m.channel == private_channel
                )
                if role_name:
                    await self.leaderboard_cog._giverole_logic(private_channel, role_name)
                else:
                    await private_channel.send("⚠️ Role assignment for Guess the Number winners was skipped due to no role name provided or timeout.")
            else:
                await private_channel.send("⚠️ Host user not found for role assignment. Skipping role prompt.")
                print(f"Warning: Host user (ID: {host_id}) not found for role assignment.")
        else:
            print(f"Error: Private channel with ID {PRIVATE_CHANNEL_ID} not found for role assignment.")
            await game_channel.send("⚠️ Could not find the private channel for role assignments.")

        self.leaderboard_cog.reset_leaderboard()

async def setup(bot):
    await bot.add_cog(Guess_no(bot))