"""Payment endpoints: crypto webhook (public, signature-verified, idempotent)
and admin manual member grants."""

from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import verify_api_token
from app.api.schemas.schemas import ManualAdd, PaymentWebhookAck
from app.core.database import get_session
from app.models.channel import Channel
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.services.channel_service import create_vip_invite_link, get_or_create_bot
from app.services.payments.crypto_provider import verify_webhook_signature
from app.services.subscription_service import (
    activate_subscription,
    get_or_create_user,
    manual_grant,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/crypto/webhook", response_model=PaymentWebhookAck)
async def crypto_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> PaymentWebhookAck:
    """Public Cryptomus/NowPayments webhook.

    Verifies the signature, marks the payment paid, activates/renews the
    subscription, sends a single-use invite link, and is idempotent.
    """
    raw_body = await request.body()
    try:
        data = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    provider = str(data.get("provider") or "cryptomus").lower()
    signature = (
        request.headers.get("X-Signature")
        or request.headers.get("sign")
        or request.headers.get("x-nowpayments-sig")
    )
    if not await verify_webhook_signature(provider, raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    order_id = str(data.get("order_id") or "")
    tx_id = str(data.get("txid") or data.get("payment_id") or order_id)
    pay_status = str(data.get("status") or data.get("payment_status") or "").lower()

    result = await session.execute(
        select(Payment).where(Payment.provider_tx_id == order_id)
    )
    payment = result.scalars().first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if pay_status not in ("paid", "success", "completed", "confirmed", "finished"):
        return PaymentWebhookAck(status="ignored", detail=f"status={pay_status}")

    if payment.status == "paid":
        return PaymentWebhookAck(status="ok", detail="already processed")  # idempotent

    # Resolve user/channel/plan for fulfillment.
    user = await session.get(User, payment.user_id)
    plan = None
    if order_id.count("-") >= 2:
        try:
            plan_id = int(order_id.split("-")[1])
            plan = await session.get(Plan, plan_id)
        except (ValueError, TypeError):
            plan = None
    if plan is None and payment.subscription_id:
        sub = await session.get(type(Plan).__mro__[0], 0) if False else None  # noqa: E501
    if user is None or plan is None:
        payment.status = "paid"
        payment.raw_payload = data
        await session.commit()
        return PaymentWebhookAck(status="ok", detail="paid, missing user/plan context")

    channel = await session.get(Channel, plan.channel_id)
    if channel is None:
        payment.status = "paid"
        payment.raw_payload = data
        await session.commit()
        return PaymentWebhookAck(status="ok", detail="paid, missing channel")

    subscription, _payment = await activate_subscription(
        session,
        user=user,
        channel=channel,
        plan=plan,
        provider=payment.provider,
        provider_tx_id=tx_id,
        amount=float(payment.amount),
        currency=payment.currency,
        raw_payload=data,
    )
    payment.subscription_id = subscription.id

    invite_link: str | None = None
    try:
        bot = await get_or_create_bot()
        invite_link = await create_vip_invite_link(bot, channel, user)
        expires = subscription.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        await bot.send_message(
            user.telegram_id,
            f"🎉 Payment confirmed!\nYour VIP invite link: {invite_link}\n"
            f"Expires: {expires:%Y-%m-%d %H:%M} UTC",
        )
    except Exception as exc:  # noqa: BLE001 - DM failure must not fail webhook
        logger.warning("Fulfillment DM failed: %s", exc)

    return PaymentWebhookAck(status="ok", detail=f"subscription={subscription.id}")


members_router = APIRouter(
    prefix="/members", tags=["members"], dependencies=[Depends(verify_api_token)]
)


@members_router.post("/manual-add")
async def manual_add(
    payload: ManualAdd, session: AsyncSession = Depends(get_session)
) -> dict:
    """Manually grant VIP membership for N days and DM the invite link."""
    admin = await get_or_create_user(session, telegram_id=payload.admin_telegram_id)
    channel = await session.get(Channel, payload.channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    sub = await manual_grant(
        session,
        admin=admin,
        user_telegram_id=payload.telegram_id,
        channel=channel,
        days=payload.days,
    )

    invite_link: str | None = None
    user = await get_or_create_user(session, telegram_id=payload.telegram_id)
    try:
        bot = await get_or_create_bot()
        invite_link = await create_vip_invite_link(bot, channel, user)
        expires = sub.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        await bot.send_message(
            payload.telegram_id,
            f"✅ VIP access granted for {channel.title}!\n"
            f"Invite link: {invite_link}\nExpires: {expires:%Y-%m-%d %H:%M} UTC",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Manual-add DM failed: %s", exc)

    return {"status": "ok", "subscription_id": sub.id, "invite_link": invite_link}


@members_router.post("/{payment_id}/retry")
async def retry_payment_delivery(
    payment_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Best-effort re-send of the invite link DM for a failed/pending payment."""
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in ("pending", "failed"):
        return {"status": "skipped", "detail": f"payment status={payment.status}"}
    if not payment.subscription_id:
        return {"status": "skipped", "detail": "no subscription context"}

    sub = await session.get(Subscription, payment.subscription_id)
    user = await session.get(User, payment.user_id)
    channel = await session.get(Channel, sub.channel_id) if sub else None
    if user is None or channel is None:
        raise HTTPException(status_code=409, detail="Missing user/channel context")

    invite_link: str | None = None
    try:
        bot = await get_or_create_bot()
        invite_link = await create_vip_invite_link(bot, channel, user)
        expires = sub.expires_at if sub else None
        expires_s = f"{expires:%Y-%m-%d %H:%M} UTC" if expires else "active"
        await bot.send_message(
            user.telegram_id,
            f"✅ VIP access for {channel.title}!\n"
            f"Invite link: {invite_link}\nExpires: {expires_s}",
        )
        if payment.status == "failed":
            payment.status = "paid"
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retry delivery for payment=%s failed: %s", payment_id, exc)
        return {"status": "failed", "detail": str(exc)}

    return {"status": "ok", "payment_id": payment_id, "invite_link": invite_link}
