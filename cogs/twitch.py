import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

import config
from utils.database import (
    get_all_twitch_alerts,
    set_twitch_last_stream,
    mark_twitch_announced,
)
from utils.twitch_api import TwitchAPI

log = logging.getLogger("etvin")


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


class TwitchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.twitch = TwitchAPI()
        self.check_streams.start()

    def cog_unload(self):
        self.check_streams.cancel()

    @tasks.loop(seconds=config.TWITCH_CHECK_INTERVAL)
    async def check_streams(self):
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return

        alerts = await get_all_twitch_alerts()
        for alert in alerts:
            await self._process_alert(alert)

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()

    async def _process_alert(self, alert: dict):
        stream = await self.twitch.get_live_stream(alert["twitch_login"])
        started_at = stream["started_at"] if stream else None
        last_started = alert.get("last_stream_started_at")

        if not stream:
            if last_started:
                await set_twitch_last_stream(alert["id"], None)
            return

        if started_at == last_started:
            return

        last_announced = alert.get("last_announced_at")
        if last_announced:
            announced_dt = _parse_iso(last_announced)
            if announced_dt:
                elapsed = (datetime.now(timezone.utc) - announced_dt).total_seconds()
                if elapsed < config.TWITCH_ANNOUNCE_COOLDOWN:
                    await set_twitch_last_stream(alert["id"], started_at)
                    log.info(
                        "Twitch %s: перезапуск в кулдауне (%.0f с), анонс пропущен",
                        alert["twitch_login"],
                        elapsed,
                    )
                    return

        await self._announce(alert, stream)
        await mark_twitch_announced(
            alert["id"],
            started_at,
            datetime.now(timezone.utc).isoformat(),
        )

    async def _announce(self, alert: dict, stream: dict):
        guild = self.bot.get_guild(alert["guild_id"])
        if not guild:
            return

        channel = guild.get_channel(alert["channel_id"])
        if not channel:
            return

        login = alert["twitch_login"]
        url = f"https://twitch.tv/{login}"

        mention = f"@{login}"
        if alert.get("discord_user_id"):
            member = guild.get_member(alert["discord_user_id"])
            if member:
                mention = member.mention

        text = config.TWITCH_ANNOUNCE_TEXT.format(
            mention=mention,
            login=login,
            url=url,
            title=stream.get("title", ""),
        )

        try:
            await channel.send(
                text,
                allowed_mentions=discord.AllowedMentions(everyone=True, users=True),
            )
            log.info("Twitch анонс: %s → #%s", login, channel.name)
        except discord.Forbidden:
            log.error("Нет прав отправить Twitch-анонс в %s", channel.id)
        except discord.HTTPException as exc:
            log.error("Ошибка Twitch-анонса: %s", exc)


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchCog(bot))
