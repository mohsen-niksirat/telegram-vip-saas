"""Start, deep-link, channel-list, plan-detail and subscriptions handlers."""

from __future__ import annotations

import datetime as dt
import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.social import register_referral
from app.bot.keyboards.inline import channels_kb, plans_kb, subscriptions_kb, t
from app.config import settings
from app.core.database import get_session
from app.models.channel import Channel
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscription_service import get_or_create_user

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _fetch_channels(session: AsyncSession) -> list[Channel]:
    """Return all active channels."""
    result = await session.execute(
        select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id)
    )
    return list(result.scalars().all())


async def _fetch_plans(session: AsyncSession, channel_id: int) -> list[Plan]:
    """Return active plans for a channel."""
    result = await session.execute(
        select(Plan)
        .where(Plan.channel_id == channel_id, Plan.is_active.is_(True))
        .order_by(Plan.id)
    )
    return list(result.scalars().all())


async def _fetch_subs(session: AsyncSession, user: User) -> list[tuple[Subscription, Channel]]:
    """Return the user's active subscriptions joined with channels."""
    result = await session.execute(
        select(Subscription, Channel)
        .join(Channel, Subscription.channel_id == Channel.id)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.expires_at)
    )
    return [(sub, ch) for sub, ch in result.all()]


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject | None = None) -> None:
    """Handle /start, jumping straight to a plan screen via deep-link payload."""
    payload = (command.args or "").strip() if command else ""
    async for session in get_session():
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        if payload.startswith("ref_"):
            try:
                referrer_tg = int(payload[len("ref_"):])
            except ValueError:
                referrer_tg = 0
            if referrer_tg:
                result_status = await register_referral(
                    session, referrer_tg, message.from_user.id
                )
                if result_status == "created":
                    await message.answer(t(message.from_user, "ref_welcome"))

        plan: Plan | None = None
        channel: Channel | None = None

        if payload.startswith("channel_") and "_plan_" in payload:
            try:
                _, ch_part, _, plan_part = payload.split("_")
                channel_id, plan_id = int(ch_part), int(plan_part)
            except ValueError:
                channel_id = plan_id = 0
            if channel_id and plan_id:
                result = await session.execute(
                    select(Plan, Channel)
                    .join(Channel, Plan.channel_id == Channel.id)
                    .where(Plan.id == plan_id, Plan.is_active.is_(True))
                )
                row = result.first()
                if row:
                    plan, channel = row

        if plan and channel:
            await message.answer(
                t(message.from_user, "plan_detail", title=plan.title, days=plan.duration_days, usd=plan.price_usd, stars=plan.price_stars),
                reply_markup=plans_kb(channel, [plan], user=message.from_user),
            )
            return

        channels = await _fetch_channels(session)
        if not channels:
            await message.answer(t(message.from_user, "channels_empty"))
            return
        await message.answer(
            t(message.from_user, "welcome"), reply_markup=channels_kb(channels, user=message.from_user)
        )


@router.callback_query(F.data.startswith("plans:"))
async def cb_plans(callback: CallbackQuery) -> None:
    """Show plans for a channel: ``plans:<channel_id>``."""
    channel_id = int(callback.data.split(":")[1])
    async for session in get_session():
        result = await session.execute(
            select(Channel).where(Channel.id == channel_id, Channel.is_active.is_(True))
        )
        channel = result.scalar_one_or_none()
        plans = await _fetch_plans(session, channel_id) if channel else []
        if not channel or not plans:
            await callback.answer(t(callback.from_user, "plans_empty"), show_alert=True)
            return
        await callback.message.edit_text(
            t(callback.from_user, "plans_title", title=channel.title),
            reply_markup=plans_kb(channel, plans, user=callback.from_user),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan(callback: CallbackQuery) -> None:
    """Show a plan detail screen: ``plan:<plan_id>``."""
    plan_id = int(callback.data.split(":")[1])
    async for session in get_session():
        result = await session.execute(
            select(Plan, Channel)
            .join(Channel, Plan.channel_id == Channel.id)
            .where(Plan.id == plan_id)
        )
        row = result.first()
        if not row:
            await callback.answer(t(callback.from_user, "plans_empty"), show_alert=True)
            return
        plan, channel = row
        await callback.message.edit_text(
            t(callback.from_user, "plan_detail", title=plan.title, days=plan.duration_days, usd=plan.price_usd, stars=plan.price_stars),
            reply_markup=plans_kb(channel, [plan], user=callback.from_user),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mysubs"))
async def cb_my_subscriptions(callback: CallbackQuery) -> None:
    """List the user's active subscriptions with remaining days."""
    async for session in get_session():
        user = await get_or_create_user(session, telegram_id=callback.from_user.id)
        rows = await _fetch_subs(session, user)
        if not rows:
            await callback.message.edit_text(t(callback.from_user, "subs_empty"))
            await callback.answer()
            return
        now = dt.datetime.now(dt.timezone.utc)
        lines = [t(callback.from_user, "my_subs")]
        for sub, channel in rows:
            expires = sub.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=dt.timezone.utc)
            days = max(0, (expires - now).days)
            lines.append(
                t(callback.from_user, "sub_item", title=channel.title, status=sub.status, days=days, expires=expires.strftime("%Y-%m-%d"))
            )
        await callback.message.edit_text("\n".join(lines), reply_markup=subscriptions_kb(rows, user=callback.from_user))
    await callback.answer()


@router.callback_query(F.data == "back:channels")
async def cb_back_channels(callback: CallbackQuery) -> None:
    """Return to the channel list."""
    async for session in get_session():
        channels = await _fetch_channels(session)
        if not channels:
            await callback.answer(t(callback.from_user, "channels_empty"), show_alert=True)
            return
        await callback.message.edit_text(
            t(callback.from_user, "welcome"), reply_markup=channels_kb(channels, user=callback.from_user)
        )
    await callback.answer()


def is_admin(telegram_id: int) -> bool:
    """Check whether a Telegram id belongs to the configured admin list."""
    return telegram_id in settings.ADMIN_TELEGRAM_IDS
