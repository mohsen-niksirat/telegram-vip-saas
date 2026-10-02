# Telegram VIP Subscription SaaS

A production-ready Telegram bot platform for selling VIP access to private
channels. Admins register channels and define subscription plans; users pay
with **Telegram Stars** or **crypto** (Cryptomus / NOWPayments) and receive a
single-use invite link with a time-limited subscription. Includes a web admin
dashboard, broadcast tooling, a referral program, and a REST API.

## Features

- **Telegram bot UX** — start flow, plan browsing, payment selection, invite-link
  fulfillment, subscription status, referral commands (aiogram 3, webhook or polling mode).
- **Payments** — Telegram Stars (XTR) plus Cryptomus and NOWPayments crypto
  invoices; signature-verified, idempotent webhooks.
- **Auto fulfillment** — on payment confirmation the bot creates a single-use
  VIP invite link and DMs it to the buyer.
- **Auto-kick** — a scheduled job (APScheduler) removes members whose
  subscription has expired and sends expiry reminders.
- **Referral system** — each referred user's first active subscription grants the
  referrer bonus subscription days (`REFERRAL_BONUS_DAYS`).
- **Web dashboard** — server-rendered SPA at `/dashboard` with login via API token.
- **Broadcast** — create and dispatch messages to all users (optionally per channel).
- **REST API** — full admin API under `/api/v1` (see API reference below).
- **Scheduler** — APScheduler background jobs for expiry reminders and auto-kick.

## Architecture

```
                       ┌──────────────────────────────────────────────┐
Telegram servers ─────► │  FastAPI (uvicorn, port 8000)                │
  (webhook updates)     │  ├── POST /webhook/{token}  → aiogram dp     │
                       │  ├── /api/v1/admin/*  admin REST API         │
Browser ──────────────► │  ├── /api/v1/botadmin/*  broadcast/logs      │
  (dashboard SPA)      │  ├── /dashboard  SPA (login with API token)   │
Crypto providers ─────► │  ├── /api/v1/payments/crypto/webhook          │
  (signed callbacks)   │  └── /healthz                                 │
                       │        │            │                         │
                       │  APScheduler   aiogram Bot                   │
                       │  (auto-kick,    (invite links,               │
                       │   reminders)     messages)                   │
                       └───────┬──────────────────────────────────────┘
                               │ async SQLAlchemy 2.0
                        ┌──────▼──────┐
                        │ PostgreSQL  │  (sqlite+aiosqlite for local tests)
                        │  (alembic)  │
                        └─────────────┘
```

Module map:

- `app/config.py` — pydantic-settings `Settings` singleton loaded from `.env`.
- `app/core/database.py` — async engine, `SessionLocal`, `get_session`, shared `Base`.
- `app/models/` — SQLAlchemy 2.0 models: `User`, `Channel`, `Plan`, `Subscription`,
  `Payment`, `BroadcastLog`, `Referral` (JSONB payloads, timezone-aware timestamps,
  cascade rules).
- `app/api/v1/` — REST API routers (channels, payments/members, stats, dashboard
  admin API, bot admin).
- `app/bot/` — aiogram handlers, bot instance, webhook/polling setup.
- `app/services/` — business logic (subscriptions, payments providers, channels, broadcasts).
- `app/tasks/` — APScheduler jobs (reminders, auto-kick).
- `app/dashboard/` — SPA router serving `/dashboard` and its static assets.
- `alembic/` — async migrations wired to `Base.metadata` and `DATABASE_URL`.

Logging uses **python-json-logger** for structured JSON logs in production.

## Quickstart (Docker)

```bash
cp .env.example .env    # fill in BOT_TOKEN, API_TOKEN, ADMIN_TELEGRAM_IDS, ...
docker compose up --build
```

- `migrate` service runs `alembic upgrade head` before the app starts.
- `db` is Postgres 16 with a `pg_isready` healthcheck; data persists in the `pgdata` volume.
- App listens on `http://localhost:8000`; dashboard at `http://localhost:8000/dashboard`.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # set BOT_TOKEN, API_TOKEN; leave WEBHOOK_BASE_URL empty for polling

# For local testing you can use SQLite (no Postgres needed):
#   DATABASE_URL=sqlite+aiosqlite:///./local.db
# Note: production uses Postgres (JSONB payloads); SQLite works for dev/tests only.

alembic upgrade head
uvicorn app.main:app --reload
```

Run the test suite (plain asyncio scripts, no pytest required):

```bash
python tests/test_api.py
python tests/test_referral_quick.py
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Bot token from @BotFather. |
| `API_TOKEN` | ✅ | — | Admin API token; sent as `X-API-Token` header and used to log into the dashboard. |
| `ADMIN_TELEGRAM_IDS` | — | `""` | Comma-separated Telegram user IDs with admin access in the bot. |
| `DATABASE_URL` | — | `postgresql+asyncpg://vip:vip@db:5432/vip` | Async SQLAlchemy URL (`asyncpg` in prod, `aiosqlite` for tests). |
| `WEBHOOK_BASE_URL` | — | `""` | Public HTTPS base URL where Telegram sends updates. If empty, the bot uses **long polling**. |
| `WEBAPP_BASE_URL` | — | `""` | Public URL of the Telegram mini-app / web app. |
| `CRYPTOMUS_API_KEY` | — | `""` | Cryptomus API key (enables Cryptomus invoices). |
| `CRYPTOMUS_MERCHANT_ID` | — | `""` | Cryptomus merchant UUID. |
| `NOWPAYMENTS_API_KEY` | — | `""` | NOWPayments API key (also used as the IPN secret for webhook signatures). |
| `REFERRAL_BONUS_DAYS` | — | `3` | Bonus days granted to the referrer per referred user's active subscription. |

## BotFather setup (step by step)

1. **Create the bot** — message [@BotFather](https://t.me/BotFather) → `/newbot`,
   pick a name and username, and copy the token into `BOT_TOKEN` in `.env`.
2. **Web app domain** — if you use the Telegram mini-app, run `/newapp` (or
   `/setdomain`) in @BotFather and set the domain to the host of
   `WEBAPP_BASE_URL`. Telegram requires HTTPS with a valid certificate.
3. **Payments (Stars)** — Telegram Stars work out of the box with
   `send_invoice(currency="XTR")`; enable payments via @BotFather if prompted.
4. **Set the webhook** — with a public HTTPS endpoint, set `WEBHOOK_BASE_URL`;
   the app registers the webhook on startup. Without it, the bot falls back to
   long polling (fine for local development, not for production).
5. **Admins** — put your numeric Telegram user ID(s) into `ADMIN_TELEGRAM_IDS`.

### Channel admin rights

For each channel you sell, **add the bot as an administrator** with:

- **Invite Users via Link** — required to create the single-use VIP invite links
  that are sent after payment.
- **Ban Users** — required by the auto-kick job to remove members whose
  subscription has expired.

Other admin permissions can stay off (least privilege). The channel must be
registered via `POST /api/v1/channels` or the bot's admin flow; registration
verifies the bot is actually an admin of that chat.

## Dashboard

1. Open `https://your-host/dashboard`.
2. Log in with `API_TOKEN` (the value of the `API_TOKEN` env var — the browser
   stores it and sends it as the `X-API-Token` header on every API call).
3. From the dashboard you can view the overview (users, active subs, revenue by
   currency), daily revenue charts, manage channels and plans, browse
   subscriptions (paginated), export subscriptions as CSV, and compose broadcasts.

## Referral flow

1. User B joins with a referral link (`/start ref_<userA_id>`): the
   `(referrer, referred)` pair is recorded once; self-referrals and duplicates
   are rejected.
2. When the referred user purchases any plan and their subscription becomes
   active, the referrer receives `REFERRAL_BONUS_DAYS` extra days on their own
   active subscription for that channel.

## API reference

All endpoints except `/healthz`, `/dashboard*`, `POST /webhook/{token}` and
`POST /api/v1/payments/crypto/webhook` require the header `X-API-Token: $API_TOKEN`.

### Channels & plans (`/api/v1`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/channels` | Register a channel (verifies the bot is an admin of the chat). |
| `POST` | `/api/v1/channels/plans` | Create a plan for a channel. |
| `GET` | `/api/v1/channels/{id}/stats` | Active subs + revenue (USD/XTR) for a channel. |
| `GET` | `/api/v1/stats/summary` | Global stats (channels, plans, subs, revenue by currency). |

### Payments & members (`/api/v1`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/payments/crypto/webhook` | **Public.** Crypto provider callback; signature-verified, idempotent. |
| `POST` | `/api/v1/members/manual-add` | Manually grant a subscription to a user. |
| `POST` | `/api/v1/members/{payment_id}/retry` | Retry fulfillment for a payment. |

### Admin dashboard API (`/api/v1/admin`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/overview` | Counts + revenue by currency + 10 recent payments. |
| `GET` | `/api/v1/admin/revenue/daily?days=30` | Daily revenue series (USD/XTR), 1–365 days. |
| `GET` | `/api/v1/admin/channels` | Channels with plan/sub counts and revenue. |
| `PATCH` | `/api/v1/admin/channels/{id}` | Update channel title / active flag. |
| `DELETE` | `/api/v1/admin/channels/{id}` | Delete a channel. |
| `PATCH` | `/api/v1/admin/plans/{id}` | Update plan (title, duration, prices, active). |
| `DELETE` | `/api/v1/admin/plans/{id}` | Delete a plan. |
| `GET` | `/api/v1/admin/subscriptions?status=&channel_id=&page=&per_page=` | Paginated subscriptions. |
| `POST` | `/api/v1/admin/broadcast` | Create a broadcast record. |
| `PATCH` | `/api/v1/admin/broadcast/{id}` | Update sent/failed counters. |
| `GET` | `/api/v1/admin/export/subscriptions.csv` | CSV export of all subscriptions. |
| `GET` | `/api/v1/admin/users/count` | User count. |
| `GET` | `/api/v1/admin/payments/by-provider` | Revenue grouped by provider. |
| `GET` | `/api/v1/admin/payments` | Payment list. |

### Bot admin (`/api/v1/botadmin`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/botadmin/broadcast/{id}/send` | Dispatch a stored broadcast via the bot. |
| `GET` | `/api/v1/botadmin/broadcast` | List broadcast logs (newest first). |
| `GET` | `/api/v1/botadmin/logs` | Last 100 in-memory log lines. |

### Misc

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness probe (`{"status": "ok"}`). |
| `POST` | `/webhook/{token}` | **Public.** Telegram updates; path token must equal `BOT_TOKEN`. |
| `GET` | `/dashboard` | Dashboard SPA (login with `API_TOKEN`). |
| `GET` | `/dashboard/assets/{file}` | Dashboard static assets. |

Interactive OpenAPI docs: `/docs` and `/redoc` when the app is running.

## Backups

The database is the single source of truth. With the Docker setup:

```bash
# Backup
docker compose exec db pg_dump -U vip vip > backup_$(date +%F).sql

# Restore
cat backup_2026-01-01.sql | docker compose exec -T db psql -U vip vip
```

Schedule daily `pg_dump` runs (cron or your backup tool) and store copies off
the host. The `pgdata` named volume alone is not a backup strategy.

## Security notes

- **API token** — every admin/botadmin endpoint requires `X-API-Token` matching
  `API_TOKEN`. Use a long random value; never commit the real `.env`.
- **Dashboard auth** — the dashboard authenticates with the same token; serve
  over HTTPS only so the header cannot be sniffed.
- **Webhook signature** — `/api/v1/payments/crypto/webhook` verifies an HMAC
  signature over the raw body (Cryptomus: HMAC-MD5 with `CRYPTOMUS_API_KEY`;
  NOWPayments: HMAC-SHA512 over sorted JSON with `NOWPAYMENTS_API_KEY`) and is
  idempotent per `provider_tx_id`; forged callbacks are rejected with 400.
- **Telegram webhook** — `/webhook/{token}` rejects any path token other than
  the bot token (403). Keep `WEBHOOK_BASE_URL` on HTTPS; Telegram refuses to
  deliver updates over plain HTTP.
- **Least privilege** — give the bot only *Invite Users* + *Ban Users* channel
  admin rights.
- **DB access** — the Docker Postgres is bound on 5432 for development; in
  production remove the `ports` mapping for `db` and keep it on the compose
  internal network.
