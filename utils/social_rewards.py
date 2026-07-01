from config import parse_social_links


def twitch_channel_login() -> str | None:
    for link in parse_social_links():
        url = link["url"].lower()
        if "twitch.tv/" in url:
            login = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
            if login:
                return login
    return None


def telegram_channel_ref() -> str | None:
    for link in parse_social_links():
        url = link["url"].lower()
        if "t.me/" in url:
            ref = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
            if ref and ref not in ("joinchat", "addstickers", "share"):
                return f"@{ref}" if not ref.startswith("@") else ref
    return None
