import logging
from typing import Any

import httpx

from config import (
    APPLE_PICKUP_URL,
    APPLE_PRODUCT_URL,
    PRODUCTS,
    STORES,
)

logger = logging.getLogger(__name__)

APPLE_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": APPLE_PRODUCT_URL,
}

CITIES = ("Abu Dhabi", "Dubai")


def parse_pickup_response(
    payload: dict[str, Any],
    expected_store_ids: set[str] | None = None,
) -> dict[tuple[str, str], bool | None]:
    """Convert Apple's pickup JSON into {(store_id, part_number): bool | None}.

    True means pickupDisplay='available'; False means 'unavailable';
    None means Apple's response did not contain a recognised status.
    Missing stores / products are omitted so they are never treated as out of stock.
    """
    head = payload.get("head") or {}
    status = str(head.get("status", "200"))
    if status not in ("", "200"):
        raise RuntimeError(f"Apple pickup endpoint returned status {status}")

    body = payload.get("body") or {}
    stores = body.get("stores")
    if not isinstance(stores, list):
        stores = (
            body.get("content", {})
            .get("pickupMessage", {})
            .get("stores")
        )
    if not isinstance(stores, list) or not stores:
        raise RuntimeError("Apple response did not contain a non-empty stores list")

    results: dict[tuple[str, str], bool | None] = {}
    returned_store_ids: set[str] = set()

    for store in stores:
        store_id = str(store.get("storeNumber", ""))
        if store_id not in STORES:
            continue

        returned_store_ids.add(store_id)
        parts = store.get("partsAvailability") or {}

        for part_number in PRODUCTS:
            item = parts.get(part_number)
            if not isinstance(item, dict):
                continue

            display = str(item.get("pickupDisplay", "")).strip().lower()
            if display == "available":
                results[(store_id, part_number)] = True
            elif display == "unavailable":
                results[(store_id, part_number)] = False
            else:
                results[(store_id, part_number)] = None

    expected = expected_store_ids if expected_store_ids is not None else set(STORES)
    missing = expected - returned_store_ids
    if missing:
        logger.warning(
            "Apple did not return these expected stores; keeping their previous state: %s",
            ", ".join(sorted(missing)),
        )

    return results


async def fetch_availability(client: httpx.AsyncClient) -> dict[tuple[str, str], bool | None]:
    """Query each target city separately and merge results for the four selected stores."""
    part_numbers = list(PRODUCTS)
    all_results: dict[tuple[str, str], bool | None] = {}

    for city in CITIES:
        expected_store_ids = {
            store_id
            for store_id, store in STORES.items()
            if store["city"] == city
        }
        params = [
            ("pl", "true"),
            ("mts.0", "regular"),
            ("parts.0", part_numbers[0]),
            ("parts.1", part_numbers[1]),
            ("location", city),
        ]

        response = await client.get(
            APPLE_PICKUP_URL,
            params=params,
            headers=APPLE_HEADERS,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Apple returned a non-JSON pickup response for {city}"
            ) from exc

        city_results = parse_pickup_response(
            payload,
            expected_store_ids=expected_store_ids,
        )
        all_results.update(city_results)

    return all_results
