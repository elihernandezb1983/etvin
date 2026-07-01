import json
from datetime import datetime, timezone

import discord

from utils.database import (
    get_active_raffles,
    get_giveaway_ticket_cost,
    get_ticket_balance,
    get_user_raffle_entries,
)

ACCENT = 0x000000


def _ts() -> str:
    return f"<t:{int(discord.utils.utcnow().timestamp())}:f>"


def _parse_ends_at(ends_at: str | None) -> datetime | None:
    if not ends_at:
        return None
    try:
        dt = datetime.fromisoformat(ends_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _ends_display(ends_at: str | None) -> str:
    dt = _parse_ends_at(ends_at)
    if not dt:
        return "— без срока"
    ts = int(dt.timestamp())
    return f"<t:{ts}:R> · <t:{ts}:f>"


def _v2_text(body: str, accent: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=discord.Color(accent))
    container.add_item(discord.ui.TextDisplay(body))
    view.add_item(container)
    return view


def _raffle_body(raffle: dict, guild: discord.Guild | None = None) -> str:
    status = raffle.get("status", "active")
    if status == "ended":
        badge = "🏆 **Завершён**"
    elif status == "cancelled":
        badge = "❌ **Отменён**"
    else:
        badge = "🎰 **Активен**"

    lines = [
        f"# {badge}\n",
        f"## {raffle['title']}\n",
        f"**🎁 Приз:** {raffle['prize']}",
    ]
    if raffle.get("description"):
        lines.append(f"**📝 Описание:** {raffle['description']}")

    lines.extend([
        "",
        f"**🎟 В билетах:** {raffle.get('total_tickets', 0)} · **👥 Участников:** {raffle.get('entrants', 0)}",
        f"**🏅 Победителей:** {raffle.get('winner_count', 1)}",
        f"**⏰ Конец:** {_ends_display(raffle.get('ends_at'))}",
        "",
        "💡 **Чем больше билетов вложишь — тем выше шанс на победу!**",
        "🚫 Организатор розыгрыша участвовать не может.",
    ])

    if status == "ended":
        winners = _parse_winners(raffle)
        if winners and guild:
            mentions = []
            for wid in winners:
                member = guild.get_member(wid)
                mentions.append(member.mention if member else f"<@{wid}>")
            lines.append(f"\n**🥇 Победители:** {', '.join(mentions)}")

    lines.append(f"\n-# Розыгрыш #{raffle['id']} · {_ts()}")
    return "\n".join(lines)


def _parse_winners(raffle: dict) -> list[int]:
    raw = raffle.get("winners_json")
    if raw:
        try:
            return [int(x) for x in json.loads(raw)]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if raffle.get("winner_id"):
        return [int(raffle["winner_id"])]
    return []


class RaffleV2View(discord.ui.LayoutView):
    def __init__(self, raffle_id: int, raffle: dict, guild: discord.Guild | None = None):
        super().__init__(timeout=None)
        self.raffle_id = raffle_id
        container = discord.ui.Container(accent_color=discord.Color(ACCENT))
        container.add_item(discord.ui.TextDisplay(_raffle_body(raffle, guild)))

        if raffle.get("status") == "active":
            row = discord.ui.ActionRow()
            btn = discord.ui.Button(
                label="🎟 Участвовать",
                style=discord.ButtonStyle.success,
                custom_id=f"giveaway:enter:{raffle_id}",
            )
            btn.callback = self._enter_cb
            row.add_item(btn)
            container.add_item(row)

        self.add_item(container)

    async def _enter_cb(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("GiveawayCog")
        if not cog or not interaction.guild:
            await interaction.response.send_message("Розыгрыш недоступен.", ephemeral=True)
            return
        await cog.prompt_enter_tickets(interaction, self.raffle_id)


def raffle_v2_view(raffle_id: int, raffle: dict, guild: discord.Guild | None = None) -> RaffleV2View:
    return RaffleV2View(raffle_id, raffle, guild)


def winners_v2_view(raffle: dict, winners: list[int], guild: discord.Guild) -> discord.ui.LayoutView:
    mentions = []
    for wid in winners:
        member = guild.get_member(wid)
        mentions.append(member.mention if member else f"<@{wid}>")

    body = (
        f"# 🏆 Розыгрыш завершён!\n\n"
        f"**#{raffle['id']}** · {raffle['prize']}\n\n"
        f"**Победители ({len(winners)}):**\n"
        + "\n".join(f"🥇 {m}" for m in mentions)
        + f"\n\n👥 Участников: **{raffle.get('entrants', 0)}** · "
        f"🎟 Билетов в пуле: **{raffle.get('total_tickets', 0)}**\n"
        f"-# {_ts()}"
    )
    return _v2_text(body, ACCENT)


async def giveaway_panel_embed(guild: discord.Guild, image_url: str | None = None) -> discord.Embed:
    active = await get_active_raffles(guild.id)
    ticket_cost = await get_giveaway_ticket_cost(guild.id)

    if active:
        lines = [
            f"**#{r['id']}** {r['prize']} — 🎟 **{r.get('total_tickets', 0)}** — 👥 **{r['entrants']}**"
            for r in active[:8]
        ]
        active_block = "\n".join(lines)
        if len(active) > 8:
            active_block += f"\n_…и ещё {len(active) - 8}_"
    else:
        active_block = "— сейчас нет активных розыгрышей"

    description = (
        f"__**🎰 Розыгрыши**__\n\n"
        f"🎟 **Билет** — **{ticket_cost}** баллов\n"
        f"Участие **только за билеты**. Вложи больше — шанс выше!\n\n"
        f"-- **Активные розыгрыши**\n"
        f"{active_block}\n\n"
        f"-- **Как участвовать**\n"
        f"1. Купи билеты кнопкой ниже\n"
        f"2. Нажми **Участвовать** на розыгрыше\n"
        f"3. Выбери, сколько билетов вложить"
    )

    embed = discord.Embed(description=description, color=discord.Color(ACCENT))
    if image_url:
        embed.set_image(url=image_url)
    return embed


async def tickets_wallet_v2(guild_id: int, user_id: int) -> discord.ui.LayoutView:
    balance = await get_ticket_balance(guild_id, user_id)
    cost = await get_giveaway_ticket_cost(guild_id)
    entries = await get_user_raffle_entries(guild_id, user_id)

    active_entries = [e for e in entries if e["status"] == "active"]
    lines = [
        f"# 🎟 Твои билеты\n",
        f"**Баланс:** {balance} билет(ов)",
        f"**Цена билета:** {cost} баллов",
        "",
        "💡 Можно докидывать билеты в активный розыгрыш — шанс растёт!",
    ]

    if active_entries:
        lines.append("\n**🎰 Ты участвуешь:**")
        for e in active_entries[:10]:
            lines.append(f"• **#{e['raffle_id']}** {e['prize']} — вложено **{e['tickets_spent']}** 🎟")

    return _v2_text("\n".join(lines), ACCENT)


class TicketAmountView(discord.ui.View):
    def __init__(self, raffle_id: int, balance: int, already_in: bool):
        super().__init__(timeout=120)
        self.raffle_id = raffle_id
        amounts = [1, 2, 3, 5, 10, 25]
        for amount in amounts:
            if amount > balance:
                continue
            btn = discord.ui.Button(
                label=f"{amount} 🎟",
                style=discord.ButtonStyle.primary,
            )
            btn.callback = self._make_cb(amount)
            self.add_item(btn)
            if len(self.children) >= 5:
                break

        if not self.children:
            self.add_item(
                discord.ui.Button(
                    label="Нет билетов",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
            )

        label = "Другое кол-во" if balance > 0 else "—"
        custom_btn = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=balance <= 0,
        )
        custom_btn.callback = self._custom_cb
        self.add_item(custom_btn)

        self._already_in = already_in

    def _make_cb(self, amount: int):
        async def cb(interaction: discord.Interaction):
            cog = interaction.client.get_cog("GiveawayCog")
            if not cog:
                await interaction.response.send_message("Недоступно.", ephemeral=True)
                return
            await cog.process_enter(interaction, self.raffle_id, amount)

        return cb

    async def _custom_cb(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketAmountModal(self.raffle_id))


class TicketAmountModal(discord.ui.Modal, title="Сколько билетов вложить?"):
    amount = discord.ui.TextInput(
        label="Количество билетов",
        placeholder="Например: 7",
        min_length=1,
        max_length=3,
    )

    def __init__(self, raffle_id: int):
        super().__init__()
        self.raffle_id = raffle_id

    async def on_submit(self, interaction: discord.Interaction):
        if not self.amount.value.isdigit() or int(self.amount.value) < 1:
            await interaction.response.send_message("Только число от 1.", ephemeral=True)
            return
        cog = interaction.client.get_cog("GiveawayCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_enter(interaction, self.raffle_id, int(self.amount.value))
