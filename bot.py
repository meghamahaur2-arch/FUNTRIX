import os
import asyncio
import discord
import random
import sqlite3
import json
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.presences = True
intents.guilds = True
intents.message_content = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)







@bot.event
async def on_ready():
    guild = discord.utils.get(bot.guilds, name=GUILD)
    await bot.tree.sync()
    print(
        f'{bot.user} is connected to the following guild:\n'
        f'{guild.name}(id: {guild.id})')

    print(f"Bot is Working as {bot.user}")



async def load_cogs():
    await bot.load_extension("cogs.games.GUESS_THE_NUMBER")
    await bot.load_extension("cogs.games.TRIVIA")
    await bot.load_extension("cogs.games.R-P-S")
    await bot.load_extension("cogs.games.scramble_words")
    await bot.load_extension("cogs.games.Lyrics_Guess")
    await bot.load_extension("cogs.games.emoji_guess")
  
    await bot.load_extension("Utilities.Leaderboard")
    await bot.load_extension("Utilities.ServerSetup")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
