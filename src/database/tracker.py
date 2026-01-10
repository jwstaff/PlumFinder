"""
Item Tracker Module

Uses Turso (libsql) to track seen items and prevent duplicates.
Falls back to local SQLite if Turso is not configured.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

# Try to import libsql, fall back to sqlite3
try:
    import libsql_experimental as libsql
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False
    print("libsql not available, using local SQLite")


class ItemTracker:
    def __init__(self):
        self.connection = None
        self.use_turso = False

        if config.TURSO_DATABASE_URL and config.TURSO_AUTH_TOKEN and HAS_LIBSQL:
            try:
                self.connection = libsql.connect(
                    config.TURSO_DATABASE_URL,
                    auth_token=config.TURSO_AUTH_TOKEN
                )
                self.use_turso = True
                print("Connected to Turso database")
            except Exception as e:
                print(f"Failed to connect to Turso: {e}")
                self._use_local_sqlite()
        else:
            self._use_local_sqlite()

        self._create_tables()

    def _use_local_sqlite(self):
        """Fall back to local SQLite database."""
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "seen_items.db"
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.connection = sqlite3.connect(db_path)
        self.use_turso = False
        print(f"Using local SQLite database: {db_path}")

    def _create_tables(self):
        """Create the necessary database tables."""
        cursor = self.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                source TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                sent_in_email INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                item_count INTEGER,
                recipient TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_items_first_seen
            ON seen_items(first_seen_at)
        """)

        self.connection.commit()

    def is_seen(self, item_id: str) -> bool:
        """Check if an item has been seen before."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM seen_items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        return result is not None

    def mark_seen(self, item) -> None:
        """Mark an item as seen."""
        cursor = self.connection.cursor()
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO seen_items (id, url, title, source, first_seen_at, last_seen_at, sent_in_email)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET last_seen_at = ?
        """, (item.id, item.url, item.title, item.source, now, now, now))

        self.connection.commit()

    def mark_sent(self, item_ids: list[str]) -> None:
        """Mark items as having been sent in an email."""
        cursor = self.connection.cursor()

        for item_id in item_ids:
            cursor.execute(
                "UPDATE seen_items SET sent_in_email = 1 WHERE id = ?",
                (item_id,)
            )

        self.connection.commit()

    def filter_new_items(self, items: list) -> list:
        """Filter items to only include ones not seen before."""
        new_items = []

        for item in items:
            if not self.is_seen(item.id):
                new_items.append(item)

        return new_items

    def get_unsent_items(self) -> list[str]:
        """Get IDs of items that haven't been sent in an email yet."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM seen_items WHERE sent_in_email = 0")
        return [row[0] for row in cursor.fetchall()]

    def record_email_sent(self, item_count: int, recipient: str) -> None:
        """Record that an email was sent."""
        cursor = self.connection.cursor()
        now = datetime.now().isoformat()

        cursor.execute(
            "INSERT INTO email_history (sent_at, item_count, recipient) VALUES (?, ?, ?)",
            (now, item_count, recipient)
        )

        self.connection.commit()

    def cleanup_old_items(self, days: int = 90) -> int:
        """Remove items older than specified days to prevent database bloat."""
        cursor = self.connection.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute(
            "DELETE FROM seen_items WHERE first_seen_at < ?",
            (cutoff,)
        )

        deleted = cursor.rowcount
        self.connection.commit()

        if deleted > 0:
            print(f"Cleaned up {deleted} old items")

        return deleted

    def get_stats(self) -> dict:
        """Get statistics about tracked items."""
        cursor = self.connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM seen_items")
        total_items = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM seen_items WHERE sent_in_email = 1")
        sent_items = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM email_history")
        total_emails = cursor.fetchone()[0]

        return {
            "total_items_tracked": total_items,
            "items_sent_in_emails": sent_items,
            "total_emails_sent": total_emails,
        }

    def close(self):
        """Close the database connection."""
        if self.connection:
            try:
                self.connection.close()
            except AttributeError:
                pass  # libsql connections don't have close()


if __name__ == "__main__":
    # Test the tracker
    tracker = ItemTracker()

    print("Database stats:", tracker.get_stats())

    tracker.close()
