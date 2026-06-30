import discord
from discord import app_commands
from discord.ext import commands

from config import TWITCH_ANNOUNCE_TEXT, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from utils.permissions import admin_only
from utils.database import add_twitch_alert, remove_twitch_alert, get_twitch_alerts


TWITCH_CHOICES = [
    app_commands.Choice(name="Добавить стримера", value="add"),
    app_commands.Choice(name="Удалить стримера", value="remove"),
    app_commands.Choice(name="Обзор", value="overview"),
]


class TwitchSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="твич-настройка", description="Уведомления о стримах Twitch")
    @admin_only()
    @app_commands.describe(
        действие="Что сделать",
        канал="Канал для анонсов",
        твич="Логин Twitch (без @)",
        участник="Кого упоминать в анонсе",
    )
    @app_commands.choices(действие=TWITCH_CHOICES)
    async def twitch_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
        твич: str | None = None,
        участник: discord.Member | None = None,
    ):
        action = действие.value
        gid = interaction.guild_id

        if action == "add":
            if not канал or not твич:
                return await interaction.response.send_message(
                    "Укажи **канал** и **твич**-логин.",
                    ephemeral=True,
                )
            if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
                return await interaction.response.send_message(
                    "Добавь `TWITCH_CLIENT_ID` и `TWITCH_CLIENT_SECRET` в `.env`",
                    ephemeral=True,
                )
            login = твич.strip().lower().lstrip("@")
            ok = await add_twitch_alert(
                gid,
                канал.id,
                login,
                участник.id if участник else None,
            )
            if not ok:
                return await interaction.response.send_message(
                    f"Стример **{login}** уже добавлен.",
                    ephemeral=True,
                )
            mention = участник.mention if участник else f"`@{login}`"
            await interaction.response.send_message(
                f"✅ Анонсы Twitch настроены:\n"
                f"• Канал: {канал.mention}\n"
                f"• Twitch: **{login}**\n"
                f"• Упоминание: {mention}",
                ephemeral=True,
            )

        elif action == "remove":
            if not твич:
                return await interaction.response.send_message(
                    "Укажи **твич**-логин.",
                    ephemeral=True,
                )
            login = твич.strip().lower().lstrip("@")
            ok = await remove_twitch_alert(gid, login)
            if not ok:
                return await interaction.response.send_message(
                    f"Стример **{login}** не найден.",
                    ephemeral=True,
                )
            await interaction.response.send_message(
                f"✅ Стример **{login}** удалён.",
                ephemeral=True,
            )

        elif action == "overview":
            alerts = await get_twitch_alerts(gid)
            if alerts:
                lines = []
                for a in alerts:
                    ch = interaction.guild.get_channel(a["channel_id"])
                    member = (
                        interaction.guild.get_member(a["discord_user_id"])
                        if a.get("discord_user_id")
                        else None
                    )
                    mention = member.mention if member else f"@{a['twitch_login']}"
                    lines.append(
                        f"• **{a['twitch_login']}** → {ch.mention if ch else '—'} | {mention}"
                    )
                alerts_value = "\n".join(lines)
            else:
                alerts_value = "— не настроены"

            api_status = (
                "✅ подключено"
                if TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
                else "❌ нужны ключи в `.env`"
            )

            embed = discord.Embed(title="📺 Twitch", color=0x9146FF)
            embed.add_field(name="Стримеры", value=alerts_value, inline=False)
            embed.add_field(name="Twitch API", value=api_status, inline=False)
            embed.add_field(
                name="Текст анонса",
                value=f"`config.py` → `TWITCH_ANNOUNCE_TEXT`\n{TWITCH_ANNOUNCE_TEXT[:150]}",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchSetupCog(bot))
