"""Channel management service: bot access and VIP invite-link handling."""

import asyncio
import logging
import time
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.channel import Channel
from app.models.user import User

logger = logging.getLogger(__name__)

_bot: Bot | None = None


async def get_or_create_bot() -> Bot:
    """Return a lazily-created singleton aiogram Bot from settings.BOT_TOKEN."""
    global _bot
    if _bot is None:
        if not settings.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN is not configured")
        _bot = Bot(token=settings.BOT_TOKEN)
    return _bot


async def create_vip_invite_link(bot: Bot, channel: Channel, user: User) -> str:
    """Create a single-use, 24h-expiring invite link for a VIP member."""
    link = await bot.create_chat_invite_link(
        chat_id=int(channel.telegram_chat_id),
        member_limit=1,
        expire_date=int(time.time()) + 24 * 3600,
        name=f"VIP_{user.id}_{int(time.time())}",
    )
    logger.info("Created VIP invite link for user=%s channel=%s", user.id, channel.id)
    return link.invite_link


async def kick_member(bot: Bot, channel: Channel, user: User) -> None:
    """Kick a member by banning then immediately unbanning (never permanent ban)."""
    chat_id = int(channel.telegram_chat_id)
    tg_id = int(user.telegram_id)
    try:
        await bot.ban_chat_member(chat_id, tg_id)
    except TelegramForbiddenError:
        logger.warning("Bot lacks ban rights in chat=%s", chat_id)
        raise
    try:
        await bot.unban_chat_member(chat_id, tg_id, only_if_banned=True)
    except TelegramBadRequest:
        logger.debug("Unban after ban failed (already unbanned?) chat=%s user=%s", chat_id, tg_id)
    logger.info("Kicked user=%s from channel=%s", user.id, channel.id)


async def check_bot_admin(bot: Bot, chat_id: int | str) -> bool:
    """Return True if the bot has administrator rights in the given chat."""
    try:
        member = await bot.get_chat_member(chat_id, (await bot.me()).id)
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.error("check_bot_admin failed for chat=%s: %s", chat_id, exc)
        return False
    return member.status == "administrator"


async def get_chat_info(bot: Bot, chat_id: int | str) -> dict[str, Any]:
    """Fetch basic chat info (id, title, type, username) as a dict."""
    chat = await bot.get_chat(chat_id)
    return {
        "id": chat.id,
        "title": chat.title,
        "type": chat.type,
        "username": chat.username,
    }
