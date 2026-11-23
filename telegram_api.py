import json
import logging
from typing import Any

import httpx

from config import BOT_TOKEN, CHAT_ID, APPLE_PRODUCT_URL, PRODUCTS, STORES

logger = logging.getLogger(__name__)
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def send_message(client: httpx.AsyncClient, text: str) -> None:
    response = await client.post(
        f"{API_BASE}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {payload.get('description', 'unknown error')}")


async def get_webhook_info(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(f"{API_BASE}/getWebhookInfo", timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram getWebhookInfo failed")
    return payload.get("result", {})


async def get_updates(client: httpx.AsyncClient, offset: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "timeout": 25,
        "allowed_updates": json.dumps(["message"]),
    }
    if offset is not None:
        params["offset"] = offset
    response = await client.get(
        f"{API_BASE}/getUpdates",
        params=params,
        timeout=35,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {payload.get('description', 'unknown error')}")
    return payload.get("result", [])


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "duration unknown"
    minutes, seconds = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def to_uae_time(value: str | None) -> str:
    if not value:
        return "not yet checked"
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(ZoneInfo("Asia/Dubai")).strftime("%d %b %Y, %I:%M:%S %p UAE")
    except (ValueError, TypeError):
        return str(value)


async def send_restock_alert(client: httpx.AsyncClient, event: dict[str, Any]) -> None:
    store = STORES[event["store_id"]]
    product = PRODUCTS[event["part_number"]]
    message = (
        "🚨 APPLE IPHONE DUO RESTOCK DETECTED!\n\n"
        f"📱 {product['name']}\n"
        f"🎨 Colour: {product['colour']}\n"
        f"📍 Apple {store['name']} — {store['city']}\n"
        f"🕒 Detected: {to_uae_time(event['observed_at'])}\n\n"
        "✅ Apple's pickup status changed to AVAILABLE.\n"
        f"🛒 Check and order: {APPLE_PRODUCT_URL}\n\n"
        "Stock can change before checkout; availability is not a reservation."
    )
    await send_message(client, message)
