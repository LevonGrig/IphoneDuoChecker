import asyncio
import logging
import time

import httpx

import database
from apple_monitor import fetch_availability
from bot_commands import command_loop
from config import CHECK_INTERVAL, validate_config
from telegram_api import (
    get_webhook_info,
    send_message,
    send_restock_alert,
    to_uae_time,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# Telegram Bot API URLs contain the bot token. Never log request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("apple_monitor")


async def deliver_pending_alerts(telegram_client: httpx.AsyncClient) -> None:
    for event in database.get_pending_notifications():
        try:
            await send_restock_alert(telegram_client, event)
            database.mark_notification_sent(int(event["id"]))
        except Exception:
            # Keep the event pending; the next cycle will retry it.
            logger.exception("Could not deliver restock alert event %s", event["id"])


async def monitor_loop(apple_client: httpx.AsyncClient, telegram_client: httpx.AsyncClient) -> None:
    while True:
        started = time.monotonic()
        try:
            results = await fetch_availability(apple_client)
            checked = 0

            for (store_id, part_number), available in results.items():
                if available is None:
                    logger.warning(
                        "Unknown Apple pickup status for %s / %s; previous state preserved",
                        store_id,
                        part_number,
                    )
                    continue

                checked += 1
                event_id = database.record_observation(
                    store_id,
                    part_number,
                    bool(available),
                )
                label = "AVAILABLE" if available else "UNAVAILABLE"
                logger.info("%s | %s | %s", store_id, part_number, label)

                if event_id is not None:
                    logger.info("Stock state changed for %s / %s", store_id, part_number)

            checked_at = database.utc_now()
            database.set_meta("last_successful_check", checked_at)
            logger.info(
                "Scan complete: %d confirmed store/colour combinations; next check in about %d seconds",
                checked,
                CHECK_INTERVAL,
            )
            await deliver_pending_alerts(telegram_client)

        except httpx.HTTPStatusError as exc:
            logger.error("Apple pickup request returned HTTP %s", exc.response.status_code)
        except Exception:
            logger.exception("Apple monitoring cycle failed; previous stock states preserved")

        elapsed = time.monotonic() - started
        await asyncio.sleep(max(0, CHECK_INTERVAL - elapsed))


async def main() -> None:
    validate_config()
    database.init_db()

    timeout = httpx.Timeout(15.0, connect=10.0)
    async with (
        httpx.AsyncClient(timeout=timeout, follow_redirects=True) as apple_client,
        httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=10.0)) as telegram_client,
    ):
        webhook = await get_webhook_info(telegram_client)
        if webhook.get("url"):
            raise RuntimeError(
                "This bot has a Telegram webhook configured. Long polling (/status and /history) "
                "cannot run until that webhook is removed via BotFather/API."
            )

        await send_message(
            telegram_client,
            "🟢 Apple UAE Stock Monitor is online.\n\n"
            "📱 iPhone Duo 256GB — Star White + Night Sky\n"
            "📍 Al Maryah Island, Yas Mall, Dubai Mall, Mall of the Emirates\n"
            f"⏱ Checking every {CHECK_INTERVAL} seconds\n\n"
            "Commands: /status · /history · /ping · /help",
        )
        logger.info("Monitor started. Chat ID is configured; credentials are not printed.")

        await asyncio.gather(
            monitor_loop(apple_client, telegram_client),
            command_loop(telegram_client),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
