"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import channels, dashboard, payments, stats
from app.api.v1 import bot_admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(bot_admin.router)
api_router.include_router(channels.router)
api_router.include_router(payments.router)
api_router.include_router(payments.members_router)
api_router.include_router(stats.router)
api_router.include_router(dashboard.router)
