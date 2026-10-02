"""APScheduler background jobs: renewal reminders and expired-member kicks."""

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.channel import Channel
from app.models.subscription import Subscription
from app.models.user import User
from app.services.channel_service import get_or_create_bot, kick_member
from app.services.subscription_service import (
    get_expiring_subscriptions,
    get_expired_subscriptions,
)

logger = logging.getLogger(__name__)

try:  # defensive: broadcast service must not break scheduler startup
    from app.services.broadcast_service import run_pending_broadcasts
except ImportError:  # pragma: no cover
    run_pending_broadcasts = None
    logger.warning("run_pending_broadcasts unavailable; pending broadcast job disabled")


_scheduler: AsyncIOScheduler | None = None


async def send_renewal_reminders() -> None:
    """DM users whose subscriptions expire within 48h (once per subscription)."""
    async with SessionLocal() as session:
        subs = await get_expiring_subscriptions(session, hours=48)
        if not subs:
            return
        bot = await get_or_create_bot()
        for sub in subs:
            try:
                result = await session.execute(
                    select(User).where(User.id == sub.user_id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    logger.error("Reminder: user=%s not found for sub=%s", sub.user_id, sub.id)
                    continue
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Renew VIP", callback_data=f"renew:{sub.id}")]
                    ]
                )
                expires = sub.expires_at
                if isinstance(expires, datetime) and expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                await bot.send_message(
                    user.telegram_id,
                    f"⏰ Your VIP subscription expires soon "
                    f"({expires:%Y-%m-%d %H:%M} UTC). Renew now to keep access!",
                    reply_markup=kb,
                )
                sub.reminder_sent = True
                await session.commit()
                logger.info("Renewal reminder sent for sub=%s", sub.id)
            except Exception:
                logger.exception("Failed to send renewal reminder for sub=%s", sub.id)


async def kick_expired_members() -> None:
    """Kick members whose subscriptions expired and mark subscriptions 'kicked'."""
    async with SessionLocal() as session:
        subs = await get_expired_subscriptions(session)
        if not subs:
            return
        bot = await get_or_create_bot()
        for sub in subs:
            try:
                result = await session.execute(
                    select(User).where(User.id == sub.user_id)
                )
                user = result.scalar_one_or_none()
                channel_result = await session.execute(
                    select(Channel).where(Channel.id == sub.channel_id)
                )
                channel = channel_result.scalar_one_or_none()
                if user is None or channel is None:
                    logger.error(
                        "Kick: missing user=%s or channel=%s for sub=%s",
                        sub.user_id, sub.channel_id, sub.id,
                    )
                    continue

                await kick_member(bot, channel, user)
                sub.status = "kicked"
                await session.commit()

                try:
                    await bot.send_message(
                        user.telegram_id,
                        "🔒 Your VIP subscription has expired and you were removed "
                        "from the channel. Use /start to subscribe again!",
                    )
                except Exception:
                    logger.error("Could not notify user=%s of expiry", user.id)
                logger.info("Kicked expired member sub=%s", sub.id)
            except Exception:
                logger.exception("Failed to kick expired member for sub=%s", sub.id)


async def run_pending_broadcasts_job() -> None:
    """Dispatch recorded broadcasts with sent_count==0 and failed_count==0."""
    if run_pending_broadcasts is None:
        return
    try:
        bot = await get_or_create_bot()
        async with SessionLocal() as session:
            await run_pending_broadcasts(session, bot)
    except Exception:
        logger.error("Pending broadcasts job failed", exc_info=True)


def start_scheduler() -> AsyncIOScheduler:
    """Start the AsyncIOScheduler with the two 30-minute jobs (idempotent)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        send_renewal_reminders, "interval", minutes=30, id="renewal_reminders"
    )
    _scheduler.add_job(
        kick_expired_members, "interval", minutes=30, id="kick_expired"
    )
    _scheduler.add_job(
        run_pending_broadcasts_job, "interval", minutes=10, id="pending_broadcasts"
    )
    _scheduler.start()
    logger.info(
        "Scheduler started (renewal reminders + expired kicks every 30 min, "
        "pending broadcasts every 10 min)"
    )
    return _scheduler


async def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
        _scheduler = None
