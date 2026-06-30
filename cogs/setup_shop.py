import discord
from discord import app_commands
from discord.ext import commands

from config import parse_shop_prizes
from utils.permissions import admin_only
from utils.database import get_shop_items, add_shop_item
from utils.shop_ui import build_shop_setup_embed, ShopSetupView


async def _seed_default_items(guild_id: int) -> None:
    if await get_shop_items(guild_id):
        return
    for prize in parse_shop_prizes():
        await add_shop_item(
            guild_id,
            prize["key"],
            prize["name"],
            prize["description"],
            prize["cost"],
            prize.get("role_id") or 0,
        )


class ShopSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="магазин-настройка", description="Настройка магазина баллов")
    @admin_only()
    async def shop_setup(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        await _seed_default_items(interaction.guild.id)
        embed = await build_shop_setup_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed,
            view=ShopSetupView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopSetupCog(bot))
