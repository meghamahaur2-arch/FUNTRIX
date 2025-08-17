import discord
import asyncio
import json
import random
import os
from discord.ext import commands
from discord import app_commands


from dotenv import load_dotenv
load_dotenv()
LEADERBOARD_CHANNEL_ID = int(os.getenv('LEADERBOARD_CHANNEL_ID'))
PRIVATE_CHANNEL_ID = int(os.getenv('PRIVATE_CHANNEL_ID'))

ALLOWED_ROLES = ["Game Master", "Moderator"]
CATEGORY_FILES = {
    "india": "Data/lyrics_India.json",
    "pakistan": "Data/lyrics_Pakistan.json",
    "nigeria": "Data/lyrics_Nigeria.json",
    "global": "Data/lyrics_global.json"
}

def normalize(text):
    return ''.join(filter(str.isalnum, text.lower()))

class Lyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_lyrics = {}
        self.leaderboard_cog = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("Lyrics cog is ready.")
        await self.bot.wait_until_ready()
        self.leaderboard_cog = self.bot.get_cog('Leaderboard')
        if self.leaderboard_cog:
            print("Leaderboard cog found and linked to Lyrics cog.")
        else:
            print("WARNING: Leaderboard cog not found. Leaderboard functions will not work for Lyrics.")

    @app_commands.command(name="lyrics", description="Start a looping lyrics game (guess the song from lyric)")
    @app_commands.describe(category="Pick a lyric category")
    @app_commands.choices(category=[
        app_commands.Choice(name="India", value="india"),
        app_commands.Choice(name="Pakistan", value="pakistan"),
        app_commands.Choice(name="Nigeria", value="nigeria"),
        app_commands.Choice(name="Global", value="global")
    ])
    async def lyrics(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

        if interaction.channel.id in self.active_lyrics:
            return await interaction.response.send_message("❗ Lyrics game is already running in this channel.", ephemeral=True)

        self.active_lyrics[interaction.channel.id] = {"running": True, "stop_event": asyncio.Event()}

        await interaction.response.send_message(f"🎵 Starting Lyrics game in category: **{category.name}**")
        self.bot.loop.create_task(self.run_lyrics_game(interaction.channel, interaction.user, CATEGORY_FILES[category.value]))

    async def run_lyrics_game(self, channel, host, file_path):
        lyrics_data = []
        try:
            with open(file_path, "r") as f:
                lyrics_data = json.load(f)
        except FileNotFoundError:
            await channel.send(f"⚠️ Error: Lyrics file not found at `{file_path}`. Please ensure it exists.")
            self.active_lyrics.pop(channel.id, None)
            return
        except json.JSONDecodeError:
            await channel.send(f"⚠️ Error: Lyrics file at `{file_path}` is corrupted or empty. Please check its format.")
            self.active_lyrics.pop(channel.id, None)
            return
        except Exception as e:
            await channel.send(f"⚠️ Failed to load lyrics due to an unexpected error: `{e}`. Please try again later.")
            self.active_lyrics.pop(channel.id, None)
            return
        
        if not lyrics_data:
            await channel.send("❌ No lyrics found in the selected category file. Please add some lyrics to play.")
            self.active_lyrics.pop(channel.id, None)
            return

        used_lines = set()
        game_state = self.active_lyrics.get(channel.id)

        while game_state and game_state["running"] and not game_state["stop_event"].is_set():
            if self.leaderboard_cog and self.leaderboard_cog.is_leaderboard_full():
                break

            if len(used_lines) >= len(lyrics_data):
                await channel.send("🎉 All lyric lines in this category have been used! Resetting for new rounds.")
                used_lines.clear()

            line_obj = random.choice(lyrics_data)
            while line_obj["line"] in used_lines and len(used_lines) < len(lyrics_data):
                line_obj = random.choice(lyrics_data)
            used_lines.add(line_obj["line"])

            answer = line_obj["answer"].lower()
            lyric_line = line_obj["line"]

            embed = discord.Embed(
                title="🎶 Guess the Song!",
                description=f"*{lyric_line}*\n\n⏱️ You have 30 seconds to answer!",
                color=discord.Color.purple()
            )
            await channel.send(embed=embed)

            def check(m):
                return m.channel == channel and not m.author.bot and normalize(m.content) == normalize(answer)

            try:
                msg = await self.bot.wait_for("message", timeout=30.0, check=check)

                user_id = str(msg.author.id)

                if self.leaderboard_cog and user_id in [entry["user_id"] for entry in self.leaderboard_cog.get_recent_winners()]:
                    await msg.add_reaction("✋")
                    await channel.send(f"{msg.author.mention}, you're already on the leaderboard! Let others have a chance.")
                    await asyncio.sleep(1)
                    continue

                await msg.add_reaction("🎉")
                await channel.send(embed=discord.Embed(
                    title="✅ Correct!",
                    description=(
                        f"{msg.author.mention} guessed it! The song was **{answer.title()}**."
                    ),
                    color=discord.Color.green()
                ))

                if self.leaderboard_cog:
                    added = self.leaderboard_cog.add_recent_winner(
                        user_id=user_id, username=msg.author.name,
                        game_name="Lyrics", host_id=host.id, host_name=host.name
                    )
                    if added:
                        await self.leaderboard_cog.update_leaderboard_display(channel) 

                        lb_channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
                        if lb_channel:
                            await self.leaderboard_cog.update_leaderboard_display(lb_channel)
                        else:
                            await channel.send(f"⚠️ Leaderboard channel (ID: {LEADERBOARD_CHANNEL_ID}) not found for automatic update.")

                        if self.leaderboard_cog.is_leaderboard_full():
                            await self.end_game(channel, host)
                            return 
                    else:
                        await channel.send(f"ℹ️ {msg.author.mention} is already on the leaderboard!")
                else:
                    await channel.send("⚠️ Leaderboard system is not available.")
                
                await asyncio.sleep(2)

            except asyncio.TimeoutError:
                if game_state and game_state["running"] and not game_state["stop_event"].is_set():
                    await channel.send(embed=discord.Embed(
                        title="⌛ Time's Up!",
                        description=f"Nobody guessed it. The answer was **{answer.title()}**.",
                        color=discord.Color.red()
                    ))
                await asyncio.sleep(1)

            game_state = self.active_lyrics.get(channel.id)

        if game_state and game_state["running"] and self.leaderboard_cog and self.leaderboard_cog.is_leaderboard_full():
            await self.end_game(channel, host)
        elif game_state and game_state["stop_event"].is_set():
            await channel.send("ℹ️ Lyrics game session ended.")
        
        self.active_lyrics.pop(channel.id, None)

    async def end_game(self, channel, host):
        if not self.leaderboard_cog:
            await channel.send("⚠️ Leaderboard system is not available, cannot finalize game.")
            return

        await channel.send(embed=discord.Embed(
            title="📋 Leaderboard Full!",
            description="We’ve got 10 winners! Ending the game now.",
            color=discord.Color.gold()
        ))
        
        await self.leaderboard_cog.display_leaderboard_command(channel)
        
        lb_channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if lb_channel:
            await self.leaderboard_cog.update_leaderboard_display(lb_channel)
        else:
            await channel.send(f"⚠️ Dedicated leaderboard channel (ID: {LEADERBOARD_CHANNEL_ID}) not found for final display.")

        private_channel = self.bot.get_channel(PRIVATE_CHANNEL_ID)
        if not private_channel:
            await channel.send(f"⚠️ Private channel for role management (ID: {PRIVATE_CHANNEL_ID}) not found. Skipping role assignment.")
        else:
            role_name = await self.leaderboard_cog._winners_role_logic(
                private_channel, self.bot, lambda m: m.author == host and m.channel == private_channel
            )
            if role_name:
                await self.leaderboard_cog._giverole_logic(private_channel, role_name)
            else:
                await private_channel.send("❌ Role assignment process cancelled or failed for winners.")

        self.leaderboard_cog.reset_leaderboard()
        self.active_lyrics.pop(channel.id, None)

    @app_commands.command(name="stoplyrics", description="Stop the ongoing lyrics game")
    async def stoplyrics(self, interaction: discord.Interaction):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)

        if interaction.channel.id in self.active_lyrics:
            self.active_lyrics[interaction.channel.id]["stop_event"].set()
            self.active_lyrics.pop(interaction.channel.id, None)
            
            await interaction.response.send_message("🛑 Lyrics game stopped.")
            await interaction.channel.send("⚠️ Lyrics game forcefully stopped.")
        else:
            await interaction.response.send_message("❗ No lyrics game running in this channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Lyrics(bot))