import discord
import asyncio
import random
import json
import os
from discord.ext import commands
from discord import app_commands


from dotenv import load_dotenv
load_dotenv()
LEADERBOARD_CHANNEL_ID = int(os.getenv('LEADERBOARD_CHANNEL_ID'))
PRIVATE_CHANNEL_ID = int(os.getenv('PRIVATE_CHANNEL_ID'))

ALLOWED_ROLES = ["Game Master", "Moderator"]

class EmojiDecode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_emoji = {}
        self.leaderboard_cog = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("EmojiDecode cog is ready.")
        await self.bot.wait_until_ready()
        self.leaderboard_cog = self.bot.get_cog('Leaderboard')
        if self.leaderboard_cog:
            print("Leaderboard cog found and linked to EmojiDecode cog.")
        else:
            print("WARNING: Leaderboard cog not found. Leaderboard functions will not work for Emoji Decode.")

    def load_clues(self):
        try:
            with open("Data/emoji_clues.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print("Error: emoji_clues.json not found.")
            return []
        except json.JSONDecodeError:
            print("Error: emoji_clues.json is corrupted or empty.")
            return []
        except Exception as e:
            print(f"An unexpected error occurred while loading emoji_clues.json: {e}")
            return []

    @app_commands.command(name="emoji", description="Guess the word based on emoji clues!")
    async def emoji(self, interaction: discord.Interaction):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if interaction.channel.id in self.active_emoji:
            await interaction.response.send_message("❗ An emoji game is already running in this channel.", ephemeral=True)
            return

        clues = self.load_clues()
        if not clues:
            await interaction.response.send_message("❌ No emoji clues found or loaded. Please check the `emoji_clues.json` file.", ephemeral=True)
            return

        self.active_emoji[interaction.channel.id] = {
            "running": True,
            "stop_event": asyncio.Event(),
            "host": interaction.user,
            "clues": clues,
            "hint_task": None
        }
        await interaction.response.send_message("🔤 Starting Emoji Decode game!")
        
        self.bot.loop.create_task(self.game_loop(interaction.channel))

    async def game_loop(self, channel):
        game_state = self.active_emoji.get(channel.id)
        if not game_state:
            return

        host = game_state["host"]
        clues = game_state["clues"]
        used_clues = set()

        while game_state["running"] and not game_state["stop_event"].is_set():
            if self.leaderboard_cog and self.leaderboard_cog.is_leaderboard_full():
                break

            if len(used_clues) >= len(clues):
                await channel.send("🎉 All emoji clues have been used! Resetting for new rounds.")
                used_clues.clear()

            clue = random.choice(clues)
            while clue["emoji"] in used_clues and len(used_clues) < len(clues):
                clue = random.choice(clues)
            used_clues.add(clue["emoji"])

            emoji_clue, answer = clue["emoji"], clue["answer"].strip().lower()

            embed = discord.Embed(
                title="🧩 Emoji Decode!",
                description=f"**Emoji Clue:**\n{emoji_clue}\n\nYou have 60 seconds to guess!",
                color=discord.Color.orange()
            )
            await channel.send(embed=embed)

            game_state["hint_task"] = self.bot.loop.create_task(self.send_hints(channel, answer))

            def check(m):
                return (
                    m.channel == channel and
                    not m.author.bot and
                    m.content.strip().lower() == answer
                )

            try:
                msg = await self.bot.wait_for("message", timeout=60.0, check=check)

                if game_state["stop_event"].is_set():
                    break

                user_id = str(msg.author.id)

                if self.leaderboard_cog:
                    if any(str(w['user_id']) == user_id for w in self.leaderboard_cog.get_recent_winners()):
                        await msg.add_reaction("✋")
                        await channel.send(f"Hey {msg.author.mention}, you've recently won a game and are already on the leaderboard! Let others have a chance! 🥳")
                        await asyncio.sleep(1)
                        continue
                else:
                    await channel.send("⚠️ Leaderboard system is not available.")
                    break

                await msg.add_reaction("🎉")

                if self.leaderboard_cog:
                    self.leaderboard_cog.add_recent_winner(
                        user_id=user_id,
                        username=msg.author.name,
                        game_name="Emoji Decode",
                        host_id=host.id,
                        host_name=host.name
                    )

                    win_embed = discord.Embed(
                        title="🎉 Correct!",
                        description=f"{msg.author.mention} guessed it right! The answer was **{answer.title()}**.",
                        color=discord.Color.green()
                    )
                    await channel.send(embed=win_embed)

                    await self.leaderboard_cog.update_leaderboard_display(channel)
                    
                    if self.leaderboard_cog.is_leaderboard_full():
                        await self.handle_leaderboard_full(channel, host)
                        break
                else:
                    await channel.send("⚠️ Leaderboard system is not available.")
                
                await asyncio.sleep(3)

            except asyncio.TimeoutError:
                if game_state["stop_event"].is_set():
                    break
                timeout_embed = discord.Embed(
                    title="⌛ Time's Up!",
                    description=f"No one guessed it. The correct answer was **{answer.title()}**.",
                    color=discord.Color.red()
                )
                await channel.send(embed=timeout_embed)
                await asyncio.sleep(2)

            finally:
                if game_state["hint_task"] and not game_state["hint_task"].done():
                    game_state["hint_task"].cancel()
                game_state["hint_task"] = None

            game_state = self.active_emoji.get(channel.id)

        if game_state and game_state["running"] and self.leaderboard_cog and self.leaderboard_cog.is_leaderboard_full():
            await self.handle_leaderboard_full(channel, host)
        elif game_state and game_state["stop_event"].is_set():
            await channel.send("ℹ️ Emoji Decode game session ended.")
        
        if channel.id in self.active_emoji:
            if self.active_emoji[channel.id]["hint_task"] and not self.active_emoji[channel.id]["hint_task"].done():
                self.active_emoji[channel.id]["hint_task"].cancel()
            del self.active_emoji[channel.id]

    async def send_hints(self, channel, answer):
        try:
            await asyncio.sleep(20)
            game_state = self.active_emoji.get(channel.id)
            if not game_state or game_state["stop_event"].is_set():
                return

            hint1 = f"The answer starts with: **{answer[0]}...**"
            hint_embed1 = discord.Embed(
                title="💡 Hint Time!",
                description=hint1,
                color=discord.Color.yellow()
            )
            await channel.send(embed=hint_embed1)

            await asyncio.sleep(15)
            game_state = self.active_emoji.get(channel.id)
            if not game_state or game_state["stop_event"].is_set():
                return

            if len(answer) > 1:
                hint2 = f"The answer starts with: **{answer[:2]}...**"
            else:
                hint2 = f"The answer has {len(answer)} letter(s)."
            
            hint_embed2 = discord.Embed(
                title="💡 Second Hint!",
                description=hint2,
                color=discord.Color.light_grey()
            )
            await channel.send(embed=hint_embed2)

        except asyncio.CancelledError:
            pass

    async def handle_leaderboard_full(self, channel, host):
        if not self.leaderboard_cog:
            await channel.send("⚠️ Leaderboard system is not available, cannot finalize leaderboard actions.")
            return

        await channel.send(embed=discord.Embed(
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
            await channel.send("⚠️ Could not find the dedicated leaderboard channel for final announcement.")

        if private_channel:
            role_name = await self.leaderboard_cog._winners_role_logic(
                private_channel, self.bot, lambda m: m.author == host and m.channel == private_channel
            )
            if role_name:
                await self.leaderboard_cog._giverole_logic(private_channel, role_name)
            else:
                await private_channel.send("⚠️ Role assignment for Emoji Decode winners was skipped due to no role name provided or timeout.")
        else:
            print(f"Error: Private channel with ID {PRIVATE_CHANNEL_ID} not found for role assignment.")
            await channel.send("⚠️ Could not find the private channel for role assignments.")

        self.leaderboard_cog.reset_leaderboard()

    @app_commands.command(name="stopemoji", description="Stop the ongoing Emoji Decode game")
    async def stopemoji(self, interaction: discord.Interaction):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)

        if interaction.channel.id in self.active_emoji:
            game_state = self.active_emoji[interaction.channel.id]
            game_state["stop_event"].set()
            
            # Cancel the hint task if it's still running
            if game_state["hint_task"] and not game_state["hint_task"].done():
                game_state["hint_task"].cancel()
            
            del self.active_emoji[interaction.channel.id]
            
            await interaction.response.send_message("🛑 Emoji Decode game stopped.")
            await interaction.channel.send("⚠️ Emoji Decode game forcefully stopped.")
        else:
            await interaction.response.send_message("❗ No Emoji Decode game running in this channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EmojiDecode(bot))