import asyncio
import re
import unicodedata

import discord

from config import (
    SQUAD_ROLE_KEYWORD,
    SQUAD_LEADER_ROLE_KEYWORD,
    SQUAD_ROLE_IDS,
    SQUAD_LEADER_ROLE_IDS,
)
from utils.database import get_settings

_SMALL_CAPS_START = 0x1D00
_SMALL_CAPS_END = 0x1D7F
_CYRILLIC_START = 0x0400
_CYRILLIC_END = 0x04FF
# Discord small-caps generators use these when the real letter is missing (e.g. q)
_FANCY_HOMOGLYPHS = {
    0x01EB: "q",  # ǫ — fake q in sǫᴜᴀᴅ
    0x024B: "q",  # ɋ
    0x051B: "q",  # ԛ
}

# Latin styled letters — only blocks with strict A-Z / a-z layout (no Script: gaps there)
_MATH_CAP_BASES = (
    0x1D400, 0x1D434, 0x1D468,
    0x1D5A0, 0x1D5D4, 0x1D608, 0x1D63C,
    0x1D504, 0x1D56C, 0x1D670, 0x1D538,
)
_MATH_SMALL_BASES = (
    0x1D41A, 0x1D44E, 0x1D482,
    0x1D5BA, 0x1D5EE, 0x1D622, 0x1D656,
    0x1D51E, 0x1D586, 0x1D68A, 0x1D552,
)
# Script / italic letters that live outside the main math block
_MATH_LETTERLIKE = {
    0x210A: "g", 0x210B: "h", 0x210C: "h", 0x210D: "h", 0x210E: "h",
    0x210F: "h", 0x2110: "i", 0x2111: "i", 0x2112: "l", 0x2113: "l",
    0x2114: "l", 0x2115: "n", 0x2119: "p", 0x211A: "q", 0x211B: "r",
    0x211C: "r", 0x211D: "r", 0x2124: "z", 0x2128: "z", 0x212C: "b",
    0x212D: "c", 0x212F: "e", 0x2130: "e", 0x2131: "f", 0x2133: "m",
    0x2134: "o", 0x1D456: "h", 0x1D49C: "a", 0x1D4A2: "c", 0x1D4A5: "f",
    0x1D4A6: "g", 0x1D4A9: "j", 0x1D4AA: "k", 0x1D4AB: "l", 0x1D4AC: "l",
    0x1D4AE: "n", 0x1D4AF: "o", 0x1D4B0: "p", 0x1D4B1: "q", 0x1D4B2: "r",
    0x1D4B3: "s", 0x1D4B4: "t", 0x1D4B5: "u", 0x1D4B6: "v", 0x1D4B7: "w",
    0x1D4B8: "x", 0x1D4B9: "y", 0x1D4BB: "a", 0x1D4BC: "b", 0x1D4BD: "c",
    0x1D4BE: "d", 0x1D4BF: "e", 0x1D4C0: "f", 0x1D4C1: "g", 0x1D4C2: "h",
    0x1D4C3: "i", 0x1D4C5: "k", 0x1D4C6: "l", 0x1D4C7: "m", 0x1D4C8: "n",
    0x1D4C9: "o", 0x1D4CA: "p", 0x1D4CB: "q", 0x1D4CC: "r", 0x1D4CD: "s",
    0x1D4CE: "t", 0x1D4CF: "u", 0x1D4D0: "a", 0x1D4D1: "b", 0x1D4D2: "c",
    0x1D4D3: "d", 0x1D4D4: "e", 0x1D4D5: "f", 0x1D4D6: "g", 0x1D4D7: "h",
    0x1D4D8: "i", 0x1D4D9: "j", 0x1D4DA: "k", 0x1D4DB: "l", 0x1D4DC: "m",
    0x1D4DD: "n", 0x1D4DE: "o", 0x1D4DF: "p", 0x1D4E0: "q", 0x1D4E1: "r",
    0x1D4E2: "s", 0x1D4E3: "t", 0x1D4E4: "u", 0x1D4E5: "v", 0x1D4E6: "w",
    0x1D4E7: "x", 0x1D4E8: "y", 0x1D4E9: "z",
}
_SQUAD_NAME_HINTS = ("squad", "сквад", "skvad", "sqaud")
_LEADER_NAME_HINTS = ("leader", "лидер")


async def squad_excluded_role_ids(guild: discord.Guild) -> set[int]:
    settings = await get_settings(guild.id)
    excluded = {guild.default_role.id}
    admin_role_id = settings.get("admin_role_id")
    if admin_role_id:
        excluded.add(admin_role_id)
    return excluded


async def ensure_members_cached(guild: discord.Guild, *, timeout: float = 6.0) -> None:
    try:
        await asyncio.wait_for(guild.chunk(), timeout=timeout)
    except (asyncio.TimeoutError, discord.HTTPException):
        pass


def normalize_role_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold()


def _math_letter(code: int) -> str | None:
    if code in _MATH_LETTERLIKE:
        return _MATH_LETTERLIKE[code]
    for base in _MATH_CAP_BASES:
        offset = code - base
        if 0 <= offset < 26:
            return chr(ord("a") + offset)
    for base in _MATH_SMALL_BASES:
        offset = code - base
        if 0 <= offset < 26:
            return chr(ord("a") + offset)
    return None


def _nfkc_letter(char: str) -> str:
    for part in unicodedata.normalize("NFKC", char):
        if part.isascii() and part.isalpha():
            return part.lower()
        if _CYRILLIC_START <= ord(part) <= _CYRILLIC_END:
            return part.lower()
    return ""


def _latin_small_cap_letter(char: str) -> str | None:
    code = ord(char)
    if code in _FANCY_HOMOGLYPHS:
        return _FANCY_HOMOGLYPHS[code]
    try:
        name = unicodedata.name(char)
    except ValueError:
        return None
    if "SMALL CAPITAL" not in name:
        return None
    token = name.rsplit(maxsplit=1)[-1]
    if len(token) == 1 and token.isalpha():
        return token.lower()
    return None


def _char_to_ascii_letter(char: str) -> str:
    if not char:
        return ""
    code = ord(char)
    if char.isascii() and char.isalpha():
        return char.lower()
    if _CYRILLIC_START <= code <= _CYRILLIC_END:
        return char.lower()
    if code in _FANCY_HOMOGLYPHS:
        return _FANCY_HOMOGLYPHS[code]
    small_cap = _latin_small_cap_letter(char)
    if small_cap:
        return small_cap
    if 0x1D400 <= code <= 0x1D7FF:
        nfkc = _nfkc_letter(char)
        if nfkc:
            return nfkc
        math_letter = _math_letter(code)
        if math_letter:
            return math_letter
    else:
        math_letter = _math_letter(code)
        if math_letter:
            return math_letter
    if 0xFF21 <= code <= 0xFF3A:
        return chr(ord("a") + code - 0xFF21)
    if 0xFF41 <= code <= 0xFF5A:
        return chr(ord("a") + code - 0xFF41)
    if 0x24B6 <= code <= 0x24CF:
        return chr(ord("a") + code - 0x24B6)
    if 0x24D0 <= code <= 0x24E9:
        return chr(ord("a") + code - 0x24D0)
    nfkc = _nfkc_letter(char)
    if nfkc:
        return nfkc
    folded = ""
    for part in unicodedata.normalize("NFKD", char):
        if part.isascii() and part.isalpha():
            folded += part.lower()
        elif _CYRILLIC_START <= ord(part) <= _CYRILLIC_END:
            folded += part.lower()
    return folded


def fold_role_name(name: str) -> str:
    letters = [_char_to_ascii_letter(char) for char in name]
    return "".join(letters)


def letters_only(name: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]", "", fold_role_name(name))


def _keyword_alternatives(keyword: str) -> list[str]:
    return [part.strip() for part in keyword.split(",") if part.strip()]


def _keyword_parts(keyword: str) -> list[str]:
    folded = letters_only(keyword)
    parts = [part for part in keyword.split() if part]
    if parts:
        folded_parts = []
        for part in parts:
            part_folded = letters_only(part)
            if part_folded:
                folded_parts.append(part_folded)
        if folded_parts:
            return folded_parts
    return [folded] if folded else []


def role_name_matches(name: str, keyword: str) -> bool:
    folded_name = letters_only(name)
    if not folded_name:
        return False
    parts = _keyword_parts(keyword)
    if not parts:
        return False
    return all(part in folded_name for part in parts)


def _folded_has_any(folded: str, hints: tuple[str, ...]) -> bool:
    return any(hint in folded for hint in hints)


def is_leader_role_name(name: str) -> bool:
    folded = letters_only(name)
    if not folded:
        return False
    return (
        _folded_has_any(folded, _LEADER_NAME_HINTS)
        and _folded_has_any(folded, _SQUAD_NAME_HINTS)
    )


def is_leader_role(role: discord.Role) -> bool:
    if role.id in SQUAD_LEADER_ROLE_IDS:
        return True
    if is_leader_role_name(role.name):
        return True
    for keyword in _keyword_alternatives(SQUAD_LEADER_ROLE_KEYWORD):
        if role_name_matches(role.name, keyword):
            return True
    return False


def is_squad_role(role: discord.Role) -> bool:
    if is_leader_role(role):
        return False
    if role.id in SQUAD_ROLE_IDS:
        return True
    folded = letters_only(role.name)
    if not folded:
        return False
    for keyword in _keyword_alternatives(SQUAD_ROLE_KEYWORD):
        parts = _keyword_parts(keyword)
        if parts and all(part in folded for part in parts):
            return True
    return _folded_has_any(folded, _SQUAD_NAME_HINTS)


def find_squad_leader_role(guild: discord.Guild) -> discord.Role | None:
    for role_id in SQUAD_LEADER_ROLE_IDS:
        role = guild.get_role(role_id)
        if role:
            return role
    for role in reversed(guild.roles):
        if is_leader_role(role):
            return role
    return None


def get_member_leader_roles(member: discord.Member) -> list[discord.Role]:
    return [role for role in member.roles if is_leader_role(role)]


def member_is_squad_leader(member: discord.Member) -> bool:
    return bool(get_member_leader_roles(member))


def get_member_leader_role(member: discord.Member) -> discord.Role | None:
    roles = get_member_leader_roles(member)
    return roles[0] if roles else None


def members_with_role(guild: discord.Guild, role: discord.Role) -> list[discord.Member]:
    members = [member for member in guild.members if role in member.roles]
    if members:
        return members
    return list(role.members)


def member_count_for_role(guild: discord.Guild, role: discord.Role) -> int:
    return len(members_with_role(guild, role))


def squad_leader_id(
    guild: discord.Guild,
    squad_role: discord.Role,
    leader_role: discord.Role | None = None,
) -> int | None:
    for member in members_with_role(guild, squad_role):
        if member_is_squad_leader(member):
            return member.id
    return None


def get_squad_roles(guild: discord.Guild, *, excluded: set[int] | None = None) -> list[discord.Role]:
    if excluded is None:
        excluded = set()
    roles = []
    for role in guild.roles:
        if role.id in excluded or role.is_integration():
            continue
        if is_squad_role(role):
            roles.append(role)
    return roles


def get_member_squad_roles(member: discord.Member, guild: discord.Guild) -> list[discord.Role]:
    return [role for role in member.roles if is_squad_role(role)]


def can_manage_squad(member: discord.Member, squad_role: discord.Role) -> bool:
    return squad_role in member.roles and member_is_squad_leader(member)


def get_led_squad_roles(member: discord.Member) -> list[discord.Role]:
    return [
        role for role in get_member_squad_roles(member, member.guild)
        if can_manage_squad(member, role)
    ]


async def collect_squad_rows(guild: discord.Guild) -> list[dict]:
    await ensure_members_cached(guild)
    excluded = await squad_excluded_role_ids(guild)
    leader_role = find_squad_leader_role(guild)
    rows: list[dict] = []

    for role in get_squad_roles(guild, excluded=excluded):
        rows.append({
            "role_id": role.id,
            "leader_id": squad_leader_id(guild, role, leader_role),
            "member_count": member_count_for_role(guild, role),
        })

    rows.sort(key=lambda row: (-row["member_count"], row["role_id"]))
    return rows


def squad_members_excluding_leader(
    guild: discord.Guild,
    squad_role: discord.Role,
    leader_role: discord.Role | None = None,
) -> list[discord.Member]:
    members = members_with_role(guild, squad_role)
    return [member for member in members if not member_is_squad_leader(member)]


def can_manage_role(guild: discord.Guild, role: discord.Role) -> tuple[bool, str]:
    me = guild.me
    if not me:
        return False, "Бот недоступен."
    if not me.guild_permissions.manage_roles:
        return False, "У бота нет права **Управление ролями**."
    if role >= me.top_role:
        return False, f"Роль {role.mention} выше роли бота — подними роль бота выше."
    return True, ""


def can_remove_squad_role(guild: discord.Guild, squad_role: discord.Role) -> tuple[bool, str]:
    return can_manage_role(guild, squad_role)


def can_assign_squad_role(guild: discord.Guild, squad_role: discord.Role) -> tuple[bool, str]:
    return can_manage_role(guild, squad_role)
