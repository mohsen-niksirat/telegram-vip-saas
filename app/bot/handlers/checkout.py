"""Checkout handlers: Stars invoices, pre-checkout, successful payment, crypto, renew."""

from __future__ import annotations

import datetime as dt
import logging
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from app.bot.keyboards.inline import plans_kb, t
from app.config import settings
from app.core.database import get_session
from app.models.channel import Channel
from app.models.plan import Plan
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.services.channel_service import create_vip_invite_link
from app.services.payments.crypto_provider import create_invoice
from app.services.payments.stars_provider import send_stars_invoice, validate_pre_checkout
from app.services.subscription_service import activate_subscription, get_or_create_user

logger = logging.getLogger(__name__)
router = Router(name="checkout")


async def _plan_and_channel(session, plan_id: int) -> tuple[Plan, Channel] | None:
    """Load a plan with its channel, or ``None``."""
    result = await session.execute(
        select(Plan, Channel).join(Channel, Plan.channel_id == Channel.id).where(Plan.id == plan_id)
    )
    return result.first()


# ---------------------------------------------------------------- Stars ----

@router.callback_query(F.data.startswith("stars:"))
async def cb_pay_stars(callback: CallbackQuery) -> None:
    """Send a Telegram Stars invoice for ``stars:<plan_id>``."""
    plan_id = int(callback.data.split(":")[1])
    async for session in get_session():
        row = await _plan_and_channel(session, plan_id)
        if not row:
            await callback.answer(t(callback.from_user, "plans_empty"), show_alert=True)
            return
        plan, channel = row
        await send_stars_invoice(
            bot=callback.bot,
            chat_id=callback.from_user.id,
            title=plan.title,
            description=f"VIP: {channel.title} · {plan.duration_days}d",
            payload=f"stars:{plan.id}:{callback.from_user.id}",
            prices=[LabeledPrice(label=f"VIP {plan.title}", amount=plan.price_stars)],
        )
        await callback.answer(t(callback.from_user, "invoice_sent"), show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Validate the incoming pre-checkout query."""
    ok, error = await validate_pre_checkout(query)
    await query.answer(ok=ok, error_message=error)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Fulfill a Stars payment: activate subscription and DM the invite link."""
    payment = message.successful_payment
    parts = payment.invoice_payload.split(":")
    if len(parts) != 3 or parts[0] != "stars":
        logger.warning("Unknown payment payload: %s", payment.invoice_payload)
        return
    plan_id = int(parts[1])
    async for session in get_session():
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        row = await _plan_and_channel(session, plan_id)
        if not row:
            logger.error("Paid plan %s missing", plan_id)
            return
        plan, channel = row
        sub = await activate_subscription(session, user_id=user.id, channel_id=channel.id, plan_id=plan.id)
        session.add(
            Payment(
                subscription_id=sub.id,
                user_id=user.id,
                amount=plan.price_stars,
                currency="XTR",
                provider="stars",
                provider_tx_id=payment.telegram_payment_charge_id,
                status="paid",
                raw_payload=payment.model_dump_json(),
            )
        )
        await session.commit()
        link = await create_vip_invite_link(session, channel=channel, bot=message.bot)
        expires = sub.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        await message.answer(
            t(message.from_user, "congrats", link=link, expires=expires.strftime("%Y-%m-%d")),
            disable_web_page_preview=True,
        )


# --------------------------------------------------------------- Crypto ----

@router.callback_query(F.data.startswith("crypto:"))
async def cb_pay_crypto(callback: CallbackQuery) -> None:
    """Create a crypto invoice and send the payment URL button."""
    plan_id = int(callback.data.split(":")[1])
    async for session in get_session():
        user = await get_or_create_user(session, telegram_id=callback.from_user.id)
        row = await _plan_and_channel(session, plan_id)
        if not row:
            await callback.answer(t(callback.from_user, "plans_empty"), show_alert=True)
            return
        plan, channel = row
        order_id = f"{user.id}-{plan.id}-{int(time.time())}"
        invoice = await create_invoice(
            amount=plan.price_usd,
            currency="USD",
            order_id=order_id,
            description=f"VIP: {channel.title} · {plan.title}",
        )
        session.add(
            Payment(
                subscription_id=None,
                user_id=user.id,
                amount=plan.price_usd,
                currency="USD",
                provider="crypto",
                provider_tx_id=order_id,
                status="pending",
                raw_payload=str(invoice),
            )
        )
        await session.commit()
        pay_url = invoice.get("pay_url") if isinstance(invoice, dict) else str(invoice)
        await callback.message.answer(
            t(callback.from_user, "crypto_order", title=channel.title, amount=plan.price_usd),
            reply_markup=_pay_url_kb(pay_url, callback.from_user),
            disable_web_page_preview=True,
        )
    await callback.answer()


def _pay_url_kb(url: str, user: object):
    """Build a keyboard with a single payment URL button."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user, "pay_now"), url=url)]]
    )


# ---------------------------------------------------------------- Renew ----

@router.callback_query(F.data.startswith("renew:"))
async def cb_renew(callback: CallbackQuery) -> None:
    """Renewal flow: re-send the plan screen for the subscription's channel."""
    sub_id = int(callback.data.split(":")[1])
    async for session in get_session():
        result = await session.execute(
            select(Subscription, Channel, Plan)
            .join(Channel, Subscription.channel_id == Channel.id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.id == sub_id)
        )
        row = result.first()
        if not row:
            await callback.answer(t(callback.from_user, "subs_empty"), show_alert=True)
            return
        sub, channel, _plan = row
        plans_result = await session.execute(
            select(Plan).where(Plan.channel_id == channel.id, Plan.is_active.is_(True)).order_by(Plan.id)
        )
        plans = list(plans_result.scalars().all())
        if not plans:
            await callback.answer(t(callback.from_user, "plans_empty"), show_alert=True)
            return
        await callback.answer(t(callback.from_user, "renewing"))
        await callback.message.edit_text(
            t(callback.from_user, "renew", title=channel.title),
            reply_markup=plans_kb(channel, plans, user=callback.from_user),
        )
