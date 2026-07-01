import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import (
    buy_raffle_tickets,
    create_raffle,
    get_raffle,
    get_raffle_entry,
    get_active_raffles,
    get_persisted_active_raffles,
    get_giveaway_ticket_cost,
    get_ticket_balance,
    enter_raffle,
    draw_raffle_winners,
    cancel_raffle,
    set_raffle_message,
    set_setting,
)
from utils.discord_log import log_server
from utils.giveaway_ui import (
    raffle_v2_view,
    winners_v2_view,
    tickets_wallet_v2,
    TicketAmountView,
)
from utils.permissions import admin_only

log = logging.getLogger("etvin")

HOUR_CHOICES = [1, 3, 6, 12, 24, 48, 72]
WINNER_CHOICES = [1, 2, 3, 5, 10]


class GiveawayPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎟 Купить 1 билет",
        style=discord.ButtonStyle.primary,
        custom_id="giveaway:buy:1",
    )
    async def buy_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_buy(interaction, 1)

    @discord.ui.button(
        label="🎟 Купить 5 билетов",
        style=discord.ButtonStyle.primary,
        custom_id="giveaway:buy:5",
    )
    async def buy_five(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_buy(interaction, 5)

    @discord.ui.button(
        label="📋 Мои билеты",
        style=discord.ButtonStyle.secondary,
        custom_id="giveaway:wallet",
    )
    async def wallet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        view = await tickets_wallet_v2(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True)


async def _handle_buy(interaction: discord.Interaction, quantity: int) -> None:
    if not interaction.guild:
        return
    cog = interaction.client.get_cog("GiveawayCog")
    if not cog:
        await interaction.response.send_message("Розыгрыш недоступен.", ephemeral=True)
        return
    await cog.process_buy(interaction, quantity)


class AdminHubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="➕ Создать", style=discord.ButtonStyle.success)
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=CreateRaffleView(),
            ephemeral=True,
        )

    @discord.ui.button(label="🏆 Завершить", style=discord.ButtonStyle.primary)
    async def draw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        active = await get_active_raffles(interaction.guild.id)
        if not active:
            await interaction.response.send_message("Нет активных розыгрышей.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=RaffleAdminPickView("draw", active),
            ephemeral=True,
        )

    @discord.ui.button(label="❌ Отменить", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        active = await get_active_raffles(interaction.guild.id)
        if not active:
            await interaction.response.send_message("Нет активных розыгрышей.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=RaffleAdminPickView("cancel", active),
            ephemeral=True,
        )

    @discord.ui.button(label="⚙️ Настройки", style=discord.ButtonStyle.secondary)
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        cost = await get_giveaway_ticket_cost(interaction.guild.id)
        await interaction.response.send_modal(TicketCostModal(cost))


class CreateRaffleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.hours = 24
        self.winners = 1

        hours_select = discord.ui.Select(
            placeholder="Быстрый выбор часов (можно изменить в форме)",
            options=[
                discord.SelectOption(label=f"{h} ч.", value=str(h), default=(h == 24))
                for h in HOUR_CHOICES
            ],
        )
        hours_select.callback = self._hours_cb
        self.add_item(hours_select)

        winners_select = discord.ui.Select(
            placeholder="Сколько победителей?",
            options=[
                discord.SelectOption(label=str(w), value=str(w), default=(w == 1))
                for w in WINNER_CHOICES
            ],
        )
        winners_select.callback = self._winners_cb
        self.add_item(winners_select)

    async def _hours_cb(self, interaction: discord.Interaction):
        self.hours = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def _winners_cb(self, interaction: discord.Interaction):
        self.winners = int(interaction.data["values"][0])
        await interaction.response.defer()

    @discord.ui.button(label="📝 Указать приз и создать", style=discord.ButtonStyle.success)
    async def publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            CreateRaffleModal(hours=self.hours, winners=self.winners)
        )

class CreateRaffleModal(discord.ui.Modal, title="Новый розыгрыш"):
    prize = discord.ui.TextInput(
        label="На что розыгрыш (приз)",
        placeholder="Например: VIP на месяц",
        max_length=120,
    )
    title_input = discord.ui.TextInput(
        label="Название",
        placeholder="Например: Весенний розыгрыш",
        required=False,
        max_length=80,
    )
    duration_hours = discord.ui.TextInput(
        label="Через сколько часов завершить?",
        placeholder="Например: 24",
        min_length=1,
        max_length=4,
    )
    description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, *, hours: int, winners: int):
        super().__init__()
        self.winners = winners
        self.duration_hours.default = str(hours)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("GiveawayCog")
        if not cog or not interaction.guild:
            return
        raw_hours = self.duration_hours.value.strip()
        if not raw_hours.isdigit() or int(raw_hours) < 1:
            await interaction.response.send_message(
                "Длительность — целое число часов от 1.",
                ephemeral=True,
            )
            return
        hours = int(raw_hours)
        if hours > 720:
            await interaction.response.send_message(
                "Максимум **720** часов (30 дней).",
                ephemeral=True,
            )
            return
        title = self.title_input.value.strip() or self.prize.value.strip()
        await cog.process_create(
            interaction,
            title=title,
            prize=self.prize.value.strip(),
            description=self.description.value.strip(),
            hours=hours,
            winners=self.winners,
        )


class RaffleAdminPickView(discord.ui.View):
    def __init__(self, action: str, raffles: list[dict]):
        super().__init__(timeout=120)
        self.action = action
        select = discord.ui.Select(
            placeholder="Выбери розыгрыш…",
            options=[
                discord.SelectOption(
                    label=f"#{r['id']} {r['prize']}"[:100],
                    description=f"👥 {r['entrants']} · 🎟 {r.get('total_tickets', 0)}"[:100],
                    value=str(r["id"]),
                )
                for r in raffles[:25]
            ],
        )

        async def callback(interaction: discord.Interaction):
            cog = interaction.client.get_cog("GiveawayCog")
            if not cog:
                await interaction.response.send_message("Недоступно.", ephemeral=True)
                return
            raffle_id = int(select.values[0])
            if self.action == "draw":
                await cog.process_draw(interaction, raffle_id)
            else:
                await cog.process_cancel(interaction, raffle_id)

        select.callback = callback
        self.add_item(select)


class TicketCostModal(discord.ui.Modal, title="Цена билета"):
    cost = discord.ui.TextInput(
        label="Баллов за 1 билет",
        placeholder="100",
        max_length=5,
    )

    def __init__(self, current: int):
        super().__init__()
        self.cost.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not self.cost.value.isdigit() or int(self.cost.value) < 1:
            await interaction.response.send_message("Только число от 1.", ephemeral=True)
            return
        await set_setting(interaction.guild.id, "giveaway_ticket_cost", int(self.cost.value))
        await interaction.response.send_message(
            f"✅ Билет теперь стоит **{int(self.cost.value)}** баллов.",
            ephemeral=True,
        )


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(GiveawayPanelView())
        for row in await get_persisted_active_raffles():
            raffle = await get_raffle(row["id"])
            if raffle:
                self.bot.add_view(raffle_v2_view(row["id"], raffle))

    async def process_buy(self, interaction: discord.Interaction, quantity: int) -> None:
        cost = await get_giveaway_ticket_cost(interaction.guild.id)
        ok, msg, balance = await buy_raffle_tickets(
            interaction.guild.id,
            interaction.user.id,
            quantity,
            cost,
        )
        if ok:
            msg += f"\n🎟 На счету: **{balance}** билет(ов)"
        await interaction.response.send_message(msg, ephemeral=True)

    async def prompt_enter_tickets(self, interaction: discord.Interaction, raffle_id: int) -> None:
        if not interaction.guild:
            return
        balance = await get_ticket_balance(interaction.guild.id, interaction.user.id)
        entry = await get_raffle_entry(raffle_id, interaction.user.id)
        hint = "Докинь билеты — шанс вырастет!" if entry else "Выбери, сколько билетов вложить:"
        await interaction.response.send_message(
            f"{hint}\n🎟 У тебя: **{balance}**",
            view=TicketAmountView(raffle_id, balance, entry is not None),
            ephemeral=True,
        )

    async def process_enter(
        self,
        interaction: discord.Interaction,
        raffle_id: int,
        tickets: int,
    ) -> None:
        if not interaction.guild:
            return
        ok, msg = await enter_raffle(raffle_id, interaction.user.id, tickets)
        if ok:
            await self.refresh_raffle_message(interaction.guild, raffle_id)
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def refresh_raffle_message(self, guild: discord.Guild, raffle_id: int) -> None:
        raffle = await get_raffle(raffle_id)
        if not raffle or not raffle.get("message_id") or not raffle.get("channel_id"):
            return
        channel = guild.get_channel(raffle["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            msg = await channel.fetch_message(raffle["message_id"])
            view = raffle_v2_view(raffle_id, raffle, guild)
            if raffle["status"] == "active":
                self.bot.add_view(view)
            await msg.edit(content=None, embed=None, view=view)
        except discord.HTTPException:
            log.warning("Не удалось обновить розыгрыш #%s", raffle_id)

    async def process_create(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        prize: str,
        description: str,
        hours: int,
        winners: int,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Создавать розыгрыш можно только в текстовом канале.",
                ephemeral=True,
            )
            return

        ends_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        raffle_id = await create_raffle(
            interaction.guild.id,
            title=title,
            prize=prize,
            description=description,
            winner_count=winners,
            ends_at=ends_at,
            created_by=interaction.user.id,
            channel_id=interaction.channel.id,
        )
        raffle = await get_raffle(raffle_id)
        view = raffle_v2_view(raffle_id, raffle, interaction.guild)
        self.bot.add_view(view)

        await interaction.response.send_message(
            f"✅ Розыгрыш **#{raffle_id}** опубликован!",
            ephemeral=True,
        )
        msg = await interaction.channel.send(view=view)
        await set_raffle_message(raffle_id, msg.id)
        await log_server(
            interaction.guild,
            f"**Розыгрыш** #{raffle_id}\n"
            f"{interaction.user.mention} · **{prize}**\n"
            f"🏅 Победителей: **{winners}** · Конец: {_ends_short(ends_at)}",
        )

    async def process_draw(self, interaction: discord.Interaction, raffle_id: int) -> None:
        if not interaction.guild:
            return
        ok, msg, winners = await draw_raffle_winners(raffle_id)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        raffle = await get_raffle(raffle_id)
        await self.refresh_raffle_message(interaction.guild, raffle_id)

        channel = interaction.guild.get_channel(raffle.get("channel_id") or 0)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(view=winners_v2_view(raffle, winners, interaction.guild))
            except discord.HTTPException:
                pass

        mentions = []
        for wid in winners:
            member = interaction.guild.get_member(wid)
            mentions.append(member.mention if member else f"<@{wid}>")

        await interaction.response.send_message(
            f"✅ {msg}\n" + "\n".join(f"🥇 {m}" for m in mentions),
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Розыгрыш завершён** #{raffle_id}\n"
            f"Приз: **{raffle['prize']}**\n"
            f"Победители: {', '.join(mentions)} · {interaction.user.mention}",
        )

    async def process_cancel(self, interaction: discord.Interaction, raffle_id: int) -> None:
        if not interaction.guild:
            return
        ok, msg = await cancel_raffle(raffle_id)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        await self.refresh_raffle_message(interaction.guild, raffle_id)
        await interaction.response.send_message(f"✅ {msg}", ephemeral=True)
        await log_server(
            interaction.guild,
            f"**Розыгрыш отменён** #{raffle_id} — {interaction.user.mention}",
        )

    @app_commands.command(name="розыгрыш", description="Управление розыгрышами")
    @admin_only()
    async def giveaway_admin(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        cost = await get_giveaway_ticket_cost(interaction.guild.id)
        embed = discord.Embed(
            title="🎰 Управление розыгрышами",
            description=(
                f"**Цена билета:** {cost} баллов (меняется в ⚙️)\n\n"
                "• **Создать** — укажи часы, победителей и приз (организатор не участвует)\n"
                "• **Завершить** — случайный выбор с учётом вложенных билетов\n"
                "• **Отменить** — вернуть билеты участникам"
            ),
            color=discord.Color(0x000000),
        )
        await interaction.response.send_message(embed=embed, view=AdminHubView(), ephemeral=True)


def _ends_short(ends_at: str | None) -> str:
    if not ends_at:
        return "без срока"
    try:
        dt = datetime.fromisoformat(ends_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f"<t:{int(dt.timestamp())}:R>"
    except ValueError:
        return ends_at


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
