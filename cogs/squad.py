import logging

import discord
from discord.ext import commands

from config import SQUAD_TRANSFER_COMMISSION_PERCENT
from utils.database import transfer_shop_points
from utils.discord_log import log_server
from utils.squad import (
    can_assign_squad_role,
    can_manage_squad,
    can_manage_role,
    can_remove_squad_role,
    get_led_squad_roles,
    get_member_leader_role,
    member_is_squad_leader,
)
from utils.squad_ui import SquadPanelView

log = logging.getLogger("etvin")


class SquadCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(SquadPanelView())

    async def _resolve_member(
        self,
        interaction: discord.Interaction,
        target: discord.User,
    ) -> discord.Member | None:
        if not interaction.guild:
            return None
        member = interaction.guild.get_member(target.id)
        if member:
            return member
        try:
            return await interaction.guild.fetch_member(target.id)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Участник не найден на сервере.",
                ephemeral=True,
            )
            return None

    async def _check_leader(
        self,
        interaction: discord.Interaction,
        squad_role: discord.Role,
    ) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if not can_manage_squad(interaction.user, squad_role):
            await interaction.response.send_message(
                "Ты не лидер этого сквада.",
                ephemeral=True,
            )
            return False
        return True

    async def process_add(
        self,
        interaction: discord.Interaction,
        squad_role_id: int,
        target: discord.User,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squad_role = interaction.guild.get_role(squad_role_id)
        if not squad_role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if not await self._check_leader(interaction, squad_role):
            return

        if target.bot:
            await interaction.response.send_message("Нельзя добавить бота.", ephemeral=True)
            return

        member = await self._resolve_member(interaction, target)
        if not member:
            return

        if squad_role in member.roles:
            await interaction.response.send_message(
                f"{member.mention} уже в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        ok, reason = can_assign_squad_role(interaction.guild, squad_role)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        try:
            await member.add_roles(
                squad_role,
                reason=f"Добавлен в сквад {squad_role.name} лидером {interaction.user}",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Не удалось выдать роль. Проверь права бота и порядок ролей.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ {member.mention} добавлен в сквад **{squad_role.name}**.",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Сквад · добавление**\n"
            f"Лидер: {interaction.user.mention}\n"
            f"Сквад: **{squad_role.name}**\n"
            f"Добавлен: {member.mention}",
        )

    async def process_kick(
        self,
        interaction: discord.Interaction,
        squad_role_id: int,
        target: discord.User,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squad_role = interaction.guild.get_role(squad_role_id)
        if not squad_role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if not await self._check_leader(interaction, squad_role):
            return

        if target.bot:
            await interaction.response.send_message("Нельзя исключить бота.", ephemeral=True)
            return

        if target.id == interaction.user.id:
            await interaction.response.send_message("Нельзя исключить себя.", ephemeral=True)
            return

        member = await self._resolve_member(interaction, target)
        if not member:
            return

        if squad_role not in member.roles:
            await interaction.response.send_message(
                f"{member.mention} не состоит в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        if member_is_squad_leader(member):
            await interaction.response.send_message(
                "Нельзя исключить другого лидера сквада.",
                ephemeral=True,
            )
            return

        ok, reason = can_remove_squad_role(interaction.guild, squad_role)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        try:
            await member.remove_roles(
                squad_role,
                reason=f"Исключён из сквада {squad_role.name} лидером {interaction.user}",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Не удалось снять роль. Проверь права бота и порядок ролей.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ {member.mention} исключён из сквада **{squad_role.name}**.",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Сквад · исключение**\n"
            f"Лидер: {interaction.user.mention}\n"
            f"Сквад: **{squad_role.name}**\n"
            f"Исключён: {member.mention}",
        )

    async def process_transfer(
        self,
        interaction: discord.Interaction,
        squad_role_id: int,
        target: discord.User,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squad_role = interaction.guild.get_role(squad_role_id)
        if not squad_role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if not await self._check_leader(interaction, squad_role):
            return

        leader_role = get_member_leader_role(interaction.user)
        if not leader_role:
            await interaction.response.send_message(
                "Роль **SQUAD LEADER** не найдена у тебя.",
                ephemeral=True,
            )
            return

        if target.bot:
            await interaction.response.send_message("Нельзя передать лидерство боту.", ephemeral=True)
            return

        if target.id == interaction.user.id:
            await interaction.response.send_message(
                "Ты уже лидер. Выбери другого участника.",
                ephemeral=True,
            )
            return

        member = await self._resolve_member(interaction, target)
        if not member:
            return

        if squad_role not in member.roles:
            await interaction.response.send_message(
                f"{member.mention} не состоит в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        ok, reason = can_manage_role(interaction.guild, leader_role)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        led_count = len(get_led_squad_roles(interaction.user))
        try:
            await member.add_roles(
                leader_role,
                reason=f"Лидерство сквада {squad_role.name} передано от {interaction.user}",
            )
            try:
                await interaction.user.remove_roles(
                    leader_role,
                    reason=f"Лидерство сквада {squad_role.name} передано {member}",
                )
            except discord.HTTPException:
                await member.remove_roles(
                    leader_role,
                    reason="Откат: не удалось снять лидерство с прежнего лидера",
                )
                raise
        except discord.HTTPException:
            await interaction.response.send_message(
                "Не удалось передать лидерство. Проверь права бота и порядок ролей.",
                ephemeral=True,
            )
            return

        extra = ""
        if led_count > 1:
            extra = "\n\n⚠️ Роль лидера снята с тебя полностью — ты больше не лидер других сквадов."

        await interaction.response.send_message(
            f"👑 {member.mention} теперь лидер сквада **{squad_role.name}**.{extra}",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Сквад · передача лидерства**\n"
            f"Сквад: **{squad_role.name}**\n"
            f"Было: {interaction.user.mention}\n"
            f"Стало: {member.mention}",
        )

    async def process_transfer_points(
        self,
        interaction: discord.Interaction,
        squad_role_id: int,
        target_id: int,
        amount: int,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squad_role = interaction.guild.get_role(squad_role_id)
        if not squad_role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if squad_role not in interaction.user.roles:
            await interaction.response.send_message(
                f"Ты не состоишь в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        if target_id == interaction.user.id:
            await interaction.response.send_message(
                "Нельзя перевести баллы себе.",
                ephemeral=True,
            )
            return

        target = interaction.guild.get_member(target_id)
        if not target:
            try:
                target = await interaction.guild.fetch_member(target_id)
            except discord.HTTPException:
                await interaction.response.send_message(
                    "Участник не найден на сервере.",
                    ephemeral=True,
                )
                return

        if target.bot:
            await interaction.response.send_message("Нельзя перевести баллы боту.", ephemeral=True)
            return

        if squad_role not in target.roles:
            await interaction.response.send_message(
                f"{target.mention} не состоит в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        ok, reason, received = await transfer_shop_points(
            interaction.guild.id,
            interaction.user.id,
            target.id,
            amount,
            commission_percent=SQUAD_TRANSFER_COMMISSION_PERCENT,
        )
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        commission = amount - received
        commission_note = ""
        if commission > 0:
            commission_note = f" (комиссия **{commission}** б.)"

        await interaction.response.send_message(
            f"✅ Переведено **{received}** б. → {target.mention}{commission_note}\n"
            f"Списано с тебя: **{amount}** б.",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Сквад · перевод баллов**\n"
            f"Сквад: **{squad_role.name}**\n"
            f"От: {interaction.user.mention}\n"
            f"Кому: {target.mention}\n"
            f"Сумма: **{amount}** б. → получил **{received}** б."
            + (f" · комиссия **{commission}** б." if commission else ""),
        )

    async def process_leave(
        self,
        interaction: discord.Interaction,
        squad_role_id: int,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        squad_role = interaction.guild.get_role(squad_role_id)
        if not squad_role:
            await interaction.response.send_message("Роль сквада не найдена.", ephemeral=True)
            return

        if squad_role not in interaction.user.roles:
            await interaction.response.send_message(
                f"Ты не состоишь в скваде **{squad_role.name}**.",
                ephemeral=True,
            )
            return

        if member_is_squad_leader(interaction.user):
            await interaction.response.send_message(
                "Лидер не может просто покинуть сквад — сначала **передай лидерство**.",
                ephemeral=True,
            )
            return

        ok, reason = can_remove_squad_role(interaction.guild, squad_role)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        try:
            await interaction.user.remove_roles(
                squad_role,
                reason=f"Покинул сквад {squad_role.name}",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Не удалось снять роль. Проверь права бота и порядок ролей.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Ты покинул сквад **{squad_role.name}**.",
            ephemeral=True,
        )
        await log_server(
            interaction.guild,
            f"**Сквад · выход**\n"
            f"Сквад: **{squad_role.name}**\n"
            f"Участник: {interaction.user.mention}",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SquadCog(bot))
