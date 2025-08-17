import discord
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

ALLOWED_ROLES = ["Game Master", "Moderator"]

CHOICES = [
    app_commands.Choice(name="🪨 Rock", value="rock"),
    app_commands.Choice(name="📄 Paper", value="paper"),
    app_commands.Choice(name="✂️ Scissors", value="scissors")
]

BEATS = {
    "rock": "paper",
    "paper": "scissors",
    "scissors": "rock"
}

class RPS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_rps = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("RPS cog is ready.")

    @app_commands.command(name="startrps", description="Start Rock Paper Scissors with a chosen answer")
    @app_commands.describe(correct_choice="Pick your secret choice (players will try to guess the counter)")
    @app_commands.choices(correct_choice=CHOICES)
    async def startrps(
        self,
        interaction: discord.Interaction,
        correct_choice: app_commands.Choice[str]
    ):
        guild_id = interaction.guild.id
        
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have permission to start RPS.", ephemeral=True)

        if guild_id in self.active_rps:
            return await interaction.response.send_message("❗ RPS is already running in this server.", ephemeral=True)

        host_choice = correct_choice.value.lower()
        if host_choice == "scissor":
            host_choice = "scissors"

        correct_answer_for_players = BEATS[host_choice] 
        self.active_rps[guild_id] = {
            "running": True,
            "stop_event": asyncio.Event(),
            "answer": correct_answer_for_players,
            "host": interaction.user,
            "channel_id": interaction.channel.id
        }

        await interaction.response.send_message(embed=discord.Embed(
            title="🎮 Rock Paper Scissors Started!",
            description=f"Host has picked a choice. Guess what **beats** it! (rock, paper, or scissors)\n\n"
                        f"⏱️ You have 60 seconds to guess!",
            color=discord.Color.blurple()
        ))

        self.bot.loop.create_task(self.wait_for_guess(interaction.channel))

    async def wait_for_guess(self, channel):
        guild_id = channel.guild.id
        data = self.active_rps.get(guild_id)
        if not data or not data["running"]:
            return

        correct_guess = data["answer"]
        stop_event = data["stop_event"]
        host = data["host"]

        timeout_seconds = 60

        winner_found = False

        while not stop_event.is_set():
            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=timeout_seconds,
                    check=lambda m: m.channel.id == data["channel_id"] and not m.author.bot and m.content.lower().strip() in ["rock", "paper", "scissors", "scissor"]
                )
                
                guess = msg.content.lower().strip()
                if guess == "scissor":
                    guess = "scissors"

                if guess == correct_guess:
                    winner_found = True
                    user_id = str(msg.author.id)

                    await msg.add_reaction("🎉")
                    await channel.send(embed=discord.Embed(
                        title="🏆 Correct Guess!",
                        description=(
                            f"{msg.author.mention} guessed **{correct_guess.capitalize()}** and won!"
                        ),
                        color=discord.Color.green()
                    ))
                    break
                
            except asyncio.TimeoutError:
                break

        if not winner_found and self.active_rps.get(guild_id, {}).get("running", False):
            await channel.send(embed=discord.Embed(
                title="⌛ Game Timed Out",
                description=f"No one guessed correctly. The correct answer was **{correct_guess.capitalize()}**.",
                color=discord.Color.red()
            ))
        
        self.active_rps.pop(guild_id, None)

    @app_commands.command(name="stoprps", description="Force stop the Rock Paper Scissors game")
    async def stoprps(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have permission to stop RPS.", ephemeral=True)

        if guild_id in self.active_rps:
            self.active_rps[guild_id]["stop_event"].set()
            self.active_rps.pop(guild_id, None)

            await interaction.response.send_message("🛑 RPS game stopped.")
            await interaction.channel.send("⚠️ RPS game forcefully stopped in this channel.")
        else:
            await interaction.response.send_message("❗ No RPS game is currently running in this channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RPS(bot))