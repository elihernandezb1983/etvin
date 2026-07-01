import discord

from config import BLACK, LEADERBOARD_REFRESH_MINUTES
from utils.database import (
    get_points_leaderboard,
    get_referrals_leaderboard,
    get_referral_count,
    get_user_referral_code,
    get_pending_referral_request,
    get_user_referrer,
    get_earning_rules,
    get_all_referral_codes,
)
from utils.squad import collect_squad_rows


def referral_request_embed(
    request_id: int,
    member: discord.Member,
    code: str,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📝 Заявка на рефку #{request_id}",
        description=(
            f"**Участник:** {member.mention}\n"
            f"**Желаемый код:** `{code}`\n\n"
            f"Обсудите детали в тикете. Когда всё ок — нажми **Одобрить**."
        ),
        color=discord.Color(BLACK),
    )
    return embed


class ReferralDecisionView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.request_id = request_id

        approve = discord.ui.Button(
            label="✅ Одобрить",
            style=discord.ButtonStyle.success,
            custom_id=f"referral:approve:{request_id}",
        )
        approve.callback = self._approve_cb
        self.add_item(approve)

        reject = discord.ui.Button(
            label="❌ Отклонить",
            style=discord.ButtonStyle.danger,
            custom_id=f"referral:reject:{request_id}",
        )
        reject.callback = self._reject_cb
        self.add_item(reject)

    async def _approve_cb(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_approve(interaction, self.request_id)

    async def _reject_cb(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_reject(interaction, self.request_id)


def referral_decision_view(request_id: int) -> ReferralDecisionView:
    return ReferralDecisionView(request_id)


class EnterReferralModal(discord.ui.Modal, title="Ввести реферальный код"):
    code = discord.ui.TextInput(
        label="Код",
        placeholder="Например: IVAN",
        min_length=3,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog or not interaction.guild:
            return
        await cog.process_enter_code(interaction, self.code.value)


class CreateReferralModal(discord.ui.Modal, title="Создать реферальный код"):
    code = discord.ui.TextInput(
        label="Название кода",
        placeholder="Например: IVAN или MYCODE",
        min_length=3,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog or not interaction.guild:
            return
        await cog.process_create_request(interaction, self.code.value)


class AdminSetReferralModal(discord.ui.Modal, title="Выдать реферальный код"):
    code = discord.ui.TextInput(
        label="Код",
        placeholder="Например: IVAN",
        min_length=3,
        max_length=20,
    )

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog or not interaction.guild:
            return
        await cog.process_admin_set(interaction, self.member, self.code.value)


class ReferralUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Выбери участника…",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Только участники сервера.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Действие для {member.mention}:",
            view=ReferralUserActionView(member),
            ephemeral=True,
        )


class ReferralAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ReferralUserSelect())


class ReferralUserActionView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=120)
        self.member = member

    @discord.ui.button(label="➕ Выдать код", style=discord.ButtonStyle.success)
    async def set_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminSetReferralModal(self.member))

    @discord.ui.button(label="🗑 Удалить код", style=discord.ButtonStyle.danger)
    async def delete_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("ReferralCog")
        if not cog or not interaction.guild:
            return
        await cog.process_admin_delete(interaction, self.member)


async def build_my_referrals_embed(guild: discord.Guild, user_id: int) -> discord.Embed:
    rules = await get_earning_rules(guild.id)
    inviter_pts = rules["referral"]["param1"]
    invitee_pts = rules["referral"]["param3"]
    refs = await get_referral_count(guild.id, user_id)
    earned = refs * inviter_pts
    own = await get_user_referral_code(guild.id, user_id)
    pending = await get_pending_referral_request(guild.id, user_id)
    used = await get_user_referrer(guild.id, user_id)

    embed = discord.Embed(title="👥 Мои рефералы", color=discord.Color(BLACK))
    embed.add_field(name="Приглашено", value=f"**{refs}** чел.", inline=True)
    embed.add_field(name="Заработано", value=f"**{earned}** баллов", inline=True)

    if own and own.get("status") == "approved":
        embed.add_field(
            name="Твой код",
            value=f"`{own['code']}` — делись, за каждого +**{inviter_pts}** б.",
            inline=False,
        )
    elif pending:
        embed.add_field(
            name="Заявка",
            value=f"⏳ Код **`{pending['requested_code']}`** на рассмотрении.",
            inline=False,
        )
    else:
        embed.add_field(
            name="Твой код",
            value="Пока нет — нажми **➕ Создать рефку** на панели магазина.",
            inline=False,
        )

    if used:
        inviter = guild.get_member(used["inviter_id"])
        inviter_label = inviter.mention if inviter else f"<@{used['inviter_id']}>"
        code_label = used.get("code") or "—"
        embed.add_field(
            name="Ты вводил",
            value=f"Код **`{code_label}`** · {inviter_label}",
            inline=False,
        )
    else:
        embed.add_field(
            name="Ты вводил",
            value=f"Ещё нет — **📝 Ввести рефку** (+**{invitee_pts}** б.)",
            inline=False,
        )

    embed.add_field(
        name="Как это работает",
        value=(
            f"1. Создай свой код (админ одобрит в тикете)\n"
            f"2. Друг вводит код — он +**{invitee_pts}** б., ты +**{inviter_pts}** б.\n"
            f"3. Один код на человека, свой код ввести нельзя"
        ),
        inline=False,
    )
    return embed


LEADERBOARD_FOOTER = f"Обновляется автоматически каждые {LEADERBOARD_REFRESH_MINUTES} мин."

LEADERBOARD_PANEL_TYPES = (
    "leaderboard_points",
    "leaderboard_referrals",
    "leaderboard_squads",
)


def _leaderboard_lines(guild: discord.Guild, rows: list[dict], value_key: str) -> str:
    if not rows:
        return "— пока пусто"
    medals = ("🥇", "🥈", "🥉")
    lines = []
    for i, row in enumerate(rows, start=1):
        member = guild.get_member(row["user_id"])
        name = member.display_name if member else f"ID {row['user_id']}"
        medal = medals[i - 1] if i <= 3 else f"**{i}.**"
        value = row[value_key]
        suffix = " б." if value_key == "points" else ""
        lines.append(f"{medal} {name} — **{value}**{suffix}")
    return "\n".join(lines)


def _squad_leaderboard_lines(guild: discord.Guild, rows: list[dict]) -> str:
    if not rows:
        return "— пока пусто"
    medals = ("🥇", "🥈", "🥉")
    lines = []
    for i, row in enumerate(rows, start=1):
        role = guild.get_role(row["role_id"])
        squad_name = role.name if role else f"ID {row['role_id']}"
        leader_id = row.get("leader_id")
        if leader_id:
            leader = guild.get_member(leader_id)
            leader_label = leader.mention if leader else f"<@{leader_id}>"
        else:
            leader_label = "—"
        medal = medals[i - 1] if i <= 3 else f"**{i}.**"
        lines.append(
            f"{medal} **{squad_name}** — **{row['member_count']}** чел. · 👑 {leader_label}"
        )
    return "\n".join(lines)


async def squads_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    rows = await collect_squad_rows(guild)

    embed = discord.Embed(
        title="🛡️ Топ сквадов",
        description=_squad_leaderboard_lines(guild, rows[:15]),
        color=discord.Color(BLACK),
    )
    embed.set_footer(text=LEADERBOARD_FOOTER)
    return embed


async def build_leaderboard_embed(guild: discord.Guild, panel_type: str) -> discord.Embed | None:
    if panel_type == "leaderboard_points":
        return await points_leaderboard_embed(guild)
    if panel_type == "leaderboard_referrals":
        return await referrals_leaderboard_embed(guild)
    if panel_type == "leaderboard_squads":
        return await squads_leaderboard_embed(guild)
    return None


async def points_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    rows = await get_points_leaderboard(guild.id)
    embed = discord.Embed(
        title="🏆 Топ по баллам",
        description=_leaderboard_lines(guild, rows, "points"),
        color=discord.Color(BLACK),
    )
    embed.set_footer(text=LEADERBOARD_FOOTER)
    return embed


async def referrals_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    rows = await get_referrals_leaderboard(guild.id)
    embed = discord.Embed(
        title="👥 Топ по рефералам",
        description=_leaderboard_lines(guild, rows, "referral_count"),
        color=discord.Color(BLACK),
    )
    embed.set_footer(text=LEADERBOARD_FOOTER)
    return embed


def _clamp_embed_text(text: str, limit: int = 4096) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n… *(обрезано)*"


def build_all_referrals_embeds(guild: discord.Guild, rows: list[dict]) -> list[discord.Embed]:
    if not rows:
        return [
            discord.Embed(
                title="👥 Все реферальные коды",
                description="— пока нет",
                color=discord.Color(BLACK),
            )
        ]

    lines: list[str] = []
    for row in rows:
        member = guild.get_member(row["user_id"])
        user_label = member.mention if member else f"<@{row['user_id']}>"
        status = row.get("status") or "approved"
        status_label = "" if status == "approved" else f" · _{status}_"
        lines.append(f"• {user_label} — `{row['code']}`{status_label}")

    embeds: list[discord.Embed] = []
    chunk: list[str] = []
    chunk_len = 0
    page = 1
    for line in lines:
        line_len = len(line) + 1
        if chunk and chunk_len + line_len > 3900:
            embeds.append(
                discord.Embed(
                    title="👥 Все реферальные коды" + (f" ({page})" if page > 1 else ""),
                    description=_clamp_embed_text("\n".join(chunk), 4096),
                    color=discord.Color(BLACK),
                )
            )
            page += 1
            chunk = [line]
            chunk_len = line_len
        else:
            chunk.append(line)
            chunk_len += line_len

    if chunk:
        embeds.append(
            discord.Embed(
                title="👥 Все реферальные коды" + (f" ({page})" if page > 1 else ""),
                description=_clamp_embed_text("\n".join(chunk), 4096),
                color=discord.Color(BLACK),
            )
        )
    embeds[0].set_footer(text=f"Всего кодов: {len(rows)}")
    return embeds[:10]
