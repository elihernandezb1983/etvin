import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import (
    get_shop_points,
    get_shop_items,
    get_settings,
    get_earning_rules,
    add_voice_seconds,
    apply_chat_message,
    adjust_shop_points,
    spend_shop_points,
    get_referral_count,
    get_user_referrer,
    create_shop_redemption,
    set_redemption_message_id,
    set_redemption_ticket_channel,
    resolve_redemption,
    get_pending_redemptions,
    award_boost_points,
    mark_boost_message_processed,
    get_all_shop_points,
)
from utils.discord_log import log_server
from utils.permissions import admin_only
from utils.shop_tickets import create_shop_ticket, remove_buyer_from_ticket
from utils.shop_ui import (
    order_request_embed,
    OrderDecisionView,
    build_admin_points_embeds,
)
from utils.referral_ui import (
    build_my_referrals_embed,
    EnterReferralModal,
    CreateReferralModal,
)

log = logging.getLogger("etvin")

_BOOST_MESSAGE_TYPES = {
    discord.MessageType.premium_guild_subscription,
    discord.MessageType.premium_guild_tier_1,
    discord.MessageType.premium_guild_tier_2,
    discord.MessageType.premium_guild_tier_3,
}
_AFK_LABEL_RE = re.compile(r"afk|а\s*ф\s*к", re.IGNORECASE)


def _fold_channel_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _text_looks_afk(text: str | None) -> bool:
    if not text:
        return False
    folded = _fold_channel_text(text)
    if _AFK_LABEL_RE.search(folded):
        return True
    letters = re.sub(r"[^a-zа-яё]", "", folded)
    return "afk" in letters or "афк" in letters


class ShopBuySelect(discord.ui.Select):
    def __init__(self, items: list[dict]):
        options = [
            discord.SelectOption(
                label=item["name"][:100],
                description=f"{item['cost']} баллов"[:100],
                value=item["item_key"],
            )
            for item in items[:25]
        ]
        super().__init__(
            placeholder="Выбери приз для покупки…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ShopCog")
        if not cog or not interaction.guild:
            await interaction.response.send_message("Магазин недоступен.", ephemeral=True)
            return
        await cog.process_purchase(interaction, self.values[0])


class ShopBuyView(discord.ui.View):
    def __init__(self, items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(ShopBuySelect(items))


class LiveBalanceView(discord.ui.View):
    REFRESH_SECONDS = 5
    PANEL_TIMEOUT = 300

    def __init__(self, cog: "ShopCog", guild_id: int, user_id: int):
        super().__init__(timeout=self.PANEL_TIMEOUT)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self._refresh_task: asyncio.Task | None = None

    def start_refresh(self, interaction: discord.Interaction) -> None:
        self._refresh_task = asyncio.create_task(self._refresh_loop(interaction))

    async def _refresh_loop(self, interaction: discord.Interaction) -> None:
        try:
            while True:
                await asyncio.sleep(self.REFRESH_SECONDS)
                embed = await self.cog.build_balance_embed(self.guild_id, self.user_id)
                await interaction.edit_original_response(embed=embed, view=self)
        except asyncio.CancelledError:
            pass
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()


class ShopPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💰 Баланс",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:balance",
        row=0,
    )
    async def balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        cog = interaction.client.get_cog("ShopCog")
        if not cog:
            await interaction.response.send_message("Магазин недоступен.", ephemeral=True)
            return

        embed = await cog.build_balance_embed(interaction.guild.id, interaction.user.id)
        view = LiveBalanceView(cog, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.start_refresh(interaction)

    @discord.ui.button(
        label="👥 Мои рефералы",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:referrals",
        row=0,
    )
    async def referrals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return

        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return

        embed = await build_my_referrals_embed(interaction.guild, interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="📝 Ввести рефку",
        style=discord.ButtonStyle.primary,
        custom_id="shop:enter_referral",
        row=1,
    )
    async def enter_referral_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return
        await interaction.response.send_modal(EnterReferralModal())

    @discord.ui.button(
        label="➕ Создать рефку",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:create_referral",
        row=1,
    )
    async def create_referral_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return
        await interaction.response.send_modal(CreateReferralModal())

    @discord.ui.button(
        label="📺✈️ Бонус за подписку",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:social_bonus",
        row=2,
    )
    async def social_bonus_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("SocialBonusCog")
        if not cog or not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_create_request(interaction)

    @discord.ui.button(
        label="🛒 Купить",
        style=discord.ButtonStyle.success,
        custom_id="shop:buy",
        row=2,
    )
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        items = await get_shop_items(interaction.guild.id)
        if not items:
            await interaction.response.send_message("В магазине пока нет товаров.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Выбери приз:",
            view=ShopBuyView(items),
            ephemeral=True,
        )


class ShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_sessions: dict[tuple[int, int], datetime] = {}
        self._voice_task: asyncio.Task | None = None

    def _pending_voice_seconds(self, guild_id: int, user_id: int) -> int:
        key = (guild_id, user_id)
        joined = self._voice_sessions.get(key)
        if not joined:
            return 0
        guild = self.bot.get_guild(guild_id)
        if not guild:
            self._voice_sessions.pop(key, None)
            return 0
        member = guild.get_member(user_id)
        if (
            not member
            or not member.voice
            or not member.voice.channel
            or not self._counts_voice_time(
                guild, member.voice.channel, voice_state=member.voice
            )
        ):
            self._voice_sessions.pop(key, None)
            return 0
        return int((datetime.now(timezone.utc) - joined).total_seconds())

    @staticmethod
    def _voice_seconds_left(buffer_seconds: int, need_seconds: int) -> int:
        if need_seconds <= 0:
            return 0
        remainder = buffer_seconds % need_seconds
        return need_seconds - remainder if remainder else need_seconds

    async def _sync_voice_session(self, guild_id: int, user_id: int) -> None:
        key = (guild_id, user_id)
        if key not in self._voice_sessions:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if (
            not member
            or not member.voice
            or not member.voice.channel
            or not self._counts_voice_time(
                guild, member.voice.channel, voice_state=member.voice
            )
        ):
            return
        now = datetime.now(timezone.utc)
        await self._flush_voice_session(guild_id, user_id, now, end_session=False)

    async def build_balance_embed(self, guild_id: int, user_id: int) -> discord.Embed:
        await self._sync_voice_session(guild_id, user_id)
        row = await get_shop_points(guild_id, user_id)
        rules = await get_earning_rules(guild_id)
        refs = await get_referral_count(guild_id, user_id)
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None

        voice = rules["voice"]
        words = rules["words"]
        voice_need = voice["param1"] * 60 if voice["enabled"] else 0
        voice_paused = False
        if (
            member
            and member.voice
            and member.voice.channel
            and guild
            and not self._counts_voice_time(
                guild, member.voice.channel, voice_state=member.voice
            )
        ):
            voice_paused = True

        voice_buffer = row["voice_buffer"] + self._pending_voice_seconds(guild_id, user_id)
        voice_left = self._voice_seconds_left(voice_buffer, voice_need)
        words_left = max(0, words["param1"] - row["word_buffer"]) if words["enabled"] else 0
        words_today = row.get("words_points_today", 0)
        words_cap = words["param3"] if words["enabled"] else 0

        embed = discord.Embed(title="💰 Твой баланс", color=0x000000)
        embed.add_field(name="Баллы", value=f"**{row['points']}**", inline=True)
        embed.add_field(name="Рефералы", value=f"**{refs}**", inline=True)

        referrer = await get_user_referrer(guild_id, user_id)
        if referrer and guild:
            inviter = guild.get_member(referrer["inviter_id"])
            inviter_label = inviter.mention if inviter else f"<@{referrer['inviter_id']}>"
            code_label = referrer.get("code") or "—"
            embed.add_field(
                name="Введённая рефка",
                value=f"`{code_label}` · {inviter_label}",
                inline=False,
            )

        progress = []
        if voice["enabled"]:
            progress.append(f"🎙️ ещё **{voice_left // 60}м {voice_left % 60}с** в войсе")
            if voice_paused:
                progress.append("⏸️ сейчас время **не идёт** (AFK или мут от прав)")
        if words["enabled"]:
            progress.append(f"💬 ещё **{words_left}** слов")
            cap_label = "∞" if words_cap <= 0 else str(words_cap)
            progress.append(f"📊 сегодня с слов: **{words_today}/{cap_label}** б.")
        if progress:
            embed.add_field(name="До награды", value="\n".join(progress), inline=False)
        embed.set_footer(text="Обновляется автоматически")
        return embed

    async def cog_load(self):
        self.bot.add_view(ShopPanelView())
        for row in await get_pending_redemptions():
            self.bot.add_view(OrderDecisionView(row["id"]))

        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            for channel in list(guild.voice_channels) + list(guild.stage_channels):
                if not self._counts_voice_time(guild, channel):
                    continue
                for member in channel.members:
                    if member.bot:
                        continue
                    if member.voice and self._counts_voice_time(
                        guild, channel, voice_state=member.voice
                    ):
                        self._voice_sessions[(guild.id, member.id)] = now

        self._voice_task = asyncio.create_task(self._voice_tick_loop())

    async def cog_unload(self):
        if self._voice_task:
            self._voice_task.cancel()
            try:
                await self._voice_task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def _is_afk_channel(guild: discord.Guild, channel: discord.abc.GuildChannel) -> bool:
        if guild.afk_channel and channel.id == guild.afk_channel.id:
            return True
        if _text_looks_afk(channel.name):
            return True
        category = getattr(channel, "category", None)
        if category and _text_looks_afk(category.name):
            return True
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            perms = channel.permissions_for(guild.default_role)
            if perms.connect and not perms.speak:
                return True
        return False

    @staticmethod
    def _counts_voice_time(
        guild: discord.Guild,
        channel: discord.abc.GuildChannel | None,
        *,
        voice_state: discord.VoiceState | None = None,
    ) -> bool:
        if channel is None:
            return False
        if ShopCog._is_afk_channel(guild, channel):
            return False
        if voice_state is not None and voice_state.mute:
            return False
        return True

    async def _voice_tick_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await asyncio.sleep(15)
                await self._prune_invalid_voice_sessions()
                await self._flush_all_voice_sessions()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Ошибка тика начисления войса")

    async def _prune_invalid_voice_sessions(self) -> None:
        for guild_id, user_id in list(self._voice_sessions):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                self._voice_sessions.pop((guild_id, user_id), None)
                continue
            member = guild.get_member(user_id)
            if (
                not member
                or not member.voice
                or not member.voice.channel
                or not self._counts_voice_time(
                    guild, member.voice.channel, voice_state=member.voice
                )
            ):
                self._voice_sessions.pop((guild_id, user_id), None)

    async def _flush_all_voice_sessions(self) -> None:
        now = datetime.now(timezone.utc)
        for guild_id, user_id in list(self._voice_sessions):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                self._voice_sessions.pop((guild_id, user_id), None)
                continue
            member = guild.get_member(user_id)
            if (
                not member
                or not member.voice
                or not member.voice.channel
                or not self._counts_voice_time(
                    guild, member.voice.channel, voice_state=member.voice
                )
            ):
                self._voice_sessions.pop((guild_id, user_id), None)
                continue
            await self._flush_voice_session(guild_id, user_id, now, end_session=False)

    async def _flush_voice_session(
        self,
        guild_id: int,
        user_id: int,
        now: datetime,
        *,
        end_session: bool,
    ) -> None:
        key = (guild_id, user_id)
        joined = self._voice_sessions.pop(key, None) if end_session else self._voice_sessions.get(key)
        if not joined:
            return

        seconds = int((now - joined).total_seconds())
        if seconds > 0:
            rules = await get_earning_rules(guild_id)
            if rules["voice"]["enabled"]:
                seconds_per = rules["voice"]["param1"] * 60
                points_per = rules["voice"]["param2"]
                await add_voice_seconds(
                    guild_id,
                    user_id,
                    seconds,
                    seconds_per_reward=seconds_per,
                    points_per_reward=points_per,
                )

        if end_session:
            return
        self._voice_sessions[key] = now

    async def process_purchase(self, interaction: discord.Interaction, item_key: str):
        if not interaction.guild:
            return

        items = {i["item_key"]: i for i in await get_shop_items(interaction.guild.id)}
        item = items.get(item_key)
        if not item:
            await interaction.response.send_message("Товар не найден.", ephemeral=True)
            return

        settings = await get_settings(interaction.guild.id)
        category_id = settings.get("shop_ticket_category_id")
        if not category_id:
            await interaction.response.send_message(
                "Категория тикетов не настроена. Админ: `/магазин-настройка` → **Категория тикетов**.",
                ephemeral=True,
            )
            return

        row = await get_shop_points(interaction.guild.id, interaction.user.id)
        if row["points"] < item["cost"]:
            await interaction.response.send_message(
                f"Не хватает баллов. Нужно **{item['cost']}**, у тебя **{row['points']}**.",
                ephemeral=True,
            )
            return

        if not await spend_shop_points(interaction.guild.id, interaction.user.id, item["cost"]):
            await interaction.response.send_message("Не удалось списать баллы.", ephemeral=True)
            return

        redemption_id = await create_shop_redemption(
            interaction.guild.id,
            interaction.user.id,
            item["item_key"],
            item["name"],
            item["cost"],
        )

        actions_view = OrderDecisionView(redemption_id)
        self.bot.add_view(actions_view)

        try:
            ticket_ch = await create_shop_ticket(
                interaction.guild,
                interaction.user,
                redemption_id,
                category_id=category_id,
            )
            await set_redemption_ticket_channel(redemption_id, ticket_ch.id)

            welcome = (
                f"{interaction.user.mention}, твой тикет по покупке **#{redemption_id}**.\n"
                f"Опиши детали, если нужно — админ ответит здесь.\n"
                f"Решение примут кнопками ниже."
            )
            await ticket_ch.send(welcome)

            embed = order_request_embed(
                redemption_id,
                interaction.user,
                item["name"],
                item["cost"],
                item.get("description") or "",
            )
            msg = await ticket_ch.send(embed=embed, view=actions_view)
            await set_redemption_message_id(redemption_id, msg.id)
        except (discord.HTTPException, ValueError):
            await adjust_shop_points(interaction.guild.id, interaction.user.id, item["cost"])
            await interaction.response.send_message(
                "Не удалось создать тикет. Баллы возвращены.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Тикет **#{redemption_id}** создан: {ticket_ch.mention}\n"
            f"Списано **{item['cost']}** баллов. Общайся с админом в канале.",
            ephemeral=True,
        )

    async def process_order_decision(
        self,
        interaction: discord.Interaction,
        redemption_id: int,
        *,
        accepted: bool,
    ):
        if not interaction.guild:
            return

        row = await resolve_redemption(
            redemption_id,
            status="accepted" if accepted else "rejected",
            admin_id=interaction.user.id,
        )
        if not row:
            await interaction.response.send_message(
                "Заявка уже обработана или не найдена.",
                ephemeral=True,
            )
            return

        if not accepted:
            await adjust_shop_points(row["guild_id"], row["user_id"], row["cost"])

        status_text = "✅ Принято" if accepted else "❌ Отклонено · баллы возвращены"
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed:
            embed = embed.copy()
            embed.color = discord.Color(0x57F287 if accepted else 0xED4245)
            embed.add_field(
                name="Решение",
                value=f"{status_text} — {interaction.user.mention}",
                inline=False,
            )
        await interaction.response.edit_message(embed=embed, view=None)

        ticket_ch = interaction.guild.get_channel(row.get("ticket_channel_id") or 0)
        if not isinstance(ticket_ch, discord.TextChannel) and isinstance(
            interaction.channel, discord.TextChannel
        ):
            ticket_ch = interaction.channel

        if isinstance(ticket_ch, discord.TextChannel):
            try:
                await remove_buyer_from_ticket(ticket_ch, row["user_id"])
            except discord.HTTPException:
                log.warning("Не удалось убрать покупателя из тикета #%s", redemption_id)

            footer = (
                f"{status_text} — {interaction.user.mention}\n"
                f"Покупатель убран из тикета. Канал остаётся для админов."
            )
            try:
                await ticket_ch.send(footer)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot or not member.guild:
            return

        rules = await get_earning_rules(member.guild.id)
        if not rules["voice"]["enabled"]:
            return

        earn_before = self._counts_voice_time(
            member.guild, before.channel, voice_state=before
        )
        earn_after = self._counts_voice_time(
            member.guild, after.channel, voice_state=after
        )
        key = (member.guild.id, member.id)
        now = datetime.now(timezone.utc)
        mute_changed = before.mute != after.mute

        if earn_before and (
            not earn_after or before.channel != after.channel or mute_changed
        ):
            await self._flush_voice_session(
                member.guild.id,
                member.id,
                now,
                end_session=not earn_after,
            )

        if earn_after and (
            not earn_before or before.channel != after.channel or mute_changed
        ):
            self._voice_sessions[key] = now

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.type in _BOOST_MESSAGE_TYPES:
            if await mark_boost_message_processed(message.id):
                total = (
                    int(message.content)
                    if message.content and message.content.isdigit()
                    else 1
                )
                points = await award_boost_points(
                    message.guild.id,
                    message.author.id,
                    total,
                )
                if points > 0:
                    await log_server(
                        message.guild,
                        f"**Буст сервера**\n{message.author.mention} · "
                        f"**{total}** буст(ов) · +**{points}** б.",
                    )
            return

        rules = await get_earning_rules(message.guild.id)
        if not rules["words"]["enabled"]:
            return

        now = datetime.now(timezone.utc)
        await apply_chat_message(
            message.guild.id,
            message.author.id,
            content=message.content,
            at=now.isoformat(),
            words_per_reward=rules["words"]["param1"],
            points_per_reward=rules["words"]["param2"],
            daily_cap=rules["words"]["param3"],
        )

    @app_commands.command(name="баллы", description="Список баллов участников (админ)")
    @admin_only()
    async def list_points(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        rows = await get_all_shop_points(interaction.guild.id)
        embeds = build_admin_points_embeds(interaction.guild, rows)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))
