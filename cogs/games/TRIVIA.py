import discord
import random
import json
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()

class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trivia = {}
        self.trivia_questions = self.load_questions()
        self.user_wins = {}
        self.used_questions = {}
        self.leaderboard_cog = None
        self.db = DatabaseManager()
        self.unanswered_count = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("Trivia cog is ready.")
        await self.bot.wait_until_ready()
        self.leaderboard_cog = self.bot.get_cog('Leaderboard')
        if self.leaderboard_cog:
            print("Leaderboard cog found and linked to Trivia cog.")
        else:
            print("WARNING: Leaderboard cog not found. Leaderboard functions will not work.")

    def load_questions(self):
        try:
            with open("Data/trivia_questions.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("Error: Data/trivia_questions.json not found!")
            return []
        except json.JSONDecodeError:
            print("Error: Data/trivia_questions.json is corrupted or empty.")
            return []

    def get_random_question(self, guild_id):
        if guild_id not in self.used_questions:
            self.used_questions[guild_id] = set()
            
        used_questions_set = self.used_questions[guild_id]

        if len(used_questions_set) >= len(self.trivia_questions) or not self.trivia_questions:
            used_questions_set.clear()
            if not self.trivia_questions:
                return None

        available = [q for q in self.trivia_questions if q["question"] not in used_questions_set]
        if not available:
            used_questions_set.clear()
            available = self.trivia_questions[:]
        
        question = random.choice(available)
        used_questions_set.add(question["question"])
        return question

    @app_commands.command(name="starttrivia", description="Start a trivia game")
    async def trivia(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        settings = self.db.get_server_settings(guild_id)
        if not settings:
            return await interaction.response.send_message("❌ This server is not set up. Please run `/setup` first!", ephemeral=True)
            
        allowed_roles = settings.get('allowed_roles', [])
        
        user_roles = [role.name for role in interaction.user.roles]
        if not any(role in user_roles for role in allowed_roles):
            return await interaction.response.send_message("❌ You don't have permission to start trivia.", ephemeral=True)

        if guild_id in self.active_trivia:
            return await interaction.response.send_message("❗ Trivia is already running in this server. Use `/stoptrivia` to end the current game.", ephemeral=True)
        
        if not self.trivia_questions:
            return await interaction.response.send_message("❌ No trivia questions loaded. Please check `Data/trivia_questions.json`.", ephemeral=True)

        self.active_trivia[guild_id] = {"running": True, "stop_event": asyncio.Event(), "channel_id": interaction.channel.id}
        self.user_wins[guild_id] = {}
        self.unanswered_count[guild_id] = 0
        await interaction.response.send_message("🧠 Starting Trivia...")
        
        self.bot.loop.create_task(self.ask_question(interaction.channel, interaction.user))

    async def ask_question(self, channel, host):
        guild_id = channel.guild.id

        if not self.active_trivia.get(guild_id, {}).get("running", False):
            return

        question_data = self.get_random_question(guild_id)
        if not question_data:
            await channel.send("❌ No more unique trivia questions available!")
            del self.active_trivia[guild_id]
            self.user_wins.pop(guild_id, None)
            return

        correct_answer = question_data["answer"].strip().lower()

        embed = discord.Embed(
            title="🧠 Trivia Time!",
            description=f"**{question_data['question']}**\n\n⏱️ You have 30 seconds to answer!",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed)

        stop_event = self.active_trivia[guild_id]["stop_event"]
        start_time = asyncio.get_event_loop().time()

        valid_winner_found = False
        
        while not stop_event.is_set():
            remaining_time = 30 - (asyncio.get_event_loop().time() - start_time)
            if remaining_time <= 0:
                break

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=remaining_time,
                    check=lambda m: (m.channel == channel and 
                                     not m.author.bot and 
                                     m.content.strip().lower() == correct_answer and
                                     self.user_wins.get(guild_id, {}).get(str(m.author.id), 0) < 5)
                )

                user_id = str(msg.author.id)
                current_wins = self.user_wins.get(guild_id, {}).get(user_id, 0)
                
                if current_wins >= 5:
                    continue

                valid_winner_found = True
                
                if guild_id not in self.user_wins:
                    self.user_wins[guild_id] = {}
                self.user_wins[guild_id][user_id] = current_wins + 1
                win_count = self.user_wins[guild_id][user_id]
                
                self.db.update_user_stats(user_id=user_id, guild_id=guild_id, game_name="Trivia", wins=1)

                await msg.add_reaction("🎉")

                await channel.send(embed=discord.Embed(
                    title="🏆 Correct!",
                    description=(
                        f"{msg.author.mention} got it! The answer was **{correct_answer}**.\n"
                        f"🎯 Total Wins: `{win_count}/5`"
                    ),
                    color=discord.Color.green()
                ))
                
                self.unanswered_count[guild_id] = 0

                if win_count == 5:
                    if self.leaderboard_cog:
                        added = self.db.add_winner(
                            user_id=user_id, username=msg.author.name,
                            game_name="Trivia", host_id=host.id, host_name=host.name,
                            guild_id=guild_id
                        )

                        if added:
                            await channel.send(embed=discord.Embed(
                                title="🌟 Milestone!",
                                description=f"{msg.author.mention} reached **5 wins** and is now on the leaderboard!",
                                color=discord.Color.blue()
                            ))
                            await self.leaderboard_cog.update_leaderboard_display(channel)
                        else:
                            await channel.send(f"ℹ️ {msg.author.mention} is already on the leaderboard!")
                    else:
                        await channel.send("⚠️ Leaderboard system is not available.")
                
                break

            except asyncio.TimeoutError:
                break

        if not valid_winner_found and self.active_trivia.get(guild_id, {}).get("running", False):
            await channel.send(embed=discord.Embed(
                title="⌛ Time's Up!",
                description=f"No one guessed it. The correct answer was **{correct_answer}**.",
                color=discord.Color.red()
            ))
            self.unanswered_count[guild_id] = self.unanswered_count.get(guild_id, 0) + 1
            
        if self.unanswered_count.get(guild_id, 0) >= 3:
            await channel.send("🚫 **Game stopping!** The last 3 questions went unanswered. Use `/starttrivia` to begin a new game.")
            self.active_trivia.pop(guild_id, None)
            self.user_wins.pop(guild_id, None)
            self.used_questions.pop(guild_id, None)
            self.unanswered_count.pop(guild_id, None)
            return

        if self.active_trivia.get(guild_id, {}).get("running", False):
            await self.ask_question(channel, host)

    @app_commands.command(name="stoptrivia", description="Stop the ongoing trivia game")
    async def stoptrivia(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id

        settings = self.db.get_server_settings(guild_id)
        if not settings:
            return await interaction.response.send_message("❌ This server is not set up. Please run `/setup` first!", ephemeral=True)
        
        allowed_roles = settings.get('allowed_roles', [])
        user_roles = [role.name for role in interaction.user.roles]
        if not any(role in user_roles for role in allowed_roles):
            return await interaction.response.send_message("❌ You don’t have permission to stop trivia.", ephemeral=True)

        if guild_id in self.active_trivia:
            self.active_trivia[guild_id]["stop_event"].set()
            
            await interaction.response.send_message("🛑 Trivia game stopped.")
            await interaction.channel.send("⚠️ Trivia game forcefully stopped in this channel. Here are the final results:")
            
            if self.leaderboard_cog:
                await self.leaderboard_cog.display_leaderboard_command(interaction.channel)
            else:
                await interaction.channel.send("⚠️ Leaderboard system is not available.")
            
            self.active_trivia.pop(guild_id, None)
            self.user_wins.pop(guild_id, None)
            self.used_questions.pop(guild_id, None)
            self.unanswered_count.pop(guild_id, None)
            
            self.db.clear_leaderboard_for_guild(guild_id)
            
        else:
            await interaction.response.send_message("❗ No trivia running in this channel.", ephemeral=True)
    
    @app_commands.command(name="resettriviawins", description="Resets all users' trivia 5-win counts for this server.")
    async def resettriviawins(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id

        settings = self.db.get_server_settings(guild_id)
        if not settings:
            return await interaction.response.send_message("❌ This server is not set up. Please run `/setup` first!", ephemeral=True)
            
        allowed_roles = settings.get('allowed_roles', [])
        user_roles = [role.name for role in interaction.user.roles]
        if not any(role in user_roles for role in allowed_roles):
            return await interaction.response.send_message("❌ You don't have permission to reset win counts.", ephemeral=True)

        if guild_id in self.user_wins and self.user_wins[guild_id]:
            self.user_wins[guild_id].clear()
            await interaction.response.send_message(
                f"✅ All users' trivia 5-win counts for this server have been reset to `0`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "ℹ️ No active 5-win counts for trivia to reset on this server.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Trivia(bot))