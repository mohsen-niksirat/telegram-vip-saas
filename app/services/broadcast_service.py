"""Broadcast service: send messages to subscribers and dispatch pending logs."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)

_SEND_DELAY_SECONDS = 0.05


async def send_broadcast(
    bot,
    session: AsyncSession,
    text: str,
    channel_id: int | None,
) -> dict:
    """Send ``text`` to users with an active/renewed subscription.

    If ``channel_id`` is None, all users are targeted. Returns
    ``{"sent": n, "failed": m}``.
    """
    query = select(User.telegram_id).distinct()
    if channel_id is not None:
        query = query.join(
            Subscription, Subscription.user_id == User.id
        ).where(
            Subscription.channel_id == channel_id,
            Subscription.status.in_(["active", "renewed"]),
        )
    result = await session.execute(query)
    telegram_ids = [row[0] for row in result.all()]

    sent = failed = 0
    from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

    for tg_id in telegram_ids:
        try:
            await bot.send_message(chat_id=tg_id, text=text)
            sent += 1
        except TelegramForbiddenError:
            logger.info("Broadcast: user %s blocked the bot", tg_id)
            failed += 1
        except TelegramAPIError as exc:
            logger.warning("Broadcast: failed to message user %s: %s", tg_id, exc)
            failed += 1
        except Exception as exc:  # noqa: BLE001 - keep broadcast going
            logger.warning("Broadcast: unexpected error for user %s: %s", tg_id, exc)
            failed += 1
        await asyncio.sleep(_SEND_DELAY_SECONDS)

    logger.info("Broadcast complete: sent=%d failed=%d", sent, failed)
    return {"sent": sent, "failed": failed}


async def run_pending_broadcasts(session: AsyncSession, bot) -> None:
    """Dispatch BroadcastLog rows with sent_count==0 and failed_count==0.

    BroadcastLog lives in app.api.v1.dashboard; if that module doesn't
    define it, this is a no-op.
    """
    try:
        from app.api.v1.dashboard import BroadcastLog
    except ImportError:
        logger.debug("BroadcastLog model unavailable; skipping pending broadcasts")
        return

    result = await session.execute(
        select(BroadcastLog).where(
            BroadcastLog.sent_count == 0, BroadcastLog.failed_count == 0
        )
    )
    pending = result.scalars().all()
    if not pending:
        return

    from app.core.database import SessionLocal  # best-effort session per log

    for entry in pending:
        try:
            async with SessionLocal() as inner:
                counts = await send_broadcast(
                    bot, inner, entry.text, getattr(entry, "channel_id", None)
                )
            entry.sent_count = counts["sent"]
            entry.failed_count = counts["failed"]
            await session.commit()
            logger.info(
                "Dispatched pending broadcast log id=%s sent=%d failed=%d",
                getattr(entry, "id", "?"), counts["sent"], counts["failed"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pending broadcast id=%s failed: %s", getattr(entry, "id", "?"), exc)
