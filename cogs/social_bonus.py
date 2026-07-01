import logging

import discord
from discord.ext import commands

from utils.database import (
    get_settings,
    get_earning_rules,
    has_social_bonus,
    get_pending_social_request,
    create_social_request,
    set_social_request_message,
    approve_social_request,
    reject_social_request,
    get_pending_social_requests,
    get_social_request,
)
from utils.discord_log import log_server
from utils.permissions import is_admin
from utils.shop_tickets import remove_buyer_from_ticket
from utils.social_tickets import create_social_ticket
from utils.social_ui import (
    social_request_embed,
    social_decision_view,
    social_bonus_enabled,
    default_social_bonus_points,
)
from utils.server_tag import scale_reward, user_has_server_tag

log = logging.getLogger("etvin")


class SocialBonusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        for row in await get_pending_social_requests():
            rules = await get_earning_rules(row["guild_id"])
            self.bot.add_view(
                social_decision_view(row["id"], default_social_bonus_points(rules))
            )

    async def process_create_request(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        rules = await get_earning_rules(interaction.guild.id)
        if not social_bonus_enabled(rules):
            await interaction.response.send_message(
                "Бонус за подписку отключён.",
                ephemeral=True,
            )
            return

        if await has_social_bonus(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "Ты уже получал бонус за подписку.",
                ephemeral=True,
            )
            return

        if await get_pending_social_request(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "Заявка уже на рассмотрении — жди ответа в тикете.",
                ephemeral=True,
            )
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
            ticket_ch = await create_social_ticket(
                interaction.guild,
                interaction.user,
                0,
                category_id=category_id,
            )
        except (discord.HTTPException, ValueError) as exc:
            log.warning("Не удалось создать тикет подписки: %s", exc)
            await interaction.response.send_message(
                "Не удалось создать тикет. Попробуй позже.",
                ephemeral=True,
            )
            return

        ok, msg, request_id = await create_social_request(
            interaction.guild.id,
            interaction.user.id,
            ticket_channel_id=ticket_ch.id,
        )
        if not ok or request_id is None:
            try:
                await ticket_ch.delete(reason="Заявка на бонус не создана")
            except discord.HTTPException:
                pass
            await interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            await ticket_ch.edit(
                name=f"подписка-{interaction.user.display_name[:20]}-{request_id}".lower()
            )
        except discord.HTTPException:
            pass

        default_points = default_social_bonus_points(rules)
        decision_view = social_decision_view(request_id, default_points)
        self.bot.add_view(decision_view)

        welcome = (
            f"{interaction.user.mention}, заявка на бонус за подписку **Twitch / Telegram**.\n"
            f"Приложи скриншот подписки — админ проверит и начислит баллы."
        )
        await ticket_ch.send(welcome)
        embed = social_request_embed(request_id, interaction.user)
        ticket_msg = await ticket_ch.send(embed=embed, view=decision_view)
        await set_social_request_message(request_id, ticket_msg.id)

        await interaction.response.send_message(
            f"✅ Заявка **#{request_id}** создана: {ticket_ch.mention}\n"
            f"Подпишись на **Twitch** или **Telegram** и приложи скрин в тикет.",
            ephemeral=True,
        )

    async def process_approve(
        self,
        interaction: discord.Interaction,
        request_id: int,
        points: int,
    ) -> None:
        if not interaction.guild:
            return
        if not await is_admin(interaction):
            await interaction.response.send_message("Только для админов.", ephemeral=True)
            return

        req_preview = await get_social_request(request_id)
        if not req_preview:
            await interaction.response.send_message("Заявка не найдена.", ephemeral=True)
            return

        member = interaction.guild.get_member(req_preview["user_id"])
        if member is None:
            try:
                member = await interaction.guild.fetch_member(req_preview["user_id"])
            except discord.HTTPException:
                member = None

        has_tag = bool(member and user_has_server_tag(member, interaction.guild.id))
        final_points = scale_reward(points, has_tag)

        ok, msg, req = await approve_social_request(
            request_id,
            admin_id=interaction.user.id,
            points=final_points,
        )
        if not ok or not req:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        ticket_ch = interaction.guild.get_channel(req.get("ticket_channel_id") or 0)
        ticket_msg = None
        if isinstance(ticket_ch, discord.TextChannel) and req.get("message_id"):
            try:
                ticket_msg = await ticket_ch.fetch_message(req["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        embed = ticket_msg.embeds[0].copy() if ticket_msg and ticket_msg.embeds else None
        if embed:
            embed.color = discord.Color(0x000000)
            embed.add_field(
                name="Решение",
                value=f"✅ Принято — +**{final_points}** б. · {interaction.user.mention}",
                inline=False,
            )

        if ticket_msg:
            await interaction.response.defer(ephemeral=True)
            await ticket_msg.edit(embed=embed, view=None)
        else:
            await interaction.response.send_message(
                f"✅ Заявка одобрена — +**{final_points}** б.",
                ephemeral=True,
            )

        if isinstance(ticket_ch, discord.TextChannel):
            try:
                await remove_buyer_from_ticket(ticket_ch, req["user_id"])
                await ticket_ch.send(
                    f"✅ Заявка одобрена — +**{final_points}** б. · {interaction.user.mention}"
                )
            except discord.HTTPException:
                pass

        member = interaction.guild.get_member(req["user_id"])
        member_label = member.mention if member else f"<@{req['user_id']}>"
        await log_server(
            interaction.guild,
            f"**Бонус за подписку** #{request_id}\n"
            f"{member_label} · +**{final_points}** б.\n"
            f"{interaction.user.mention}",
        )

    async def process_reject(self, interaction: discord.Interaction, request_id: int) -> None:
        if not interaction.guild:
            return
        if not await is_admin(interaction):
            await interaction.response.send_message("Только для админов.", ephemeral=True)
            return

        ok, msg, req = await reject_social_request(
            request_id,
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
                value=f"❌ Отказано — {interaction.user.mention}",
                inline=False,
            )
        await interaction.response.edit_message(embed=embed, view=None)

        ticket_ch = interaction.guild.get_channel(req.get("ticket_channel_id") or 0)
        if isinstance(ticket_ch, discord.TextChannel):
            try:
                await ticket_ch.send(f"❌ Заявка отклонена — {interaction.user.mention}")
            except discord.HTTPException:
                pass

        member = interaction.guild.get_member(req["user_id"])
        member_label = member.mention if member else f"<@{req['user_id']}>"
        await log_server(
            interaction.guild,
            f"**Бонус за подписку отклонён** #{request_id}\n"
            f"{member_label}\n"
            f"{interaction.user.mention}",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialBonusCog(bot))
