import logging
import os

import discord

log = logging.getLogger("etvin")

# Discord: до 8 МБ на серверах без буста; 25 МБ — верхняя граница для ботов
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
from config import (
    BLACK,
    ROLE_PANEL_TEXT,
    SOCIAL_PANEL_TITLE,
    SOCIAL_PANEL_TEXT,
    FOTO_DIR,
    SOCIAL_PANEL_IMAGE,
    WELCOME_IMAGE,
    WELCOME_IMAGE_URL,
    RULES_FORBIDDEN,
    RULES_PENALTIES,
    RULES_PANEL_TITLE,
    RULES_PANEL_INTRO,
    RULES_PANEL_FOOTER,
    RULES_PANEL_IMAGE,
    rules_admin_mention,
    SHOP_PANEL_TITLE,
    SHOP_PANEL_IMAGE,
    SHOP_SQUAD_INVITE,
    GIVEAWAY_PANEL_IMAGE,
)
from utils.database import get_shop_items, get_earning_rules
from utils.social_ui import format_social_bonus_earning_lines, social_bonus_enabled


def role_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="🎭 Получение роли",
        description=ROLE_PANEL_TEXT,
        color=discord.Color(BLACK),
    )


class SocialPanelView(discord.ui.View):
    def __init__(self, links: list[dict]):
        super().__init__(timeout=None)
        for link in links[:2]:
            self.add_item(
                discord.ui.Button(
                    label=link["label"][:80],
                    url=link["url"],
                    style=discord.ButtonStyle.link,
                )
            )


def _load_panel_image(filename: str) -> tuple[str | None, discord.File | None]:
    if not filename or not os.path.isdir(FOTO_DIR):
        return None, None

    path = os.path.join(FOTO_DIR, filename)
    if not os.path.isfile(path):
        return None, None

    size = os.path.getsize(path)
    basename = os.path.basename(path)
    if size > MAX_ATTACHMENT_BYTES:
        log.warning(
            "Файл %s слишком большой для Discord (%.1f МБ, лимит %.0f МБ)",
            basename,
            size / (1024 * 1024),
            MAX_ATTACHMENT_BYTES / (1024 * 1024),
        )
        return None, None

    return f"attachment://{basename}", discord.File(path, filename=basename)


def _normalize_image_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if "imgur.com/" in url and "i.imgur.com" not in url:
        # https://imgur.com/BIETPKz -> https://i.imgur.com/BIETPKz.gif
        code = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        if code and not code.startswith("."):
            return f"https://i.imgur.com/{code}.gif"
    return url


def load_welcome_image() -> tuple[str | None, discord.File | None]:
    url = os.getenv("WELCOME_IMAGE_URL", WELCOME_IMAGE_URL or "").strip()
    if url:
        return _normalize_image_url(url), None
    return _load_panel_image(WELCOME_IMAGE)


def load_social_panel_image() -> tuple[str | None, discord.File | None]:
    return _load_panel_image(SOCIAL_PANEL_IMAGE)


def social_panel_embed(image_url: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=SOCIAL_PANEL_TITLE,
        description=SOCIAL_PANEL_TEXT,
        color=discord.Color(BLACK),
    )
    if image_url:
        embed.set_image(url=image_url)
    return embed


def load_rules_panel_image() -> tuple[str | None, discord.File | None]:
    return _load_panel_image(RULES_PANEL_IMAGE)


def _rules_list(text: str) -> str:
    lines: list[str] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("•"):
            line = f"• {line}"
        lines.append(line)
    return "\n\n".join(lines)


def rules_panel_embed(image_url: str | None = None) -> discord.Embed:
    admin = rules_admin_mention()
    fmt = {"admin": admin}
    forbidden = _rules_list(RULES_FORBIDDEN.format(**fmt))
    penalties = _rules_list(RULES_PENALTIES.format(**fmt))

    description_parts: list[str] = []
    intro = RULES_PANEL_INTRO.strip()
    if intro:
        description_parts.append(intro)
        description_parts.append("")

    description_parts.extend(
        [
            "**🚫  НА СЕРВЕРЕ НЕ ПРИВЕТСТВУЕТСЯ**",
            "",
            forbidden,
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "**⚖️  ОТВЕТСТВЕННОСТЬ**",
            "",
            penalties,
        ]
    )

    embed = discord.Embed(
        title=RULES_PANEL_TITLE,
        description="\n".join(description_parts),
        color=discord.Color(BLACK),
    )
    footer = RULES_PANEL_FOOTER.strip()
    if footer:
        embed.set_footer(text=footer)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def load_shop_panel_image() -> tuple[str | None, discord.File | None]:
    return _load_panel_image(SHOP_PANEL_IMAGE)


def load_giveaway_panel_image() -> tuple[str | None, discord.File | None]:
    return _load_panel_image(GIVEAWAY_PANEL_IMAGE)


def _shop_item_line(guild: discord.Guild, item: dict, admin: str) -> str:
    role_id = item.get("role_id") or 0
    if role_id:
        role = guild.get_role(role_id)
        label = role.mention if role else f"**{item['name']}**"
    else:
        label = f"**{item['name']}**"

    description = (item.get("description") or "").format(admin=admin)
    description = " ".join(description.split())
    if "роль" in item["name"].lower() and SHOP_SQUAD_INVITE:
        description = f"{description}\nИнвайт в сквад: {SHOP_SQUAD_INVITE}"

    return f"{label} — {description} — **{item['cost']} баллов**"


async def shop_panel_embed(guild: discord.Guild, image_url: str | None = None) -> discord.Embed:
    admin = rules_admin_mention()
    items = await get_shop_items(guild.id)
    rules = await get_earning_rules(guild.id)

    earning_lines = []
    if rules["voice"]["enabled"]:
        earning_lines.append(
            f"🎙️ **{rules['voice']['param1']} минут в войсе** — "
            f"**{rules['voice']['param2']} баллов**"
        )
    if rules["words"]["enabled"]:
        earning_lines.append(
            f"💬 **{rules['words']['param1']} слов в чате** — "
            f"**{rules['words']['param2']} баллов** (макс. **{rules['words']['param3']}**/день)"
        )
    if rules["referral"]["enabled"]:
        earning_lines.append(
            f"👥 **Ввод рефки** — **{rules['referral']['param3']}** баллов · "
            f"владельцу **{rules['referral']['param1']}**"
        )
    boost = rules.get("boost", {})
    if boost.get("enabled"):
        earning_lines.append(
            f"🚀 **Буст сервера** — **{boost['param1']}** баллов за каждый буст"
        )
    earning_lines.extend(format_social_bonus_earning_lines(rules))
    earning = "\n".join(earning_lines) if earning_lines else "— правила не настроены"

    if items:
        prize_lines = [_shop_item_line(guild, i, admin) for i in items]
        prizes_block = "\n".join(prize_lines)
    else:
        prizes_block = "— товаров пока нет"

    usage_lines = [
        "• Кнопки ниже — баланс, рефералы, покупка",
        "• **Создать рефку** — заявка в тикет, админ одобрит",
        f"• **Ввести рефку** — один раз, +**{rules['referral']['param3']}** баллов",
        "• Слова: флуд и спам не засчитываются",
    ]
    if social_bonus_enabled(rules):
        usage_lines.insert(
            1,
            "• **Бонус за подписку** — подпишись на **Twitch** или **Telegram**, "
            "приложи скрин в тикет (один раз)",
        )

    description = (
        f"__**{SHOP_PANEL_TITLE}**__\n\n"
        f"-- **Начисление баллов**\n"
        f"{earning}\n\n"
        f"-- **Призы**\n"
        f"{prizes_block}\n\n"
        f"-- **Как пользоваться**\n"
        f"{chr(10).join(usage_lines)}"
    )

    embed = discord.Embed(description=description, color=discord.Color(BLACK))
    if image_url:
        embed.set_image(url=image_url)
    return embed


def build_welcome_greeting(
    member: discord.Member,
    roles_channel: discord.abc.GuildChannel | None,
) -> str | None:
    from config import WELCOME_GREETING, WELCOME_TITLE

    fmt = {"name": member.display_name, "user": member.mention}
    roles_mention = roles_channel.mention if roles_channel else "—"
    greeting = (WELCOME_GREETING or WELCOME_TITLE).strip()
    if not greeting:
        return None
    return greeting.format(**fmt, roles=roles_mention)


def build_welcome_embed(
    member: discord.Member,
    image_url: str | None,
    roles_channel: discord.abc.GuildChannel | None,
) -> discord.Embed:
    from config import (
        WELCOME_COLOR,
        WELCOME_TITLE,
        WELCOME_GREETING,
        WELCOME_TEXT,
        WELCOME_LINKS,
        WELCOME_ADMIN_TITLE,
        WELCOME_ADMIN_TEXT,
    )

    fmt = {"name": member.display_name, "user": member.mention}
    roles_mention = roles_channel.mention if roles_channel else "—"

    description_parts: list[str] = []
    description_parts.append(WELCOME_TEXT.format(**fmt, roles=roles_mention))

    links = WELCOME_LINKS.strip()
    if links:
        description_parts.append(links.format(**fmt, roles=roles_mention))

    description = "\n\n".join(description_parts)

    title = WELCOME_TITLE.strip()
    if title and "{user}" not in WELCOME_TITLE:
        title = title.format(**fmt, roles=roles_mention)
    else:
        title = None

    embed = discord.Embed(description=description, color=WELCOME_COLOR)
    if title:
        embed.title = title

    embed.set_author(
        name=member.display_name,
        icon_url=member.display_avatar.url,
    )

    admin_title = WELCOME_ADMIN_TITLE.strip()
    admin_text = WELCOME_ADMIN_TEXT.strip()
    if admin_title and admin_text:
        embed.add_field(
            name=admin_title,
            value=admin_text.format(**fmt),
            inline=False,
        )

    if image_url:
        embed.set_image(url=image_url)

    return embed
