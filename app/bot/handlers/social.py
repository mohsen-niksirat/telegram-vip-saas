"""Referral handlers: /myref, referral registration and bonus claiming."""
from __future__ import annotations

import datetime as dt
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import t
from app.config import settings
from app.core.database import get_session
from app.models.channel import Channel
from app.models.referral import Referral
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscription_service import get_or_create_user

logger = logging.getLogger(__name__)
router = Router(name="social")


async def register_referral(
    session: AsyncSession, referrer_tg: int, referred_tg: int
) -> str:
    """Store a referral row. Returns 'created', 'self', 'duplicate' or 'no_referrer'."""
    if referrer_tg == referred_tg:
        return "self"
    referrer = (
        await session.execute(select(User).where(User.telegram_id == referrer_tg))
    ).scalar_one_or_none()
    if referrer is None:
        return "no_referrer"
    referred = (
        await session.execute(select(User).where(User.telegram_id == referred_tg))
    ).scalar_one_or_none()
    if referred is None:
        return "no_referrer"
    existing = (
        await session.execute(select(Referral).where(Referral.referred_id == referred.id))
    ).scalar_one_or_none()
    if existing is not None:
        return "duplicate"
    session.add(
        Referral(referrer_id=referrer.id, referred_id=referred.id, reward_days=settings.REFERRAL_BONUS_DAYS)
    )
    await session.flush()
    logger.info("Referral registered: referrer=%s referred=%s", referrer_tg, referred_tg)
    return "created"


async def claim_referral_bonuses(session: AsyncSession, user: User) -> int:
    """Grant pending referral bonus days to each active-subscription channel of ``user``.

    Returns the number of bonuses applied. Rows stay pending if the user has no
    active subscriptions yet (claimable later).
    """
    rows = (
        await session.execute(
            select(Referral).where(Referral.referrer_id == user.id, Referral.bonus_applied.is_(False))
        )
    ).scalars().all()
    if not rows:
        return 0
    now_user_subs = (
        await session.execute(
            select(Subscription.channel_id).where(
                Subscription.user_id == user.id, Subscription.status == "active"
            )
        )
    ).scalars().all()
    if not now_user_subs:
        return 0
    applied = 0
    for row in rows:
        for channel_id in now_user_subs:
            sub = (
                await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user.id,
                        Subscription.channel_id == channel_id,
                        Subscription.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if sub is None:
                continue
            sub.expires_at = sub.expires_at + dt.timedelta(days=row.reward_days)
            sub.status = "renewed"
            sub.reminder_sent = False
            applied += 1
        row.bonus_applied = True
    await session.flush()
    logger.info("Applied %s referral bonuses for user=%s", applied, user.telegram_id)
    return applied


@router.message(Command("myref"))
async def cmd_myref(message: Message) -> None:
    """Show the user's referral link, referral count and bonus status."""
    async for session in get_session():
        user = await get_or_create_user(session, telegram_id=message.from_user.id)
        count = (
            await session.execute(
                select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id)
            )
        ).scalar_one()
        pending = (
            await session.execute(
                select(func.count())
                .select_from(Referral)
                .where(Referral.referrer_id == user.id, Referral.bonus_applied.is_(False))
            )
        ).scalar_one()
        bot_info = await message.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
        applied = await claim_referral_bonuses(session, user)
        await session.commit()
        if pending and applied:
            bonus_note = t(message.from_user, "ref_bonus_claimed", days=applied * settings.REFERRAL_BONUS_DAYS)
        elif pending:
            bonus_note = t(message.from_user, "ref_bonus_pending", count=pending)
        else:
            bonus_note = t(message.from_user, "ref_bonus_claimed", days=0) if count else ""
        await message.answer(
            t(message.from_user, "myref")
            + "\n\n"
            + t(message.from_user, "ref_link", link=link)
            + "\n"
            + t(message.from_user, "ref_count", count=count)
            + ("\n" + bonus_note if bonus_note else "")
        )
