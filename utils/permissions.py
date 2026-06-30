import discord
from discord import app_commands

from utils.database import get_settings


async def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    settings = await get_settings(interaction.guild_id)
    role_id = settings.get("admin_role_id")
    if role_id:
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
    return False


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        return await is_admin(interaction)

    return app_commands.check(predicate)
