"""Durable per-key "already sent" marker so a rerun does not duplicate a Slack alert."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def database(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("""
            create table if not exists sent_deliveries (
                delivery_key text primary key,
                sent_at text not null default current_timestamp
            )
        """)
        yield connection
    finally:
        connection.close()


def already_sent(path: Path, key: str) -> bool:
    with database(path) as connection:
        row = connection.execute(
            "select 1 from sent_deliveries where delivery_key = ?", (key,)
        ).fetchone()
        return row is not None


def mark_sent(path: Path, key: str) -> None:
    with database(path) as connection:
        connection.execute(
            "insert or ignore into sent_deliveries (delivery_key) values (?)", (key,)
        )
        connection.commit()
