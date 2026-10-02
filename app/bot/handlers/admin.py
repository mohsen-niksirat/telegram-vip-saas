"""Admin handlers: stats and guided add-channel / add-plan flows (FSM)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.keyboards.inline import cancel_kb, t
from app.config import settings
from app.core.database import get_session
from app.models.channel import Channel
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.channel_service import check_bot_admin, get_or_create_bot

logger = logging.getLogger(__name__)
router = Router(name="admin")


def is_admin(telegram_id: int) -> bool:
    """Return True if the Telegram id is in ADMIN_TELEGRAM_IDS."""
    return telegram_id in settings.ADMIN_TELEGRAM_IDS


class AddChannelStates(StatesGroup):
    """FSM states for the add-channel flow."""

    waiting_chat_id = State()


class AddPlanStates(StatesGroup):
    """FSM states for the add-plan flow."""

    waiting_channel_id = State()
    waiting_title = State()
    waiting_duration = State()
    waiting_price_usd = State()
    waiting_price_stars = State()


@router.message(F.text.startswith("/admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    """Admin dashboard: stats and action buttons (admins only)."""
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    async for session in get_session():
        channels = (await session.execute(select(func.count(Channel.id)))).scalar() or 0
        active_subs = (
            await session.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))
        ).scalar() or 0
        usd = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                    Payment.status == "paid", Payment.currency == "USD"
                )
            )
        ).scalar() or 0.0
        xtr = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == "paid", Payment.currency == "XTR"
                )
            )
        ).scalar() or 0
        text = (
            f"🛠 <b>Admin</b>\n\n"
            f"📢 Channels: {channels}\n"
            f"✅ Active subs: {active_subs}\n"
            f"💵 Revenue (USD): {float(usd):.2f}\n"
            f"⭐ Revenue (XTR): {int(xtr)}\n\n"
            f"/addchannel — add a channel\n"
            f"/addplan — add a plan"
        )
        await message.answer(text, reply_markup=cancel_kb(message.from_user))
    # no-op to keep loop semantics clear


@router.message(F.text.startswith("/addchannel"))
async def cmd_add_channel(message: Message, state: FSMContext) -> None:
    """Start guided add-channel flow: ask for chat id."""
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddChannelStates.waiting_chat_id)
    await message.answer(
        "Send the channel chat id (e.g. <code>-1001234567890</code> or <code>@username</code>):",
        reply_markup=cancel_kb(message.from_user),
    )


@router.message(AddChannelStates.waiting_chat_id, F.text)
async def add_channel_chat_id(message: Message, state: FSMContext) -> None:
    """Validate bot admin rights and create the channel."""
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit() and not raw.startswith("@"):
        await message.answer("Invalid chat id. Send a numeric id like <code>-100...</code> or @username.")
        return
    await state.clear()
    async for session in get_session():
        bot_instance = await get_or_create_bot(session)
        try:
            ok = await check_bot_admin(session, bot=bot_instance, chat_id=raw)
        except Exception as exc:  # noqa: BLE001 - surface Telegram errors to admin
            await message.answer(f"⚠️ Telegram error: {exc}")
            return
        if not ok:
            await message.answer("⚠️ Bot is not an admin of that chat. Add it as admin and retry.")
            return
        chat = await bot_instance.get_chat(raw)
        existing = (
            await session.execute(select(Channel).where(Channel.telegram_chat_id == chat.id))
        ).scalar_one_or_none()
        if existing:
            existing.is_active = True
            existing.title = chat.title or chat.username or str(chat.id)
            channel = existing
        else:
            channel = Channel(
                admin_id=message.from_user.id,
                telegram_chat_id=chat.id,
                title=chat.title or chat.username or str(chat.id),
                is_active=True,
            )
            session.add(channel)
        await session.commit()
        await message.answer(f"✅ Channel saved: <b>{channel.title}</b> (id {channel.id})")


@router.message(F.text.startswith("/addplan"))
async def cmd_add_plan(message: Message, state: FSMContext) -> None:
    """Start guided add-plan flow."""
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddPlanStates.waiting_channel_id)
    await message.answer("Send the internal channel id (see /admin or DB):", reply_markup=cancel_kb(message.from_user))


@router.message(AddPlanStates.waiting_channel_id, F.text)
async def add_plan_channel(message: Message, state: FSMContext) -> None:
    """Store channel id, ask for plan title."""
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("Send a numeric channel id.")
        return
    async for session in get_session():
        channel = await session.get(Channel, int(message.text.strip()))
        if not channel:
            await message.answer("Channel not found.")
            return
    await state.update_data(channel_id=int(message.text.strip()))
    await state.set_state(AddPlanStates.waiting_title)
    await message.answer("Plan title:")


@router.message(AddPlanStates.waiting_title, F.text)
async def add_plan_title(message: Message, state: FSMContext) -> None:
    """Store title, ask for duration."""
    await state.update_data(title=message.text.strip())
    await state.set_state(AddPlanStates.waiting_duration)
    await message.answer("Duration in days:")


@router.message(AddPlanStates.waiting_duration, F.text)
async def add_plan_duration(message: Message, state: FSMContext) -> None:
    """Store duration, ask for USD price."""
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("Send a positive integer (days).")
        return
    await state.update_data(duration_days=int(message.text.strip()))
    await state.set_state(AddPlanStates.waiting_price_usd)
    await message.answer("Price in USD (e.g. 9.99):")


@router.message(AddPlanStates.waiting_price_usd, F.text)
async def add_plan_price_usd(message: Message, state: FSMContext) -> None:
    """Store USD price, ask for Stars price."""
    try:
        price_usd = float(message.text.strip())
        if price_usd < 0:
            raise ValueError
    except ValueError:
        await message.answer("Send a valid non-negative number.")
        return
    await state.update_data(price_usd=price_usd)
    await state.set_state(AddPlanStates.waiting_price_stars)
    await message.answer("Price in Telegram Stars (integer):")


@router.message(AddPlanStates.waiting_price_stars, F.text)
async def add_plan_price_stars(message: Message, state: FSMContext) -> None:
    """Create the plan from collected FSM data."""
    if not message.text.strip().isdigit():
        await message.answer("Send a non-negative integer (Stars).")
        return
    data = await state.get_data()
    await state.clear()
    async for session in get_session():
        plan = Plan(
            channel_id=data["channel_id"],
            title=data["title"],
            duration_days=data["duration_days"],
            price_usd=data["price_usd"],
            price_stars=int(message.text.strip()),
            is_active=True,
        )
        session.add(plan)
        await session.commit()
        await message.answer(f"✅ Plan saved: <b>{plan.title}</b> (id {plan.id})")


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel any admin FSM flow."""
    await state.clear()
    await callback.answer(t(callback.from_user, "cancel"))
