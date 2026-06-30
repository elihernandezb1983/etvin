import logging

import discord
from discord.ext import commands

from config import VOICE_CHANNEL_PREFIX
from utils.database import (
    get_voice_setup,
    get_temp_voice,
    get_all_temp_voices,
    save_temp_voice,
    delete_temp_voice,
    set_temp_voice_panel_message,
)
from utils.voice_views import VoicePanelView, voice_panel_embed

log = logging.getLogger("etvin")


class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        for row in await get_all_temp_voices():
            self.bot.add_view(VoicePanelView(row["channel_id"]))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        if after.channel:
            setup = await get_voice_setup(member.guild.id)
            if setup and after.channel.id == setup["lobby_channel_id"]:
                await self._create_temp_channel(member, setup)

        if before.channel:
            await self._cleanup_if_empty(before.channel)

    async def _create_temp_channel(self, member: discord.Member, setup: dict):
        guild = member.guild
        category = guild.get_channel(setup["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            log.warning("Категория войса не найдена: %s", setup["category_id"])
            return

        try:
            channel = await guild.create_voice_channel(
                name=f"{VOICE_CHANNEL_PREFIX}{member.display_name}",
                category=category,
                reason=f"Временный войс для {member}",
            )
        except discord.HTTPException as exc:
            log.error("Не удалось создать войс: %s", exc)
            return

        await save_temp_voice(channel.id, guild.id, member.id)

        try:
            await channel.set_permissions(
                member,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                priority_speaker=True,
                mute_members=True,
                deafen_members=True,
                move_members=True,
                manage_channels=True,
                reason="Владелец временного войса",
            )
        except discord.HTTPException as exc:
            log.warning("Не удалось выдать права владельцу: %s", exc)

        try:
            await member.move_to(channel, reason="Создание личного войса")
        except discord.HTTPException as exc:
            log.error("Не удалось переместить в войс: %s", exc)
            await delete_temp_voice(channel.id)
            try:
                await channel.delete(reason="Ошибка перемещения")
            except discord.HTTPException:
                pass
            return

        self.bot.add_view(VoicePanelView(channel.id))
        await self._send_panel(channel, member)

    async def _send_panel(self, channel: discord.VoiceChannel, owner: discord.Member):
        embed = voice_panel_embed(owner)
        view = VoicePanelView(channel.id)

        try:
            msg = await channel.send(embed=embed, view=view)
            await set_temp_voice_panel_message(channel.id, msg.id)
            return
        except discord.HTTPException:
            pass

        if channel.category:
            for text_ch in channel.category.text_channels:
                try:
                    msg = await text_ch.send(
                        content=f"Панель для {channel.mention} / {owner.mention}",
                        embed=embed,
                        view=view,
                    )
                    await set_temp_voice_panel_message(channel.id, msg.id)
                    return
                except discord.HTTPException:
                    continue

        log.warning("Не удалось отправить панель для войса %s", channel.id)

    async def _cleanup_if_empty(self, channel: discord.VoiceChannel):
        temp = await get_temp_voice(channel.id)
        if not temp:
            return
        if channel.members:
            return

        await delete_temp_voice(channel.id)
        try:
            await channel.delete(reason="Временный войс пуст")
            log.info("Удалён пустой войс %s", channel.id)
        except discord.HTTPException as exc:
            log.warning("Не удалось удалить войс %s: %s", channel.id, exc)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
