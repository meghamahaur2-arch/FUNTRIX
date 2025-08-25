import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseManager()

    @app_commands.command(name="setup", description="Configure the bot for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, game_master_role: discord.Role):
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        
        # The database call is now safe because the interaction is deferred
        self.db.update_server_settings(
            guild_id=guild_id,
            allowed_roles=[game_master_role.name]
        )

        # Send the final response as a follow-up message
        await interaction.followup.send(
            "Make a role with the name \"Host\" **with H in capital letter and assign it to the people who will be hosting games.**"
            "youre good to go! 🎉",
        )

    @setup.error
    async def setup_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Check if the interaction has already been responded to
        if not interaction.response.is_done():
            # Defer the response if not already done
            await interaction.response.defer(ephemeral=True)
            
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send("❌ You must have administrator permissions to run this command.", ephemeral=True)
        else:
            await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Setup(bot))
