"""Application settings loaded from environment variables / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Telegram VIP subscription SaaS."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram bot
    BOT_TOKEN: str

    # Comma-separated list of Telegram user IDs with admin access.
    ADMIN_TELEGRAM_IDS: str = ""

    # Database (asyncpg driver by default).
    DATABASE_URL: str = "postgresql+asyncpg://vip:vip@db:5432/vip"

    # Public base URLs used for webhook registration and the mini-app.
    WEBHOOK_BASE_URL: str = ""
    WEBAPP_BASE_URL: str = ""

    # Payment providers (optional).
    CRYPTOMUS_API_KEY: str = ""
    CRYPTOMUS_MERCHANT_ID: str = ""
    NOWPAYMENTS_API_KEY: str = ""

    # Bearer token for the admin REST API.
    API_TOKEN: str

    # Referral reward: bonus days granted to the referrer per active-subscription channel.
    REFERRAL_BONUS_DAYS: int = 3


settings = Settings()
