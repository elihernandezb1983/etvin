import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import admin_only
from utils.database import adjust_shop_points, get_shop_points
from utils.discord_log import log_server
from utils.shop_ui import build_earning_setup_embed, EarningSetupView


class EarningSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="начисление-настройка", description="Настройка начисления баллов")
    @admin_only()
    async def earning_setup(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        embed = await build_earning_setup_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed,
            view=EarningSetupView(),
            ephemeral=True,
        )

    @app_commands.command(name="начислить-баллы", description="Выдать баллы участнику")
    @admin_only()
    @app_commands.describe(
        пользователь="Кому начислить (выбери через @)",
        количество="Сколько баллов",
    )
    async def grant_points(
        self,
        interaction: discord.Interaction,
        пользователь: discord.User,
        количество: app_commands.Range[int, 1, 1_000_000],
    ):
        if not interaction.guild:
            return
        if пользователь.bot:
            await interaction.response.send_message("Нельзя начислить боту.", ephemeral=True)
            return

        total = await adjust_shop_points(interaction.guild.id, пользователь.id, количество)
        await interaction.response.send_message(
            f"✅ {пользователь.mention} +**{количество}** баллов → всего **{total}**",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Начисление баллов**\n{interaction.user.mention} → {пользователь.mention}\n"
            f"+**{количество}** · всего **{total}**",
        )

    @app_commands.command(name="убрать-баллы", description="Снять баллы у участника")
    @admin_only()
    @app_commands.describe(
        пользователь="У кого снять (выбери через @)",
        количество="Сколько баллов",
    )
    async def remove_points(
        self,
        interaction: discord.Interaction,
        пользователь: discord.User,
        количество: app_commands.Range[int, 1, 1_000_000],
    ):
        if not interaction.guild:
            return
        if пользователь.bot:
            await interaction.response.send_message("Нельзя снять у бота.", ephemeral=True)
            return

        before = await get_shop_points(interaction.guild.id, пользователь.id)
        total = await adjust_shop_points(interaction.guild.id, пользователь.id, -количество)
        removed = before["points"] - total

        await interaction.response.send_message(
            f"✅ {пользователь.mention} −**{removed}** баллов → всего **{total}**",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Снятие баллов**\n{interaction.user.mention} → {пользователь.mention}\n"
            f"−**{removed}** · всего **{total}**",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EarningSetupCog(bot))
