"""Stats endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.schemas import StatsResponse
from app.api.v1.deps import verify_api_token
from app.core.database import get_session
from app.models.payment import Payment
from app.models.subscription import Subscription

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(verify_api_token)])


@router.get("/summary")
async def stats_summary(session: AsyncSession = Depends(get_session)) -> dict:
    """Global stats: channels, plans, active subs, total revenue by currency."""
    from app.models.channel import Channel
    from app.models.plan import Plan

    channels = (await session.execute(select(func.count(Channel.id)))).scalar() or 0
    plans = (await session.execute(select(func.count(Plan.id)))).scalar() or 0
    active_subs = (
        await session.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))
    ).scalar() or 0
    revenue_usd = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                Payment.status == "paid", Payment.currency == "USD"
            )
        )
    ).scalar() or 0.0
    revenue_xtr = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "paid", Payment.currency == "XTR"
            )
        )
    ).scalar() or 0
    return {
        "channels": int(channels),
        "plans": int(plans),
        "active_subscriptions": int(active_subs),
        "revenue_usd": float(revenue_usd),
        "revenue_xtr": int(revenue_xtr),
    }
