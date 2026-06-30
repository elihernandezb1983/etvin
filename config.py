import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _env_int(key: str, default: int = 0) -> int:
    raw = os.getenv(key, "")
    if not raw or not raw.strip().isdigit():
        return default
    return int(raw)


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = _env_int("GUILD_ID")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bot.db")
FOTO_DIR = os.path.join(os.path.dirname(__file__), "foto")
BLACK = 0x000000
WELCOME_COLOR = _env_int("WELCOME_COLOR", BLACK)

# {name} — имя на сервере, {user} — тег (только в тексте/embed, не в заголовке)
WELCOME_TITLE = os.getenv("WELCOME_TITLE", "")
WELCOME_GREETING = os.getenv("WELCOME_GREETING", "Дарова {user}!")
WELCOME_TEXT = os.getenv(
    "WELCOME_TEXT",
    "Рады, что ты с нами. Загляни в каналы ниже:",
)

# Каждая строка: ➡ Название | <#ID_КАНАЛА>
WELCOME_LINKS = os.getenv(
    "WELCOME_LINKS",
    """➡ Стримы | <#1462129161752678483>
➡ Получи роль | {roles}""",
)

WELCOME_ADMIN_TITLE = os.getenv("WELCOME_ADMIN_TITLE", "Сообщение от Админов")
WELCOME_ADMIN_TEXT = os.getenv(
    "WELCOME_ADMIN_TEXT",
    "Мы рады видеть тебя с нами, удачного времяпровождения!",
)

# Имя файла в папке foto/ (пусто = без картинки в приветствии)
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE", "")
# Прямая ссылка на картинку (imgur, CDN Discord и т.д.) — приоритет над файлом
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL", "")

# Текст панели ролей (отдельное сообщение в канале с реакциями)
ROLE_PANEL_TEXT = os.getenv(
    "ROLE_PANEL_TEXT",
    "Поставь **любую реакцию** на это сообщение — роль выдастся автоматически.",
)

SOCIAL_PANEL_TITLE = os.getenv("SOCIAL_PANEL_TITLE", "SOCIALLY LINK")

SOCIAL_PANEL_TEXT = os.getenv(
    "SOCIAL_PANEL_TEXT",
    "Здесь собраны мои официальные ссылки. Подписывайтесь на соцсети, "
    "следите за анонсами, стримами и новостями — будьте в курсе всего, что происходит!",
)

# Имя файла в папке foto/ (пусто = первое изображение из папки)
SOCIAL_PANEL_IMAGE = os.getenv("SOCIAL_PANEL_IMAGE", "")

# Каждая строка: Название | https://ссылка (макс. 2 кнопки)
SOCIAL_LINKS = os.getenv(
    "SOCIAL_LINKS",
    """Telegram | https://t.me/etvin7
Twitch | https://www.twitch.tv/etv1n7""",
)

# {admin} — упоминание админа (RULES_ADMIN_ID)
RULES_ADMIN_ID = _env_int("RULES_ADMIN_ID")

RULES_PANEL_TITLE = os.getenv("RULES_PANEL_TITLE", "📜  ПРАВИЛА СЕРВЕРА")
RULES_PANEL_INTRO = os.getenv(
    "RULES_PANEL_INTRO",
    "Ознакомься с правилами перед общением — так комфортнее всем участникам.",
)
RULES_PANEL_FOOTER = os.getenv(
    "RULES_PANEL_FOOTER",
    "Нарушение правил может привести к предупреждению, муту или бану.",
)
# Имя файла в папке foto/ (пусто = без картинки; иначе баннер внизу embed)
RULES_PANEL_IMAGE = os.getenv("RULES_PANEL_IMAGE", "")

RULES_FORBIDDEN = os.getenv(
    "RULES_FORBIDDEN",
    """• Оскорбления любого участника сервера по любым причинам
• Флуд (кроме канала созданного для флуда)
• Запретки во время стрима
• Размещения рекламы без согласования {admin}
• Спам
• Громкие крики в голосовых каналах""",
)

RULES_PENALTIES = os.getenv(
    "RULES_PENALTIES",
    """• При нарушении правил сервера Дискорд принимаются меры к пользователям вплоть до ограничения доступа.
• Обход бана путем входа под другим идентификатором или иными путями — бан.
• Нарушение упомянутых выше норм — бан.
• Неуважительное отношение к другим пользователям и оскорбление — бан.
• Разжигание межнациональной розни, конфликтов на политической и религиозной основании — бан.
• Насчёт разбана писать {admin}""",
)


def rules_admin_mention() -> str:
    if RULES_ADMIN_ID:
        return f"<@{RULES_ADMIN_ID}>"
    return "@админ"

# Текст панели временного войса ({owner} — упоминание владельца)
VOICE_PANEL_TEXT = os.getenv(
    "VOICE_PANEL_TEXT",
    "Кнопки ниже — настройка вашей голосовой комнаты. (чат справа от этого войса): "
    "**Название, Лимит, Регион**\n"
    "• сразу меняют войс; **Кикнуть** — из списка;\n"
    "**Прихожая** — закрыть вход всем кроме вас;\n"
    "**Забрать** — передать владение из списка; **Друзья / Баны** — выбор из списка.\n"
    "**Владелец:** {owner}\n"
    "Комната создаётся автоматически после входа в прихожую.",
)

VOICE_CHANNEL_PREFIX = os.getenv("VOICE_CHANNEL_PREFIX", "🔊 ")

VOICE_GUIDE_TEXT = os.getenv(
    "VOICE_GUIDE_TEXT",
    "**Название** — переименовать комнату\n"
    "**Лимит** — лимит участников (0 = без лимита)\n"
    "**Регион** — голосовой регион сервера\n"
    "**Кикнуть** — выгнать участника из комнаты\n"
    "**Прихожая** — закрыть/открыть вход в комнату\n"
    "**Забрать** — передать владение другому участнику\n"
    "**Друзья** — разрешить вход выбранному пользователю\n"
    "**Баны** — запретить вход и выгнать пользователя",
)


TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_CHECK_INTERVAL = _env_int("TWITCH_CHECK_INTERVAL", 60)
TWITCH_ANNOUNCE_COOLDOWN = _env_int("TWITCH_ANNOUNCE_COOLDOWN", 300)

# {mention} — Discord-упоминание, {login} — логин Twitch, {url} — ссылка на стрим
TWITCH_ANNOUNCE_TEXT = os.getenv(
    "TWITCH_ANNOUNCE_TEXT",
    "@everyone\n🔴 {mention} запустил стрим! Заходи смотреть:\n{url}",
)


def parse_social_links(raw: str | None = None) -> list[dict]:
    links = []
    for line in (raw if raw is not None else SOCIAL_LINKS).strip().splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        label, url = line.split("|", 1)
        label = label.strip()
        url = url.strip()
        if label and url.startswith(("http://", "https://")):
            links.append({"label": label, "url": url})
    return links


# --- Магазин баллов ---
SHOP_PANEL_TITLE = os.getenv("SHOP_PANEL_TITLE", "Информация о Магазине")
SHOP_PANEL_IMAGE = os.getenv("SHOP_PANEL_IMAGE", "")
SHOP_SQUAD_INVITE = os.getenv("SHOP_SQUAD_INVITE", "")

SHOP_VOICE_MINUTES = _env_int("SHOP_VOICE_MINUTES", 10)
SHOP_VOICE_POINTS = _env_int("SHOP_VOICE_POINTS", 10)
SHOP_WORDS_THRESHOLD = _env_int("SHOP_WORDS_THRESHOLD", 250)
SHOP_WORDS_POINTS = _env_int("SHOP_WORDS_POINTS", 10)
SHOP_REFERRAL_POINTS = _env_int("SHOP_REFERRAL_POINTS", 50)

# ключ | Название | стоимость | описание [| role_id]
SHOP_PRIZES = os.getenv(
    "SHOP_PRIZES",
    """twitch_vip | Випка на Twitch | 500 | VIP на канале Twitch — после покупки пиши {admin} | 0
custom_role | Своя ролька | 1000 | Личная роль + инвайт в сквад — создаём и кидаем инвайт | 0""",
)


def parse_shop_prizes(raw: str | None = None) -> list[dict]:
    prizes = []
    for line in (raw if raw is not None else SHOP_PRIZES).strip().splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        key, name, cost_raw, description = parts[:4]
        role_id = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        if not key or not name or not cost_raw.isdigit():
            continue
        prizes.append({
            "key": key,
            "name": name,
            "cost": int(cost_raw),
            "description": description,
            "role_id": role_id,
        })
    return prizes
