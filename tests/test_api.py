"""API integration tests (runnable with pytest or plain: python tests/test_api.py).

Covers: admin overview, revenue/daily, channels list, plan PATCH/DELETE,
subscriptions pagination, broadcast create + botadmin list, CSV export,
dashboard SPA + assets, crypto webhook bad-signature rejection, and the
Telegram webhook token check.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "111,222")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("WEBHOOK_BASE_URL", "")
os.environ.setdefault("REFERRAL_BONUS_DAYS", "3")

import httpx  # noqa: E402
from sqlalchemy import JSON  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.database import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    BroadcastLog,
    Channel,
    Payment,
    Plan,
    Subscription,
    User,
)
from datetime import UTC, datetime, timedelta  # noqa: E402

TOKEN = {"X-API-Token": os.environ["API_TOKEN"]}

passed: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        raise AssertionError(f"FAIL: {name} {extra}")
    passed.append(name)
    print(f"  ok - {name}")


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    # sqlite cannot compile postgres JSONB; swap for generic JSON before DDL.
    for col in Base.metadata.tables["payments"].columns:
        if "JSONB" in type(col.type).__name__:
            col.type = JSON()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Seed data -----------------------------------------------------------
    async with Session() as s:
        user = User(telegram_id=42, username="tester", full_name="Test User")
        s.add(user)
        await s.flush()
        ch = Channel(admin_id=user.id, telegram_chat_id=-100123, title="VIP Channel")
        s.add(ch)
        await s.flush()
        plan = Plan(
            channel_id=ch.id, title="1 month", duration_days=30,
            price_usd=9.99, price_stars=500, is_active=True,
        )
        s.add(plan)
        await s.flush()
        sub = Subscription(
            user_id=user.id, channel_id=ch.id, plan_id=plan.id,
            status="active",
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        s.add(sub)
        await s.flush()
        s.add(Payment(
            subscription_id=sub.id, user_id=user.id, amount=9.99,
            currency="USD", provider="cryptomus", provider_tx_id="tx-1",
            status="paid",
        ))
        s.add(BroadcastLog(text="Hello VIPs!", sent_count=0, failed_count=0))
        await s.commit()
        ids = {"channel": ch.id, "plan": plan.id, "sub": sub.id, "user": user.id}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # Overview ---------------------------------------------------------
        r = await c.get("/api/v1/admin/overview", headers=TOKEN)
        check("overview 200", r.status_code == 200)
        ov = r.json()
        check("overview revenue_usd > 0", ov.get("revenue_usd", 0) > 0, str(ov.get("revenue_usd")))
        check("overview counts", ov["channels"] == 1 and ov["plans"] == 1 and ov["users"] == 1)

        # Auth required ----------------------------------------------------
        r = await c.get("/api/v1/admin/overview")
        check("overview rejected without token", r.status_code in (401, 422))
        r = await c.get("/api/v1/admin/overview", headers={"X-API-Token": "wrong"})
        check("overview unauthorized bad token", r.status_code == 401)

        # Revenue daily ----------------------------------------------------
        r = await c.get("/api/v1/admin/revenue/daily", headers=TOKEN)
        check("revenue/daily 200", r.status_code == 200)
        daily = r.json()
        check("revenue/daily has today with usd", any(d["total_usd"] > 0 for d in daily))

        # Channels list ----------------------------------------------------
        r = await c.get("/api/v1/admin/channels", headers=TOKEN)
        check("channels list 200", r.status_code == 200)
        check("channels list has channel", len(r.json()) == 1)

        # Plans PATCH/DELETE -----------------------------------------------
        extra_plan = Plan(
            channel_id=ids["channel"], title="temp", duration_days=7,
            price_usd=1.0, price_stars=100, is_active=True,
        )
        async with Session() as s:
            s.add(extra_plan)
            await s.commit()
            extra_id = extra_plan.id
        r = await c.patch(f"/api/v1/admin/plans/{extra_id}", headers=TOKEN,
                          json={"title": "week", "price_usd": 2.5, "is_active": False})
        check("plan PATCH 200", r.status_code == 200 and r.json()["title"] == "week")
        r = await c.delete(f"/api/v1/admin/plans/{extra_id}", headers=TOKEN)
        check("plan DELETE 200", r.status_code == 200)
        r = await c.patch(f"/api/v1/admin/plans/{extra_id}", headers=TOKEN, json={"title": "x"})
        check("plan 404 after delete", r.status_code == 404)

        # Subscriptions pagination -----------------------------------------
        r = await c.get("/api/v1/admin/subscriptions", headers=TOKEN,
                        params={"page": 1, "per_page": 1})
        check("subscriptions 200", r.status_code == 200)
        body = r.json()
        check("subscriptions pagination", body["total"] >= 1 and len(body["items"]) == 1
              and body["per_page"] == 1)

        # Broadcast create + botadmin list ----------------------------------
        r = await c.post("/api/v1/admin/broadcast", headers=TOKEN, json={"text": "Test blast"})
        check("broadcast create 200", r.status_code == 200)
        bid = r.json()["id"]
        r = await c.get("/api/v1/botadmin/broadcast", headers=TOKEN)
        check("botadmin broadcast list 200", r.status_code == 200 and
              any(b["id"] == bid for b in r.json()))
        r = await c.get("/api/v1/botadmin/logs", headers=TOKEN)
        check("botadmin logs 200", r.status_code == 200)

        # CSV export ---------------------------------------------------------
        r = await c.get("/api/v1/admin/export/subscriptions.csv", headers=TOKEN)
        check("export csv 200", r.status_code == 200)
        check("export csv content", "user_telegram_id" in r.text and "42" in r.text)

        # Dashboard SPA ------------------------------------------------------
        r = await c.get("/dashboard")
        check("dashboard 200", r.status_code == 200 and "text/html" in r.headers["content-type"])
        for asset in ("style.css", "app.js"):
            r = await c.get(f"/dashboard/assets/{asset}")
            check(f"dashboard asset {asset}", r.status_code == 200)

        # Health -------------------------------------------------------------
        r = await c.get("/healthz")
        check("healthz 200", r.status_code == 200)

        # Crypto webhook: bad signature rejected ------------------------------
        r = await c.post("/api/v1/payments/crypto/webhook",
                         json={"provider": "cryptomus", "order_id": "tx-1", "status": "paid"})
        check("crypto webhook missing signature rejected", r.status_code == 400)
        r = await c.post("/api/v1/payments/crypto/webhook", headers={"sign": "bad"},
                         json={"provider": "cryptomus", "order_id": "tx-1", "status": "paid"})
        check("crypto webhook bad signature rejected", r.status_code == 400)

        # Telegram webhook: wrong token rejected ------------------------------
        r = await c.post("/webhook/wrong-token", json={"update_id": 1})
        check("telegram webhook bad token rejected", r.status_code == 403)

    await engine.dispose()
    print(f"\nALL {len(passed)} ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
