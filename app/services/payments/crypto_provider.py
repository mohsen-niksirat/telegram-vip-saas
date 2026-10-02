"""Provider-agnostic crypto payment provider: Cryptomus and NOWPayments.

The active provider is chosen by which API key is configured in settings:
- CRYPTOMUS_API_KEY (with CRYPTOMUS_MERCHANT_ID) -> Cryptomus USDT invoices
- NOWPAYMENTS_API_KEY -> NOWPayments USD invoices

Webhook signature verification assumptions (documented per task spec):
- Cryptomus: signature = HMAC-MD5(raw_request_body, CRYPTOMUS_API_KEY),
  sent in the ``sign`` header.
- NOWPayments: signature = HMAC-SHA512(sorted_json_body, IPN secret). We
  reuse NOWPAYMENTS_API_KEY as the IPN secret since the schema exposes no
  separate IPN secret field; the body is re-serialized with sorted keys.
"""

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import aiohttp

from app.config import settings
from app.models.plan import Plan

logger = logging.getLogger(__name__)

CRYPTOMUS_URL = "https://api.cryptomus.com/v1/payment"
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/invoice"


def _active_provider() -> str:
    """Return 'cryptomus', 'nowpayments', or raise if none is configured."""
    if getattr(settings, "CRYPTOMUS_API_KEY", None):
        return "cryptomus"
    if getattr(settings, "NOWPAYMENTS_API_KEY", None):
        return "nowpayments"
    raise RuntimeError("No crypto payment provider configured (Cryptomus or NOWPayments)")


async def create_invoice(plan: Plan, order_id: str, callback_url: str | None = None) -> dict[str, Any]:
    """Create a crypto invoice for `plan`.

    Returns a dict containing at least 'payment_url' and 'invoice_id'.
    """
    provider = _active_provider()
    amount = str(plan.price_usd)
    if provider == "cryptomus":
        return await _create_cryptomus_invoice(plan, order_id, amount, callback_url)
    return await _create_nowpayments_invoice(plan, order_id, amount, callback_url)


async def _create_cryptomus_invoice(
    plan: Plan, order_id: str, amount: str, callback_url: str | None
) -> dict[str, Any]:
    """Create a USDT invoice via Cryptomus (HMAC-MD5 signed request)."""
    api_key = settings.CRYPTOMUS_API_KEY
    merchant = settings.CRYPTOMUS_MERCHANT_ID
    body = {
        "amount": amount,
        "currency": "USDT",
        "order_id": order_id,
        "url_callback": callback_url,
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    sign = hmac.new(api_key.encode(), base64.b64encode(raw), hashlib.md5).hexdigest()

    headers = {
        "merchant": merchant or "",
        "sign": sign,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(CRYPTOMUS_URL, data=raw, headers=headers) as resp:
            data = await resp.json()
    logger.info("Cryptomus invoice created order_id=%s status=%s", order_id, data.get("state"))
    result = data.get("result", data)
    return {
        "payment_url": result.get("url"),
        "invoice_id": result.get("uuid") or result.get("invoice_id"),
        "provider": "cryptomus",
        "raw": data,
    }


async def _create_nowpayments_invoice(
    plan: Plan, order_id: str, amount: str, callback_url: str | None
) -> dict[str, Any]:
    """Create a USD invoice via NOWPayments (x-api-key header)."""
    body = {
        "price_amount": float(amount),
        "price_currency": "usd",
        "order_id": order_id,
        "ipn_callback_url": callback_url,
        "order_description": plan.title,
    }
    headers = {
        "x-api-key": settings.NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(NOWPAYMENTS_URL, json=body, headers=headers) as resp:
            data = await resp.json()
    logger.info("NOWPayments invoice created order_id=%s id=%s", order_id, data.get("id"))
    return {
        "payment_url": data.get("invoice_url"),
        "invoice_id": data.get("id"),
        "provider": "nowpayments",
        "raw": data,
    }


async def verify_webhook_signature(
    provider: str, raw_body: bytes, signature: str | None
) -> bool:
    """Verify a provider webhook signature over the raw request body.

    - Cryptomus: HMAC-MD5(body, CRYPTOMUS_API_KEY) compared to `signature`.
    - NOWPayments: HMAC-SHA512(sorted-JSON body, NOWPAYMENTS_API_KEY used as
      the IPN secret) compared to `signature`.
    Returns False on missing signature, unparseable JSON, or mismatch.
    """
    if not signature:
        logger.warning("%s webhook missing signature", provider)
        return False

    if provider == "cryptomus":
        expected = hmac.new(
            settings.CRYPTOMUS_API_KEY.encode(), raw_body, hashlib.md5
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    if provider == "nowpayments":
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error("NOWPayments webhook body is not valid JSON")
            return False
        sorted_body = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            settings.NOWPAYMENTS_API_KEY.encode(), sorted_body.encode(), hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    logger.error("Unknown crypto provider: %s", provider)
    return False
