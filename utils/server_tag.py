import discord

import config


def user_has_server_tag(user: discord.abc.User, guild_id: int) -> bool:
    pg = getattr(user, "primary_guild", None)
    if pg is None:
        return False
    if pg.identity_enabled is not True:
        return False
    if pg.id != guild_id:
        return False
    return True


def scale_reward(base: int, has_tag: bool) -> int:
    if base <= 0 or not has_tag:
        return base
    return base * config.SERVER_TAG_MULTIPLIER_NUM // config.SERVER_TAG_MULTIPLIER_DEN


def multiplier_label() -> str:
    num = config.SERVER_TAG_MULTIPLIER_NUM
    den = config.SERVER_TAG_MULTIPLIER_DEN
    if num % den == 0:
        return str(num // den)
    if den == 2 and num == 3:
        return "1.5"
    return f"{num}/{den}"
