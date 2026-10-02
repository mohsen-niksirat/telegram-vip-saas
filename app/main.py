"""FastAPI application entrypoint: lifespan, webhook/polling, scheduler, health."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, HTTPException, Request
from aiogram.types import Update

from app.api.v1.router import api_router
from app.bot.bot_instance import bot, dp, setup_polling, setup_webhook
from app.config import settings
from app.tasks.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLLING_TASK_NAME = "bot-polling"


async def _import_models() -> None:
    """Import all model modules so ``Base.metadata`` is fully populated."""
    import app.models.channel  # noqa: F401
    import app.models.payment  # noqa: F401
    import app.models.plan  # noqa: F401
    import app.models.subscription  # noqa: F401
    import app.models.user  # noqa: F401


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: init DB, bot mode, scheduler."""
    await _import_models()

    # Create tables if not managed by Alembic (idempotent).
    try:
        from app.core.database import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001 - don't block startup on schema ops
        logger.warning("Could not run create_all: %s", exc)

    polling_task: asyncio.Task | None = None
    try:
        if settings.WEBHOOK_BASE_URL:
            await setup_webhook(bot)
            logger.info("Webhook mode active")
        else:
            polling_task = asyncio.create_task(setup_polling(bot), name=POLLING_TASK_NAME)
            logger.info("Polling mode active")
        start_scheduler()
        yield
    finally:
        if polling_task and not polling_task.done():
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task
        await shutdown_scheduler()
        with contextlib.suppress(Exception):
            await bot.session.close()


app = FastAPI(title="Telegram VIP SaaS", version="1.0.0", lifespan=lifespan)
app.include_router(api_router)


def _include_optional_routers() -> None:
    """Include dashboard API + SPA routers if their modules are present."""
    try:
        from app.api.v1 import dashboard as dashboard_api

        app.include_router(dashboard_api.router)
        logger.info("Included admin dashboard API router")
    except ImportError as exc:
        logger.warning("Dashboard API module not available: %s", exc)

    try:
        from app.dashboard import get_dashboard_router

        app.include_router(get_dashboard_router())
        logger.info("Included dashboard SPA router")
    except Exception as exc:  # noqa: BLE001 - SPA assets may be mid-build
        logger.warning("Dashboard SPA router not available: %s", exc)


_include_optional_routers()


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request) -> dict:
    """Receive Telegram updates; token must match the bot token."""
    if not token or token != settings.BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}
