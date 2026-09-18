"""SQLite storage for scraped FollowUpBoss clients and their viewed homes.

Usage:
    conn = init_db()
    is_new, added, skipped = store_client(conn, item)
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Tuple

DB_PATH = Path(__file__).resolve().parent.parent / "clients.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS viewed_homes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES clients(id),
    viewed_date TEXT,
    status      TEXT,
    price       TEXT,
    address     TEXT,
    city        TEXT,
    state       TEXT,
    zip         TEXT,
    mls_id      TEXT,
    url         TEXT,
    scraped_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (client_id, url)
);
"""


def init_db() -> sqlite3.Connection:
    """Create the database/tables if needed and return a connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def client_exists(conn: sqlite3.Connection, client_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    return row is not None


def upsert_client(conn: sqlite3.Connection, client: Dict[str, Any]) -> bool:
    """Insert the client if new, refresh name/email if existing.

    Returns True when the client row was newly created.
    """
    if client_exists(conn, client["id"]):
        conn.execute(
            "UPDATE clients SET name = ?, email = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (client.get("name", ""), client.get("email", ""), client["id"]),
        )
        return False
    conn.execute(
        "INSERT INTO clients (id, name, email) VALUES (?, ?, ?)",
        (client["id"], client.get("name", ""), client.get("email", "")),
    )
    return True


def home_exists(conn: sqlite3.Connection, client_id: int, home: Dict[str, Any]) -> bool:
    """True when this viewed home was already stored for the client.

    Deduplicates by URL when present; falls back to address+zip+date for
    cards without a link.
    """
    if home.get("url"):
        row = conn.execute(
            "SELECT 1 FROM viewed_homes WHERE client_id = ? AND url = ?",
            (client_id, home["url"]),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM viewed_homes WHERE client_id = ? AND url IS NULL "
            "AND address = ? AND zip = ? AND viewed_date = ?",
            (
                client_id,
                home.get("address", ""),
                home.get("zip", ""),
                home.get("date", ""),
            ),
        ).fetchone()
    return row is not None


def insert_viewed_home(
    conn: sqlite3.Connection, client_id: int, home: Dict[str, Any]
) -> None:
    conn.execute(
        "INSERT INTO viewed_homes (client_id, viewed_date, status, price, "
        "address, city, state, zip, mls_id, url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            client_id,
            home.get("date", ""),
            home.get("status", ""),
            home.get("price", ""),
            home.get("address", ""),
            home.get("city", ""),
            home.get("state", ""),
            home.get("zip", ""),
            home.get("mls_id", ""),
            home.get("url"),
        ),
    )


def store_client(
    conn: sqlite3.Connection, item: Dict[str, Any]
) -> Tuple[bool, int, int]:
    """Store one scraped client item.

    Checks whether the client exists first (inserting/updating as needed),
    then inserts only the viewed homes that are not already stored.

    Returns (is_new_client, homes_added, homes_skipped).
    """
    is_new_client = upsert_client(conn, item)

    added = 0
    skipped = 0
    for home in item.get("viewed_homes", []):
        if home_exists(conn, item["id"], home):
            skipped += 1
            continue
        insert_viewed_home(conn, item["id"], home)
        added += 1

    conn.commit()
    return is_new_client, added, skipped
