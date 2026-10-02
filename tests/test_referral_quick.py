"""Quick sqlite test for register_referral: created, self-ref blocked, duplicate blocked."""
import asyncio
import os

os.environ.setdefault("BOT_TOKEN", "123:TEST")
os.environ.setdefault("API_TOKEN", "x")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models import Referral, User  # noqa: E402,F401
from app.bot.handlers.social import register_referral  # noqa: E402


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        session.add_all([User(telegram_id=100), User(telegram_id=200)])
        await session.commit()

        assert await register_referral(session, 100, 100) == "self", "self-ref not blocked"
        assert await register_referral(session, 100, 200) == "created", "valid referral failed"
        assert await register_referral(session, 100, 200) == "duplicate", "duplicate not blocked"
        assert await register_referral(session, 999, 300) == "no_referrer"
        rows = (await session.execute(__import__("sqlalchemy").select(Referral))).scalars().all()
        assert len(rows) == 1 and rows[0].referrer_id == 1 and rows[0].referred_id == 2
        assert rows[0].reward_days == 3
        await session.commit()
    print("sqlite referral test PASSED")


asyncio.run(main())
