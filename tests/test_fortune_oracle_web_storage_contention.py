"""Live reads coexist with SQLite writers without weakening session revocation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web import create_app, service
from fortune_web import storage
from fortune_web.storage import WebStore


PROFILE = {"birth_date": "1990-05-17", "birth_time": "12:30", "display_name": "synthetic-contention",
           "timezone": "Asia/Seoul", "gender": "male"}
DAY = "2026-11-20"


def test_live_and_unknown_cookie_lookups_finish_while_writer_holds_transaction(tmp_path):
    store = WebStore(tmp_path / "web.sqlite3")
    token = store.create(86400)
    assert store.save(token, PROFILE)
    unknown = secrets.token_hex(32)
    writer = sqlite3.connect(store.path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        # Readers must see committed state and finish before this writer releases.
        writer.execute("UPDATE web_sessions SET profile = NULL WHERE id = ?", (store.key(token),))
        with ThreadPoolExecutor(max_workers=6) as readers:
            pending = [readers.submit(store.find, value) for value in (token, unknown) * 3]
            try:
                assert [future.result(timeout=2) for future in pending] == [
                    {"profile": PROFILE}, None,
                ] * 3
            finally:
                writer.rollback()
    finally:
        writer.close()
    assert store.find(token) == {"profile": PROFILE}


def test_reading_requests_do_not_queue_for_an_unrelated_writer(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3"), "COOKIE_SECURE": False})
    store = app.extensions["fortune_store"]
    tokens = [store.create(86400) for _ in range(6)]
    for token in tokens:
        assert store.save(token, PROFILE)
    monkeypatch.setattr(service, "daily", lambda *_: {"ok": True, "computed": True, "text": "synthetic"})

    def read(token):
        client = app.test_client()
        client.set_cookie("fortune_session", token)
        response = client.get("/api/readings/today")
        return response.status_code, response.json["computed"]

    writer = sqlite3.connect(store.path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(max_workers=6) as readers:
            pending = [readers.submit(read, token) for token in tokens]
            try:
                assert [future.result(timeout=2) for future in pending] == [(200, True)] * 6
            finally:
                writer.rollback()
    finally:
        writer.close()


def test_lookup_rechecks_expiry_after_waiting_for_an_exclusive_writer(tmp_path, monkeypatch):
    clock = [100]
    monkeypatch.setattr(storage, "time", SimpleNamespace(time=lambda: clock[0]))
    store = WebStore(tmp_path / "web.sqlite3")
    token = store.create(1)
    assert store.save(token, PROFILE)
    assert store.record_event(token, DAY, "visit", "entry")
    lookup_ready, start_lookup, selecting = threading.Event(), threading.Event(), threading.Event()
    original_connect = store.connect

    @contextmanager
    def coordinated_connect():
        # Open/configure the reader before the writer reserves EXCLUSIVE; the
        # find() call then attempts its SELECT while that lock is held.
        with original_connect() as db:
            class Connection:
                def execute(self, statement, parameters=()):
                    if statement.startswith("SELECT expires, profile"):
                        lookup_ready.set()
                        assert start_lookup.wait(2)
                        selecting.set()
                    return db.execute(statement, parameters)
            yield Connection()

    writer = sqlite3.connect(store.path)
    with monkeypatch.context() as lookup_patch:
        lookup_patch.setattr(store, "connect", coordinated_connect)
        try:
            with ThreadPoolExecutor(max_workers=1) as reader:
                pending = reader.submit(store.find, token)
                try:
                    assert lookup_ready.wait(2)
                    writer.execute("BEGIN EXCLUSIVE")
                    start_lookup.set()
                    assert selecting.wait(2)
                    assert not pending.done()
                    # Advance the clock across expiry before allowing the blocked
                    # SELECT to return. No real-time sleep or short-lived token.
                    clock[0] = 101
                finally:
                    start_lookup.set()
                    writer.rollback()
                assert pending.result(timeout=2) is None
        finally:
            writer.close()
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
        assert db.execute("SELECT sum(count) FROM metric_counts").fetchone()[0] == 1
    assert PROFILE["display_name"].encode() not in store.path.read_bytes()


@pytest.mark.parametrize("revoke", ["delete", "expire"])
def test_revoked_lookup_cleans_receipts_and_parallel_late_writes_cannot_revive_profile(tmp_path, revoke):
    store = WebStore(tmp_path / "web.sqlite3")
    token = store.create(86400)
    assert store.save(token, PROFILE)
    assert store.record_event(token, DAY, "visit", "entry")
    if revoke == "delete":
        store.delete(token)
    else:
        with store.connect() as db:
            db.execute("UPDATE web_sessions SET expires = 0 WHERE id = ?", (store.key(token),))
    assert store.find(token) is None

    def late_write(_):
        return (store.save(token, PROFILE), store.record_event(token, DAY, "profile_saved", "entry"),
                store.record_sample_event(token, DAY, "product_sample_viewed", "self_manual_v1"))

    with ThreadPoolExecutor(max_workers=6) as writers:
        assert list(writers.map(late_write, range(12))) == [(False, False, "session_expired")] * 12
    assert store.find(token) is None
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
        assert [tuple(row) for row in db.execute("SELECT event, count FROM metric_counts")] == [("visit", 1)]
    assert PROFILE["display_name"].encode() not in store.path.read_bytes()


def test_periodic_purge_removes_expired_profile_not_visited_by_its_cookie(tmp_path):
    store = WebStore(tmp_path / "web.sqlite3")
    live, expired = store.create(86400), store.create(86400)
    assert store.save(live, {**PROFILE, "display_name": "synthetic-live"})
    assert store.save(expired, PROFILE)
    assert store.record_event(expired, DAY, "visit", "entry")
    with store.connect() as db:
        db.execute("UPDATE web_sessions SET expires = 0 WHERE id = ?", (store.key(expired),))
    assert store.find(live)["profile"]["display_name"] == "synthetic-live"
    store.purge_expired()
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
        assert db.execute("SELECT sum(count) FROM metric_counts").fetchone()[0] == 1
    assert PROFILE["display_name"].encode() not in store.path.read_bytes()
