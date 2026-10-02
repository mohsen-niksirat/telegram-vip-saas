"""Pydantic v2 API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    """Payload to create a channel."""

    telegram_chat_id: int = Field(..., description="Telegram chat id, typically -100...")
    title: str = Field(..., min_length=1, max_length=255)


class PlanCreate(BaseModel):
    """Payload to create a plan for a channel."""

    channel_id: int
    title: str = Field(..., min_length=1, max_length=255)
    duration_days: int = Field(..., gt=0)
    price_usd: float = Field(..., ge=0)
    price_stars: int = Field(..., ge=0)


class ManualAdd(BaseModel):
    """Payload for manually granting a VIP membership."""

    telegram_id: int
    admin_telegram_id: int = 0
    channel_id: int
    days: int = Field(..., gt=0)


class StatsResponse(BaseModel):
    """Channel statistics response."""

    channel_id: int
    title: str
    active_subscriptions: int
    revenue_usd: float
    revenue_xtr: int


class PaymentWebhookAck(BaseModel):
    """Acknowledgement returned by payment webhooks."""

    status: str = "ok"
    detail: str | None = None


# ---- Admin dashboard schemas ----


class AdminRecentPayment(BaseModel):
    """Recent payment entry in the admin overview."""

    id: int
    user_telegram_id: int | None = None
    username: str | None = None
    amount: float
    currency: str
    provider: str
    status: str
    created_at: datetime


class AdminOverviewResponse(BaseModel):
    """Aggregated admin dashboard overview."""

    channels: int
    plans: int
    users: int
    active_subscriptions: int
    expired_subscriptions: int
    revenue_usd: float
    revenue_xtr: float
    revenue_ton: float
    payments_count: int
    recent_payments: list[AdminRecentPayment]


class AdminRevenueDailyResponse(BaseModel):
    """Daily revenue point (missing days are zero-filled)."""

    date: str
    total_usd: float
    total_xtr: float


class AdminChannelResponse(BaseModel):
    """Channel with per-channel dashboard aggregates."""

    id: int
    title: str | None
    telegram_chat_id: int
    is_active: bool
    plans_count: int
    active_subscriptions: int
    revenue: float


class AdminChannelPatch(BaseModel):
    """Fields to update on a channel."""

    title: str | None = None
    is_active: bool | None = None


class AdminPlanPatch(BaseModel):
    """Fields to update on a plan."""

    title: str | None = None
    duration_days: int | None = Field(None, gt=0)
    price_usd: float | None = Field(None, ge=0)
    price_stars: int | None = Field(None, ge=0)
    is_active: bool | None = None


class AdminSubscriptionResponse(BaseModel):
    """Subscription with user/channel/plan info."""

    id: int
    user_telegram_id: int
    username: str | None = None
    channel_title: str | None = None
    plan_title: str | None = None
    status: str
    days_remaining: int
    started_at: datetime
    expires_at: datetime


class AdminBroadcastRequest(BaseModel):
    """Broadcast request payload."""

    text: str = Field(..., min_length=1, max_length=4096)
    channel_id: int | None = None


class AdminBroadcastPatch(BaseModel):
    """Update broadcast delivery counters."""

    sent_count: int | None = Field(None, ge=0)
    failed_count: int | None = Field(None, ge=0)


class AdminBroadcastResponse(BaseModel):
    """Broadcast log entry."""

    id: int
    text: str
    channel_id: int | None = None
    sent_count: int
    failed_count: int
    created_at: datetime
