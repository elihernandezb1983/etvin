import discord
from discord import app_commands
from discord.ext import commands

from config import SOCIAL_PANEL_TITLE, SOCIAL_PANEL_TEXT, parse_social_links
from utils.permissions import admin_only
from utils.database import get_panel


SOCIAL_CHOICES = [
    app_commands.Choice(name="Обзор", value="overview"),
]


class SocialSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="соц-настройка", description="Настройка панели соцсетей")
    @admin_only()
    @app_commands.describe(действие="Что посмотреть")
    @app_commands.choices(действие=SOCIAL_CHOICES)
    async def social_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
    ):
        gid = interaction.guild_id
        social_panel = await get_panel(gid, "social")
        social_panel_ch = (
            interaction.guild.get_channel(social_panel["channel_id"])
            if social_panel
            else None
        )
        social_links = parse_social_links()
        if social_links:
            social_lines = [f"• {link['label']} — {link['url']}" for link in social_links]
            links_value = "\n".join(social_lines)
        else:
            links_value = "— не настроены"

        embed = discord.Embed(title="🌐 Соцсети", color=0x000000)
        embed.add_field(
            name="Панель",
            value=social_panel_ch.mention if social_panel_ch else "— не опубликована (`/панель`)",
            inline=False,
        )
        embed.add_field(
            name="Ссылки",
            value=links_value,
            inline=False,
        )
        embed.add_field(
            name="Текст панели",
            value=(
                "настраивается в `config.py` / `.env`\n"
                f"**Заголовок:** {SOCIAL_PANEL_TITLE}\n"
                f"**Текст:** {SOCIAL_PANEL_TEXT[:120]}"
            ),
            inline=False,
        )
        embed.set_footer(text="Ссылки и текст — SOCIAL_LINKS, SOCIAL_PANEL_TEXT в config")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialSetupCog(bot))
