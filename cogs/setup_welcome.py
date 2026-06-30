import os

import discord
from discord import app_commands
from discord.ext import commands

from config import WELCOME_TITLE, WELCOME_GREETING, WELCOME_TEXT, FOTO_DIR
from utils.permissions import admin_only
from utils.database import get_settings, set_setting


WELCOME_CHOICES = [
    app_commands.Choice(name="Канал приветствий", value="channel"),
    app_commands.Choice(name="Обзор", value="overview"),
]


class WelcomeSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="привет-настройка", description="Настройка приветствий")
    @admin_only()
    @app_commands.describe(
        действие="Что настроить",
        канал="Канал для приветствий",
    )
    @app_commands.choices(действие=WELCOME_CHOICES)
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
    ):
        action = действие.value
        gid = interaction.guild_id

        if action == "channel":
            if not канал:
                return await interaction.response.send_message("Укажи **канал**.", ephemeral=True)
            await set_setting(gid, "welcome_channel_id", канал.id)
            await interaction.response.send_message(f"✅ Приветствия → {канал.mention}", ephemeral=True)

        elif action == "overview":
            s = await get_settings(gid)
            ch = (
                interaction.guild.get_channel(s["welcome_channel_id"])
                if s.get("welcome_channel_id")
                else None
            )
            foto_status = "есть" if os.path.isdir(FOTO_DIR) and any(
                f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
                for f in os.listdir(FOTO_DIR)
            ) else "папка `foto` пуста"

            embed = discord.Embed(title="👋 Приветствия", color=0x000000)
            embed.add_field(
                name="Канал",
                value=ch.mention if ch else "— не настроен",
                inline=False,
            )
            embed.add_field(
                name="Текст и ссылки",
                value=(
                    "настраиваются в `config.py` / `.env`\n"
                    f"**Заголовок:** {(WELCOME_GREETING or WELCOME_TITLE or '—')[:80]}\n"
                    f"**Текст:** {WELCOME_TEXT[:120]}"
                ),
                inline=False,
            )
            embed.add_field(
                name="Фото",
                value=f"из папки `foto` ({foto_status})",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeSetupCog(bot))
