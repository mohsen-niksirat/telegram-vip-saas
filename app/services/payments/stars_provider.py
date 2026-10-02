"""Telegram Stars (XTR) payment provider helpers."""

import logging

from aiogram import Bot
from aiogram.methods.base import TelegramMethod
from aiogram.types import LabeledPrice, PreCheckoutQuery

from app.models.plan import Plan

logger = logging.getLogger(__name__)


async def send_stars_invoice(bot: Bot, chat_id: int, plan: Plan, payload: str) -> TelegramMethod:
    """Send a Telegram Stars invoice for the given plan.

    Currency is always 'XTR' and price is taken from plan.price_stars.
    `payload` is an opaque merchant string (e.g. 'sub:<plan_id>:<user_id>').
    """
    return await bot.send_invoice(
        chat_id=chat_id,
        title=plan.title,
        description=f"VIP access — {plan.title}",
        payload=payload,
        provider_token="",  # required empty string for XTR invoices
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=plan.price_stars)],
    )


async def validate_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> bool:
    """Validate the incoming pre-checkout query; always accepts Stars invoices.

    Extend here with payload checks (e.g. lookup plan/user) as needed.
    """
    if not pre_checkout_query.invoice_payload:
        logger.warning("Pre-checkout query missing payload: %s", pre_checkout_query.id)
        await pre_checkout_query.answer(ok=False, error_message="Invalid payment payload.")
        return False
    await pre_checkout_query.answer(ok=True)
    return True
