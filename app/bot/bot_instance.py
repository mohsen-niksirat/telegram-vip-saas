"""Bot and dispatcher instances plus webhook/polling setup helpers."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import admin, checkout, social, start
from app.config import settings

logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_routers(start.router, checkout.router, admin.router, social.router)


async def setup_webhook(bot_instance: Bot) -> str:
    """Register the Telegram webhook under ``WEBHOOK_BASE_URL`` and return its URL."""
    url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/{settings.BOT_TOKEN}"
    await bot_instance.set_webhook(url, drop_pending_updates=True)
    logger.info("Webhook set to %s", url)
    return url


async def setup_polling(bot_instance: Bot) -> None:
    """Delete any webhook and start long polling (blocking; run as a task)."""
    await bot_instance.delete_webhook(drop_pending_updates=True)
    await bot_instance.delete_my_commands()
    logger.info("Starting polling")
    await dp.start_polling(bot_instance)
