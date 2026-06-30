import re

import discord

from utils.database import get_settings

_TICKET_NAME_RE = re.compile(r"[^\w-]", re.UNICODE)


def _ticket_channel_name(member: discord.Member, redemption_id: int) -> str:
    slug = _TICKET_NAME_RE.sub("", member.display_name.lower().replace(" ", "-"))[:24]
    slug = slug or "user"
    return f"заявка-{slug}-{redemption_id}"[:100]


async def create_shop_ticket(
    guild: discord.Guild,
    buyer: discord.Member,
    redemption_id: int,
    *,
    category_id: int,
) -> discord.TextChannel:
    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        raise ValueError("Категория тикетов не найдена")

    settings = await get_settings(guild.id)
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        buyer: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    staff_role_id = settings.get("admin_role_id")
    if staff_role_id:
        staff_role = guild.get_role(staff_role_id)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            )

    return await guild.create_text_channel(
        name=_ticket_channel_name(buyer, redemption_id),
        category=category,
        overwrites=overwrites,
        reason=f"Тикет магазина #{redemption_id} · {buyer}",
    )


async def remove_buyer_from_ticket(
    channel: discord.TextChannel,
    buyer_id: int,
) -> None:
    buyer = channel.guild.get_member(buyer_id)
    if not buyer:
        return

    overwrite = channel.overwrites_for(buyer)
    overwrite.view_channel = False
    overwrite.send_messages = False
    overwrite.read_message_history = False
    await channel.set_permissions(buyer, overwrite=overwrite, reason="Заявка обработана")
