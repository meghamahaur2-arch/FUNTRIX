import os
import asyncio
import discord
import random
import json
from discord.ext import commands
from dotenv import load_dotenv


# --- NEW: tiny web server for Render ---
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Render provides $PORT
    app.run(host="0.0.0.0", port=port)

# ---------------------------------------

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
    # Start the Flask server in a background thread
    threading.Thread(target=run_flask).start()
    asyncio.run(main())
