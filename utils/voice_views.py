import discord

from config import BLACK, VOICE_PANEL_TEXT, VOICE_GUIDE_TEXT
from utils.database import (
    get_temp_voice,
    set_temp_voice_owner,
    set_temp_voice_locked,
)


RTC_REGIONS = [
    ("auto", "Авто", None),
    ("us-west", "US West", "us-west"),
    ("us-east", "US East", "us-east"),
    ("us-central", "US Central", "us-central"),
    ("us-south", "US South", "us-south"),
    ("rotterdam", "Rotterdam", "rotterdam"),
    ("brazil", "Brazil", "brazil"),
    ("singapore", "Singapore", "singapore"),
    ("japan", "Japan", "japan"),
    ("hongkong", "Hong Kong", "hongkong"),
    ("sydney", "Sydney", "sydney"),
    ("southafrica", "South Africa", "southafrica"),
]


def voice_panel_embed(owner: discord.Member) -> discord.Embed:
    return discord.Embed(
        title="Панель управления",
        description=VOICE_PANEL_TEXT.format(owner=owner.mention),
        color=discord.Color(BLACK),
    )


async def _owner_only(interaction: discord.Interaction, channel_id: int) -> dict | None:
    temp = await get_temp_voice(channel_id)
    if not temp:
        await interaction.response.send_message("Комната не найдена.", ephemeral=True)
        return None
    if interaction.user.id != temp["owner_id"]:
        await interaction.response.send_message(
            "Только владелец может управлять комнатой.",
            ephemeral=True,
        )
        return None
    return temp


def _voice_channel(interaction: discord.Interaction, channel_id: int) -> discord.VoiceChannel | None:
    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        return None
    return channel


class NameModal(discord.ui.Modal, title="Название комнаты"):
    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.name_input = discord.ui.TextInput(
            label="Название",
            placeholder="Моя комната",
            max_length=100,
            required=True,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        channel = _voice_channel(interaction, self.channel_id)
        if not channel:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        await channel.edit(name=self.name_input.value)
        await interaction.response.send_message("✅ Название изменено.", ephemeral=True)


class LimitModal(discord.ui.Modal, title="Лимит участников"):
    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.limit_input = discord.ui.TextInput(
            label="Лимит (0 = без лимита)",
            placeholder="0",
            max_length=2,
            required=True,
        )
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        try:
            limit = int(self.limit_input.value)
        except ValueError:
            return await interaction.response.send_message(
                "Введи число от 0 до 99.",
                ephemeral=True,
            )
        if limit < 0 or limit > 99:
            return await interaction.response.send_message(
                "Лимит должен быть от 0 до 99.",
                ephemeral=True,
            )
        channel = _voice_channel(interaction, self.channel_id)
        if not channel:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        await channel.edit(user_limit=limit)
        await interaction.response.send_message(
            f"✅ Лимит установлен: {limit if limit else 'без лимита'}.",
            ephemeral=True,
        )


class RegionSelect(discord.ui.Select):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        options = [
            discord.SelectOption(label=label, value=value)
            for value, label, _ in RTC_REGIONS
        ]
        super().__init__(
            placeholder="Выбери регион",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        channel = _voice_channel(interaction, self.channel_id)
        if not channel:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)
        region = next((r for v, _, r in RTC_REGIONS if v == self.values[0]), None)
        await channel.edit(rtc_region=region)
        label = next((l for v, l, _ in RTC_REGIONS if v == self.values[0]), self.values[0])
        await interaction.response.send_message(f"✅ Регион: **{label}**.", ephemeral=True)


class RegionView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=60)
        self.add_item(RegionSelect(channel_id))


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, channel_id: int, action: str):
        self.channel_id = channel_id
        self.action = action
        placeholders = {
            "kick": "Кого кикнуть?",
            "transfer": "Кому передать владение?",
            "friend": "Кого добавить в друзья?",
            "ban": "Кого забанить?",
        }
        super().__init__(
            placeholder=placeholders[action],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        channel = _voice_channel(interaction, self.channel_id)
        if not channel:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)

        target = self.values[0]
        if target.bot:
            return await interaction.response.send_message("Нельзя выбрать бота.", ephemeral=True)
        if target.id == interaction.user.id and self.action != "transfer":
            return await interaction.response.send_message("Нельзя выбрать себя.", ephemeral=True)

        if self.action == "kick":
            member = channel.guild.get_member(target.id)
            if not member or member.voice is None or member.voice.channel != channel:
                return await interaction.response.send_message(
                    "Пользователь не в этой комнате.",
                    ephemeral=True,
                )
            try:
                await member.move_to(None, reason="Кик с временного войса")
            except discord.HTTPException:
                return await interaction.response.send_message("Не удалось кикнуть.", ephemeral=True)
            await interaction.response.send_message(f"✅ {target.mention} кикнут.", ephemeral=True)

        elif self.action == "transfer":
            member = channel.guild.get_member(target.id)
            if not member or member.voice is None or member.voice.channel != channel:
                return await interaction.response.send_message(
                    "Пользователь должен быть в комнате.",
                    ephemeral=True,
                )
            await set_temp_voice_owner(self.channel_id, target.id)
            await channel.set_permissions(
                interaction.user,
                overwrite=None,
                reason="Передача владения",
            )
            await channel.set_permissions(
                target,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                priority_speaker=True,
                mute_members=True,
                deafen_members=True,
                move_members=True,
                manage_channels=True,
                reason="Новый владелец временного войса",
            )
            await interaction.response.send_message(
                f"✅ Владение передано {target.mention}.",
                ephemeral=True,
            )

        elif self.action == "friend":
            await channel.set_permissions(
                target,
                connect=True,
                view_channel=True,
                reason="Друг в временном войсе",
            )
            await interaction.response.send_message(
                f"✅ {target.mention} может заходить в комнату.",
                ephemeral=True,
            )

        elif self.action == "ban":
            await channel.set_permissions(
                target,
                connect=False,
                view_channel=True,
                reason="Бан в временном войсе",
            )
            member = channel.guild.get_member(target.id)
            if member and member.voice and member.voice.channel == channel:
                try:
                    await member.move_to(None, reason="Бан с временного войса")
                except discord.HTTPException:
                    pass
            await interaction.response.send_message(
                f"✅ {target.mention} забанен в комнате.",
                ephemeral=True,
            )


class MemberActionView(discord.ui.View):
    def __init__(self, channel_id: int, action: str):
        super().__init__(timeout=60)
        self.add_item(MemberSelect(channel_id, action))


class VoicePanelView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

        name_btn = discord.ui.Button(
            label="Название",
            emoji="🔤",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:name:{channel_id}",
            row=0,
        )
        name_btn.callback = self._name_callback
        self.add_item(name_btn)

        limit_btn = discord.ui.Button(
            label="Лимит",
            emoji="👤",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:limit:{channel_id}",
            row=0,
        )
        limit_btn.callback = self._limit_callback
        self.add_item(limit_btn)

        region_btn = discord.ui.Button(
            label="Регион",
            emoji="🌐",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:region:{channel_id}",
            row=0,
        )
        region_btn.callback = self._region_callback
        self.add_item(region_btn)

        kick_btn = discord.ui.Button(
            label="Кикнуть",
            emoji="👢",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:kick:{channel_id}",
            row=1,
        )
        kick_btn.callback = self._kick_callback
        self.add_item(kick_btn)

        guide_btn = discord.ui.Button(
            label="Гайд",
            emoji="ℹ️",
            style=discord.ButtonStyle.primary,
            custom_id=f"vc:guide:{channel_id}",
            row=1,
        )
        guide_btn.callback = self._guide_callback
        self.add_item(guide_btn)

        lock_btn = discord.ui.Button(
            label="Прихожая",
            emoji="🚪",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:lock:{channel_id}",
            row=2,
        )
        lock_btn.callback = self._lock_callback
        self.add_item(lock_btn)

        transfer_btn = discord.ui.Button(
            label="Забрать",
            emoji="⭐",
            style=discord.ButtonStyle.secondary,
            custom_id=f"vc:transfer:{channel_id}",
            row=2,
        )
        transfer_btn.callback = self._transfer_callback
        self.add_item(transfer_btn)

        friend_btn = discord.ui.Button(
            label="Друзья",
            emoji="👥",
            style=discord.ButtonStyle.success,
            custom_id=f"vc:friend:{channel_id}",
            row=2,
        )
        friend_btn.callback = self._friend_callback
        self.add_item(friend_btn)

        ban_btn = discord.ui.Button(
            label="Баны",
            emoji="⛔",
            style=discord.ButtonStyle.danger,
            custom_id=f"vc:ban:{channel_id}",
            row=3,
        )
        ban_btn.callback = self._ban_callback
        self.add_item(ban_btn)

    async def _name_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_modal(NameModal(self.channel_id))

    async def _limit_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_modal(LimitModal(self.channel_id))

    async def _region_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_message(
            "Выбери регион:",
            view=RegionView(self.channel_id),
            ephemeral=True,
        )

    async def _kick_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_message(
            "Выбери участника:",
            view=MemberActionView(self.channel_id, "kick"),
            ephemeral=True,
        )

    async def _guide_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(VOICE_GUIDE_TEXT, ephemeral=True)

    async def _lock_callback(self, interaction: discord.Interaction):
        temp = await _owner_only(interaction, self.channel_id)
        if not temp:
            return
        channel = _voice_channel(interaction, self.channel_id)
        if not channel:
            return await interaction.response.send_message("Канал не найден.", ephemeral=True)

        locked = bool(temp.get("locked"))
        guild = interaction.guild
        owner = guild.get_member(temp["owner_id"])
        if not owner:
            return await interaction.response.send_message("Владелец не найден.", ephemeral=True)

        if locked:
            await channel.set_permissions(guild.default_role, overwrite=None)
            await set_temp_voice_locked(self.channel_id, False)
            await interaction.response.send_message("✅ Комната открыта.", ephemeral=True)
        else:
            await channel.set_permissions(guild.default_role, connect=False, view_channel=True)
            await channel.set_permissions(owner, connect=True, view_channel=True)
            await set_temp_voice_locked(self.channel_id, True)
            await interaction.response.send_message("✅ Комната закрыта.", ephemeral=True)

    async def _transfer_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_message(
            "Кому передать владение?",
            view=MemberActionView(self.channel_id, "transfer"),
            ephemeral=True,
        )

    async def _friend_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_message(
            "Кого добавить?",
            view=MemberActionView(self.channel_id, "friend"),
            ephemeral=True,
        )

    async def _ban_callback(self, interaction: discord.Interaction):
        if not await _owner_only(interaction, self.channel_id):
            return
        await interaction.response.send_message(
            "Кого забанить?",
            view=MemberActionView(self.channel_id, "ban"),
            ephemeral=True,
        )
