import logging
from datetime import datetime, timezone
from typing import Any

import httpx

import database
from config import CHAT_ID, CHECK_INTERVAL, PRODUCTS, STORES
from telegram_api import (
    format_duration,
    get_updates,
    send_message,
    to_uae_time,
)

logger = logging.getLogger(__name__)


def build_status_message() -> str:
    states = database.get_all_states()
    last_check = database.get_meta("last_successful_check")
    lines = [
        "📊 APPLE IPHONE DUO — LIVE STATUS",
        f"Last successful scan: {to_uae_time(last_check)}",
        f"Configured interval: {CHECK_INTERVAL} seconds",
        "",
    ]

    for store_id, store in STORES.items():
        lines.append(f"📍 {store['name']} — {store['city']}")
        for part_number, product in PRODUCTS.items():
            state = states.get((store_id, part_number))
            if not state:
                status = "⚪ UNKNOWN — awaiting first successful result"
            else:
                status = "🟢 AVAILABLE" if state["status"] == "available" else "🔴 UNAVAILABLE"
                checked_at = datetime.fromisoformat(state["observed_at"])
                age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
                freshness = " · STALE" if age_seconds > CHECK_INTERVAL * 3 else ""
                status += f" · checked {to_uae_time(state['observed_at'])}{freshness}"
            lines.append(f"  {product['colour']}: {status}")
        lines.append("")

    lines.append("Availability is Apple's pickup result at the time checked, not a reservation.")
    return "\n".join(lines)


def build_history_message() -> str:
    events = database.get_latest_events(10)
    if not events:
        return "🕘 No stock changes have been recorded yet."

    lines = ["🕘 RECENT STOCK HISTORY", ""]
    for event in events:
        store = STORES.get(event["store_id"], {"name": event["store_id"], "city": ""})
        product = PRODUCTS.get(event["part_number"], {"name": event["part_number"], "colour": ""})
        when = to_uae_time(event["observed_at"])
        if event["event_type"] == "available":
            lines.append(f"🟢 AVAILABLE — {product['colour']} at {store['name']} ({store['city']})")
            lines.append(f"   Detected: {when}")
        else:
            lines.append(f"⚫ SOLD OUT — {product['colour']} at {store['name']} ({store['city']})")
            lines.append(f"   Detected: {when}; previous availability lasted {format_duration(event['duration_seconds'])}")
        lines.append("")
    return "\n".join(lines).strip()


async def handle_update(client: httpx.AsyncClient, update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if str(chat.get("id", "")) != CHAT_ID:
        return

    text = str(message.get("text", "")).strip()
    if not text.startswith("/"):
        return

    command = text.split()[0].split("@", 1)[0].lower()
    if command == "/status":
        reply = build_status_message()
    elif command == "/history":
        reply = build_history_message()
    elif command in ("/help", "/start"):
        reply = (
            "🤖 APPLE UAE STOCK MONITOR\n\n"
            "/status — current stock status for all four stores and both colours\n"
            "/history — latest availability and sold-out events\n"
            "/ping — check that the bot is responding\n"
            "/help — show this message"
        )
    elif command == "/ping":
        reply = "✅ Apple UAE monitor bot is responding."
    else:
        return

    await send_message(client, reply)


async def command_loop(client: httpx.AsyncClient) -> None:
    raw_offset = database.get_meta("telegram_update_offset")
    offset = int(raw_offset) if raw_offset else None

    while True:
        try:
            updates = await get_updates(client, offset)
            for update in updates:
                update_id = int(update["update_id"])
                await handle_update(client, update)
                offset = update_id + 1
                database.set_meta("telegram_update_offset", str(offset))
        except httpx.HTTPStatusError as exc:
            logger.error("Telegram command polling returned HTTP %s", exc.response.status_code)
            import asyncio
            await asyncio.sleep(5)
        except Exception:
            logger.exception("Telegram command polling failed; retrying")
            import asyncio
            await asyncio.sleep(5)
