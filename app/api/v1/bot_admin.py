"""Bot admin endpoints: broadcast dispatch, broadcast log listing, log viewer."""

from __future__ import annotations

import logging
from collections import deque

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import verify_api_token
from app.core.database import get_session
from app.models.broadcast import BroadcastLog
from app.services.broadcast_service import send_broadcast
from app.services.channel_service import get_or_create_bot

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/botadmin", tags=["bot-admin"], dependencies=[Depends(verify_api_token)]
)


# ------------------------------------------------------------- log buffer
class InMemoryLogHandler(logging.Handler):
    """Keep the last N formatted log records in a bounded deque."""

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self.buffer: deque[str] = deque(maxlen=maxlen)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append(self.format(record))
        except Exception:  # noqa: BLE001 - never break logging
            self.handleError(record)


_log_handler = InMemoryLogHandler()
logging.getLogger().addHandler(_log_handler)


# ------------------------------------------------------------- endpoints
@router.post("/broadcast/{broadcast_id}/send")
async def send_broadcast_by_id(
    broadcast_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Dispatch a recorded broadcast immediately; update sent/failed counts."""
    log = await session.get(BroadcastLog, broadcast_id)
    if not log:
        raise HTTPException(status_code=404, detail="Broadcast log not found")
    try:
        bot = await get_or_create_bot()
        counts = await send_broadcast(bot, session, log.text, log.channel_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Broadcast id=%s dispatch failed: %s", broadcast_id, exc)
        raise HTTPException(status_code=502, detail=f"Broadcast failed: {exc}") from exc
    log.sent_count = counts["sent"]
    log.failed_count = counts["failed"]
    await session.commit()
    return {"id": log.id, "sent": counts["sent"], "failed": counts["failed"]}


@router.get("/broadcast")
async def list_broadcasts(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List recorded broadcast logs (newest first)."""
    result = await session.execute(
        select(BroadcastLog).order_by(BroadcastLog.id.desc())
    )
    return [
        {
            "id": log.id,
            "text": log.text,
            "channel_id": log.channel_id,
            "sent_count": log.sent_count,
            "failed_count": log.failed_count,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in result.scalars().all()
    ]


@router.get("/logs")
async def get_logs() -> list[str]:
    """Return the last 100 lines of the in-memory log buffer."""
    return list(_log_handler.buffer)[-100:]
