import discord
from discord import app_commands
from discord.ext import commands

from config import WELCOME_IMAGE_URL, rules_admin_mention
from utils.permissions import admin_only
from utils.database import (
    get_settings,
    get_all_panels,
    get_role_bindings,
    get_voice_setup,
    get_twitch_alerts,
    get_shop_items,
    get_earning_rules,
)

PANEL_LABELS = {
    "roles": "🎭 Роли",
    "social": "📱 Соцсети",
    "rules": "📜 Правила",
    "shop": "🛒 Магазин",
    "giveaway": "🎁 Розыгрыши",
    "leaderboard_points": "🏆 Лидерборд (баллы)",
    "leaderboard_referrals": "👥 Лидерборд (рефералы)",
    "leaderboard_squads": "🛡️ Лидерборд (сквады)",
    "squad_manage": "⚙️ Сквады (управление)",
}


def _ch(guild: discord.Guild, channel_id: int | None) -> str:
    if not channel_id:
        return "—"
    ch = guild.get_channel(channel_id)
    return ch.mention if ch else f"`{channel_id}` (удалён)"


def _role(guild: discord.Guild, role_id: int | None) -> str:
    if not role_id:
        return "—"
    role = guild.get_role(role_id)
    return role.mention if role else f"`{role_id}` (удалена)"


def _panel_line(guild: discord.Guild, panel: dict) -> str:
    label = PANEL_LABELS.get(panel["panel_type"], panel["panel_type"])
    ch = _ch(guild, panel["channel_id"])
    link = (
        f"https://discord.com/channels/{guild.id}/"
        f"{panel['channel_id']}/{panel['message_id']}"
    )
    return f"{label} — {ch} · [сообщение]({link})"


def _earning_summary(rules: dict[str, dict]) -> str:
    lines: list[str] = []
    voice = rules.get("voice", {})
    if voice.get("enabled"):
        lines.append(
            f"🎙️ {voice['param1']} мин → {voice['param2']} б."
        )
    words = rules.get("words", {})
    if words.get("enabled"):
        lines.append(
            f"💬 {words['param1']} слов → {words['param2']} б. "
            f"(макс. {words['param3']}/день)"
        )
    referral = rules.get("referral", {})
    if referral.get("enabled"):
        lines.append(
            f"👥 реферал → владельцу {referral['param1']} б., вводящему {referral['param3']} б."
        )
    boost = rules.get("boost", {})
    if boost.get("enabled"):
        lines.append(f"🚀 буст → {boost['param1']} б. за каждый буст")
    twitch = rules.get("twitch", {})
    telegram = rules.get("telegram", {})
    if twitch.get("enabled"):
        lines.append(f"📺 Twitch → до {twitch['param1']} б., тикет (один раз)")
    if telegram.get("enabled"):
        lines.append(f"✈️ Telegram → до {telegram['param1']} б., тикет (один раз)")
    return "\n".join(lines) if lines else "— всё выключено"


def _clamp_field(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n… *(обрезано)*"


class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="сводка", description="Все привязки и настройки бота на сервере")
    @admin_only()
    async def summary(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild = interaction.guild
        gid = guild.id
        settings = await get_settings(gid)
        panels = await get_all_panels(gid)
        bindings = await get_role_bindings(gid)
        voice = await get_voice_setup(gid)
        twitch = await get_twitch_alerts(gid)
        items = await get_shop_items(gid)
        rules = await get_earning_rules(gid)

        embed = discord.Embed(
            title="📋 Сводка привязок",
            color=0x000000,
        )

        admin_parts = []
        if settings.get("admin_role_id"):
            admin_parts.append(f"Роль админа: {_role(guild, settings['admin_role_id'])}")
        admin_parts.append(f"Админ в конфиге: {rules_admin_mention()}")
        embed.add_field(name="👑 Админ", value=_clamp_field("\n".join(admin_parts)), inline=False)

        welcome_lines = [f"Канал: {_ch(guild, settings.get('welcome_channel_id'))}"]
        if (WELCOME_IMAGE_URL or "").strip():
            welcome_lines.append(f"Картинка: [ссылка]({WELCOME_IMAGE_URL.strip()})")
        else:
            welcome_lines.append("Картинка: из `foto/` или —")
        embed.add_field(name="👋 Приветствия", value=_clamp_field("\n".join(welcome_lines)), inline=False)

        if panels:
            panels_value = "\n".join(_panel_line(guild, p) for p in panels)
        else:
            panels_value = "— ни одна панель не опубликована (`/панель`)"
        embed.add_field(name="📌 Панели", value=_clamp_field(panels_value), inline=False)

        roles_value = (
            "\n".join(f"• {_role(guild, b['role_id'])}" for b in bindings)
            if bindings
            else "— роли не добавлены (`/роли-настройка`)"
        )
        embed.add_field(name="🎭 Роли на панели", value=_clamp_field(roles_value), inline=False)

        logs_value = (
            f"Сервер: {_ch(guild, settings.get('server_log_channel_id'))}\n"
            f"Бот: {_ch(guild, settings.get('bot_log_channel_id'))}"
        )
        embed.add_field(name="📋 Логи", value=_clamp_field(logs_value), inline=False)

        if voice:
            voice_value = (
                f"Категория: {_ch(guild, voice['category_id'])}\n"
                f"Прихожая: {_ch(guild, voice['lobby_channel_id'])}"
            )
        else:
            voice_value = "— не настроен (`/войс-настройка`)"
        embed.add_field(name="🔊 Кастом войс", value=_clamp_field(voice_value), inline=False)

        ticket_cat = settings.get("shop_ticket_category_id")
        shop_value = (
            f"Категория тикетов: {_ch(guild, ticket_cat)}\n"
            f"Товаров: **{len(items)}**"
        )
        embed.add_field(name="🛒 Магазин", value=_clamp_field(shop_value), inline=False)
        embed.add_field(name="💰 Начисление", value=_clamp_field(_earning_summary(rules)), inline=False)

        if twitch:
            twitch_lines = []
            for alert in twitch:
                ch = _ch(guild, alert["channel_id"])
                login = alert["twitch_login"]
                user = (
                    f" · <@{alert['discord_user_id']}>"
                    if alert.get("discord_user_id")
                    else ""
                )
                twitch_lines.append(f"• **{login}** → {ch}{user}")
            twitch_value = "\n".join(twitch_lines)
        else:
            twitch_value = "— нет алертов (`/твич-настройка`)"
        embed.add_field(name="📺 Twitch", value=_clamp_field(twitch_value), inline=False)

        embed.set_footer(text="Тексты панелей и ссылки соцсетей — в config.py / .env")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryCog(bot))
