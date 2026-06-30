import re

import discord

from utils.database import (
    get_shop_items,
    get_settings,
    get_earning_rules,
    add_shop_item,
    remove_shop_item,
    set_setting,
    set_earning_rule,
)
from utils.permissions import is_admin

BLACK = 0x000000
GREEN = 0x57F287
RED = 0xED4245


def _ts() -> str:
    return f"<t:{int(discord.utils.utcnow().timestamp())}:f>"


def v2_view(body: str, accent: int = BLACK) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    container = discord.ui.Container(accent_color=discord.Color(accent))
    container.add_item(discord.ui.TextDisplay(body))
    view.add_item(container)
    return view


def verdict_dm_view(*, accepted: bool, prize_name: str, cost: int, note: str = "") -> discord.ui.LayoutView:
    if accepted:
        title = "✅ Заявка одобрена"
        accent = GREEN
        status = "Админ принял заявку. Приз будет выдан."
    else:
        title = "❌ Заявка отклонена"
        accent = RED
        status = f"Баллы возвращены на баланс (**{cost}**)."

    body = (
        f"**{title}**\n\n"
        f"**Приз:** {prize_name}\n"
        f"**Стоимость:** {cost} баллов\n"
        f"**Статус:** {status}"
    )
    if note:
        body += f"\n**Комментарий:** {note}"
    body += f"\n-# {_ts()}"
    return v2_view(body, accent)


def order_request_embed(
    redemption_id: int,
    user: discord.abc.User,
    prize_name: str,
    cost: int,
    description: str = "",
) -> discord.Embed:
    embed = discord.Embed(title=f"🛒 Заявка #{redemption_id}", color=BLACK)
    embed.add_field(name="Покупатель", value=user.mention, inline=True)
    embed.add_field(name="Приз", value=prize_name, inline=True)
    embed.add_field(name="Списано", value=f"**{cost}** баллов", inline=True)
    if description:
        embed.add_field(name="Описание", value=description, inline=False)
    embed.set_footer(text=_ts())
    return embed


class OrderDecisionView(discord.ui.View):
    def __init__(self, redemption_id: int):
        super().__init__(timeout=None)
        self.redemption_id = redemption_id

        accept_btn = discord.ui.Button(
            label="✅ Принять",
            style=discord.ButtonStyle.success,
            custom_id=f"shop:accept:{redemption_id}",
        )
        reject_btn = discord.ui.Button(
            label="❌ Отклонить",
            style=discord.ButtonStyle.danger,
            custom_id=f"shop:reject:{redemption_id}",
        )
        accept_btn.callback = self._accept_cb
        reject_btn.callback = self._reject_cb
        self.add_item(accept_btn)
        self.add_item(reject_btn)

    async def _accept_cb(self, interaction: discord.Interaction):
        await _handle_order_decision(interaction, self.redemption_id, accepted=True)

    async def _reject_cb(self, interaction: discord.Interaction):
        await _handle_order_decision(interaction, self.redemption_id, accepted=False)


class CloseTicketView(discord.ui.View):
    def __init__(self, redemption_id: int):
        super().__init__(timeout=None)
        self.redemption_id = redemption_id
        close_btn = discord.ui.Button(
            label="🔒 Закрыть тикет",
            style=discord.ButtonStyle.secondary,
            custom_id=f"shop:close:{redemption_id}",
        )
        close_btn.callback = self._close_cb
        self.add_item(close_btn)

    async def _close_cb(self, interaction: discord.Interaction):
        if not interaction.guild or not await is_admin(interaction):
            await interaction.response.send_message("Только для админов.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        await interaction.response.send_message("Тикет закрывается…", ephemeral=True)
        try:
            await interaction.channel.delete(reason=f"Тикет #{self.redemption_id} закрыт")
        except discord.HTTPException:
            pass


async def _handle_order_decision(
    interaction: discord.Interaction,
    redemption_id: int,
    *,
    accepted: bool,
):
    if not interaction.guild or not await is_admin(interaction):
        await interaction.response.send_message("Только для админов.", ephemeral=True)
        return

    cog = interaction.client.get_cog("ShopCog")
    if not cog:
        await interaction.response.send_message("Магазин недоступен.", ephemeral=True)
        return

    await cog.process_order_decision(interaction, redemption_id, accepted=accepted)


def _slug_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", name.lower().strip())
    return key.strip("_")[:40] or "item"


# --- Настройка магазина ---

async def build_shop_setup_embed(guild: discord.Guild) -> discord.Embed:
    settings = await get_settings(guild.id)
    items = await get_shop_items(guild.id)
    ticket_cat_id = settings.get("shop_ticket_category_id") or settings.get("shop_orders_channel_id")
    ticket_cat = guild.get_channel(ticket_cat_id) if ticket_cat_id else None
    if isinstance(ticket_cat, discord.TextChannel) and ticket_cat.category:
        ticket_cat = ticket_cat.category

    if items:
        items_text = "\n".join(
            f"• **{i['name']}** — {i['cost']} б." for i in items
        )
    else:
        items_text = "— товаров нет"

    embed = discord.Embed(title="🛒 Настройка магазина", color=BLACK)
    embed.add_field(
        name="Категория тикетов",
        value=ticket_cat.mention if isinstance(ticket_cat, discord.CategoryChannel) else "— не настроена",
        inline=False,
    )
    embed.add_field(name="Товары", value=items_text, inline=False)
    embed.set_footer(text="Выбери действие в меню ниже")
    return embed


class ShopSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        placeholder="Выбери действие…",
        options=[
            discord.SelectOption(label="Обзор", value="overview", emoji="📋"),
            discord.SelectOption(label="Добавить товар", value="add", emoji="➕"),
            discord.SelectOption(label="Удалить товар", value="remove", emoji="🗑️"),
            discord.SelectOption(label="Категория тикетов", value="ticket_category", emoji="🎫"),
        ],
    )
    async def action_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not interaction.guild or not await is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        action = select.values[0]
        if action == "overview":
            embed = await build_shop_setup_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=ShopSetupView())
        elif action == "add":
            await interaction.response.send_modal(AddItemModal())
        elif action == "remove":
            items = await get_shop_items(interaction.guild.id)
            if not items:
                await interaction.response.send_message("Товаров нет.", ephemeral=True)
                return
            view = RemoveItemView(items)
            await interaction.response.send_message(
                "Выбери товар для удаления:",
                view=view,
                ephemeral=True,
            )
        elif action == "ticket_category":
            view = TicketCategoryView()
            await interaction.response.send_message(
                "Выбери категорию, где будут создаваться тикеты покупок:",
                view=view,
                ephemeral=True,
            )


class AddItemModal(discord.ui.Modal, title="Добавить товар"):
    name = discord.ui.TextInput(label="Название", max_length=80)
    description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )
    cost = discord.ui.TextInput(label="Стоимость (баллы)", placeholder="500", max_length=6)
    role_id = discord.ui.TextInput(
        label="ID роли (необязательно)",
        placeholder="0",
        required=False,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not self.cost.value.strip().isdigit():
            await interaction.response.send_message("Стоимость — число.", ephemeral=True)
            return

        cost = int(self.cost.value.strip())
        role_raw = (self.role_id.value or "0").strip()
        role_id = int(role_raw) if role_raw.isdigit() else 0
        key = _slug_key(self.name.value)
        items = await get_shop_items(interaction.guild.id)
        existing = {i["item_key"] for i in items}
        if key in existing:
            key = f"{key}_{len(items) + 1}"

        ok = await add_shop_item(
            interaction.guild.id,
            key,
            self.name.value.strip(),
            (self.description.value or "").strip(),
            cost,
            role_id,
        )
        if not ok:
            await interaction.response.send_message("Не удалось добавить.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Товар **{self.name.value.strip()}** добавлен.",
            ephemeral=True,
        )


class RemoveItemView(discord.ui.View):
    def __init__(self, items: list[dict]):
        super().__init__(timeout=120)
        options = [
            discord.SelectOption(label=i["name"][:100], value=i["item_key"])
            for i in items[:25]
        ]
        select = discord.ui.Select(placeholder="Товар для удаления", options=options)

        async def callback(interaction: discord.Interaction):
            if not interaction.guild:
                return
            key = select.values[0]
            await remove_shop_item(interaction.guild.id, key)
            await interaction.response.edit_message(
                content="✅ Товар удалён.",
                view=None,
            )

        select.callback = callback
        self.add_item(select)


class TicketCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(self._category_select())

    def _category_select(self) -> discord.ui.ChannelSelect:
        sel = discord.ui.ChannelSelect(
            placeholder="Категория тикетов",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1,
        )

        async def callback(interaction: discord.Interaction):
            if not interaction.guild:
                return
            category = sel.values[0]
            await set_setting(interaction.guild.id, "shop_ticket_category_id", category.id)
            await interaction.response.edit_message(
                content=f"✅ Категория тикетов → **{category.name}**",
                view=None,
            )

        sel.callback = callback
        return sel


# --- Настройка начисления ---

async def build_earning_setup_embed(guild: discord.Guild) -> discord.Embed:
    rules = await get_earning_rules(guild.id)
    voice = rules["voice"]
    words = rules["words"]
    referral = rules["referral"]

    def onoff(v: int) -> str:
        return "✅ вкл" if v else "❌ выкл"

    embed = discord.Embed(title="⚙️ Настройка начисления", color=BLACK)
    embed.add_field(
        name="🎙️ Войс",
        value=(
            f"{onoff(voice['enabled'])}\n"
            f"{voice['param1']} мин → **{voice['param2']}** баллов"
        ),
        inline=True,
    )
    embed.add_field(
        name="💬 Слова",
        value=(
            f"{onoff(words['enabled'])}\n"
            f"{words['param1']} слов → **{words['param2']}** б.\n"
            f"Лимит в день: **{words['param3']}** б."
        ),
        inline=True,
    )
    embed.add_field(
        name="👥 Реферал",
        value=f"{onoff(referral['enabled'])}\n**{referral['param1']}** баллов за друга",
        inline=True,
    )
    embed.set_footer(text="Антифлуд: короткие, одинаковые и быстрые сообщения не засчитываются")
    return embed


class EarningSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        placeholder="Выбери действие…",
        options=[
            discord.SelectOption(label="Обзор", value="overview", emoji="📋"),
            discord.SelectOption(label="Настроить войс", value="voice", emoji="🎙️"),
            discord.SelectOption(label="Настроить слова", value="words", emoji="💬"),
            discord.SelectOption(label="Настроить реферал", value="referral", emoji="👥"),
            discord.SelectOption(label="Вкл/выкл войс", value="toggle_voice", emoji="🔀"),
            discord.SelectOption(label="Вкл/выкл слова", value="toggle_words", emoji="🔀"),
            discord.SelectOption(label="Вкл/выкл реферал", value="toggle_referral", emoji="🔀"),
        ],
    )
    async def action_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not interaction.guild or not await is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        action = select.values[0]
        guild_id = interaction.guild.id

        if action == "overview":
            embed = await build_earning_setup_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=EarningSetupView())
        elif action == "voice":
            await interaction.response.send_modal(EditVoiceModal())
        elif action == "words":
            await interaction.response.send_modal(EditWordsModal())
        elif action == "referral":
            await interaction.response.send_modal(EditReferralModal())
        elif action.startswith("toggle_"):
            key = action.replace("toggle_", "")
            rules = await get_earning_rules(guild_id)
            new_val = 0 if rules[key]["enabled"] else 1
            await set_earning_rule(guild_id, key, enabled=new_val)
            embed = await build_earning_setup_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=EarningSetupView())


class EditVoiceModal(discord.ui.Modal, title="Настройка войса"):
    minutes = discord.ui.TextInput(label="Минут для награды", default="10", max_length=4)
    points = discord.ui.TextInput(label="Баллов за награду", default="10", max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not self.minutes.value.isdigit() or not self.points.value.isdigit():
            await interaction.response.send_message("Только числа.", ephemeral=True)
            return
        await set_earning_rule(
            interaction.guild.id,
            "voice",
            param1=int(self.minutes.value),
            param2=int(self.points.value),
        )
        embed = await build_earning_setup_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed,
            view=EarningSetupView(),
            ephemeral=True,
        )


class EditWordsModal(discord.ui.Modal, title="Настройка слов"):
    threshold = discord.ui.TextInput(label="Слов для награды", default="250", max_length=5)
    points = discord.ui.TextInput(label="Баллов за награду", default="10", max_length=4)
    daily_cap = discord.ui.TextInput(label="Лимит баллов в день", default="100", max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not all(
            x.isdigit()
            for x in (self.threshold.value, self.points.value, self.daily_cap.value)
        ):
            await interaction.response.send_message("Только числа.", ephemeral=True)
            return
        await set_earning_rule(
            interaction.guild.id,
            "words",
            param1=int(self.threshold.value),
            param2=int(self.points.value),
            param3=int(self.daily_cap.value),
        )
        embed = await build_earning_setup_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed,
            view=EarningSetupView(),
            ephemeral=True,
        )


class EditReferralModal(discord.ui.Modal, title="Настройка реферала"):
    points = discord.ui.TextInput(label="Баллов за друга", default="50", max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not self.points.value.isdigit():
            await interaction.response.send_message("Только числа.", ephemeral=True)
            return
        await set_earning_rule(
            interaction.guild.id,
            "referral",
            param1=int(self.points.value),
        )
        embed = await build_earning_setup_embed(interaction.guild)
        await interaction.response.send_message(
            embed=embed,
            view=EarningSetupView(),
            ephemeral=True,
        )
