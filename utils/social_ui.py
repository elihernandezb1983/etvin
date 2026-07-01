import discord

from config import BLACK


def social_bonus_enabled(rules: dict) -> bool:
    return bool(
        rules.get("twitch", {}).get("enabled")
        or rules.get("telegram", {}).get("enabled")
    )


def default_social_bonus_points(rules: dict) -> int:
    points = 0
    for key in ("twitch", "telegram"):
        rule = rules.get(key, {})
        if rule.get("enabled"):
            points = max(points, rule.get("param1", 0))
    return points


def format_social_bonus_earning_lines(rules: dict) -> list[str]:
    lines: list[str] = []
    twitch = rules.get("twitch", {})
    telegram = rules.get("telegram", {})
    if twitch.get("enabled"):
        lines.append(
            f"📺 **Подписка Twitch** — до **{twitch['param1']}** б. (один раз)"
        )
    if telegram.get("enabled"):
        lines.append(
            f"✈️ **Подписка Telegram** — до **{telegram['param1']}** б. (один раз)"
        )
    return lines


def social_request_embed(request_id: int, member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title=f"📱 Бонус за подписку #{request_id}",
        description=(
            f"**Участник:** {member.mention}\n"
            "**Платформы:** Twitch / Telegram\n\n"
            "Проверь подписку (скрин). Если всё ок — **Принять** и укажи баллы. "
            "Иначе — **Отказать**."
        ),
        color=discord.Color(BLACK),
    )
    return embed


class SocialApproveModal(discord.ui.Modal, title="Принять заявку"):
    def __init__(self, request_id: int, default_points: int):
        super().__init__()
        self.request_id = request_id
        self.points = discord.ui.TextInput(
            label="Баллы",
            placeholder="Сколько начислить",
            default=str(default_points),
            min_length=1,
            max_length=6,
        )
        self.add_item(self.points)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SocialBonusCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        raw = self.points.value.strip()
        if not raw.isdigit() or int(raw) <= 0:
            await interaction.response.send_message(
                "Укажи целое число больше нуля.",
                ephemeral=True,
            )
            return
        await cog.process_approve(interaction, self.request_id, int(raw))


class SocialDecisionView(discord.ui.View):
    def __init__(self, request_id: int, default_points: int):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.default_points = default_points

        approve = discord.ui.Button(
            label="✅ Принять",
            style=discord.ButtonStyle.success,
            custom_id=f"social:approve:{request_id}",
        )
        approve.callback = self._approve_cb
        self.add_item(approve)

        reject = discord.ui.Button(
            label="❌ Отказать",
            style=discord.ButtonStyle.danger,
            custom_id=f"social:reject:{request_id}",
        )
        reject.callback = self._reject_cb
        self.add_item(reject)

    async def _approve_cb(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SocialBonusCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await interaction.response.send_modal(
            SocialApproveModal(self.request_id, self.default_points)
        )

    async def _reject_cb(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SocialBonusCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_reject(interaction, self.request_id)


def social_decision_view(request_id: int, default_points: int) -> SocialDecisionView:
    return SocialDecisionView(request_id, default_points)
