import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import is_admin
from config import parse_social_links
from utils.database import get_role_bindings, save_panel
from utils.views import (
    role_panel_embed,
    social_panel_embed,
    rules_panel_embed,
    shop_panel_embed,
    SocialPanelView,
    load_social_panel_image,
    load_rules_panel_image,
    load_shop_panel_image,
    load_giveaway_panel_image,
)
from cogs.shop import ShopPanelView
from cogs.giveaway import GiveawayPanelView
from utils.giveaway_ui import giveaway_panel_embed
from utils.referral_ui import (
    points_leaderboard_embed,
    referrals_leaderboard_embed,
    squads_leaderboard_embed,
)
from utils.squad_ui import squad_panel_embed, SquadPanelView


PANEL_CHOICES = [
    app_commands.Choice(name="Роли (реакции)", value="roles"),
    app_commands.Choice(name="Социальные сети", value="social"),
    app_commands.Choice(name="Правила", value="rules"),
    app_commands.Choice(name="Магазин", value="shop"),
    app_commands.Choice(name="Розыгрыши", value="giveaway"),
    app_commands.Choice(name="Лидерборд (баллы)", value="leaderboard_points"),
    app_commands.Choice(name="Лидерборд (рефералы)", value="leaderboard_referrals"),
    app_commands.Choice(name="Лидерборд (сквады)", value="leaderboard_squads"),
    app_commands.Choice(name="Сквады (управление)", value="squad_manage"),
]


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _done(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await interaction.followup.send(
            f"✅ Панель опубликована в {channel.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="панель", description="Опубликовать панель в выбранный канал")
    @app_commands.describe(
        тип="Тип панели",
        канал="Канал, куда отправить панель",
    )
    @app_commands.choices(тип=PANEL_CHOICES)
    async def panel(
        self,
        interaction: discord.Interaction,
        тип: app_commands.Choice[str],
        канал: discord.TextChannel,
    ):
        if not interaction.guild:
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if not await is_admin(interaction):
            await interaction.followup.send("Недостаточно прав.", ephemeral=True)
            return

        panel_type = тип.value

        if panel_type == "roles":
            bindings = await get_role_bindings(interaction.guild_id)
            if not bindings:
                await interaction.followup.send(
                    "Сначала добавь роли: `/роли-настройка` → **Добавить роль**",
                    ephemeral=True,
                )
                return

            embed = role_panel_embed()
            msg = await канал.send(embed=embed)
            await save_panel(interaction.guild_id, "roles", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "social":
            links = parse_social_links()
            if not links:
                await interaction.followup.send(
                    "Добавь ссылки в `config.py` / `.env` → `SOCIAL_LINKS`",
                    ephemeral=True,
                )
                return

            image_url, image_file = load_social_panel_image()
            embed = social_panel_embed(image_url)
            view = SocialPanelView(links)
            files = [image_file] if image_file else None
            msg = await канал.send(embed=embed, view=view, files=files)
            await save_panel(interaction.guild_id, "social", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "rules":
            image_url, image_file = load_rules_panel_image()
            embed = rules_panel_embed(image_url)
            files = [image_file] if image_file else None
            msg = await канал.send(embed=embed, files=files)
            await save_panel(interaction.guild_id, "rules", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "shop":
            image_url, image_file = load_shop_panel_image()
            embed = await shop_panel_embed(interaction.guild, image_url)
            view = ShopPanelView()
            files = [image_file] if image_file else None
            msg = await канал.send(embed=embed, view=view, files=files)
            await save_panel(interaction.guild_id, "shop", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "giveaway":
            image_url, image_file = load_giveaway_panel_image()
            embed = await giveaway_panel_embed(interaction.guild, image_url)
            view = GiveawayPanelView()
            files = [image_file] if image_file else None
            msg = await канал.send(embed=embed, view=view, files=files)
            await save_panel(interaction.guild_id, "giveaway", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "leaderboard_points":
            embed = await points_leaderboard_embed(interaction.guild)
            msg = await канал.send(embed=embed)
            await save_panel(interaction.guild_id, "leaderboard_points", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "leaderboard_referrals":
            embed = await referrals_leaderboard_embed(interaction.guild)
            msg = await канал.send(embed=embed)
            await save_panel(interaction.guild_id, "leaderboard_referrals", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "leaderboard_squads":
            embed = await squads_leaderboard_embed(interaction.guild)
            msg = await канал.send(embed=embed)
            await save_panel(interaction.guild_id, "leaderboard_squads", канал.id, msg.id)
            await self._done(interaction, канал)

        elif panel_type == "squad_manage":
            embed = squad_panel_embed()
            view = SquadPanelView()
            msg = await канал.send(embed=embed, view=view)
            await save_panel(interaction.guild_id, "squad_manage", канал.id, msg.id)
            await self._done(interaction, канал)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
