import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import admin_only
from utils.database import add_role_binding, remove_role_binding, get_role_bindings, get_panel


ROLES_CHOICES = [
    app_commands.Choice(name="Добавить роль", value="add"),
    app_commands.Choice(name="Удалить роль", value="remove"),
    app_commands.Choice(name="Обзор", value="overview"),
]


class RolesSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="роли-настройка", description="Настройка панели ролей")
    @admin_only()
    @app_commands.describe(
        действие="Что сделать",
        роль="Роль Discord",
    )
    @app_commands.choices(действие=ROLES_CHOICES)
    async def roles_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        роль: discord.Role | None = None,
    ):
        action = действие.value
        gid = interaction.guild_id

        if action == "add":
            if not роль:
                return await interaction.response.send_message("Укажи **роль**.", ephemeral=True)
            ok = await add_role_binding(gid, роль.id, роль.name)
            if not ok:
                return await interaction.response.send_message(
                    f"Роль {роль.mention} уже добавлена.",
                    ephemeral=True,
                )
            await interaction.response.send_message(
                f"✅ Добавлена роль {роль.mention}\nОпубликуй панель: `/панель`",
                ephemeral=True,
            )

        elif action == "remove":
            if not роль:
                return await interaction.response.send_message("Укажи **роль**.", ephemeral=True)
            ok = await remove_role_binding(gid, роль.id)
            if not ok:
                return await interaction.response.send_message("Такая роль не найдена.", ephemeral=True)
            await interaction.response.send_message(f"✅ Удалена роль {роль.mention}", ephemeral=True)

        elif action == "overview":
            panel = await get_panel(gid, "roles")
            panel_ch = (
                interaction.guild.get_channel(panel["channel_id"])
                if panel
                else None
            )
            bindings = await get_role_bindings(gid)
            roles_value = (
                "\n".join(f"• <@&{b['role_id']}>" for b in bindings)
                if bindings
                else "— не настроены"
            )

            embed = discord.Embed(title="🎭 Роли", color=0x000000)
            embed.add_field(
                name="Панель",
                value=panel_ch.mention if panel_ch else "— не опубликована (`/панель`)",
                inline=False,
            )
            embed.add_field(name="Роли на панели", value=roles_value, inline=False)
            embed.set_footer(text="Любая реакция на панели выдаёт все перечисленные роли.")
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesSetupCog(bot))
