import logging

import discord

from utils.database import get_settings

log = logging.getLogger("etvin")

SERVER_LOG_COLOR = 0x000000
BOT_LOG_COLOR = 0x000000


def _ts() -> str:
    return f"-# <t:{int(discord.utils.utcnow().timestamp())}:f>"


def _log_view(body: str, accent: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=discord.Color(accent))
    container.add_item(discord.ui.TextDisplay(body))
    view.add_item(container)
    return view


async def _send(guild: discord.Guild, setting_key: str, body: str, accent: int) -> None:
    settings = await get_settings(guild.id)
    channel_id = settings.get(setting_key)
    if not channel_id:
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    try:
        await channel.send(view=_log_view(f"{body}\n{_ts()}", accent))
    except discord.HTTPException as exc:
        log.warning("Не удалось отправить лог в #%s: %s", channel_id, exc)


async def log_server(guild: discord.Guild, body: str, *, color: int = SERVER_LOG_COLOR) -> None:
    await _send(guild, "server_log_channel_id", body, color)


async def log_bot(guild: discord.Guild, body: str, *, color: int = BOT_LOG_COLOR) -> None:
    await _send(guild, "bot_log_channel_id", body, color)
