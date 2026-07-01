import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.database import (
    get_settings,
    get_earning_rules,
    create_referral_request,
    set_referral_request_message,
    resolve_referral_request,
    apply_referral_code,
    admin_set_referral_code,
    admin_delete_referral_code,
    get_pending_referral_requests,
    normalize_referral_code,
    validate_referral_request,
    get_panel,
    get_all_referral_codes,
)
from utils.discord_log import log_server
from utils.permissions import admin_only, is_admin
from utils.referral_tickets import create_referral_ticket
from utils.referral_ui import (
    referral_request_embed,
    referral_decision_view,
    EnterReferralModal,
    CreateReferralModal,
    ReferralAdminView,
    build_my_referrals_embed,
    build_leaderboard_embed,
    build_all_referrals_embeds,
    LEADERBOARD_PANEL_TYPES,
)
from utils.squad import ensure_members_cached
from utils.shop_tickets import remove_buyer_from_ticket

log = logging.getLogger("etvin")


class ReferralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_leaderboards.start()

    def cog_unload(self):
        self.refresh_leaderboards.cancel()

    async def cog_load(self):
        for row in await get_pending_referral_requests():
            self.bot.add_view(referral_decision_view(row["id"]))

    @tasks.loop(minutes=max(1, config.LEADERBOARD_REFRESH_MINUTES))
    async def refresh_leaderboards(self):
        for guild in self.bot.guilds:
            for panel_type in LEADERBOARD_PANEL_TYPES:
                panel = await get_panel(guild.id, panel_type)
                if not panel:
                    continue
                channel = guild.get_channel(panel["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    continue
                embed = await build_leaderboard_embed(guild, panel_type)
                if not embed:
                    continue
                try:
                    message = await channel.fetch_message(panel["message_id"])
                    await message.edit(embed=embed, view=None)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

    @refresh_leaderboards.before_loop
    async def before_refresh_leaderboards(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            asyncio.create_task(ensure_members_cached(guild, timeout=30.0))

    async def process_enter_code(self, interaction: discord.Interaction, code: str) -> None:
        if not interaction.guild:
            return
        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return

        ok, msg, inviter_id = await apply_referral_code(
            interaction.guild.id,
            interaction.user.id,
            code,
            inviter_points=rules["referral"]["param1"],
            invitee_points=rules["referral"]["param3"],
        )
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        inviter = interaction.guild.get_member(inviter_id) if inviter_id else None
        inviter_str = inviter.mention if inviter else f"<@{inviter_id}>"
        await interaction.response.send_message(msg, ephemeral=True)
        await log_server(
            interaction.guild,
            f"**Реферал (код)**\n{interaction.user.mention} ввёл **`{normalize_referral_code(code)}`**\n"
            f"Владелец: {inviter_str}",
        )

    async def process_create_request(self, interaction: discord.Interaction, code: str) -> None:
        if not interaction.guild:
            return
        rules = await get_earning_rules(interaction.guild.id)
        if not rules["referral"]["enabled"]:
            await interaction.response.send_message("Рефералы отключены.", ephemeral=True)
            return

        normalized = normalize_referral_code(code)
        ok, msg, _ = await validate_referral_request(
            interaction.guild.id,
            interaction.user.id,
            normalized,
        )
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        settings = await get_settings(interaction.guild.id)
        category_id = settings.get("shop_ticket_category_id")
        if not category_id:
            await interaction.response.send_message(
                "Категория тикетов не настроена. Админ: `/магазин-настройка` → **Категория тикетов**.",
                ephemeral=True,
            )
            return

        try:
            ticket_ch = await create_referral_ticket(
                interaction.guild,
                interaction.user,
                0,
                category_id=category_id,
            )
        except (discord.HTTPException, ValueError) as exc:
            log.warning("Не удалось создать тикет рефки: %s", exc)
            await interaction.response.send_message(
                "Не удалось создать тикет. Попробуй позже.",
                ephemeral=True,
            )
            return

        ok, msg, request_id = await create_referral_request(
            interaction.guild.id,
            interaction.user.id,
            normalized,
            ticket_channel_id=ticket_ch.id,
        )
        if not ok or request_id is None:
            try:
                await ticket_ch.delete(reason="Заявка на рефку не создана")
            except discord.HTTPException:
                pass
            await interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            await ticket_ch.edit(name=f"рефка-{interaction.user.display_name[:20]}-{request_id}".lower())
        except discord.HTTPException:
            pass

        decision_view = referral_decision_view(request_id)
        self.bot.add_view(decision_view)

        welcome = (
            f"{interaction.user.mention}, заявка на рефку **`{normalized}`**.\n"
            f"Опиши, если нужно что-то уточнить — админ ответит здесь.\n"
            f"Решение примут кнопками ниже."
        )
        await ticket_ch.send(welcome)
        embed = referral_request_embed(request_id, interaction.user, normalized)
        msg = await ticket_ch.send(embed=embed, view=decision_view)
        await set_referral_request_message(request_id, msg.id)

        await interaction.response.send_message(
            f"✅ Заявка **#{request_id}** создана: {ticket_ch.mention}\n"
            f"Код **`{normalized}`** ждёт одобрения админа.",
            ephemeral=True,
        )

    async def process_approve(self, interaction: discord.Interaction, request_id: int) -> None:
        if not interaction.guild:
            return
        if not await is_admin(interaction):
            await interaction.response.send_message("Только для админов.", ephemeral=True)
            return

        ok, msg, req = await resolve_referral_request(
            request_id,
            approved=True,
            admin_id=interaction.user.id,
        )
        if not ok or not req:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = interaction.message.embeds[0].copy() if interaction.message and interaction.message.embeds else None
        if embed:
            embed.color = discord.Color(0x000000)
            embed.add_field(
                name="Решение",
                value=f"✅ Одобрено — {interaction.user.mention}",
                inline=False,
            )
        await interaction.response.edit_message(embed=embed, view=None)

        member = interaction.guild.get_member(req["user_id"])

        ticket_ch = interaction.guild.get_channel(req.get("ticket_channel_id") or 0)
        if isinstance(ticket_ch, discord.TextChannel):
            try:
                await remove_buyer_from_ticket(ticket_ch, req["user_id"])
                await ticket_ch.send(
                    f"✅ Код **`{req['requested_code']}`** одобрен — {interaction.user.mention}"
                )
            except discord.HTTPException:
                pass

        await log_server(
            interaction.guild,
            f"**Рефка одобрена** #{request_id}\n"
            f"Код: **`{req['requested_code']}`** · {member.mention if member else req['user_id']}\n"
            f"{interaction.user.mention}",
        )

    async def process_reject(self, interaction: discord.Interaction, request_id: int) -> None:
        if not interaction.guild:
            return
        if not await is_admin(interaction):
            await interaction.response.send_message("Только для админов.", ephemeral=True)
            return

        ok, msg, req = await resolve_referral_request(
            request_id,
            approved=False,
            admin_id=interaction.user.id,
        )
        if not ok or not req:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = interaction.message.embeds[0].copy() if interaction.message and interaction.message.embeds else None
        if embed:
            embed.color = discord.Color(0x000000)
            embed.add_field(
                name="Решение",
                value=f"❌ Отклонено — {interaction.user.mention}",
                inline=False,
            )
        await interaction.response.edit_message(embed=embed, view=None)

        ticket_ch = interaction.guild.get_channel(req.get("ticket_channel_id") or 0)
        if isinstance(ticket_ch, discord.TextChannel):
            try:
                await ticket_ch.send(f"❌ Заявка отклонена — {interaction.user.mention}")
            except discord.HTTPException:
                pass

    async def process_admin_set(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        code: str,
    ) -> None:
        if not interaction.guild:
            return
        ok, msg = await admin_set_referral_code(interaction.guild.id, member.id, code)
        await interaction.response.send_message(msg, ephemeral=True)
        if ok:
            await log_server(
                interaction.guild,
                f"**Рефка выдана**\n{interaction.user.mention} → {member.mention}\n{msg}",
            )

    async def process_admin_delete(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not interaction.guild:
            return
        ok, msg = await admin_delete_referral_code(interaction.guild.id, member.id)
        await interaction.response.send_message(msg, ephemeral=True)
        if ok:
            await log_server(
                interaction.guild,
                f"**Рефка удалена**\n{interaction.user.mention} → {member.mention}\n{msg}",
            )

    @app_commands.command(name="реферал-настройка", description="Управление реферальными кодами")
    @admin_only()
    async def referral_setup(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        embed = discord.Embed(
            title="👥 Реферальные коды",
            description=(
                "Выбери участника — можно **выдать** или **удалить** код.\n\n"
                "Заявки на создание кода приходят в тикеты (как покупки в магазине)."
            ),
            color=discord.Color(0x000000),
        )
        await interaction.response.send_message(embed=embed, view=ReferralAdminView(), ephemeral=True)

    @app_commands.command(name="рефки", description="Список всех реферальных кодов на сервере")
    @admin_only()
    async def list_referrals(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        rows = await get_all_referral_codes(interaction.guild.id)
        embeds = build_all_referrals_embeds(interaction.guild, rows)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReferralCog(bot))
