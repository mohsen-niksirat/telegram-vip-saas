"""Admin dashboard API endpoints (prefix ``/admin``)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.schemas import (
    AdminBroadcastPatch,
    AdminBroadcastRequest,
    AdminBroadcastResponse,
    AdminChannelPatch,
    AdminChannelResponse,
    AdminOverviewResponse,
    AdminPlanPatch,
    AdminRecentPayment,
    AdminRevenueDailyResponse,
    AdminSubscriptionResponse,
)
from app.api.v1.deps import verify_api_token
from app.core.database import get_session
from app.models.channel import Channel
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_api_token)])


# ---------------------------------------------------------------- helpers


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


# ---------------------------------------------------------------- overview


@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(session: AsyncSession = Depends(get_session)) -> AdminOverviewResponse:
    channels_count = (await session.scalar(select(func.count(Channel.id)))) or 0
    plans_count = (await session.scalar(select(func.count(Plan.id)))) or 0
    users_count = (await session.scalar(select(func.count(User.id)))) or 0
    active_subs = (await session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == "active")
    )) or 0
    expired_subs = (await session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status != "active")
    )) or 0

    revenue_rows = (await session.execute(
        select(Payment.currency, func.count(Payment.id), func.sum(Payment.amount))
        .where(Payment.status == "paid")
        .group_by(Payment.currency)
    )).all()

    rev: dict[str, tuple[int, float]] = {}
    for currency, count, total in revenue_rows:
        cur = (currency or "unknown").lower()
        rev[cur] = (count or 0, _as_float(total))

    payments_count = (await session.scalar(select(func.count(Payment.id)))) or 0

    recent_rows = (await session.execute(
        select(Payment, User)
        .join(User, Payment.user_id == User.id, isouter=True)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(10)
    )).all()

    recent = [
        AdminRecentPayment(
            id=p.id,
            user_telegram_id=u.telegram_id if u else None,
            username=u.username if u else None,
            amount=_as_float(p.amount),
            currency=p.currency,
            provider=p.provider,
            status=p.status,
            created_at=p.created_at,
        )
        for p, u in recent_rows
    ]

    return AdminOverviewResponse(
        channels=channels_count,
        plans=plans_count,
        users=users_count,
        active_subscriptions=active_subs,
        expired_subscriptions=expired_subs,
        revenue_usd=rev.get("usd", (0, 0.0))[1],
        revenue_xtr=rev.get("xtr", (0, 0.0))[1],
        revenue_ton=rev.get("ton", (0, 0.0))[1],
        payments_count=payments_count,
        recent_payments=recent,
    )


# ---------------------------------------------------------------- revenue daily


@router.get("/revenue/daily", response_model=list[AdminRevenueDailyResponse])
async def admin_revenue_daily(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> list[AdminRevenueDailyResponse]:
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    rows = (await session.execute(
        select(func.date(Payment.created_at), Payment.currency, func.sum(Payment.amount))
        .where(Payment.status == "paid", Payment.created_at >= since)
        .group_by(func.date(Payment.created_at), Payment.currency)
    )).all()

    agg: dict[str, dict[str, float]] = {}
    for date, currency, total in rows:
        key = str(date)
        cur = (currency or "unknown").lower()
        agg.setdefault(key, {})[cur] = agg.setdefault(key, {}).get(cur, 0.0) + _as_float(total)

    out = []
    for i in range(days):
        day = (since + timedelta(days=i)).date().isoformat()
        day_data = agg.get(day, {})
        out.append(AdminRevenueDailyResponse(
            date=day,
            total_usd=round(day_data.get("usd", 0.0), 2),
            total_xtr=round(day_data.get("xtr", 0.0), 2),
        ))
    return out


# ---------------------------------------------------------------- channels


@router.get("/channels", response_model=list[AdminChannelResponse])
async def admin_channels(session: AsyncSession = Depends(get_session)) -> list[AdminChannelResponse]:
    channels = (await session.execute(select(Channel).order_by(Channel.id))).scalars().all()
    out = []
    for ch in channels:
        plans_count = (await session.scalar(
            select(func.count(Plan.id)).where(Plan.channel_id == ch.id)
        )) or 0
        active_subs = (await session.scalar(
            select(func.count(Subscription.id))
            .where(Subscription.channel_id == ch.id, Subscription.status == "active")
        )) or 0
        revenue = (await session.scalar(
            select(func.sum(Payment.amount))
            .join(Subscription, Payment.subscription_id == Subscription.id)
            .where(Subscription.channel_id == ch.id, Payment.status == "paid", Payment.currency == "USD")
        )) or 0
        out.append(AdminChannelResponse(
            id=ch.id,
            title=ch.title,
            telegram_chat_id=ch.telegram_chat_id,
            is_active=ch.is_active,
            plans_count=plans_count,
            active_subscriptions=active_subs,
            revenue=_as_float(revenue),
        ))
    return out


@router.patch("/channels/{channel_id}", response_model=AdminChannelResponse)
async def admin_update_channel(
    channel_id: int,
    payload: AdminChannelPatch,
    session: AsyncSession = Depends(get_session),
) -> AdminChannelResponse:
    ch = await session.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    if payload.title is not None:
        ch.title = payload.title
    if payload.is_active is not None:
        ch.is_active = payload.is_active
    await session.commit()
    return AdminChannelResponse(
        id=ch.id,
        title=ch.title,
        telegram_chat_id=ch.telegram_chat_id,
        is_active=ch.is_active,
        plans_count=(await session.scalar(select(func.count(Plan.id)).where(Plan.channel_id == ch.id))) or 0,
        active_subscriptions=(await session.scalar(
            select(func.count(Subscription.id))
            .where(Subscription.channel_id == ch.id, Subscription.status == "active")
        )) or 0,
        revenue=0.0,
    )


@router.delete("/channels/{channel_id}")
async def admin_delete_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    ch = await session.get(Channel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    await session.delete(ch)
    await session.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------- plans


@router.patch("/plans/{plan_id}")
async def admin_update_plan(
    plan_id: int,
    payload: AdminPlanPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if payload.title is not None:
        plan.title = payload.title
    if payload.duration_days is not None:
        plan.duration_days = payload.duration_days
    if payload.price_usd is not None:
        plan.price_usd = Decimal(str(payload.price_usd))
    if payload.price_stars is not None:
        plan.price_stars = payload.price_stars
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    await session.commit()
    return {"id": plan.id, "title": plan.title, "duration_days": plan.duration_days,
            "price_usd": _as_float(plan.price_usd), "price_stars": plan.price_stars,
            "is_active": plan.is_active}


@router.delete("/plans/{plan_id}")
async def admin_delete_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await session.delete(plan)
    await session.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------- subscriptions


@router.get("/subscriptions")
async def admin_subscriptions(
    status: str | None = None,
    channel_id: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    q = select(Subscription).join(User).join(Channel).join(Plan, isouter=True)
    count_q = select(func.count(Subscription.id))
    if status:
        q = q.where(Subscription.status == status)
        count_q = count_q.where(Subscription.status == status)
    if channel_id is not None:
        q = q.where(Subscription.channel_id == channel_id)
        count_q = count_q.where(Subscription.channel_id == channel_id)

    total = (await session.scalar(count_q)) or 0
    rows = (await session.execute(
        q.order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    now = datetime.now(UTC)
    items = []
    for s in rows:
        await session.refresh(s, ["user", "channel", "plan"])
        expires = s.expires_at
        now = datetime.now(UTC)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        days_remaining = max(0, (expires - now).days)
        items.append(AdminSubscriptionResponse(
            id=s.id,
            user_telegram_id=s.user.telegram_id,
            username=s.user.username,
            channel_title=s.channel.title,
            plan_title=s.plan.title if s.plan else None,
            status=s.status,
            days_remaining=days_remaining,
            started_at=s.started_at,
            expires_at=s.expires_at,
        ))

    return {"total": total, "page": page, "per_page": per_page, "items": items}


# ---------------------------------------------------------------- broadcast


@router.post("/broadcast", response_model=AdminBroadcastResponse)
async def admin_broadcast(
    payload: AdminBroadcastRequest,
    session: AsyncSession = Depends(get_session),
) -> AdminBroadcastResponse:
    from app.models.broadcast import BroadcastLog

    log = BroadcastLog(
        text=payload.text,
        channel_id=payload.channel_id,
        sent_count=0,
        failed_count=0,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return AdminBroadcastResponse(
        id=log.id, text=log.text, channel_id=log.channel_id,
        sent_count=log.sent_count, failed_count=log.failed_count, created_at=log.created_at,
    )


@router.patch("/broadcast/{broadcast_id}", response_model=AdminBroadcastResponse)
async def admin_broadcast_patch(
    broadcast_id: int,
    payload: AdminBroadcastPatch,
    session: AsyncSession = Depends(get_session),
) -> AdminBroadcastResponse:
    from app.models.broadcast import BroadcastLog

    log = await session.get(BroadcastLog, broadcast_id)
    if not log:
        raise HTTPException(status_code=404, detail="Broadcast log not found")
    if payload.sent_count is not None:
        log.sent_count = payload.sent_count
    if payload.failed_count is not None:
        log.failed_count = payload.failed_count
    await session.commit()
    await session.refresh(log)
    return AdminBroadcastResponse(
        id=log.id, text=log.text, channel_id=log.channel_id,
        sent_count=log.sent_count, failed_count=log.failed_count, created_at=log.created_at,
    )


# ---------------------------------------------------------------- CSV export


@router.get("/export/subscriptions.csv")
async def admin_export_subscriptions_csv(
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    rows = (await session.execute(
        select(Subscription).join(User).join(Channel).join(Plan, isouter=True)
        .order_by(Subscription.id)
    )).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "user_telegram_id", "username", "channel_title", "plan_title",
        "status", "started_at", "expires_at", "created_at",
    ])
    for s in rows:
        await session.refresh(s, ["user", "channel", "plan"])
        writer.writerow([
            s.id,
            s.user.telegram_id,
            s.user.username or "",
            s.channel.title or "",
            s.plan.title if s.plan else "",
            s.status,
            s.started_at.isoformat(),
            s.expires_at.isoformat(),
            s.created_at.isoformat(),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscriptions.csv"},
    )


@router.get("/users/count")
async def users_count(session: AsyncSession = Depends(get_session)) -> dict:
    """Total registered users (for the dashboard KPI card)."""
    total = (await session.execute(select(func.count(User.id)))).scalar() or 0
    return {"count": int(total)}


@router.get("/payments/by-provider")
async def payments_by_provider(session: AsyncSession = Depends(get_session)) -> list:
    """Paid payment totals grouped by provider (for the doughnut chart)."""
    rows = (
        await session.execute(
            select(
                Payment.provider,
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.amount), 0.0),
            )
            .where(Payment.status == "paid")
            .group_by(Payment.provider)
        )
    ).all()
    return [
        {"provider": provider, "count": int(count), "total": float(total)}
        for provider, count, total in rows
    ]


@router.get("/payments")
async def recent_payments(
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list:
    """Most recent payments with user info (dashboard table)."""
    rows = (
        await session.execute(
            select(Payment)
            .options(joinedload(Payment.user))
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for p in rows:
        out.append({
            "id": p.id,
            "user_telegram_id": p.user.telegram_id if p.user else None,
            "username": p.user.username if p.user else None,
            "amount": float(p.amount),
            "currency": p.currency,
            "provider": p.provider,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return out
