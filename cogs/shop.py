import logging
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.database import (
    get_shop_points,
    get_shop_items,
    get_settings,
    get_earning_rules,
    add_voice_seconds,
    add_message_words,
    adjust_shop_points,
    spend_shop_points,
    get_or_create_referral_code,
    get_referral_invite_code,
    set_referral_invite_code,
    get_referral_inviter_by_invite,
    register_referral,
    referral_already_used,
    get_referral_count,
    create_shop_redemption,
    set_redemption_message_id,
    set_redemption_ticket_channel,
    resolve_redemption,
    get_pending_redemptions,
    update_message_meta,
)
from utils.discord_log import log_server
from utils.shop_tickets import create_shop_ticket, remove_buyer_from_ticket
from utils.shop_ui import (
    order_request_embed,
    verdict_dm_view,
    OrderDecisionView,
    CloseTicketView,
)

log = logging.getLogger("etvin")
_WORD_RE = re.compile(r"\S+")


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


class ShopPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💰 Баланс",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:balance",
    )
    async def balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        embed = await _balance_embed(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="👥 Мои рефералы",
        style=discord.ButtonStyle.secondary,
        custom_id="shop:referrals",
    )
    async def referrals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return
        cog = interaction.client.get_cog("ShopCog")
        if not cog:
            await interaction.response.send_message("Магазин недоступен.", ephemeral=True)
            return

        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return

        ref_pts = rules["referral"]["param1"]
        refs = await get_referral_count(interaction.guild.id, interaction.user.id)
        earned = refs * ref_pts

        invite = await cog.get_or_create_referral_invite(interaction.guild, interaction.user.id)
        if not invite:
            await interaction.response.send_message(
                "Не удалось создать реферальную ссылку. "
                "Нужны права **Создавать приглашения** и настроенный канал.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="👥 Мои рефералы", color=0x000000)
        embed.add_field(name="Ссылка", value=invite.url, inline=False)
        embed.add_field(name="Приглашено", value=f"**{refs}** чел.", inline=True)
        embed.add_field(name="Заработано", value=f"**{earned}** баллов", inline=True)
        embed.add_field(
            name="Награда",
            value=f"**{ref_pts}** баллов за каждого друга по ссылке",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="🛒 Купить",
        style=discord.ButtonStyle.success,
        custom_id="shop:buy",
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


async def _balance_embed(guild_id: int, user_id: int) -> discord.Embed:
    row = await get_shop_points(guild_id, user_id)
    rules = await get_earning_rules(guild_id)
    refs = await get_referral_count(guild_id, user_id)

    voice = rules["voice"]
    words = rules["words"]
    voice_need = voice["param1"] * 60 if voice["enabled"] else 0
    voice_left = max(0, voice_need - row["voice_buffer"]) if voice_need else 0
    words_left = max(0, words["param1"] - row["word_buffer"]) if words["enabled"] else 0
    words_today = row.get("words_points_today", 0)
    words_cap = words["param3"] if words["enabled"] else 0

    embed = discord.Embed(title="💰 Твой баланс", color=0x000000)
    embed.add_field(name="Баллы", value=f"**{row['points']}**", inline=True)
    embed.add_field(name="Рефералы", value=f"**{refs}**", inline=True)
    progress = []
    if voice["enabled"]:
        progress.append(f"🎙️ ещё **{voice_left // 60}м {voice_left % 60}с** в войсе")
    if words["enabled"]:
        progress.append(f"💬 ещё **{words_left}** слов")
        progress.append(f"📊 сегодня с слов: **{words_today}/{words_cap}** б.")
    if progress:
        embed.add_field(name="До награды", value="\n".join(progress), inline=False)
    return embed


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _effective_words(
    content: str,
    last_content: str | None,
    last_at: str | None,
    now: datetime,
) -> int:
    words = _WORD_RE.findall(content)
    if len(words) < 2:
        return 0

    if last_content and content.strip().lower() == last_content.strip().lower():
        return 0

    if last_at:
        try:
            prev = datetime.fromisoformat(last_at)
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            delta = (now - prev).total_seconds()
            if delta < 1:
                return 0
            if delta < 3 and len(words) < 8:
                return 0
        except ValueError:
            pass

    lowered = [w.lower() for w in words]
    if len(set(lowered)) == 1 and len(lowered) >= 3:
        return 0

    unique_ratio = len(set(lowered)) / len(lowered)
    if unique_ratio < 0.35:
        return max(0, int(len(words) * 0.25))

    compact = content.replace(" ", "")
    if len(compact) > 5 and len(set(compact)) <= 2:
        return 0

    return len(words)


class ShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_sessions: dict[tuple[int, int], datetime] = {}
        self._invite_cache: dict[int, dict[str, int]] = {}

    async def cog_load(self):
        self.bot.add_view(ShopPanelView())
        for row in await get_pending_redemptions():
            self.bot.add_view(OrderDecisionView(row["id"]))

        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            await self._refresh_invite_cache(guild)
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        self._voice_sessions[(guild.id, member.id)] = now

    async def _refresh_invite_cache(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
            self._invite_cache[guild.id] = {i.code: i.uses or 0 for i in invites}
        except discord.Forbidden:
            self._invite_cache[guild.id] = {}
        except discord.HTTPException as exc:
            log.warning("Не удалось обновить инвайты на %s: %s", guild.id, exc)

    async def _resolve_invite_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await get_settings(guild.id)
        ch_id = settings.get("welcome_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                perms = ch.permissions_for(guild.me)
                if perms.create_instant_invite:
                    return ch

        if guild.system_channel:
            perms = guild.system_channel.permissions_for(guild.me)
            if perms.create_instant_invite:
                return guild.system_channel

        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).create_instant_invite:
                return ch
        return None

    async def get_or_create_referral_invite(
        self,
        guild: discord.Guild,
        user_id: int,
    ) -> discord.Invite | None:
        stored_code = await get_referral_invite_code(guild.id, user_id)
        if stored_code:
            try:
                invites = await guild.invites()
            except (discord.Forbidden, discord.HTTPException):
                invites = []
            for inv in invites:
                if inv.code == stored_code:
                    return inv

        channel = await self._resolve_invite_channel(guild)
        if not channel:
            return None

        await get_or_create_referral_code(guild.id, user_id)
        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=True,
                reason=f"Реферальная ссылка пользователя {user_id}",
            )
        except discord.HTTPException as exc:
            log.warning("Не удалось создать инвайт для %s: %s", user_id, exc)
            return None

        await set_referral_invite_code(guild.id, user_id, invite.code)
        cache = self._invite_cache.setdefault(guild.id, {})
        cache[invite.code] = invite.uses or 0
        return invite

    async def _process_referral_join(self, member: discord.Member) -> None:
        guild = member.guild
        rules = await get_earning_rules(guild.id)
        if not rules["referral"]["enabled"]:
            return

        if await referral_already_used(guild.id, member.id):
            return

        before = dict(self._invite_cache.get(guild.id, {}))
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            return
        except discord.HTTPException as exc:
            log.warning("Не удалось получить инвайты при входе %s: %s", member.id, exc)
            return

        used_code: str | None = None
        for invite in invites:
            old = before.get(invite.code, 0)
            new = invite.uses or 0
            if new > old:
                used_code = invite.code
                break

        self._invite_cache[guild.id] = {i.code: (i.uses or 0) for i in invites}
        if not used_code:
            return

        inviter_id = await get_referral_inviter_by_invite(guild.id, used_code)
        if not inviter_id or inviter_id == member.id:
            return

        if not await register_referral(guild.id, inviter_id, member.id):
            return

        ref_pts = rules["referral"]["param1"]
        inviter_total = await adjust_shop_points(guild.id, inviter_id, ref_pts)
        inviter = guild.get_member(inviter_id)
        inviter_str = inviter.mention if inviter else f"<@{inviter_id}>"

        await log_server(
            guild,
            f"**Реферал**\n{inviter_str} ← {member.mention}\n"
            f"+**{ref_pts}** (всего **{inviter_total}**)",
        )

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

        user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
        dm_view = verdict_dm_view(
            accepted=accepted,
            prize_name=row["prize_name"],
            cost=row["cost"],
        )
        try:
            await user.send(view=dm_view)
        except discord.HTTPException:
            log.warning("Не удалось отправить ЛС пользователю %s", row["user_id"])

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

            close_view = CloseTicketView(redemption_id)
            self.bot.add_view(close_view)
            footer = (
                f"{status_text} — {interaction.user.mention}\n"
                f"Покупатель убран из тикета. Админ может закрыть канал кнопкой ниже."
            )
            try:
                await ticket_ch.send(footer, view=close_view)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self._process_referral_join(member)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if not invite.guild:
            return
        cache = self._invite_cache.setdefault(invite.guild.id, {})
        cache[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if not invite.guild:
            return
        cache = self._invite_cache.get(invite.guild.id)
        if cache:
            cache.pop(invite.code, None)

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

        seconds_per = rules["voice"]["param1"] * 60
        points_per = rules["voice"]["param2"]
        key = (member.guild.id, member.id)
        now = datetime.now(timezone.utc)

        if before.channel is None and after.channel is not None:
            self._voice_sessions[key] = now
            return

        if before.channel is not None and after.channel is None:
            joined = self._voice_sessions.pop(key, None)
            if joined:
                seconds = int((now - joined).total_seconds())
                if seconds > 0:
                    await add_voice_seconds(
                        member.guild.id,
                        member.id,
                        seconds,
                        seconds_per_reward=seconds_per,
                        points_per_reward=points_per,
                    )
            return

        if before.channel != after.channel and after.channel is not None:
            joined = self._voice_sessions.get(key)
            if joined:
                seconds = int((now - joined).total_seconds())
                if seconds > 0:
                    await add_voice_seconds(
                        member.guild.id,
                        member.id,
                        seconds,
                        seconds_per_reward=seconds_per,
                        points_per_reward=points_per,
                    )
            self._voice_sessions[key] = now

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        rules = await get_earning_rules(message.guild.id)
        if not rules["words"]["enabled"]:
            return

        row = await get_shop_points(message.guild.id, message.author.id)
        now = datetime.now(timezone.utc)
        words = _effective_words(
            message.content,
            row.get("last_message_content"),
            row.get("last_message_at"),
            now,
        )
        await update_message_meta(
            message.guild.id,
            message.author.id,
            content=message.content,
            at=now.isoformat(),
        )
        if words <= 0:
            return

        await add_message_words(
            message.guild.id,
            message.author.id,
            words,
            words_per_reward=rules["words"]["param1"],
            points_per_reward=rules["words"]["param2"],
            daily_cap=rules["words"]["param3"],
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))
