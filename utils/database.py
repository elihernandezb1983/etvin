import os
import aiosqlite
from config import DB_PATH


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()


async def _ensure_shop_row(db, guild_id: int, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO shop_points (guild_id, user_id) VALUES (?, ?)",
        (guild_id, user_id),
    )


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


async def _reset_words_day_if_needed(row: dict) -> dict:
    today = __import__("datetime").date.today().isoformat()
    if row.get("words_day") != today:
        row = dict(row)
        row["words_points_today"] = 0
        row["words_day"] = today
    return row


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
    if seconds <= 0:
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


async def add_message_words(
    guild_id: int,
    user_id: int,
    words: int,
    *,
    words_per_reward: int,
    points_per_reward: int,
    daily_cap: int,
) -> tuple[int, int]:
    if words <= 0:
        row = await get_shop_points(guild_id, user_id)
        return 0, row["points"]

    today = __import__("datetime").date.today().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_shop_row(db, guild_id, user_id)
        await db.commit()
        async with db.execute(
            "SELECT * FROM shop_points WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        row = dict(row)

        if row.get("words_day") != today:
            row["words_points_today"] = 0
            row["words_day"] = today

        remaining_cap = max(0, daily_cap - row["words_points_today"])
        if remaining_cap <= 0:
            return 0, row["points"]

        word_buffer = row["word_buffer"] + words
        points = row["points"]
        awarded = 0
        while word_buffer >= words_per_reward and awarded + points_per_reward <= remaining_cap:
            word_buffer -= words_per_reward
            points += points_per_reward
            awarded += points_per_reward
            row["words_points_today"] += points_per_reward

        await db.execute(
            "UPDATE shop_points SET points = ?, word_buffer = ?, voice_buffer = ?, "
            "words_points_today = ?, words_day = ? WHERE guild_id = ? AND user_id = ?",
            (
                points,
                word_buffer,
                row["voice_buffer"],
                row["words_points_today"],
                row["words_day"],
                guild_id,
                user_id,
            ),
        )
        await db.commit()
    return awarded, points


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


async def get_or_create_referral_code(guild_id: int, user_id: int) -> str:
    import secrets
    import string

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT code FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
        if row:
            return row["code"]

        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            try:
                await db.execute(
                    "INSERT INTO shop_referral_codes (guild_id, user_id, code) VALUES (?, ?, ?)",
                    (guild_id, user_id, code),
                )
                await db.commit()
                return code
            except aiosqlite.IntegrityError:
                continue
    raise RuntimeError("Не удалось создать реф-код")


async def get_referral_inviter(guild_id: int, code: str) -> int | None:
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM shop_referral_codes WHERE guild_id = ? AND code = ?",
            (guild_id, code),
        ) as c:
            row = await c.fetchone()
    return row["user_id"] if row else None


async def get_referral_invite_code(guild_id: int, user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT invite_code FROM shop_referral_codes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as c:
            row = await c.fetchone()
    if row and row["invite_code"]:
        return row["invite_code"]
    return None


async def set_referral_invite_code(guild_id: int, user_id: int, invite_code: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shop_referral_codes SET invite_code = ? WHERE guild_id = ? AND user_id = ?",
            (invite_code, guild_id, user_id),
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
    "referral": {"enabled": 1, "param1": 50, "param2": 0, "param3": 0},
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
