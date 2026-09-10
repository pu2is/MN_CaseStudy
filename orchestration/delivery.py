"""Durable single-host delivery reservations and explicit operator reconciliation."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class DeliveryUncertain(RuntimeError):
    """A previous attempt may have reached Slack and must not be resent blindly."""


@contextmanager
def database(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("""
            create table if not exists deliveries (
                delivery_key text primary key,
                status text not null,
                updated_at text not null default current_timestamp
            )
        """)
        yield connection
    finally:
        connection.close()


def reserve(path: Path, key: str) -> bool:
    """Commit before POST; only an absent or definitely rejected attempt can send."""
    with database(path) as connection:
        connection.execute("begin immediate")
        row = connection.execute(
            "select status from deliveries where delivery_key = ?", (key,)
        ).fetchone()
        if row and row[0] == "sent":
            connection.commit()
            return False
        if row and row[0] != "failed":
            raise DeliveryUncertain(
                f"Delivery {key} needs reconciliation; automatic resend blocked"
            )
        connection.execute(
            "insert into deliveries (delivery_key, status) values (?, 'pending') "
            "on conflict(delivery_key) do update set status='pending', updated_at=current_timestamp",
            (key,),
        )
        connection.commit()
        return True


def finish(path: Path, key: str, status: str) -> None:
    if status not in ("sent", "failed", "uncertain"):
        raise ValueError("Invalid delivery status")
    with database(path) as connection:
        cursor = connection.execute(
            "update deliveries set status=?, updated_at=current_timestamp "
            "where delivery_key=? and status='pending'",
            (status, key),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Delivery reservation is missing or no longer pending")
        connection.commit()


def reconcile(path: Path, key: str, outcome: str) -> None:
    """Operator-only: stop the runner and verify Slack before resolving a reservation."""
    if outcome not in ("sent", "not-sent"):
        raise ValueError("Outcome must be sent or not-sent")
    with database(path) as connection:
        cursor = connection.execute(
            "update deliveries set status=?, updated_at=current_timestamp "
            "where delivery_key=? and status in ('pending', 'uncertain')",
            ("sent" if outcome == "sent" else "failed", key),
        )
        if cursor.rowcount != 1:
            raise ValueError("No pending or uncertain delivery with this key")
        connection.commit()


def main() -> None:
    from orchestration.settings import alert_state_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "resolve"))
    parser.add_argument("--key")
    parser.add_argument("--outcome", choices=("sent", "not-sent"))
    args = parser.parse_args()
    path = alert_state_path()
    if args.command == "resolve":
        if not args.key or not args.outcome:
            parser.error(
                "resolve requires --key and --outcome; stop the runner and verify Slack first"
            )
        reconcile(path, args.key, args.outcome)
    else:
        with database(path) as connection:
            for row in connection.execute(
                "select delivery_key, status, updated_at from deliveries order by updated_at"
            ):
                print(" | ".join(row))


if __name__ == "__main__":
    main()
