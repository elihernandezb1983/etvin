import os
from datetime import date, datetime, timezone

import aiosqlite
import config
from config import DB_PATH
from utils.earning import effective_words


def _today_iso() -> str:
    return date.today().isoformat()


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                welcome_text TEXT DEFAULT 'Добро пожаловать, {user}! 🎉',
                welcome_image_url TEXT,
                admin_role_id INTEGER,
                server_log_channel_id INTEGER,
                bot_log_channel_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS role_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                emoji TEXT,
                role_id INTEGER NOT NULL,
                label TEXT
            );

            CREATE TABLE IF NOT EXISTS panels (
                guild_id INTEGER NOT NULL,
                panel_type TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, panel_type)
            );

            CREATE TABLE IF NOT EXISTS voice_setups (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                lobby_channel_id INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS temp_voice_channels (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0,
                panel_message_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS twitch_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                twitch_login TEXT NOT NULL,
                discord_user_id INTEGER,
                last_stream_started_at TEXT,
                last_announced_at TEXT,
                UNIQUE(guild_id, twitch_login)
            );

            CREATE TABLE IF NOT EXISTS shop_points (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                word_buffer INTEGER NOT NULL DEFAULT 0,
                voice_buffer INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS shop_referral_codes (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id),
                UNIQUE (guild_id, code)
            );

            CREATE TABLE IF NOT EXISTS shop_referrals (
                guild_id INTEGER NOT NULL,
                inviter_id INTEGER NOT NULL,
                invited_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, invited_id)
            );

            CREATE TABLE IF NOT EXISTS shop_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                prize_key TEXT NOT NULL,
                prize_name TEXT NOT NULL,
                cost INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                order_message_id INTEGER,
                resolved_by INTEGER,
                resolved_at TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                cost INTEGER NOT NULL,
                role_id INTEGER NOT NULL DEFAULT 0,
                UNIQUE(guild_id, item_key)
            );

            CREATE TABLE IF NOT EXISTS shop_earning_rules (
                guild_id INTEGER NOT NULL,
                rule_key TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                param1 INTEGER NOT NULL DEFAULT 0,
                param2 INTEGER NOT NULL DEFAULT 0,
                param3 INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, rule_key)
            );

            CREATE TABLE IF NOT EXISTS shop_boost_grants (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                boosts_awarded INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS shop_boost_messages (
                message_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS shop_social_claims (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                external_id TEXT,
                claimed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, user_id, platform)
            );

            CREATE TABLE IF NOT EXISTS squads (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                leader_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            );
        """)
        await db.commit()
        async with db.execute("PRAGMA table_info(guild_settings)") as c:
            guild_cols = {row[1] for row in await c.fetchall()}
        if guild_cols and "server_log_channel_id" not in guild_cols:
            await db.execute("ALTER TABLE guild_settings ADD COLUMN server_log_channel_id INTEGER")
        if guild_cols and "bot_log_channel_id" not in guild_cols:
            await db.execute("ALTER TABLE guild_settings ADD COLUMN bot_log_channel_id INTEGER")
        async with db.execute("PRAGMA table_info(twitch_alerts)") as c:
            cols = {row[1] for row in await c.fetchall()}
        if cols and "last_announced_at" not in cols:
            await db.execute("ALTER TABLE twitch_alerts ADD COLUMN last_announced_at TEXT")
        if guild_cols and "shop_orders_channel_id" not in guild_cols:
            await db.execute("ALTER TABLE guild_settings ADD COLUMN shop_orders_channel_id INTEGER")
        if guild_cols and "shop_ticket_category_id" not in guild_cols:
            await db.execute("ALTER TABLE guild_settings ADD COLUMN shop_ticket_category_id INTEGER")
        if guild_cols and "giveaway_ticket_cost" not in guild_cols:
            await db.execute(
                "ALTER TABLE guild_settings ADD COLUMN giveaway_ticket_cost INTEGER NOT NULL DEFAULT 100"
            )
        async with db.execute("PRAGMA table_info(shop_points)") as c:
            pts_cols = {row[1] for row in await c.fetchall()}
        if pts_cols and "words_points_today" not in pts_cols:
            await db.execute("ALTER TABLE shop_points ADD COLUMN words_points_today INTEGER NOT NULL DEFAULT 0")
        if pts_cols and "words_day" not in pts_cols:
            await db.execute("ALTER TABLE shop_points ADD COLUMN words_day TEXT NOT NULL DEFAULT ''")
        if pts_cols and "last_message_at" not in pts_cols:
            await db.execute("ALTER TABLE shop_points ADD COLUMN last_message_at TEXT")
        if pts_cols and "last_message_content" not in pts_cols:
            await db.execute("ALTER TABLE shop_points ADD COLUMN last_message_content TEXT")
        async with db.execute("PRAGMA table_info(shop_redemptions)") as c:
            red_cols = {row[1] for row in await c.fetchall()}
        if red_cols and "order_message_id" not in red_cols:
            await db.execute("ALTER TABLE shop_redemptions ADD COLUMN order_message_id INTEGER")
        if red_cols and "resolved_by" not in red_cols:
            await db.execute("ALTER TABLE shop_redemptions ADD COLUMN resolved_by INTEGER")
        if red_cols and "resolved_at" not in red_cols:
            await db.execute("ALTER TABLE shop_redemptions ADD COLUMN resolved_at TEXT")
        if red_cols and "note" not in red_cols:
            await db.execute("ALTER TABLE shop_redemptions ADD COLUMN note TEXT")
        if red_cols and "ticket_channel_id" not in red_cols:
            await db.execute("ALTER TABLE shop_redemptions ADD COLUMN ticket_channel_id INTEGER")
        async with db.execute("PRAGMA table_info(shop_referral_codes)") as c:
            ref_cols = {row[1] for row in await c.fetchall()}
        if ref_cols and "invite_code" not in ref_cols:
            await db.execute("ALTER TABLE shop_referral_codes ADD COLUMN invite_code TEXT")
        if ref_cols and "status" not in ref_cols:
            await db.execute(
                "ALTER TABLE shop_referral_codes ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'"
            )

        await db.executescript("""
            CREATE TABLE IF NOT EXISTS shop_referral_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                requested_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                ticket_channel_id INTEGER,
                message_id INTEGER,
                resolved_by INTEGER,
                resolved_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS shop_invite_snapshots (
                guild_id INTEGER NOT NULL,
                invite_code TEXT NOT NULL,
                uses INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, invite_code)
            );

            CREATE TABLE IF NOT EXISTS raffle_tickets (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tickets INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS raffles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                prize TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tickets_per_entry INTEGER NOT NULL DEFAULT 1,
                winner_count INTEGER NOT NULL DEFAULT 1,
                winners_json TEXT,
                total_tickets INTEGER NOT NULL DEFAULT 0,
                ends_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                winner_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                entrants INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS raffle_entries (
                raffle_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tickets_spent INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (raffle_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS shop_social_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                ticket_channel_id INTEGER,
                message_id INTEGER,
                points_awarded INTEGER,
                resolved_by INTEGER,
                resolved_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
        async with db.execute("PRAGMA table_info(raffles)") as c:
            raffle_cols = {row[1] for row in await c.fetchall()}
        if raffle_cols and "winner_count" not in raffle_cols:
            await db.execute("ALTER TABLE raffles ADD COLUMN winner_count INTEGER NOT NULL DEFAULT 1")
        if raffle_cols and "winners_json" not in raffle_cols:
            await db.execute("ALTER TABLE raffles ADD COLUMN winners_json TEXT")
        if raffle_cols and "total_tickets" not in raffle_cols:
            await db.execute("ALTER TABLE raffles ADD COLUMN total_tickets INTEGER NOT NULL DEFAULT 0")
        await db.commit()
        await db.execute(
            """
            UPDATE shop_earning_rules
            SET param3 = 100
            WHERE rule_key = 'referral' AND param3 = 0
            """
        )
        await db.commit()


async def _ensure_shop_row(db, guild_id: int, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO shop_points (guild_id, user_id) VALUES (?, ?)",
        (guild_id, user_id),
    )


async def _normalize_words_day(db, row: dict) -> dict:
    today = _today_iso()
    if row.get("words_day") == today:
        return row
    await db.execute(
        "UPDATE shop_points SET words_points_today = 0, words_day = ? "
        "WHERE guild_id = ? AND user_id = ?",
        (today, row["guild_id"], row["user_id"]),
    )
    row = dict(row)
    row["words_points_today"] = 0
    row["words_day"] = today
    return row


async def get_shop_points(guild_id: int, user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT * FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        if row:
            row = await _normalize_words_day(db, dict(row))
            await db.commit()
    return dict(row) if row else {
        "guild_id": guild_id,
        "user_id": user_id,
        "points": 0,
        "word_buffer": 0,
        "voice_buffer": 0,
        "words_points_today": 0,
        "words_day": "",
        "last_message_at": None,
        "last_message_content": None,
    }


async def update_message_meta(
    guild_id: int,
    user_id: int,
    *,
    content: str,
    at: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_shop_row(db, guild_id, user_id)
        await db.execute(
            "UPDATE shop_points SET last_message_at = ?, last_message_content = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (at, content[:500], guild_id, user_id),
        )
        await db.commit()


async def _update_shop_points(
    db,
    guild_id: int,
    user_id: int,
    *,
    points: int,
    word_buffer: int,
    voice_buffer: int,
):
    await db.execute(
        "UPDATE shop_points SET points = ?, word_buffer = ?, voice_buffer = ? "
        "WHERE guild_id = ? AND user_id = ?",
        (points, word_buffer, voice_buffer, guild_id, user_id),
    )


async def add_voice_seconds(
    guild_id: int,
    user_id: int,
    seconds: int,
    *,
    seconds_per_reward: int,
    points_per_reward: int,
) -> tuple[int, int]:
    if seconds <= 0 or seconds_per_reward <= 0 or points_per_reward <= 0:
        row = await get_shop_points(guild_id, user_id)
        return 0, row["points"]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT * FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()

        voice_buffer = row["voice_buffer"] + seconds
        points = row["points"]
        awarded = 0
        while voice_buffer >= seconds_per_reward:
            voice_buffer -= seconds_per_reward
            points += points_per_reward
            awarded += points_per_reward

        await _update_shop_points(
            db, guild_id, user_id,
            points=points, word_buffer=row["word_buffer"], voice_buffer=voice_buffer,
        )
        await db.commit()
    return awarded, points


async def apply_chat_message(
    guild_id: int,
    user_id: int,
    *,
    content: str,
    at: str,
    words_per_reward: int,
    points_per_reward: int,
    daily_cap: int,
) -> tuple[int, int]:
    """Считает слова, обновляет антиспам-мету и начисляет баллы в одной транзакции."""
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT * FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        row = await _normalize_words_day(db, dict(row))

        counted_words = effective_words(
            content,
            row.get("last_message_content"),
            row.get("last_message_at"),
            now,
        )

        points = row["points"]
        word_buffer = row["word_buffer"]
        awarded = 0

        if (
            counted_words > 0
            and words_per_reward > 0
            and points_per_reward > 0
        ):
            word_buffer += counted_words
            if daily_cap <= 0:
                remaining_cap = None
            else:
                remaining_cap = max(0, daily_cap - row["words_points_today"])

            if remaining_cap is None or remaining_cap > 0:
                while word_buffer >= words_per_reward:
                    if remaining_cap is not None and awarded + points_per_reward > remaining_cap:
                        break
                    word_buffer -= words_per_reward
                    points += points_per_reward
                    awarded += points_per_reward
                    row["words_points_today"] += points_per_reward

        await db.execute(
            "UPDATE shop_points SET points = ?, word_buffer = ?, voice_buffer = ?, "
            "words_points_today = ?, words_day = ?, last_message_at = ?, last_message_content = ? "
            "WHERE guild_id = ? AND user_id = ?",
            (
                points,
                word_buffer,
                row["voice_buffer"],
                row["words_points_today"],
                row["words_day"],
                at,
                content[:500],
                guild_id,
                user_id,
            ),
        )
        await db.commit()
    return awarded, points


async def transfer_shop_points(
    guild_id: int,
    from_user_id: int,
    to_user_id: int,
    amount: int,
    *,
    commission_percent: int = 10,
) -> tuple[bool, str, int]:
    if amount <= 0:
        return False, "Сумма должна быть больше нуля.", 0
    if from_user_id == to_user_id:
        return False, "Нельзя перевести баллы себе.", 0

    commission = amount * commission_percent // 100
    received = amount - commission
    if received <= 0:
        return False, "Слишком маленькая сумма после комиссии.", 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, from_user_id)
        await _ensure_shop_row(db, guild_id, to_user_id)
        await db.commit()
        async with db.execute(
            "SELECT points FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, from_user_id),
        ) as c:
            row = await c.fetchone()
        if row["points"] < amount:
            return (
                False,
                f"Не хватает баллов. Нужно **{amount}**, у тебя **{row['points']}**.",
                0,
            )
        await db.execute(
            "UPDATE shop_points SET points = points - ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, from_user_id),
        )
        await db.execute(
            "UPDATE shop_points SET points = points + ? WHERE guild_id = ? AND user_id = ?",
            (received, guild_id, to_user_id),
        )
        await db.commit()
    return True, "", received


async def adjust_shop_points(guild_id: int, user_id: int, delta: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT points FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        new_points = max(0, row["points"] + delta)
        await db.execute(
            "UPDATE shop_points SET points = ? WHERE guild_id = ? AND user_id = ?",
            (new_points, guild_id, user_id),
        )
        await db.commit()
    return new_points


async def get_boost_awarded_count(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT boosts_awarded FROM shop_boost_grants "
            "WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def set_boost_awarded_count(guild_id: int, user_id: int, count: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO shop_boost_grants (guild_id, user_id, boosts_awarded) "
            "VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET boosts_awarded = ?",
            (guild_id, user_id, count, count),
        )
        await db.commit()


async def mark_boost_message_processed(message_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO shop_boost_messages (message_id) VALUES (?)",
                (message_id,),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def award_boost_points(guild_id: int, user_id: int, total_boosts: int) -> int:
    rules = await get_earning_rules(guild_id)
    boost_rule = rules.get("boost", {})
    if not boost_rule.get("enabled"):
        return 0
    points_per = boost_rule.get("param1", 0)
    if points_per <= 0 or total_boosts <= 0:
        return 0

    paid = await get_boost_awarded_count(guild_id, user_id)
    delta = max(0, total_boosts - paid)
    if delta <= 0:
        return 0

    await set_boost_awarded_count(guild_id, user_id, paid + delta)
    awarded = delta * points_per
    await adjust_shop_points(guild_id, user_id, awarded)
    return awarded


async def has_social_bonus(guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM shop_social_claims WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            return await c.fetchone() is not None


async def has_social_claim(guild_id: int, user_id: int, platform: str) -> bool:
    if platform == "bonus":
        return await has_social_bonus(guild_id, user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM shop_social_claims "
            "WHERE guild_id = ? AND user_id = ? AND platform = ?",
            (guild_id, user_id, platform),
        ) as c:
            return await c.fetchone() is not None


async def external_id_claimed(guild_id: int, platform: str, external_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM shop_social_claims "
            "WHERE guild_id = ? AND platform = ? AND external_id = ?",
            (guild_id, platform, external_id),
        ) as c:
            return await c.fetchone() is not None


async def claim_social_bonus(
    guild_id: int,
    user_id: int,
    platform: str,
    *,
    external_id: str | None = None,
) -> int:
    rules = await get_earning_rules(guild_id)
    rule = rules.get(platform, {})
    if not rule.get("enabled"):
        return 0
    if await has_social_claim(guild_id, user_id, platform):
        return 0
    if external_id and await external_id_claimed(guild_id, platform, external_id):
        return 0

    points = rule.get("param1", 0)
    if points <= 0:
        return 0

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO shop_social_claims (guild_id, user_id, platform, external_id) "
                "VALUES (?, ?, ?, ?)",
                (guild_id, user_id, platform, external_id),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            return 0

    await adjust_shop_points(guild_id, user_id, points)
    return points


async def get_pending_social_request(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM shop_social_requests
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
            """,
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def create_social_request(
    guild_id: int,
    user_id: int,
    *,
    ticket_channel_id: int,
) -> tuple[bool, str, int | None]:
    if await has_social_bonus(guild_id, user_id):
        return False, "Ты уже получал бонус за подписку.", None
    if await get_pending_social_request(guild_id, user_id):
        return False, "Заявка уже на рассмотрении.", None

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO shop_social_requests (
                guild_id, user_id, platform, ticket_channel_id
            ) VALUES (?, ?, 'bonus', ?)
            """,
            (guild_id, user_id, ticket_channel_id),
        )
        await db.commit()
        return True, "Заявка создана.", cursor.lastrowid


async def set_social_request_message(request_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shop_social_requests SET message_id = ? WHERE id = ?",
            (message_id, request_id),
        )
        await db.commit()


async def get_social_request(request_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_social_requests WHERE id = ?",
            (request_id,),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_pending_social_requests() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM shop_social_requests
            WHERE status = 'pending' AND message_id IS NOT NULL
            """,
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def approve_social_request(
    request_id: int,
    *,
    admin_id: int,
    points: int,
) -> tuple[bool, str, dict | None]:
    if points <= 0:
        return False, "Баллы должны быть больше нуля.", None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_social_requests WHERE id = ?",
            (request_id,),
        ) as c:
            req = await c.fetchone()
        if not req:
            return False, "Заявка не найдена.", None
        if req["status"] != "pending":
            return False, "Заявка уже обработана.", None

        guild_id = req["guild_id"]
        user_id = req["user_id"]

        async with db.execute(
            "SELECT 1 FROM shop_social_claims WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            if await c.fetchone():
                return False, "Пользователь уже получал бонус.", dict(req)

        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """
                INSERT INTO shop_social_claims (guild_id, user_id, platform, external_id)
                VALUES (?, ?, 'bonus', NULL)
                """,
                (guild_id, user_id),
            )
        except aiosqlite.IntegrityError:
            return False, "Бонус уже получен.", dict(req)

        await db.execute(
            """
            UPDATE shop_social_requests
            SET status = 'approved', points_awarded = ?, resolved_by = ?, resolved_at = ?
            WHERE id = ?
            """,
            (points, admin_id, now, request_id),
        )
        await db.commit()

    await adjust_shop_points(guild_id, user_id, points)
    return True, f"Начислено **{points}** баллов.", dict(req)


async def reject_social_request(
    request_id: int,
    *,
    admin_id: int,
) -> tuple[bool, str, dict | None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_social_requests WHERE id = ?",
            (request_id,),
        ) as c:
            req = await c.fetchone()
        if not req:
            return False, "Заявка не найдена.", None
        if req["status"] != "pending":
            return False, "Заявка уже обработана.", None

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """
            UPDATE shop_social_requests
            SET status = 'rejected', resolved_by = ?, resolved_at = ?
            WHERE id = ?
            """,
            (admin_id, now, request_id),
        )
        await db.commit()
        return True, "Заявка отклонена.", dict(req)


async def spend_shop_points(guild_id: int, user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT points FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        if row["points"] < amount:
            return False
        await db.execute(
            "UPDATE shop_points SET points = points - ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        await db.commit()
    return True


def normalize_referral_code(code: str) -> str:
    import re

    return re.sub(r"[^A-Z0-9_]", "", code.strip().upper())[:20]


async def get_user_referral_code(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_pending_referral_request(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM shop_referral_requests
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
            """,
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def referral_code_taken(guild_id: int, code: str, *, exclude_user_id: int | None = None) -> bool:
    code = normalize_referral_code(code)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM shop_referral_codes WHERE guild_id = ? AND code = ?",
            (guild_id, code),
        ) as c:
            row = await c.fetchone()
        if row and row["user_id"] != exclude_user_id:
            return True
        async with db.execute(
            """
            SELECT user_id FROM shop_referral_requests
            WHERE guild_id = ? AND requested_code = ? AND status = 'pending'
            """,
            (guild_id, code),
        ) as c:
            pending = await c.fetchone()
    return bool(pending and pending["user_id"] != exclude_user_id)


async def validate_referral_request(guild_id: int, user_id: int, code: str) -> tuple[bool, str, str]:
    normalized = normalize_referral_code(code)
    if len(normalized) < 3:
        return False, "Код — минимум **3** символа (латиница, цифры, `_`).", normalized
    if await get_user_referral_code(guild_id, user_id):
        return False, "У тебя уже есть реферальный код.", normalized
    if await get_pending_referral_request(guild_id, user_id):
        return False, "Заявка уже на рассмотрении — жди ответа в тикете.", normalized
    if await referral_code_taken(guild_id, normalized):
        return False, f"Код **{normalized}** уже занят.", normalized
    return True, "", normalized


async def create_referral_request(
    guild_id: int,
    user_id: int,
    code: str,
    *,
    ticket_channel_id: int,
) -> tuple[bool, str, int | None]:
    ok, msg, normalized = await validate_referral_request(guild_id, user_id, code)
    if not ok:
        return False, msg, None
    code = normalized

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO shop_referral_requests (
                guild_id, user_id, requested_code, ticket_channel_id
            ) VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, code, ticket_channel_id),
        )
        await db.commit()
        return True, "Заявка создана.", cursor.lastrowid


async def set_referral_request_message(request_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shop_referral_requests SET message_id = ? WHERE id = ?",
            (message_id, request_id),
        )
        await db.commit()


async def get_referral_request(request_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_referral_requests WHERE id = ?",
            (request_id,),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_pending_referral_requests() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_referral_requests WHERE status = 'pending' AND message_id IS NOT NULL",
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def resolve_referral_request(
    request_id: int,
    *,
    approved: bool,
    admin_id: int,
) -> tuple[bool, str, dict | None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_referral_requests WHERE id = ?",
            (request_id,),
        ) as c:
            req = await c.fetchone()
        if not req:
            return False, "Заявка не найдена.", None
        if req["status"] != "pending":
            return False, "Заявка уже обработана.", None

        now = datetime.now(timezone.utc).isoformat()
        if not approved:
            await db.execute(
                """
                UPDATE shop_referral_requests
                SET status = 'rejected', resolved_by = ?, resolved_at = ?
                WHERE id = ?
                """,
                (admin_id, now, request_id),
            )
            await db.commit()
            return True, "Заявка отклонена.", dict(req)

        async with db.execute(
            "SELECT 1 FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (req["guild_id"], req["user_id"]),
        ) as c:
            if await c.fetchone():
                return False, "У пользователя уже есть код.", dict(req)

        try:
            await db.execute(
                """
                INSERT INTO shop_referral_codes (guild_id, user_id, code, status)
                VALUES (?, ?, ?, 'approved')
                """,
                (req["guild_id"], req["user_id"], req["requested_code"]),
            )
        except aiosqlite.IntegrityError:
            return False, "Этот код уже занят.", dict(req)

        await db.execute(
            """
            UPDATE shop_referral_requests
            SET status = 'approved', resolved_by = ?, resolved_at = ?
            WHERE id = ?
            """,
            (admin_id, now, request_id),
        )
        await db.commit()
        return True, f"Код **{req['requested_code']}** одобрен.", dict(req)


async def get_referral_inviter(guild_id: int, code: str) -> int | None:
    code = normalize_referral_code(code)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id FROM shop_referral_codes
            WHERE guild_id = ? AND code = ? AND status = 'approved'
            """,
            (guild_id, code),
        ) as c:
            row = await c.fetchone()
    return row["user_id"] if row else None


async def admin_set_referral_code(
    guild_id: int,
    user_id: int,
    code: str,
) -> tuple[bool, str]:
    code = normalize_referral_code(code)
    if len(code) < 3:
        return False, "Код — минимум **3** символа."
    if await referral_code_taken(guild_id, code, exclude_user_id=user_id):
        return False, f"Код **{code}** уже занят."

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            exists = await c.fetchone()
        if exists:
            await db.execute(
                "UPDATE shop_referral_codes SET code = ?, status = 'approved' "
                "WHERE guild_id = ? AND user_id = ?",
                (code, guild_id, user_id),
            )
        else:
            await db.execute(
                """
                INSERT INTO shop_referral_codes (guild_id, user_id, code, status)
                VALUES (?, ?, ?, 'approved')
                """,
                (guild_id, user_id, code),
            )
        await db.execute(
            """
            UPDATE shop_referral_requests
            SET status = 'rejected', resolved_at = datetime('now')
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            """,
            (guild_id, user_id),
        )
        await db.commit()
    return True, f"Код **{code}** выдан."


async def admin_delete_referral_code(guild_id: int, user_id: int) -> tuple[bool, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, "У пользователя нет реферального кода."
        await db.execute(
            "DELETE FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
    return True, f"Код **{row[0]}** удалён."


async def get_user_referrer(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT r.inviter_id, c.code
            FROM shop_referrals r
            LEFT JOIN shop_referral_codes c
              ON c.guild_id = r.guild_id AND c.user_id = r.inviter_id
            WHERE r.guild_id = ? AND r.invited_id = ?
            """,
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def apply_referral_code(
    guild_id: int,
    user_id: int,
    code: str,
    *,
    inviter_points: int,
    invitee_points: int,
) -> tuple[bool, str, int | None]:
    code = normalize_referral_code(code)
    inviter_id = await get_referral_inviter(guild_id, code)
    if not inviter_id:
        return False, "Код не найден или ещё не одобрен.", None
    if inviter_id == user_id:
        return False, "Нельзя ввести свою рефку.", None
    if await referral_already_used(guild_id, user_id):
        return False, "Ты уже вводил реферальный код.", None
    if not await register_referral(guild_id, inviter_id, user_id):
        return False, "Не удалось применить код.", None

    await adjust_shop_points(guild_id, user_id, invitee_points)
    await adjust_shop_points(guild_id, inviter_id, inviter_points)
    return True, (
        f"✅ Код **{code}** принят!\n"
        f"+**{invitee_points}** баллов тебе · +**{inviter_points}** владельцу кода."
    ), inviter_id


async def get_points_leaderboard(guild_id: int, limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, points FROM shop_points
            WHERE guild_id = ? AND points > 0
            ORDER BY points DESC, user_id ASC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_all_shop_points(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, points FROM shop_points
            WHERE guild_id = ? AND points > 0
            ORDER BY points DESC, user_id ASC
            """,
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_referrals_leaderboard(guild_id: int, limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT inviter_id AS user_id, COUNT(*) AS referral_count
            FROM shop_referrals
            WHERE guild_id = ?
            GROUP BY inviter_id
            ORDER BY referral_count DESC, inviter_id ASC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_all_referral_codes(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, code, status
            FROM shop_referral_codes
            WHERE guild_id = ?
            ORDER BY code ASC, user_id ASC
            """,
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_custom_role_leaders(guild_id: int, item_key: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT DISTINCT user_id FROM shop_redemptions
            WHERE guild_id = ? AND status = 'accepted' AND prize_key = ?
            ORDER BY user_id ASC
            """,
            (guild_id, item_key),
        ) as c:
            rows = await c.fetchall()
    return [row[0] for row in rows]


async def get_squads(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role_id, leader_id FROM squads WHERE guild_id = ? ORDER BY role_id ASC",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def upsert_squad(guild_id: int, role_id: int, leader_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO squads (guild_id, role_id, leader_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, role_id) DO UPDATE SET leader_id = excluded.leader_id
            """,
            (guild_id, role_id, leader_id),
        )
        await db.commit()


async def get_invite_snapshot(guild_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT invite_code, uses FROM shop_invite_snapshots WHERE guild_id = ?",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return {row[0]: row[1] for row in rows}


async def save_invite_snapshot(guild_id: int, snapshot: dict[str, int]) -> None:
    if not snapshot:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO shop_invite_snapshots (guild_id, invite_code, uses)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, invite_code) DO UPDATE SET uses = excluded.uses
            """,
            [(guild_id, code, uses) for code, uses in snapshot.items()],
        )
        await db.commit()


async def get_referral_inviter_by_invite(guild_id: int, invite_code: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM shop_referral_codes WHERE guild_id = ? AND invite_code = ?",
            (guild_id, invite_code),
        ) as c:
            row = await c.fetchone()
    return row["user_id"] if row else None


async def register_referral(guild_id: int, inviter_id: int, invited_id: int) -> bool:
    if inviter_id == invited_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO shop_referrals (guild_id, inviter_id, invited_id) VALUES (?, ?, ?)",
                (guild_id, inviter_id, invited_id),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def referral_already_used(guild_id: int, invited_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM shop_referrals WHERE guild_id = ? AND invited_id = ?",
            (guild_id, invited_id),
        ) as c:
            return await c.fetchone() is not None


async def get_referral_count(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM shop_referrals WHERE guild_id = ? AND inviter_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def create_shop_redemption(
    guild_id: int,
    user_id: int,
    prize_key: str,
    prize_name: str,
    cost: int,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO shop_redemptions (guild_id, user_id, prize_key, prize_name, cost) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, prize_key, prize_name, cost),
        )
        await db.commit()
        return cursor.lastrowid


_DEFAULT_EARNING = {
    "voice": {"enabled": 1, "param1": 10, "param2": 10, "param3": 0},
    "words": {"enabled": 1, "param1": 250, "param2": 10, "param3": 100},
    "referral": {"enabled": 1, "param1": 50, "param2": 0, "param3": 100},
    "boost": {"enabled": 1, "param1": config.SHOP_BOOST_POINTS, "param2": 0, "param3": 0},
    "twitch": {"enabled": 1, "param1": config.SHOP_TWITCH_FOLLOW_POINTS, "param2": 0, "param3": 0},
    "telegram": {"enabled": 1, "param1": config.SHOP_TELEGRAM_JOIN_POINTS, "param2": 0, "param3": 0},
}


async def ensure_earning_rules(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        for key, defaults in _DEFAULT_EARNING.items():
            await db.execute(
                "INSERT OR IGNORE INTO shop_earning_rules "
                "(guild_id, rule_key, enabled, param1, param2, param3) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    guild_id,
                    key,
                    defaults["enabled"],
                    defaults["param1"],
                    defaults["param2"],
                    defaults["param3"],
                ),
            )
        await db.commit()


async def get_earning_rules(guild_id: int) -> dict[str, dict]:
    await ensure_earning_rules(guild_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_earning_rules WHERE guild_id = ?",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return {row["rule_key"]: dict(row) for row in rows}


async def set_earning_rule(
    guild_id: int,
    rule_key: str,
    *,
    enabled: int | None = None,
    param1: int | None = None,
    param2: int | None = None,
    param3: int | None = None,
) -> None:
    await ensure_earning_rules(guild_id)
    fields = []
    values = []
    if enabled is not None:
        fields.append("enabled = ?")
        values.append(enabled)
    if param1 is not None:
        fields.append("param1 = ?")
        values.append(param1)
    if param2 is not None:
        fields.append("param2 = ?")
        values.append(param2)
    if param3 is not None:
        fields.append("param3 = ?")
        values.append(param3)
    if not fields:
        return
    values.extend([guild_id, rule_key])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE shop_earning_rules SET {', '.join(fields)} "
            f"WHERE guild_id = ? AND rule_key = ?",
            values,
        )
        await db.commit()


async def get_shop_items(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_items WHERE guild_id = ? ORDER BY cost, id",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def add_shop_item(
    guild_id: int,
    item_key: str,
    name: str,
    description: str,
    cost: int,
    role_id: int = 0,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO shop_items (guild_id, item_key, name, description, cost, role_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, item_key, name, description, cost, role_id),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_shop_item(guild_id: int, item_key: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM shop_items WHERE guild_id = ? AND item_key = ?",
            (guild_id, item_key),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_shop_redemption(redemption_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_redemptions WHERE id = ?",
            (redemption_id,),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def set_redemption_message_id(redemption_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shop_redemptions SET order_message_id = ? WHERE id = ?",
            (message_id, redemption_id),
        )
        await db.commit()


async def set_redemption_ticket_channel(redemption_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shop_redemptions SET ticket_channel_id = ? WHERE id = ?",
            (channel_id, redemption_id),
        )
        await db.commit()


async def get_pending_redemptions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_redemptions WHERE status = 'pending' AND order_message_id IS NOT NULL"
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def resolve_redemption(
    redemption_id: int,
    *,
    status: str,
    admin_id: int,
    note: str = "",
) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_redemptions WHERE id = ?",
            (redemption_id,),
        ) as c:
            row = await c.fetchone()
        if not row or row["status"] != "pending":
            return None
        await db.execute(
            "UPDATE shop_redemptions SET status = ?, resolved_by = ?, resolved_at = datetime('now'), note = ? "
            "WHERE id = ?",
            (status, admin_id, note[:500], redemption_id),
        )
        await db.commit()
    return dict(row)


async def get_settings(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
        await db.commit()
        async with db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)) as c:
            row = await c.fetchone()
    return dict(row) if row else {"guild_id": guild_id}


async def set_setting(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
        await db.execute(f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id))
        await db.commit()


async def add_role_binding(guild_id: int, role_id: int, label: str = "") -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM role_bindings WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        ) as c:
            if await c.fetchone():
                return False
        await db.execute(
            "INSERT INTO role_bindings (guild_id, emoji, role_id, label) VALUES (?, ?, ?, ?)",
            (guild_id, "", role_id, label or ""),
        )
        await db.commit()
    return True


async def remove_role_binding(guild_id: int, role_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM role_bindings WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_role_bindings(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM role_bindings WHERE guild_id = ? ORDER BY id",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_panel_role_ids(guild_id: int) -> list[int]:
    bindings = await get_role_bindings(guild_id)
    return [b["role_id"] for b in bindings]


async def save_panel(guild_id: int, panel_type: str, channel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO panels (guild_id, panel_type, channel_id, message_id) VALUES (?, ?, ?, ?)",
            (guild_id, panel_type, channel_id, message_id),
        )
        await db.commit()


async def get_panel(guild_id: int, panel_type: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM panels WHERE guild_id = ? AND panel_type = ?",
            (guild_id, panel_type),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_all_panels(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM panels WHERE guild_id = ? ORDER BY panel_type",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_panel_by_message(message_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM panels WHERE message_id = ?", (message_id,)) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def save_voice_setup(guild_id: int, category_id: int, lobby_channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO voice_setups (guild_id, category_id, lobby_channel_id) VALUES (?, ?, ?)",
            (guild_id, category_id, lobby_channel_id),
        )
        await db.commit()


async def delete_voice_setup(guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM voice_setups WHERE guild_id = ?", (guild_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_voice_setup(guild_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM voice_setups WHERE guild_id = ?", (guild_id,)) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def save_temp_voice(
    channel_id: int,
    guild_id: int,
    owner_id: int,
    panel_message_id: int | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO temp_voice_channels "
            "(channel_id, guild_id, owner_id, locked, panel_message_id) VALUES (?, ?, ?, 0, ?)",
            (channel_id, guild_id, owner_id, panel_message_id),
        )
        await db.commit()


async def delete_temp_voice(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM temp_voice_channels WHERE channel_id = ?", (channel_id,))
        await db.commit()


async def get_temp_voice(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM temp_voice_channels WHERE channel_id = ?",
            (channel_id,),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_all_temp_voices() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM temp_voice_channels") as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def set_temp_voice_owner(channel_id: int, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE temp_voice_channels SET owner_id = ? WHERE channel_id = ?",
            (owner_id, channel_id),
        )
        await db.commit()


async def set_temp_voice_locked(channel_id: int, locked: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE temp_voice_channels SET locked = ? WHERE channel_id = ?",
            (1 if locked else 0, channel_id),
        )
        await db.commit()


async def set_temp_voice_panel_message(channel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE temp_voice_channels SET panel_message_id = ? WHERE channel_id = ?",
            (message_id, channel_id),
        )
        await db.commit()


async def add_twitch_alert(
    guild_id: int,
    channel_id: int,
    twitch_login: str,
    discord_user_id: int | None = None,
) -> bool:
    login = twitch_login.strip().lower().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO twitch_alerts (guild_id, channel_id, twitch_login, discord_user_id) "
                "VALUES (?, ?, ?, ?)",
                (guild_id, channel_id, login, discord_user_id),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_twitch_alert(guild_id: int, twitch_login: str) -> bool:
    login = twitch_login.strip().lower().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM twitch_alerts WHERE guild_id = ? AND twitch_login = ?",
            (guild_id, login),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_twitch_alerts(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM twitch_alerts WHERE guild_id = ? ORDER BY id",
            (guild_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_all_twitch_alerts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM twitch_alerts ORDER BY id") as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def set_twitch_last_stream(alert_id: int, started_at: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE twitch_alerts SET last_stream_started_at = ? WHERE id = ?",
            (started_at, alert_id),
        )
        await db.commit()


async def mark_twitch_announced(alert_id: int, started_at: str, announced_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE twitch_alerts SET last_stream_started_at = ?, last_announced_at = ? WHERE id = ?",
            (started_at, announced_at, alert_id),
        )
        await db.commit()


# --- Розыгрыши ---


async def get_giveaway_ticket_cost(guild_id: int) -> int:
    settings = await get_settings(guild_id)
    cost = settings.get("giveaway_ticket_cost") or 100
    return max(1, int(cost))


async def get_ticket_balance(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tickets FROM raffle_tickets WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    return row["tickets"] if row else 0


async def buy_raffle_tickets(
    guild_id: int,
    user_id: int,
    quantity: int,
    cost_per_ticket: int,
) -> tuple[bool, str, int]:
    if quantity <= 0:
        return False, "Укажи количество больше нуля.", 0
    total_cost = quantity * cost_per_ticket
    if not await spend_shop_points(guild_id, user_id, total_cost):
        return False, f"Не хватает баллов. Нужно **{total_cost}**.", 0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO raffle_tickets (guild_id, user_id, tickets) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET tickets = tickets + ?",
            (guild_id, user_id, quantity, quantity),
        )
        await db.commit()
        async with db.execute(
            "SELECT tickets FROM raffle_tickets WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    balance = row[0] if row else quantity
    return True, f"✅ Куплено **{quantity}** билет(ов) за **{total_cost}** баллов.", balance


async def create_raffle(
    guild_id: int,
    *,
    title: str,
    prize: str,
    description: str,
    winner_count: int,
    ends_at: str | None,
    created_by: int,
    channel_id: int,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO raffles (
                guild_id, title, prize, description, winner_count,
                ends_at, created_by, channel_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                title,
                prize,
                description,
                max(1, winner_count),
                ends_at,
                created_by,
                channel_id,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def set_raffle_message(raffle_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE raffles SET message_id = ? WHERE id = ?",
            (message_id, raffle_id),
        )
        await db.commit()


async def get_raffle(raffle_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM raffles WHERE id = ?", (raffle_id,)) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_active_raffles(guild_id: int) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM raffles
            WHERE guild_id = ? AND status = 'active'
              AND (ends_at IS NULL OR ends_at > ?)
            ORDER BY id DESC
            """,
            (guild_id, now),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_persisted_active_raffles() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM raffles
            WHERE status = 'active' AND message_id IS NOT NULL
              AND (ends_at IS NULL OR ends_at > ?)
            """,
            (now,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_raffle_entry(raffle_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
            (raffle_id, user_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def enter_raffle(raffle_id: int, user_id: int, tickets: int) -> tuple[bool, str]:
    if tickets < 1:
        return False, "Нужно потратить хотя бы **1** билет."

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM raffles WHERE id = ?", (raffle_id,)) as c:
            raffle = await c.fetchone()
        if not raffle:
            return False, "Розыгрыш не найден."
        if raffle["status"] != "active":
            return False, "Розыгрыш уже завершён."
        if user_id == raffle["created_by"]:
            return False, "Организатор розыгрыша не может участвовать."
        if raffle["ends_at"]:
            try:
                ends = datetime.fromisoformat(raffle["ends_at"])
                if ends.tzinfo is None:
                    ends = ends.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= ends:
                    return False, "Время участия истекло."
            except ValueError:
                pass

        async with db.execute(
            "SELECT tickets FROM raffle_tickets WHERE guild_id = ? AND user_id = ?",
            (raffle["guild_id"], user_id),
        ) as c:
            row = await c.fetchone()
        balance = row["tickets"] if row else 0
        if balance < tickets:
            return False, (
                f"Нужно **{tickets}** билет(ов), у тебя **{balance}**. "
                f"Купи билеты на панели розыгрышей."
            )

        async with db.execute(
            "SELECT tickets_spent FROM raffle_entries WHERE raffle_id = ? AND user_id = ?",
            (raffle_id, user_id),
        ) as c:
            existing = await c.fetchone()

        await db.execute(
            "UPDATE raffle_tickets SET tickets = tickets - ? "
            "WHERE guild_id = ? AND user_id = ?",
            (tickets, raffle["guild_id"], user_id),
        )

        if existing:
            new_spent = existing["tickets_spent"] + tickets
            await db.execute(
                "UPDATE raffle_entries SET tickets_spent = ? "
                "WHERE raffle_id = ? AND user_id = ?",
                (new_spent, raffle_id, user_id),
            )
            msg = f"🎟 Добавлено **{tickets}** билет(ов)! Всего в розыгрыше: **{new_spent}**."
        else:
            await db.execute(
                "INSERT INTO raffle_entries (raffle_id, user_id, tickets_spent) VALUES (?, ?, ?)",
                (raffle_id, user_id, tickets),
            )
            await db.execute(
                "UPDATE raffles SET entrants = entrants + 1 WHERE id = ?",
                (raffle_id,),
            )
            msg = f"🎉 Ты в розыгрыше с **{tickets}** билет(ами)! Чем больше билетов — тем выше шанс."

        await db.execute(
            "UPDATE raffles SET total_tickets = total_tickets + ? WHERE id = ?",
            (tickets, raffle_id),
        )
        await db.commit()
    return True, msg


async def get_raffle_entries(raffle_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM raffle_entries WHERE raffle_id = ? ORDER BY created_at",
            (raffle_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def draw_raffle_winners(raffle_id: int) -> tuple[bool, str, list[int]]:
    import json
    import random

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM raffles WHERE id = ?", (raffle_id,)) as c:
            raffle = await c.fetchone()
        if not raffle:
            return False, "Розыгрыш не найден.", []
        if raffle["status"] != "active":
            return False, "Розыгрыш уже завершён.", []

        async with db.execute(
            "SELECT user_id, tickets_spent FROM raffle_entries WHERE raffle_id = ?",
            (raffle_id,),
        ) as c:
            rows = await c.fetchall()
        if not rows:
            return False, "Нет участников.", []

        pool = [
            (row["user_id"], row["tickets_spent"])
            for row in rows
            if row["user_id"] != raffle["created_by"]
        ]
        if not pool:
            return False, "Нет участников (организатор исключён).", []
        winner_count = max(1, raffle["winner_count"] or 1)
        winners: list[int] = []

        for _ in range(min(winner_count, len(pool))):
            users = [user_id for user_id, _ in pool]
            weights = [weight for _, weight in pool]
            winner = random.choices(users, weights=weights, k=1)[0]
            winners.append(winner)
            pool = [(user_id, weight) for user_id, weight in pool if user_id != winner]

        await db.execute(
            "UPDATE raffles SET status = 'ended', winner_id = ?, winners_json = ? WHERE id = ?",
            (winners[0], json.dumps(winners), raffle_id),
        )
        await db.commit()
    return True, "Победители выбраны.", winners


async def cancel_raffle(raffle_id: int) -> tuple[bool, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM raffles WHERE id = ?", (raffle_id,)) as c:
            raffle = await c.fetchone()
        if not raffle:
            return False, "Розыгрыш не найден."
        if raffle["status"] != "active":
            return False, "Розыгрыш уже завершён."

        async with db.execute(
            "SELECT user_id, tickets_spent FROM raffle_entries WHERE raffle_id = ?",
            (raffle_id,),
        ) as c:
            entries = await c.fetchall()

        for entry in entries:
            await db.execute(
                "INSERT INTO raffle_tickets (guild_id, user_id, tickets) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET tickets = tickets + ?",
                (
                    raffle["guild_id"],
                    entry["user_id"],
                    entry["tickets_spent"],
                    entry["tickets_spent"],
                ),
            )

        await db.execute("DELETE FROM raffle_entries WHERE raffle_id = ?", (raffle_id,))
        await db.execute(
            "UPDATE raffles SET status = 'cancelled', entrants = 0, total_tickets = 0 WHERE id = ?",
            (raffle_id,),
        )
        await db.commit()
    return True, "Розыгрыш отменён, билеты возвращены участникам."


async def get_user_raffle_entries(guild_id: int, user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT e.*, r.title, r.prize, r.status
            FROM raffle_entries e
            JOIN raffles r ON r.id = e.raffle_id
            WHERE r.guild_id = ? AND e.user_id = ?
            ORDER BY e.created_at DESC
            """,
            (guild_id, user_id),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]
