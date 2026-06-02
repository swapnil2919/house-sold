"""TTL-based SQLite cache for scraped listings and price data.

Lives next to the project (~/.house_sold_cache.sqlite) so it survives Streamlit
reruns. Keys are arbitrary strings (we hash the query tuple); values are JSON.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

_DEFAULT_PATH = os.path.expanduser("~/.house_sold_cache.sqlite")
_TTL_SECONDS_DEFAULT = 60 * 60  # 1 hour


def _path() -> str:
    return os.environ.get("HOUSE_SOLD_CACHE_PATH", _DEFAULT_PATH)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(_path())
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "  key TEXT PRIMARY KEY, "
            "  value TEXT NOT NULL, "
            "  expires_at REAL NOT NULL"
            ")"
        )
        yield con
        con.commit()
    finally:
        con.close()


def get(key: str) -> Any | None:
    with _conn() as con:
        row = con.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    value, expires_at = row
    if expires_at < time.time():
        return None
    return json.loads(value)


def put(key: str, value: Any, ttl: int = _TTL_SECONDS_DEFAULT) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO cache(key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), time.time() + ttl),
        )


def clear() -> None:
    with _conn() as con:
        con.execute("DELETE FROM cache")
