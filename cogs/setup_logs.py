import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import admin_only
from utils.database import get_settings, set_setting


LOG_CHOICES = [
    app_commands.Choice(name="Канал логов сервера", value="server"),
    app_commands.Choice(name="Канал логов бота", value="bot"),
    app_commands.Choice(name="Обзор", value="overview"),
]


class LogsSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="лог-настройка",
        description="Настройка каналов логов (сервер и бот — отдельно)",
    )
    @admin_only()
    @app_commands.describe(
        действие="Что настроить",
        канал="Канал для логов",
    )
    @app_commands.choices(действие=LOG_CHOICES)
    async def logs_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
    ):
        action = действие.value
        gid = interaction.guild_id

        if action == "server":
            if not канал:
                return await interaction.response.send_message("Укажи **канал**.", ephemeral=True)
            await set_setting(gid, "server_log_channel_id", канал.id)
            await interaction.response.send_message(
                f"✅ Логи сервера → {канал.mention}",
                ephemeral=True,
            )

        elif action == "bot":
            if not канал:
                return await interaction.response.send_message("Укажи **канал**.", ephemeral=True)
            await set_setting(gid, "bot_log_channel_id", канал.id)
            await interaction.response.send_message(
                f"✅ Логи бота → {канал.mention}",
                ephemeral=True,
            )

        elif action == "overview":
            s = await get_settings(gid)
            server_ch = (
                interaction.guild.get_channel(s["server_log_channel_id"])
                if s.get("server_log_channel_id")
                else None
            )
            bot_ch = (
                interaction.guild.get_channel(s["bot_log_channel_id"])
                if s.get("bot_log_channel_id")
                else None
            )

            embed = discord.Embed(title="📋 Логи", color=0x000000)
            embed.add_field(
                name="Сервер",
                value=(
                    f"{server_ch.mention}\nВход, выход, роли, баны, кики, таймауты, муты"
                    if server_ch
                    else "— не настроен\nВход, выход, роли, баны, кики, таймауты, муты"
                ),
                inline=False,
            )
            embed.add_field(
                name="Бот",
                value=(
                    f"{bot_ch.mention}\nSlash-команды"
                    if bot_ch
                    else "— не настроен\nSlash-команды"
                ),
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LogsSetupCog(bot))
