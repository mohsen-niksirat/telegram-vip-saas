"""Channel and plan management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.schemas import ChannelCreate, PlanCreate, StatsResponse
from app.api.v1.deps import verify_api_token
from app.core.database import get_session
from app.models.channel import Channel
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.channel_service import check_bot_admin, get_or_create_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(verify_api_token)])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_channel(payload: ChannelCreate, session: AsyncSession = Depends(get_session)) -> dict:
    """Create a channel after verifying the bot is an admin of the chat."""
    bot_instance = await get_or_create_bot()
    try:
        is_admin = await check_bot_admin(bot_instance, payload.telegram_chat_id)
    except Exception as exc:  # noqa: BLE001 - surface Telegram API errors
        raise HTTPException(status_code=400, detail=f"Telegram error: {exc}") from exc
    if not is_admin:
        raise HTTPException(status_code=400, detail="Bot is not an admin of this chat")
    existing = (
        await session.execute(select(Channel).where(Channel.telegram_chat_id == payload.telegram_chat_id))
    ).scalar_one_or_none()
    if existing:
        existing.title = payload.title
        existing.is_active = True
        await session.commit()
        return {"id": existing.id, "telegram_chat_id": existing.telegram_chat_id, "title": existing.title}
    channel = Channel(
        admin_id=0,
        telegram_chat_id=payload.telegram_chat_id,
        title=payload.title,
        is_active=True,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return {"id": channel.id, "telegram_chat_id": channel.telegram_chat_id, "title": channel.title}


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(payload: PlanCreate, session: AsyncSession = Depends(get_session)) -> dict:
    """Create a plan for an existing channel."""
    channel = await session.get(Channel, payload.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    plan = Plan(
        channel_id=payload.channel_id,
        title=payload.title,
        duration_days=payload.duration_days,
        price_usd=payload.price_usd,
        price_stars=payload.price_stars,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return {"id": plan.id, "channel_id": plan.channel_id, "title": plan.title}


@router.get("/{channel_id}/stats", response_model=StatsResponse)
async def channel_stats(channel_id: int, session: AsyncSession = Depends(get_session)) -> StatsResponse:
    """Active subscription count and revenue (USD and XTR) for a channel."""
    channel = await session.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    active_subs = (
        await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.channel_id == channel_id, Subscription.status == "active"
            )
        )
    ).scalar() or 0
    revenue_usd = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                Payment.currency == "USD", Payment.status == "paid",
                Payment.subscription_id.in_(select(Subscription.id).where(Subscription.channel_id == channel_id)),
            )
        )
    ).scalar() or 0.0
    revenue_xtr = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.currency == "XTR", Payment.status == "paid",
                Payment.subscription_id.in_(select(Subscription.id).where(Subscription.channel_id == channel_id)),
            )
        )
    ).scalar() or 0
    return StatsResponse(
        channel_id=channel_id,
        title=channel.title,
        active_subscriptions=int(active_subs),
        revenue_usd=float(revenue_usd),
        revenue_xtr=int(revenue_xtr),
    )
