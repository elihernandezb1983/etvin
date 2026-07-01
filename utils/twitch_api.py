import logging
import time

import aiohttp

import config

log = logging.getLogger("etvin")


class TwitchAPI:
    def __init__(self):
        self._token: str | None = None
        self._token_expires = 0.0

    async def _ensure_token(self, session: aiohttp.ClientSession) -> str | None:
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return None
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": config.TWITCH_CLIENT_ID,
                "client_secret": config.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        ) as resp:
            if resp.status != 200:
                log.error("Twitch token error: %s", await resp.text())
                return None
            data = await resp.json()

        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    async def get_live_stream(self, login: str) -> dict | None:
        login = login.strip().lower().lstrip("@")
        if not login:
            return None

        async with aiohttp.ClientSession() as session:
            token = await self._ensure_token(session)
            if not token:
                return None

            headers = {
                "Client-ID": config.TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}",
            }
            async with session.get(
                "https://api.twitch.tv/helix/streams",
                params={"user_login": login},
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    log.error("Twitch streams error for %s: %s", login, await resp.text())
                    return None
                data = await resp.json()

        streams = data.get("data", [])
        return streams[0] if streams else None

    async def _headers(self, session: aiohttp.ClientSession) -> dict[str, str] | None:
        token = await self._ensure_token(session)
        if not token or not config.TWITCH_CLIENT_ID:
            return None
        return {
            "Client-ID": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }

    async def get_user_id(self, login: str) -> str | None:
        login = login.strip().lower().lstrip("@")
        if not login:
            return None

        async with aiohttp.ClientSession() as session:
            headers = await self._headers(session)
            if not headers:
                return None
            async with session.get(
                "https://api.twitch.tv/helix/users",
                params={"login": login},
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    log.error("Twitch users error for %s: %s", login, await resp.text())
                    return None
                data = await resp.json()

        users = data.get("data", [])
        return users[0]["id"] if users else None

    async def user_follows_channel(self, user_login: str, channel_login: str) -> bool:
        user_login = user_login.strip().lower().lstrip("@")
        channel_login = channel_login.strip().lower().lstrip("@")
        if not user_login or not channel_login:
            return False

        async with aiohttp.ClientSession() as session:
            headers = await self._headers(session)
            if not headers:
                return False

            async with session.get(
                "https://api.twitch.tv/helix/users",
                params={"login": [user_login, channel_login]},
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    log.error("Twitch users lookup failed: %s", await resp.text())
                    return False
                data = await resp.json()

        users = {u["login"].lower(): u["id"] for u in data.get("data", [])}
        user_id = users.get(user_login)
        broadcaster_id = users.get(channel_login)
        if not user_id or not broadcaster_id:
            return False

        async with aiohttp.ClientSession() as session:
            headers = await self._headers(session)
            if not headers:
                return False
            async with session.get(
                "https://api.twitch.tv/helix/channels/followers",
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
                headers=headers,
            ) as resp:
                if resp.status == 404:
                    return False
                if resp.status != 200:
                    log.error("Twitch followers check failed: %s", await resp.text())
                    return False
                data = await resp.json()

        return bool(data.get("data"))
