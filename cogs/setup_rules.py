import discord
from discord import app_commands
from discord.ext import commands

from config import RULES_FORBIDDEN, RULES_PENALTIES, rules_admin_mention
from utils.permissions import admin_only
from utils.database import get_panel


RULES_CHOICES = [
    app_commands.Choice(name="Обзор", value="overview"),
]


class RulesSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="правила-настройка", description="Настройка панели правил")
    @admin_only()
    @app_commands.describe(действие="Что посмотреть")
    @app_commands.choices(действие=RULES_CHOICES)
    async def rules_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
    ):
        gid = interaction.guild_id
        rules_panel = await get_panel(gid, "rules")
        rules_ch = (
            interaction.guild.get_channel(rules_panel["channel_id"])
            if rules_panel
            else None
        )
        admin = rules_admin_mention()

        embed = discord.Embed(title="📜 Правила", color=0x000000)
        embed.add_field(
            name="Панель",
            value=rules_ch.mention if rules_ch else "— не опубликована (`/панель`)",
            inline=False,
        )
        embed.add_field(
            name="Админ для упоминаний",
            value=admin,
            inline=False,
        )
        embed.add_field(
            name="Текст",
            value=(
                "настраивается в `config.py` / `.env`\n"
                f"**Запреты:** {RULES_FORBIDDEN.format(admin=admin)[:100]}…\n"
                f"**Ответственность:** {RULES_PENALTIES.format(admin=admin)[:100]}…"
            ),
            inline=False,
        )
        embed.set_footer(text="RULES_ADMIN_ID, RULES_FORBIDDEN, RULES_PENALTIES в config")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesSetupCog(bot))
