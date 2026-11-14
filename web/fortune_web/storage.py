"""Web-only browser sessions. No Telegram store, reading cache, or raw session tokens."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time


class WebStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS web_sessions (id TEXT PRIMARY KEY, expires INTEGER NOT NULL, profile TEXT)")
            db.execute("""CREATE TABLE IF NOT EXISTS metric_receipts (
                session_id TEXT NOT NULL REFERENCES web_sessions(id) ON DELETE CASCADE,
                day TEXT NOT NULL, event TEXT NOT NULL, view TEXT NOT NULL,
                PRIMARY KEY (session_id, day, event, view))""")
            db.execute("""CREATE TABLE IF NOT EXISTS metric_counts (
                day TEXT NOT NULL, event TEXT NOT NULL, view TEXT NOT NULL, count INTEGER NOT NULL,
                PRIMARY KEY (day, event, view))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete = ON")
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, lifetime):
        token = secrets.token_hex(32)
        with self.connect() as db:
            db.execute("DELETE FROM web_sessions WHERE expires <= ?", (int(time.time()),))
            db.execute("INSERT INTO web_sessions(id, expires) VALUES (?, ?)",
                       (self.key(token), int(time.time()) + lifetime))
        return token

    def purge_expired(self):
        with self.connect() as db:
            return db.execute("DELETE FROM web_sessions WHERE expires <= ?", (int(time.time()),)).rowcount

    def find(self, token):
        if not token or len(token) != 64:
            return None
        with self.connect() as db:
            db.execute("DELETE FROM web_sessions WHERE expires <= ?", (int(time.time()),))
            row = db.execute("SELECT profile FROM web_sessions WHERE id = ? AND expires > ?",
                             (self.key(token), int(time.time()))).fetchone()
        return None if row is None else {"profile": json.loads(row["profile"]) if row["profile"] else None}

    def save(self, token, profile):
        with self.connect() as db:
            changed = db.execute("UPDATE web_sessions SET profile = ? WHERE id = ? AND expires > ?",
                                 (json.dumps(profile, ensure_ascii=False), self.key(token), int(time.time()))).rowcount
        return bool(changed)

    def delete(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM web_sessions WHERE id = ?", (self.key(token),))

    def record_event(self, token, day, event, view):
        """At most once per browser/day/event/view; late events cannot revive a session.

        Session-linked deduplication receipts expire with the session. Only daily
        counts, with no identifier or arbitrary properties, survive deletion.
        """
        with self.connect() as db:
            inserted = db.execute("""INSERT OR IGNORE INTO metric_receipts
                SELECT id, ?, ?, ? FROM web_sessions WHERE id = ? AND expires > ?""",
                (day, event, view, self.key(token), int(time.time()))).rowcount
            if inserted:
                db.execute("""INSERT INTO metric_counts VALUES (?, ?, ?, 1)
                    ON CONFLICT(day, event, view) DO UPDATE SET count = count + 1""", (day, event, view))
        return bool(inserted)

    def record_sample_event(self, token, day, event, view):
        """Return inserted/duplicate, session_expired, or sample_not_viewed atomically.

        Reserve the writer before checking the live session and prerequisite so
        deletion and concurrent retries cannot invalidate the acknowledgement.
        Receipts cascade away with sessions; anonymous daily totals survive.
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            key = self.key(token)
            if db.execute("SELECT 1 FROM web_sessions WHERE id = ? AND expires > ?",
                          (key, int(time.time()))).fetchone() is None:
                return "session_expired"
            if event == "product_sample_interest" and db.execute(
                """SELECT 1 FROM metric_receipts
                   WHERE session_id = ? AND day = ? AND event = 'product_sample_viewed' AND view = ?""",
                (key, day, view),
            ).fetchone() is None:
                return "sample_not_viewed"
            inserted = db.execute("INSERT OR IGNORE INTO metric_receipts VALUES (?, ?, ?, ?)",
                                  (key, day, event, view)).rowcount
            if inserted:
                db.execute("""INSERT INTO metric_counts VALUES (?, ?, ?, 1)
                    ON CONFLICT(day, event, view) DO UPDATE SET count = count + 1""", (day, event, view))
            return "inserted" if inserted else "duplicate"
