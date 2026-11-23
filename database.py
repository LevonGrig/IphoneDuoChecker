import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import DATABASE_PATH, DATA_DIR, PRODUCTS, STORES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=15000")
    return connection


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS item_state (
                store_id TEXT NOT NULL,
                part_number TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('available', 'unavailable')),
                observed_at TEXT NOT NULL,
                available_since TEXT,
                PRIMARY KEY (store_id, part_number)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                part_number TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK(event_type IN ('available', 'unavailable')),
                observed_at TEXT NOT NULL,
                duration_seconds INTEGER,
                notified INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def record_observation(store_id: str, part_number: str, is_available: bool, observed_at: str | None = None) -> int | None:
    """Store a confirmed Apple observation and return a new event ID, if any.

    Unknown/missing API results are not passed here. Only confirmed true/false
    pickupDisplay values can change stock state.
    """
    now = observed_at or utc_now()
    new_status = "available" if is_available else "unavailable"
    event_id: int | None = None

    with db_connection() as db:
        row = db.execute(
            "SELECT status, available_since FROM item_state WHERE store_id=? AND part_number=?",
            (store_id, part_number),
        ).fetchone()

        if row is None:
            available_since = now if is_available else None
            db.execute(
                "INSERT INTO item_state(store_id, part_number, status, observed_at, available_since) VALUES (?, ?, ?, ?, ?)",
                (store_id, part_number, new_status, now, available_since),
            )
            if is_available:
                cursor = db.execute(
                    "INSERT INTO events(store_id, part_number, event_type, observed_at, duration_seconds, notified) VALUES (?, ?, 'available', ?, NULL, 0)",
                    (store_id, part_number, now),
                )
                event_id = int(cursor.lastrowid)
            return event_id

        old_status = str(row["status"])
        available_since = row["available_since"]

        if old_status == new_status:
            db.execute(
                "UPDATE item_state SET observed_at=? WHERE store_id=? AND part_number=?",
                (now, store_id, part_number),
            )
            return None

        if is_available:
            db.execute(
                "UPDATE item_state SET status='available', observed_at=?, available_since=? WHERE store_id=? AND part_number=?",
                (now, now, store_id, part_number),
            )
            cursor = db.execute(
                "INSERT INTO events(store_id, part_number, event_type, observed_at, duration_seconds, notified) VALUES (?, ?, 'available', ?, NULL, 0)",
                (store_id, part_number, now),
            )
            event_id = int(cursor.lastrowid)
        else:
            duration_seconds = None
            if available_since:
                try:
                    start = datetime.fromisoformat(available_since)
                    end = datetime.fromisoformat(now)
                    duration_seconds = max(0, int((end - start).total_seconds()))
                except ValueError:
                    duration_seconds = None

            db.execute(
                "UPDATE item_state SET status='unavailable', observed_at=?, available_since=NULL WHERE store_id=? AND part_number=?",
                (now, store_id, part_number),
            )
            db.execute(
                "INSERT INTO events(store_id, part_number, event_type, observed_at, duration_seconds, notified) VALUES (?, ?, 'unavailable', ?, ?, 1)",
                (store_id, part_number, now, duration_seconds),
            )

    return event_id


def set_meta(key: str, value: str) -> None:
    with db_connection() as db:
        db.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str) -> str | None:
    with db_connection() as db:
        row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None


def get_all_states() -> dict[tuple[str, str], dict[str, str | None]]:
    with db_connection() as db:
        rows = db.execute(
            "SELECT store_id, part_number, status, observed_at, available_since FROM item_state"
        ).fetchall()
    return {
        (str(row["store_id"]), str(row["part_number"])): {
            "status": str(row["status"]),
            "observed_at": str(row["observed_at"]),
            "available_since": row["available_since"],
        }
        for row in rows
    }


def get_pending_notifications() -> list[dict[str, Any]]:
    with db_connection() as db:
        rows = db.execute(
            "SELECT id, store_id, part_number, observed_at FROM events WHERE event_type='available' AND notified=0 ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def mark_notification_sent(event_id: int) -> None:
    with db_connection() as db:
        db.execute("UPDATE events SET notified=1 WHERE id=?", (event_id,))


def get_latest_events(limit: int = 10) -> list[dict[str, Any]]:
    with db_connection() as db:
        rows = db.execute(
            "SELECT id, store_id, part_number, event_type, observed_at, duration_seconds FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_expected_combinations() -> list[tuple[str, str]]:
    return [(store_id, part_number) for store_id in STORES for part_number in PRODUCTS]
