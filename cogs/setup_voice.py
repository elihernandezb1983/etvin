import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import admin_only
from utils.database import save_voice_setup, delete_voice_setup, get_voice_setup


VOICE_CHOICES = [
    app_commands.Choice(name="Привязать", value="setup"),
    app_commands.Choice(name="Сброс", value="reset"),
    app_commands.Choice(name="Обзор", value="overview"),
]


class VoiceSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="войс-настройка", description="Настройка кастом войсов")
    @admin_only()
    @app_commands.describe(
        действие="Что сделать",
        категория="Категория для временных войсов",
        войс="Канал-прихожая (триггер)",
    )
    @app_commands.choices(действие=VOICE_CHOICES)
    async def voice_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        категория: discord.CategoryChannel | None = None,
        войс: discord.VoiceChannel | None = None,
    ):
        action = действие.value
        gid = interaction.guild_id

        if action == "setup":
            if not категория or not войс:
                return await interaction.response.send_message(
                    "Укажи **категорию** и **войс**-канал (прихожую).",
                    ephemeral=True,
                )
            await save_voice_setup(gid, категория.id, войс.id)
            await interaction.response.send_message(
                f"✅ Войс настроен:\n"
                f"• Категория: **{категория.name}**\n"
                f"• Прихожая: {войс.mention}\n\n"
                f"Новые комнаты создаются в категории с её правами.",
                ephemeral=True,
            )

        elif action == "reset":
            ok = await delete_voice_setup(gid)
            if not ok:
                return await interaction.response.send_message(
                    "Войс не был настроен.",
                    ephemeral=True,
                )
            await interaction.response.send_message("✅ Привязка войса сброшена.", ephemeral=True)

        elif action == "overview":
            voice_setup = await get_voice_setup(gid)
            if voice_setup:
                voice_cat = interaction.guild.get_channel(voice_setup["category_id"])
                voice_lobby = interaction.guild.get_channel(voice_setup["lobby_channel_id"])
                voice_value = (
                    f"Категория: **{voice_cat.name if voice_cat else '—'}**\n"
                    f"Прихожая: {voice_lobby.mention if voice_lobby else '—'}"
                )
            else:
                voice_value = "— не настроен"

            embed = discord.Embed(title="🔊 Кастом войс", color=0x000000)
            embed.add_field(name="Привязка", value=voice_value, inline=False)
            embed.set_footer(text="Текст панели — в config.py → VOICE_PANEL_TEXT")
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceSetupCog(bot))
