"""Inline keyboard builders and bilingual (FA/EN) string helpers."""

from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from app.config import settings
from app.models.channel import Channel
from app.models.plan import Plan

TEXT: dict[str, dict[str, str]] = {
    "fa": {
        "welcome": "👋 خوش آمدید!\n\nکانال مورد نظر خود را انتخاب کنید:",
        "channels_empty": "در حال حاضر کانالی موجود نیست. بعداً مراجعه کنید.",
        "plans_title": "🎁 پلن‌های عضویت ویژه «{title}»:",
        "plans_empty": "پلنی برای این کانال تعریف نشده است.",
        "plan_detail": "📋 <b>{title}</b>\n⏳ مدت: {days} روز\n💵 قیمت: {usd:.2f} دلار\n⭐ قیمت: {stars} ستاره\n\nروش پرداخت را انتخاب کنید:",
        "my_subs": "📋 اشتراک‌های شما:",
        "sub_item": "📢 <b>{title}</b>\nوضعیت: {status}\nروز باقی‌مانده: {days}\nانقضا: {expires}\n",
        "subs_empty": "شما اشتراک فعالی ندارید.",
        "renew": "🔄 تمدید «{title}» — پلن را انتخاب کنید:",
        "back": "🔙 بازگشت",
        "cancel": "❌ انصراف",
        "my_subs_btn": "📋 اشتراک‌های من",
        "pay_stars": "⭐ پرداخت با ستاره",
        "pay_crypto": "💳 پرداخت ارز دیجیتال",
        "invoice_sent": "فاکتور ستاره‌ای ارسال شد. لطفاً پرداخت را تکمیل کنید.",
        "precheck_failed": "پرداخت تأیید نشد. دوباره تلاش کنید.",
        "congrats": "🎉 <b>پرداخت با موفقیت انجام شد!</b>\n\nلینک عضویت:\n{link}\n\nاین لینک یک‌بار مصرف است.\nانقضای اشتراک: {expires}",
        "crypto_order": "🧾 فاکتور ارز دیجیتال برای «{title}» ایجاد شد.\n\nمبلغ: {amount:.2f} دلار\n\nبرای پرداخت روی دکمه بزنید:",
        "pay_now": "💳 پرداخت",
        "renewing": "در حال آماده‌سازی تمدید...",
        "myref": "🎁 <b>دعوت دوستان</b>\n\nلینک دعوت اختصاصی خود را با دوستان به اشتراک بگذارید:",
        "ref_link": "🔗 لینک دعوت: {link}",
        "ref_count": "👥 تعداد دعوت‌های موفق: {count}",
        "ref_bonus_claimed": "✅ {days} روز پاداش به اشتراک‌های فعال شما اضافه شد.",
        "ref_bonus_pending": "⏳ پاداش {count} دعوت پس از خرید اشتراک فعال اعمال می‌شود.",
        "ref_welcome": "🎁 خوش آمدید! شما با لینک دعوت وارد شدید.",
        "open_app": "🚀 فروشگاه VIP",
    },
    "en": {
        "welcome": "👋 Welcome!\n\nChoose a channel:",
        "channels_empty": "No channels available yet. Please check back later.",
        "plans_title": "🎁 VIP plans for «{title}»:",
        "plans_empty": "No plans configured for this channel yet.",
        "plan_detail": "📋 <b>{title}</b>\n⏳ Duration: {days} days\n💵 Price: ${usd:.2f}\n⭐ Price: {stars} Stars\n\nChoose a payment method:",
        "my_subs": "📋 Your subscriptions:",
        "sub_item": "📢 <b>{title}</b>\nStatus: {status}\nDays remaining: {days}\nExpires: {expires}\n",
        "subs_empty": "You have no active subscriptions.",
        "renew": "🔄 Renew «{title}» — pick a plan:",
        "back": "🔙 Back",
        "cancel": "❌ Cancel",
        "my_subs_btn": "📋 My subscriptions",
        "pay_stars": "⭐ Pay with Stars",
        "pay_crypto": "💳 Pay with Crypto",
        "invoice_sent": "Stars invoice sent. Please complete the payment.",
        "precheck_failed": "Payment could not be confirmed. Please try again.",
        "congrats": "🎉 <b>Payment successful!</b>\n\nYour invite link:\n{link}\n\nThis link is single-use.\nSubscription expires: {expires}",
        "crypto_order": "🧾 Crypto invoice created for «{title}».\n\nAmount: ${amount:.2f}\n\nTap the button below to pay:",
        "pay_now": "💳 Pay now",
        "renewing": "Preparing your renewal...",
        "myref": "🎁 <b>Invite friends</b>\n\nShare your personal referral link:",
        "ref_link": "🔗 Referral link: {link}",
        "ref_count": "👥 Successful referrals: {count}",
        "ref_bonus_claimed": "✅ {days} bonus days added to your active subscriptions.",
        "ref_bonus_pending": "⏳ Bonus for {count} referral(s) applies after you hold an active subscription.",
        "ref_welcome": "🎁 Welcome! You joined via a referral link.",
        "open_app": "🚀 Open VIP Store",
    },
}


def lang_of(user: object) -> str:
    """Detect language: 'fa' for Persian speakers, otherwise 'en'."""
    code = getattr(user, "language_code", None) or ""
    return "fa" if code.startswith("fa") else "en"


def t(user: object, key: str, **kwargs: object) -> str:
    """Translate ``key`` for ``user`` with optional ``str.format`` kwargs."""
    template = TEXT[lang_of(user)].get(key) or TEXT["en"].get(key) or key
    return template.format(**kwargs) if kwargs else template


def channels_kb(channels: list, user: object) -> InlineKeyboardMarkup:
    """Keyboard listing channels: callback ``plans:<channel_id>`` + My subscriptions."""
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.button(text=f"📢 {ch.title}", callback_data=f"plans:{ch.id}")
    kb.button(text=t(user, "my_subs_btn"), callback_data="mysubs")
    if settings.WEBAPP_BASE_URL:
        from aiogram.types import WebAppInfo

        kb.button(text=t(user, "open_app"), web_app=WebAppInfo(url=settings.WEBAPP_BASE_URL))
    kb.adjust(1)
    return kb.as_markup()


def plans_kb(channel: Channel, plans: list, user: object) -> InlineKeyboardMarkup:
    """Plan list with payment buttons and back navigation."""
    kb = InlineKeyboardBuilder()
    for plan in plans:
        kb.button(text=f"🎟 {plan.title} · {plan.duration_days}d", callback_data=f"plan:{plan.id}")
        kb.row()
    if len(plans) == 1:
        plan = plans[0]
        kb.button(text=t(user, "pay_stars"), callback_data=f"stars:{plan.id}")
        kb.button(text=t(user, "pay_crypto"), callback_data=f"crypto:{plan.id}")
        kb.adjust(2)
        kb.row()
    kb.button(text=t(user, "back"), callback_data="back:channels")
    kb.adjust(1)
    return kb.as_markup()


def payment_kb(plan: Plan, user: object) -> InlineKeyboardMarkup:
    """Payment method buttons for a plan (Stars / Crypto) plus cancel."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t(user, "pay_stars"), callback_data=f"stars:{plan.id}")
    kb.button(text=t(user, "pay_crypto"), callback_data=f"crypto:{plan.id}")
    kb.button(text=t(user, "cancel"), callback_data="back:channels")
    kb.adjust(2, 1)
    return kb.as_markup()


def subscriptions_kb(subs: list, user: object) -> InlineKeyboardMarkup:
    """Keyboard for subscription list with renew buttons: ``renew:<sub_id>``."""
    kb = InlineKeyboardBuilder()
    for sub, _channel in subs:
        kb.button(text=f"🔄 {getattr(_channel, 'title', 'VIP')}", callback_data=f"renew:{sub.id}")
    kb.button(text=t(user, "back"), callback_data="back:channels")
    kb.adjust(1)
    return kb.as_markup()


def renew_kb(sub_id: int, user: object) -> InlineKeyboardMarkup:
    """Renew button for a subscription."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t(user, "pay_crypto"), callback_data=f"renew:{sub_id}")
    kb.button(text=t(user, "cancel"), callback_data="back:channels")
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb(user: object) -> InlineKeyboardMarkup:
    """Single cancel/back button."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t(user, "cancel"), callback_data="back:channels")
    return kb.as_markup()
