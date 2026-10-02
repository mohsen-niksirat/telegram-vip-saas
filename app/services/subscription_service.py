"""Subscription lifecycle service: users, activation, renewals, expiry."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> User:
    """Fetch a user by telegram_id, creating/updating profile fields if missing."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username, full_name=full_name)
        session.add(user)
        await session.flush()
        logger.info("Created new user telegram_id=%s", telegram_id)
    elif username is not None or full_name is not None:
        user.username = username or user.username
        user.full_name = full_name or user.full_name
    return user


async def activate_subscription(
    session: AsyncSession,
    user: User,
    channel: Channel,
    plan: Plan,
    provider: str,
    provider_tx_id: str | None,
    amount: float,
    currency: str,
    raw_payload: dict,
) -> tuple[Subscription, Payment]:
    """Record a paid Payment and activate or renew a Subscription.

    If the user already has an active subscription for the channel, its
    expires_at is extended (status 'renewed'); otherwise a new active
    subscription is created. Commits the session.
    """
    now = datetime.now(timezone.utc)

    payment = Payment(
        subscription_id=None,
        user_id=user.id,
        amount=amount,
        currency=currency,
        provider=provider,
        provider_tx_id=provider_tx_id,
        status="paid",
        raw_payload=raw_payload,
    )
    session.add(payment)
    await session.flush()

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.channel_id == channel.id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
    )
    sub = result.scalar_one_or_none()

    if sub is not None:
        base = sub.expires_at
        sub.expires_at = base + timedelta(days=plan.duration_days)
        sub.plan_id = plan.id
        sub.status = "renewed"
        sub.reminder_sent = False
        logger.info(
            "Renewed subscription=%s for user=%s until=%s", sub.id, user.id, sub.expires_at
        )
    else:
        sub = Subscription(
            user_id=user.id,
            channel_id=channel.id,
            plan_id=plan.id,
            status="active",
            started_at=now,
            expires_at=now + timedelta(days=plan.duration_days),
            reminder_sent=False,
        )
        session.add(sub)
        logger.info(
            "Activated new subscription for user=%s channel=%s until=%s",
            user.id, channel.id, sub.expires_at,
        )

    await session.flush()
    payment.subscription_id = sub.id
    await session.commit()
    await session.refresh(sub)
    return sub, payment


async def get_active_subscriptions(session: AsyncSession, user: User) -> Sequence[Subscription]:
    """All subscriptions of a user currently active or renewed."""
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["active", "renewed"]),
        )
    )
    return result.scalars().all()


async def get_expiring_subscriptions(
    session: AsyncSession, hours: int = 48
) -> Sequence[Subscription]:
    """Active subscriptions expiring within `hours` that have not had a reminder."""
    deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
    result = await session.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.reminder_sent.is_(False),
            Subscription.expires_at <= deadline,
        )
    )
    return result.scalars().all()


async def get_expired_subscriptions(session: AsyncSession) -> Sequence[Subscription]:
    """Active-status subscriptions whose expires_at has already passed."""
    result = await session.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.expires_at < datetime.now(timezone.utc),
        )
    )
    return result.scalars().all()


async def manual_grant(
    session: AsyncSession,
    admin: User,
    user_telegram_id: int,
    channel: Channel,
    days: int,
) -> Subscription:
    """Admin-granted subscription: create new or extend by `days` (as renewal)."""
    now = datetime.now(timezone.utc)
    user = await get_or_create_user(session, user_telegram_id)

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.channel_id == channel.id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
    )
    sub = result.scalar_one_or_none()

    if sub is not None:
        sub.expires_at += timedelta(days=days)
        sub.status = "renewed"
        sub.reminder_sent = False
        logger.info(
            "Admin=%s extended subscription=%s by %sd", admin.id, sub.id, days
        )
    else:
        sub = Subscription(
            user_id=user.id,
            channel_id=channel.id,
            plan_id=None,
            status="active",
            started_at=now,
            expires_at=now + timedelta(days=days),
            reminder_sent=False,
        )
        session.add(sub)
        logger.info(
            "Admin=%s granted %sd in channel=%s to telegram_id=%s",
            admin.id, days, channel.id, user_telegram_id,
        )

    await session.commit()
    await session.refresh(sub)
    return sub
