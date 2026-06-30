import asyncio
import logging

import discord
from discord.ext import commands

from utils.discord_log import log_server

log = logging.getLogger("etvin")


async def _audit_entry(
    guild: discord.Guild,
    target_id: int,
    *actions: discord.AuditLogAction,
    max_age: float = 5.0,
) -> discord.AuditLogEntry | None:
    try:
        async for entry in guild.audit_logs(limit=8):
            if entry.target is None or entry.target.id != target_id:
                continue
            if actions and entry.action not in actions:
                continue
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > max_age:
                continue
            return entry
    except discord.Forbidden:
        log.debug("Нет доступа к audit log на сервере %s", guild.id)
    except discord.HTTPException as exc:
        log.warning("Ошибка audit log: %s", exc)
    return None


def _actor(entry: discord.AuditLogEntry | None) -> str:
    if entry and entry.user:
        return entry.user.mention
    return "—"


def _reason(entry: discord.AuditLogEntry | None) -> str:
    if entry and entry.reason:
        return f"`{entry.reason}`"
    return ""


class ModerationLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        await asyncio.sleep(0.5)
        entry = await _audit_entry(guild, user.id, discord.AuditLogAction.ban)
        body = f"**Бан**\n{_actor(entry)} → {user.mention}"
        if reason := _reason(entry):
            body += f"\n{reason}"
        await log_server(guild, body)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await asyncio.sleep(0.5)
        entry = await _audit_entry(guild, user.id, discord.AuditLogAction.unban)
        body = f"**Разбан**\n{_actor(entry)} → {user.mention}"
        if reason := _reason(entry):
            body += f"\n{reason}"
        await log_server(guild, body)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.timed_out_until == after.timed_out_until:
            return

        await asyncio.sleep(0.5)
        entry = await _audit_entry(
            after.guild,
            after.id,
            discord.AuditLogAction.member_update,
        )

        if after.timed_out_until and (
            not before.timed_out_until or after.timed_out_until > before.timed_out_until
        ):
            until = f"<t:{int(after.timed_out_until.timestamp())}:R>"
            body = f"**Таймаут**\n{_actor(entry)} → {after.mention}\nдо {until}"
            if reason := _reason(entry):
                body += f"\n{reason}"
            await log_server(after.guild, body)
        elif before.timed_out_until and not after.timed_out_until:
            body = f"**Таймаут снят**\n{_actor(entry)} → {after.mention}"
            if reason := _reason(entry):
                body += f"\n{reason}"
            await log_server(after.guild, body)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await asyncio.sleep(0.7)

        kick = await _audit_entry(member.guild, member.id, discord.AuditLogAction.kick)
        if kick:
            body = f"**Кик**\n{_actor(kick)} → {member.mention}"
            if reason := _reason(kick):
                body += f"\n{reason}"
            await log_server(member.guild, body)
            return

        ban = await _audit_entry(member.guild, member.id, discord.AuditLogAction.ban)
        if ban:
            return

        roles = ", ".join(r.mention for r in member.roles if r != member.guild.default_role)
        joined = (
            f"был <t:{int(member.joined_at.timestamp())}:R>"
            if member.joined_at
            else "—"
        )
        body = f"**Выход**\n{member.mention}\n{joined}"
        if roles:
            body += f"\n{roles}"
        await log_server(member.guild, body)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        guild = member.guild

        if before.channel != after.channel:
            if before.channel and after.channel:
                body = (
                    f"**Переход**\n{member.mention}\n"
                    f"{before.channel.mention} → {after.channel.mention}"
                )
            elif after.channel:
                body = f"**Вошёл в войс**\n{member.mention}\n{after.channel.mention}"
            else:
                body = f"**Вышел из войса**\n{member.mention}\n{before.channel.mention}"
            await log_server(guild, body)

        if before.mute != after.mute:
            await asyncio.sleep(0.5)
            entry = await _audit_entry(
                guild,
                member.id,
                discord.AuditLogAction.member_update,
            )
            title = "Мут" if after.mute else "Размут"
            channel = after.channel or before.channel
            ch = channel.mention if channel else "—"
            body = f"**{title}**\n{_actor(entry)} → {member.mention}\n{ch}"
            await log_server(guild, body)

        if before.deaf != after.deaf:
            await asyncio.sleep(0.5)
            entry = await _audit_entry(
                guild,
                member.id,
                discord.AuditLogAction.member_update,
            )
            title = "Глушение" if after.deaf else "Снято глушение"
            channel = after.channel or before.channel
            ch = channel.mention if channel else "—"
            body = f"**{title}**\n{_actor(entry)} → {member.mention}\n{ch}"
            await log_server(guild, body)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationLogCog(bot))
