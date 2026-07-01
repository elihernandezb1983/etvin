import discord
from discord.ext import commands

from utils.discord_log import log_bot

_COMMAND_LABELS = {
    "панель": "Панель",
    "роли-настройка": "Настройка ролей",
    "соц-настройка": "Настройка соцсетей",
    "правила-настройка": "Настройка правил",
    "магазин-настройка": "Настройка магазина",
    "начисление-настройка": "Настройка начисления",
    "начислить-баллы": "Начислить баллы",
    "убрать-баллы": "Убрать баллы",
    "твич-настройка": "Настройка Twitch",
    "привет-настройка": "Настройка приветствий",
    "войс-настройка": "Настройка войса",
    "логи-настройка": "Настройка логов",
}

_OPTION_LABELS = {
    "действие": "Действие",
    "тип": "Тип",
    "канал": "Канал",
    "роль": "Роль",
    "логин": "Логин",
    "пользователь": "Пользователь",
    "количество": "Количество",
}

_VALUE_LABELS = {
    "overview": "Обзор",
    "channel": "Канал",
    "roles": "Роли",
    "social": "Соцсети",
    "rules": "Правила",
    "shop": "Магазин",
    "add": "Добавить",
    "remove": "Удалить",
    "list": "Список",
    "bot": "Логи бота",
    "server": "Логи сервера",
}


def _label_value(name: str, value: str) -> str:
    label = _VALUE_LABELS.get(value, value)
    return f"{_OPTION_LABELS.get(name, name)}: **{label}**"


def _resolve_value(guild: discord.Guild | None, opt: dict) -> str:
    val = opt.get("value")
    if val is None:
        if "options" in opt:
            return ", ".join(_format_option(guild, o) for o in opt["options"])
        return "—"

    opt_type = opt.get("type")
    name = opt.get("name", "")

    if guild and opt_type in (6, 13):
        member = guild.get_member(int(val))
        return member.mention if member else f"<@{val}>"

    if guild and opt_type in (7, 14):
        channel = guild.get_channel(int(val))
        return channel.mention if channel else f"<#{val}>"

    if guild and opt_type == 8:
        role = guild.get_role(int(val))
        return role.mention if role else f"@{val}"

    if isinstance(val, str) and val.isdigit() and name in ("канал", "channel"):
        if guild:
            channel = guild.get_channel(int(val))
            if channel:
                return channel.mention

    return _label_value(name, str(val))


def _format_option(guild: discord.Guild | None, opt: dict) -> str:
    if opt.get("type") == 1:
        parts = [_resolve_value(guild, sub) for sub in opt.get("options", [])]
        return " · ".join(parts) if parts else opt["name"]
    return _resolve_value(guild, opt)


def _format_command(interaction: discord.Interaction) -> str:
    data = interaction.data or {}
    cmd = data.get("name", "?")
    title = _COMMAND_LABELS.get(cmd, cmd)

    details: list[str] = []
    for opt in data.get("options", []):
        if opt.get("type") == 1:
            details.append(_format_option(interaction.guild, opt))
        else:
            details.append(_format_option(interaction.guild, opt))

    if details:
        return f"**{title}**\n" + "\n".join(details)
    return f"**{title}**"


class InteractionLogCog(commands.Cog):
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.user.bot:
            return
        if interaction.type != discord.InteractionType.application_command:
            return

        channel = interaction.channel
        channel_str = channel.mention if channel else "—"
        asyncio.create_task(
            self._log_command(interaction, channel_str),
            name=f"log-cmd-{interaction.id}",
        )

    async def _log_command(self, interaction: discord.Interaction, channel_str: str) -> None:
        try:
            await log_bot(
                interaction.guild,
                f"{_format_command(interaction)}\n"
                f"{interaction.user.mention} · {channel_str}",
            )
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(InteractionLogCog(bot))
