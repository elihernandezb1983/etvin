import logging

import discord
from discord.ext import commands

from utils.views import build_welcome_embed, build_welcome_greeting, load_welcome_image
from utils.database import (
    get_settings,
    get_panel,
    get_panel_by_message,
    get_panel_role_ids,
)
from utils.discord_log import log_server

log = logging.getLogger("etvin")


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_member(self, guild: discord.Guild, user_id: int) -> discord.Member | None:
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _assign_panel_roles(self, member: discord.Member, guild: discord.Guild) -> None:
        role_ids = await get_panel_role_ids(guild.id)
        if not role_ids:
            return

        roles = [guild.get_role(rid) for rid in role_ids]
        roles = [r for r in roles if r is not None]
        if not roles:
            return

        bot_top = guild.me.top_role if guild.me else None
        to_add = []
        for role in roles:
            if role in member.roles:
                continue
            if bot_top is not None and role >= bot_top:
                log.warning(
                    "Роль %s выше роли бота — не могу выдать %s",
                    role.name,
                    member,
                )
                continue
            to_add.append(role)

        if not to_add:
            return

        try:
            await member.add_roles(*to_add, reason="Реакция на панель ролей")
            log.debug("Выданы роли %s → %s", [r.name for r in to_add], member)
            await log_server(
                guild,
                f"**Роли выданы**\n{member.mention}\n{', '.join(r.mention for r in to_add)}",
            )
        except discord.Forbidden:
            log.error("Нет прав выдать роли %s → %s", [r.name for r in to_add], member)

    async def _remove_panel_roles(self, member: discord.Member, guild: discord.Guild) -> None:
        role_ids = await get_panel_role_ids(guild.id)
        if not role_ids:
            return

        roles = [guild.get_role(rid) for rid in role_ids]
        roles = [r for r in roles if r is not None and r in member.roles]
        if not roles:
            return

        try:
            await member.remove_roles(*roles, reason="Убрал реакции с панели ролей")
            log.debug("Сняты роли %s → %s", [r.name for r in roles], member)
            await log_server(
                guild,
                f"**Роли сняты**\n{member.mention}\n{', '.join(r.mention for r in roles)}",
            )
        except discord.Forbidden:
            log.error("Нет прав снять роли %s → %s", [r.name for r in roles], member)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await log_server(
            member.guild,
            f"**Вход**\n{member.mention}\n"
            f"<t:{int(member.created_at.timestamp())}:R> · {member.guild.member_count} чел.",
        )

        settings = await get_settings(member.guild.id)
        welcome_ch_id = settings.get("welcome_channel_id")
        if not welcome_ch_id:
            return

        channel = member.guild.get_channel(welcome_ch_id)
        if not channel:
            return

        role_panel = await get_panel(member.guild.id, "roles")
        roles_channel = (
            member.guild.get_channel(role_panel["channel_id"])
            if role_panel
            else None
        )

        image_url, image_file = load_welcome_image()
        files = [image_file] if image_file else None
        embed = build_welcome_embed(member, image_url, roles_channel)
        greeting = build_welcome_greeting(member, roles_channel)

        if not image_url and not image_file:
            log.warning(
                "Приветствие без картинки для %s — проверь WELCOME_IMAGE_URL в .env",
                member,
            )

        try:
            log.debug(
                "Приветствие для %s → #%s (картинка: %s)",
                member,
                channel.name,
                image_url or (image_file.filename if image_file else "нет"),
            )
            await channel.send(content=greeting, embed=embed, files=files)
        except discord.Forbidden:
            pass
        except discord.HTTPException as exc:
            if exc.status == 413 and files:
                log.warning(
                    "Приветственное фото слишком большое — отправляю без картинки (%s)",
                    member,
                )
                embed = build_welcome_embed(member, None, roles_channel)
                try:
                    await channel.send(content=greeting, embed=embed)
                except discord.HTTPException:
                    log.exception("Не удалось отправить приветствие %s", member)
            else:
                log.warning("Ошибка приветствия для %s: %s", member, exc)

    async def _member_has_reactions_on_message(
        self,
        guild: discord.Guild,
        message_id: int,
        user_id: int,
    ) -> bool:
        channel_id = None
        panel = await get_panel_by_message(message_id)
        if panel:
            channel_id = panel["channel_id"]

        if not channel_id:
            return False

        channel = guild.get_channel(channel_id)
        if not channel:
            return False

        try:
            message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False

        for reaction in message.reactions:
            async for user in reaction.users(limit=None):
                if user.id == user_id:
                    return True
        return False

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        panel = await get_panel_by_message(payload.message_id)
        if not panel or panel["panel_type"] != "roles":
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = await self._resolve_member(guild, payload.user_id)
        if not member or member.bot:
            return

        await self._assign_panel_roles(member, guild)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        panel = await get_panel_by_message(payload.message_id)
        if not panel or panel["panel_type"] != "roles":
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = await self._resolve_member(guild, payload.user_id)
        if not member or member.bot:
            return

        if await self._member_has_reactions_on_message(guild, payload.message_id, payload.user_id):
            return

        await self._remove_panel_roles(member, guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
