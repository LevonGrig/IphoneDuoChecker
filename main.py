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
)

# Apple has returned HTTP 541 to direct requests from automated clients.
# Treat it as a temporary block: stop polling for a while instead of
# repeatedly hitting the same blocked endpoint every 30 seconds.
APPLE_541_INITIAL_BACKOFF_SECONDS = 15 * 60
APPLE_541_MAX_BACKOFF_SECONDS = 60 * 60
TRANSIENT_ERROR_INITIAL_BACKOFF_SECONDS = 60
TRANSIENT_ERROR_MAX_BACKOFF_SECONDS = 5 * 60
RECOMMENDED_CHECK_INTERVAL_SECONDS = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# Telegram Bot API URLs contain the bot token. Never log request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("apple_monitor")


async def safe_health_notice(
    telegram_client: httpx.AsyncClient,
    message: str,
) -> None:
    """Send health notices without allowing Telegram errors to stop monitoring."""
    try:
        await send_message(telegram_client, message)
    except Exception:
        logger.exception("Could not deliver monitor health notification")


async def deliver_pending_alerts(telegram_client: httpx.AsyncClient) -> None:
    for event in database.get_pending_notifications():
        try:
            await send_restock_alert(telegram_client, event)
            database.mark_notification_sent(int(event["id"]))
        except Exception:
            # Keep the event pending; the next cycle will retry it.
            logger.exception("Could not deliver restock alert event %s", event["id"])


async def monitor_loop(
    apple_client: httpx.AsyncClient,
    telegram_client: httpx.AsyncClient,
) -> None:
    apple_541_backoff = APPLE_541_INITIAL_BACKOFF_SECONDS
    transient_backoff = TRANSIENT_ERROR_INITIAL_BACKOFF_SECONDS
    apple_block_notice_sent = False
    next_delay = CHECK_INTERVAL

    while True:
        started = time.monotonic()
        next_delay = CHECK_INTERVAL

        try:
            results = await fetch_availability(apple_client)

            expected = database.get_expected_combinations()
            if len(results) != len(expected):
                missing = set(expected) - set(results)
                missing_labels = ", ".join(
                    f"{store_id}/{part}" for store_id, part in sorted(missing)
                )
                raise RuntimeError(
                    "Incomplete Apple pickup response: "
                    f"received {len(results)}/{len(expected)} combinations. "
                    f"Missing: {missing_labels or 'unknown'}"
                )

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

            if checked != len(expected):
                raise RuntimeError(
                    f"Apple returned only {checked}/{len(expected)} confirmed statuses"
                )

            database.set_meta("last_successful_check", database.utc_now())
            logger.info(
                "Scan complete: %d confirmed store/colour combinations; "
                "next check in about %d seconds",
                checked,
                CHECK_INTERVAL,
            )

            # A successful full scan means Apple has started responding again.
            if apple_block_notice_sent:
                await safe_health_notice(
                    telegram_client,
                    "🟢 Apple pickup monitoring has recovered. "
                    "The latest complete availability scan succeeded.",
                )
                apple_block_notice_sent = False

            apple_541_backoff = APPLE_541_INITIAL_BACKOFF_SECONDS
            transient_backoff = TRANSIENT_ERROR_INITIAL_BACKOFF_SECONDS
            await deliver_pending_alerts(telegram_client)

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code

            if status == 541:
                body_excerpt = " ".join(exc.response.text.split())[:240]
                logger.error(
                    "Apple returned HTTP 541 (likely Apple Shield/edge rejection). "
                    "Pausing checks for %d seconds. response_body=%r",
                    apple_541_backoff,
                    body_excerpt,
                )

                if not apple_block_notice_sent:
                    await safe_health_notice(
                        telegram_client,
                        "⚠️ Apple pickup requests are being rejected (HTTP 541). "
                        "The monitor has paused Apple checks temporarily to avoid "
                        "repeated requests. It will retry automatically and notify "
                        "you when a complete scan succeeds.",
                    )
                    apple_block_notice_sent = True

                next_delay = apple_541_backoff
                apple_541_backoff = min(
                    apple_541_backoff * 2,
                    APPLE_541_MAX_BACKOFF_SECONDS,
                )

            elif status == 429:
                retry_after = exc.response.headers.get("Retry-After", "")
                try:
                    next_delay = max(int(retry_after), CHECK_INTERVAL)
                except (TypeError, ValueError):
                    next_delay = max(5 * 60, CHECK_INTERVAL)
                logger.warning(
                    "Apple returned HTTP 429. Respecting Retry-After; "
                    "next attempt in %d seconds.",
                    next_delay,
                )

            else:
                logger.error(
                    "Apple pickup request returned HTTP %s; response body=%r",
                    status,
                    " ".join(exc.response.text.split())[:240],
                )
                next_delay = max(transient_backoff, CHECK_INTERVAL)
                transient_backoff = min(
                    transient_backoff * 2,
                    TRANSIENT_ERROR_MAX_BACKOFF_SECONDS,
                )

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(
                "Temporary Apple network error (%s): %s. "
                "Retrying in %d seconds.",
                type(exc).__name__,
                exc,
                transient_backoff,
            )
            next_delay = max(transient_backoff, CHECK_INTERVAL)
            transient_backoff = min(
                transient_backoff * 2,
                TRANSIENT_ERROR_MAX_BACKOFF_SECONDS,
            )

        except Exception:
            logger.exception(
                "Apple monitoring cycle failed; last successful scan timestamp preserved"
            )
            next_delay = max(transient_backoff, CHECK_INTERVAL)
            transient_backoff = min(
                transient_backoff * 2,
                TRANSIENT_ERROR_MAX_BACKOFF_SECONDS,
            )

        elapsed = time.monotonic() - started
        sleep_seconds = max(0, next_delay - elapsed)
        logger.info(
            "Next Apple check scheduled in %.0f seconds",
            sleep_seconds,
        )
        await asyncio.sleep(sleep_seconds)


async def main() -> None:
    validate_config()
    database.init_db()

    timeout = httpx.Timeout(20.0, connect=10.0)
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
            f"⏱ Normal checking interval: {CHECK_INTERVAL} seconds\n"
            "🛡 Automatic cooldown is enabled for Apple HTTP 541 responses.\n\n"
            "Commands: /status · /history · /ping · /help",
        )
        logger.info(
            "Monitor started. Chat ID is configured; credentials are not printed. "
            "Configured normal interval=%d seconds; minimum supported interval=%d seconds.",
            CHECK_INTERVAL,
            RECOMMENDED_CHECK_INTERVAL_SECONDS,
        )

        await asyncio.gather(
            monitor_loop(apple_client, telegram_client),
            command_loop(telegram_client),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
