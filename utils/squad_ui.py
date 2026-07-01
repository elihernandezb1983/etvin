import discord

from config import BLACK, SQUAD_TRANSFER_COMMISSION_PERCENT
from utils.squad import (
    get_led_squad_roles,
    get_member_squad_roles,
    member_is_squad_leader,
    members_with_role,
    squad_leader_id,
    find_squad_leader_role,
    squad_members_excluding_leader,
)


def squad_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="🛡️ Управление сквадом",
        description=(
            "**📋 Мой сквад** — состав и лидер\n"
            f"**💸 Перевести баллы** — перевод участнику сквада (комиссия **{SQUAD_TRANSFER_COMMISSION_PERCENT}%**)\n"
            "**⚙️ Панель лидера** — добавить, исключить или передать лидерство\n"
            "**🚪 Покинуть сквад** — снять с себя роль сквада\n\n"
            "Панель лидера доступна, если у тебя есть роль сквада и **SQUAD LEADER**."
        ),
        color=discord.Color(BLACK),
    )


def build_my_squad_embed(member: discord.Member) -> discord.Embed | str:
    squads = get_member_squad_roles(member, member.guild)
    if not squads:
        return "Ты не состоишь ни в одном скваде."

    leader_role = find_squad_leader_role(member.guild)
    blocks: list[str] = []

    for squad_role in squads:
        members = members_with_role(member.guild, squad_role)
        leader_id = squad_leader_id(member.guild, squad_role, leader_role)
        leader = member.guild.get_member(leader_id) if leader_id else None
        leader_label = leader.mention if leader else "—"

        member_lines = []
        for squad_member in members[:25]:
            prefix = "👑 " if squad_member.id == leader_id else "• "
            member_lines.append(f"{prefix}{squad_member.mention}")

        roster = "\n".join(member_lines) if member_lines else "— пока пусто"
        if len(members) > 25:
            roster += f"\n… и ещё **{len(members) - 25}**"

        blocks.append(
            f"**{squad_role.name}** · {len(members)} чел.\n"
            f"Лидер: {leader_label}\n{roster}"
        )

    return discord.Embed(
        title="📋 Твой сквад",
        description="\n\n".join(blocks),
        color=discord.Color(BLACK),
    )


def leader_panel_embed(squad_role: discord.Role) -> discord.Embed:
    return discord.Embed(
        title="⚙️ Панель лидера",
        description=(
            f"Сквад: **{squad_role.name}**\n\n"
            "**➕ Добавить** — выдать роль участнику, который ещё не в скваде\n"
            "**➖ Исключить** — снять роль у участника из сквада\n"
            "**👑 Передать лидерство** — отдать роль лидера другому участнику сквада"
        ),
        color=discord.Color(BLACK),
    )


def _member_select_options(members: list[discord.Member]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=member.display_name[:100],
            value=str(member.id),
        )
        for member in sorted(members, key=lambda m: m.display_name.casefold())[:25]
    ]


class KickMemberSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, squad_role: discord.Role, actor_id: int):
        self.squad_role_id = squad_role.id
        members = [
            member for member in squad_members_excluding_leader(guild, squad_role)
            if member.id != actor_id
        ]
        super().__init__(
            placeholder="Кого исключить из сквада?",
            options=_member_select_options(members),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SquadCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        target = interaction.guild.get_member(int(self.values[0])) if interaction.guild else None
        if not target:
            await interaction.response.send_message("Участник не найден.", ephemeral=True)
            return
        await cog.process_kick(interaction, self.squad_role_id, target)


class AddMemberSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, squad_role: discord.Role):
        self.squad_role_id = squad_role.id
        members = [
            member for member in guild.members
            if squad_role not in member.roles and not member.bot
        ]
        super().__init__(
            placeholder="Кого добавить в сквад?",
            options=_member_select_options(members),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SquadCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        target = interaction.guild.get_member(int(self.values[0])) if interaction.guild else None
        if not target:
            await interaction.response.send_message("Участник не найден.", ephemeral=True)
            return
        await cog.process_add(interaction, self.squad_role_id, target)


class TransferLeaderSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, squad_role: discord.Role, actor_id: int):
        self.squad_role_id = squad_role.id
        members = [
            member for member in members_with_role(guild, squad_role)
            if member.id != actor_id and not member_is_squad_leader(member)
        ]
        super().__init__(
            placeholder="Кому передать лидерство?",
            options=_member_select_options(members),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("SquadCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        target = interaction.guild.get_member(int(self.values[0])) if interaction.guild else None
        if not target:
            await interaction.response.send_message("Участник не найден.", ephemeral=True)
            return
        await cog.process_transfer(interaction, self.squad_role_id, target)


class SquadManageView(discord.ui.View):
    def __init__(self, guild: discord.Guild, squad_role: discord.Role, actor_id: int):
        super().__init__(timeout=180)
        self.guild = guild
        self.squad_role = squad_role
        self.actor_id = actor_id

    @discord.ui.button(label="➕ Добавить", style=discord.ButtonStyle.success)
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        eligible = [
            m for m in self.guild.members
            if self.squad_role not in m.roles and not m.bot
        ]
        if not eligible:
            await interaction.response.send_message(
                "Нет участников, которых можно добавить — все уже в скваде или это боты.",
                ephemeral=True,
            )
            return
        view = discord.ui.View(timeout=120)
        view.add_item(AddMemberSelect(self.guild, self.squad_role))
        note = ""
        if len(eligible) > 25:
            note = f"\n\nПоказаны первые **25** из **{len(eligible)}**."
        await interaction.response.send_message(
            f"Выбери участника для добавления в **{self.squad_role.name}**.{note}",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="➖ Исключить", style=discord.ButtonStyle.danger)
    async def kick_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = [
            m for m in squad_members_excluding_leader(self.guild, self.squad_role)
            if m.id != self.actor_id
        ]
        if not members:
            await interaction.response.send_message(
                "В скваде никого нельзя исключить.",
                ephemeral=True,
            )
            return
        view = discord.ui.View(timeout=120)
        view.add_item(KickMemberSelect(self.guild, self.squad_role, self.actor_id))
        await interaction.response.send_message(
            f"Выбери участника сквада **{self.squad_role.name}** для исключения.",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="👑 Передать лидерство", style=discord.ButtonStyle.primary)
    async def transfer_leader(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = [
            m for m in members_with_role(self.guild, self.squad_role)
            if m.id != self.actor_id and not member_is_squad_leader(m)
        ]
        if not members:
            await interaction.response.send_message(
                "Нет участников, которым можно передать лидерство.",
                ephemeral=True,
            )
            return
        view = discord.ui.View(timeout=120)
        view.add_item(TransferLeaderSelect(self.guild, self.squad_role, self.actor_id))
        await interaction.response.send_message(
            f"Выбери нового лидера сквада **{self.squad_role.name}**.",
            view=view,
            ephemeral=True,
        )


class TransferPointsAmountModal(discord.ui.Modal, title="Перевод баллов"):
    def __init__(self, squad_role_id: int, target_id: int):
        super().__init__()
        self.squad_role_id = squad_role_id
        self.target_id = target_id
        self.amount = discord.ui.TextInput(
            label="Сколько баллов перевести?",
            placeholder="100",
            max_length=8,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.amount.value.strip()
        if not raw.isdigit() or int(raw) <= 0:
            await interaction.response.send_message(
                "Укажи целое число больше нуля.",
                ephemeral=True,
            )
            return
        cog = interaction.client.get_cog("SquadCog")
        if not cog:
            await interaction.response.send_message("Недоступно.", ephemeral=True)
            return
        await cog.process_transfer_points(
            interaction,
            self.squad_role_id,
            self.target_id,
            int(raw),
        )


class TransferRecipientSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, squad_role: discord.Role, actor_id: int):
        self.squad_role_id = squad_role.id
        members = [
            member for member in members_with_role(guild, squad_role)
            if member.id != actor_id and not member.bot
        ]
        super().__init__(
            placeholder="Кому перевести баллы?",
            options=_member_select_options(members),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            TransferPointsAmountModal(self.squad_role_id, int(self.values[0]))
        )


async def prompt_transfer_recipient(
    interaction: discord.Interaction,
    squad_role: discord.Role,
    actor_id: int,
) -> None:
    members = [
        member for member in members_with_role(interaction.guild, squad_role)
        if member.id != actor_id and not member.bot
    ]
    if not members:
        await interaction.response.send_message(
            f"В скваде **{squad_role.name}** нет других участников для перевода.",
            ephemeral=True,
        )
        return
    view = discord.ui.View(timeout=120)
    view.add_item(TransferRecipientSelect(interaction.guild, squad_role, actor_id))
    note = ""
    if len(members) > 25:
        note = f"\n\nПоказаны первые **25** из **{len(members)}**."
    await interaction.response.send_message(
        f"Перевод в сквад **{squad_role.name}**.\n"
        f"Комиссия: **{SQUAD_TRANSFER_COMMISSION_PERCENT}%** — получатель получит меньше на эту долю."
        f"{note}\n\nВыбери получателя:",
        view=view,
        ephemeral=True,
    )


class SquadPickSelect(discord.ui.Select):
    def __init__(
        self,
        squad_roles: list[discord.Role],
        *,
        for_leave: bool = False,
        for_transfer: bool = False,
    ):
        self.for_leave = for_leave
        self.for_transfer = for_transfer
        options = [
            discord.SelectOption(label=role.name[:100], value=str(role.id))
            for role in squad_roles[:25]
        ]
        super().__init__(
            placeholder="Выбери сквад",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if self.for_leave:
            cog = interaction.client.get_cog("SquadCog")
            if not cog:
                await interaction.response.send_message("Недоступно.", ephemeral=True)
                return
            await cog.process_leave(interaction, role_id)
            return

        if self.for_transfer:
            await prompt_transfer_recipient(interaction, role, interaction.user.id)
            return

        await interaction.response.send_message(
            embed=leader_panel_embed(role),
            view=SquadManageView(interaction.guild, role, interaction.user.id),
            ephemeral=True,
        )


class SquadPickView(discord.ui.View):
    def __init__(
        self,
        squad_roles: list[discord.Role],
        *,
        for_leave: bool = False,
        for_transfer: bool = False,
    ):
        super().__init__(timeout=120)
        self.add_item(
            SquadPickSelect(
                squad_roles,
                for_leave=for_leave,
                for_transfer=for_transfer,
            )
        )


class SquadPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Мой сквад",
        style=discord.ButtonStyle.secondary,
        custom_id="squad:my",
    )
    async def my_squad(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        result = build_my_squad_embed(interaction.user)
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
            return
        await interaction.response.send_message(embed=result, ephemeral=True)

    @discord.ui.button(
        label="💸 Перевести баллы",
        style=discord.ButtonStyle.success,
        custom_id="squad:transfer",
    )
    async def transfer_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squads = get_member_squad_roles(interaction.user, interaction.guild)
        if not squads:
            await interaction.response.send_message(
                "Ты не состоишь ни в одном скваде.",
                ephemeral=True,
            )
            return

        if len(squads) == 1:
            await prompt_transfer_recipient(interaction, squads[0], interaction.user.id)
            return

        embed = discord.Embed(
            title="💸 Перевести баллы",
            description="В каком скваде переводим?",
            color=discord.Color(BLACK),
        )
        await interaction.response.send_message(
            embed=embed,
            view=SquadPickView(squads, for_transfer=True),
            ephemeral=True,
        )

    @discord.ui.button(
        label="⚙️ Панель лидера",
        style=discord.ButtonStyle.primary,
        custom_id="squad:manage",
    )
    async def manage_squad(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        led = get_led_squad_roles(interaction.user)
        if not led:
            await interaction.response.send_message(
                "Только **SQUAD LEADER** с ролью своего сквада может управлять составом.",
                ephemeral=True,
            )
            return

        if len(led) == 1:
            await interaction.response.send_message(
                embed=leader_panel_embed(led[0]),
                view=SquadManageView(interaction.guild, led[0], interaction.user.id),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⚙️ Панель лидера",
            description="У тебя несколько сквадов — выбери, каким управлять.",
            color=discord.Color(BLACK),
        )
        await interaction.response.send_message(
            embed=embed,
            view=SquadPickView(led),
            ephemeral=True,
        )

    @discord.ui.button(
        label="🚪 Покинуть сквад",
        style=discord.ButtonStyle.secondary,
        custom_id="squad:leave",
    )
    async def leave_squad(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if member_is_squad_leader(interaction.user):
            await interaction.response.send_message(
                "Лидер не может просто покинуть сквад — сначала **передай лидерство**.",
                ephemeral=True,
            )
            return

        squads = get_member_squad_roles(interaction.user, interaction.guild)
        if not squads:
            await interaction.response.send_message(
                "Ты не состоишь ни в одном скваде.",
                ephemeral=True,
            )
            return

        if len(squads) == 1:
            cog = interaction.client.get_cog("SquadCog")
            if not cog:
                await interaction.response.send_message("Недоступно.", ephemeral=True)
                return
            await cog.process_leave(interaction, squads[0].id)
            return

        embed = discord.Embed(
            title="🚪 Покинуть сквад",
            description="Из какого сквада выйти?",
            color=discord.Color(BLACK),
        )
        await interaction.response.send_message(
            embed=embed,
            view=SquadPickView(squads, for_leave=True),
            ephemeral=True,
        )
