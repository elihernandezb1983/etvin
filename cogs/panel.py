import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import admin_only
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
)
from cogs.shop import ShopPanelView


PANEL_CHOICES = [
    app_commands.Choice(name="Роли (реакции)", value="roles"),
    app_commands.Choice(name="Социальные сети", value="social"),
    app_commands.Choice(name="Правила", value="rules"),
    app_commands.Choice(name="Магазин", value="shop"),
]


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="панель", description="Опубликовать панель в выбранный канал")
    @admin_only()
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
        panel_type = тип.value

        if panel_type == "roles":
            bindings = await get_role_bindings(interaction.guild_id)
            if not bindings:
                await interaction.response.send_message(
                    "Сначала добавь роли: `/роли-настройка` → **Добавить роль**",
                    ephemeral=True,
                )
                return

            embed = role_panel_embed()
            await interaction.response.send_message(
                f"✅ Панель опубликована в {канал.mention}",
                ephemeral=True,
            )
            msg = await канал.send(embed=embed)
            await save_panel(interaction.guild_id, "roles", канал.id, msg.id)

        elif panel_type == "social":
            links = parse_social_links()
            if not links:
                await interaction.response.send_message(
                    "Добавь ссылки в `config.py` / `.env` → `SOCIAL_LINKS`",
                    ephemeral=True,
                )
                return

            image_url, image_file = load_social_panel_image()

            embed = social_panel_embed(image_url)
            view = SocialPanelView(links)
            files = [image_file] if image_file else None
            await interaction.response.send_message(
                f"✅ Панель опубликована в {канал.mention}",
                ephemeral=True,
            )
            msg = await канал.send(embed=embed, view=view, files=files)
            await save_panel(interaction.guild_id, "social", канал.id, msg.id)

        elif panel_type == "rules":
            image_url, image_file = load_rules_panel_image()
            embed = rules_panel_embed(image_url)
            files = [image_file] if image_file else None
            await interaction.response.send_message(
                f"✅ Панель опубликована в {канал.mention}",
                ephemeral=True,
            )
            msg = await канал.send(embed=embed, files=files)
            await save_panel(interaction.guild_id, "rules", канал.id, msg.id)

        elif panel_type == "shop":
            image_url, image_file = load_shop_panel_image()
            embed = await shop_panel_embed(interaction.guild, image_url)
            view = ShopPanelView()
            files = [image_file] if image_file else None
            await interaction.response.send_message(
                f"✅ Панель опубликована в {канал.mention}",
                ephemeral=True,
            )
            msg = await канал.send(embed=embed, view=view, files=files)
            await save_panel(interaction.guild_id, "shop", канал.id, msg.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
