"""Failure boundaries and privacy of the first-party funnel, with no external calls."""
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

import pytest

from test_fortune_oracle_web import app, session, PROFILE
from fortune_web.metrics import metric_day
from fortune_web.storage import WebStore
from metrics_report import read_counts


@pytest.mark.parametrize("payload", [
    None, [], "visit", {}, {"event": "visit", "view": "entry"},
    {"event": "profile_saved", "view": "entry"},
    {"event": "form_started", "view": "today"},
    {"event": "share_card_opened", "view": "compat"},
    {"event": "form_started", "view": "entry", "birth_date": "1990-05-17"},
    {"event": [], "view": "entry"}, {"event": "form_started", "view": {}},
    {"event": "가상 이름", "view": "entry"},
])
def test_event_rejects_unknown_properties_labels_and_server_events(app, payload):
    client = app.test_client(); headers = session(client)
    assert client.post("/api/events", json=payload, headers=headers).status_code == 400
    with app.extensions["fortune_store"].connect() as db:
        assert [tuple(r) for r in db.execute("SELECT event, view, count FROM metric_counts")] == [("visit", "entry", 1)]


def test_event_needs_live_session_csrf_origin_and_profile_for_results(app):
    client = app.test_client()
    event = {"event": "reading_viewed", "view": "today"}
    assert client.post("/api/events", json=event).status_code == 401
    headers = session(client)
    assert client.post("/api/events", json=event).status_code == 403
    assert client.post("/api/events", json=event, headers={**headers, "Origin": "https://elsewhere.test"}).status_code == 403
    assert client.post("/api/events", json=event, headers=headers).status_code == 409
    cookie = client.get_cookie("fortune_session").value
    assert client.delete("/api/profile", headers=headers).status_code == 200
    client.set_cookie("fortune_session", cookie)
    assert client.post("/api/events", headers=headers, json=event).status_code == 401
    store = app.extensions["fortune_store"]
    assert not store.record_event(cookie, "2026-10-28", "reading_viewed", "today")
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0


def test_events_deduplicate_by_day_view_and_browser_and_do_not_store_content(app):
    clients = [app.test_client(), app.test_client()]
    for client in clients:
        headers = session(client)
        session(client)
        assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
        for _ in range(2):
            for view in ("today", "tomorrow"):
                assert client.post("/api/events", headers=headers, json={"event": "reading_viewed", "view": view}).status_code == 202
        assert client.delete("/api/profile", headers=headers).status_code == 200
    with app.extensions["fortune_store"].connect() as db:
        counts = {tuple(r[:3]): r[3] for r in db.execute("SELECT day, event, view, count FROM metric_counts")}
        assert counts == {("2026-10-28", "visit", "entry"): 2, ("2026-10-28", "profile_saved", "entry"): 2,
                          ("2026-10-28", "reading_viewed", "today"): 2, ("2026-10-28", "reading_viewed", "tomorrow"): 2}
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
    raw = Path(app.config["WEB_STORE"]).read_bytes()
    for value in (PROFILE["birth_date"], PROFILE["display_name"], "12:30"):
        assert value.encode() not in raw


def test_concurrent_retry_is_counted_once_and_expiry_cascades(tmp_path):
    store = WebStore(tmp_path / "metrics.sqlite3")
    token = store.create(86400)
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda _: store.record_event(token, "2026-10-28", "visit", "entry"), range(12)))
    assert sum(results) == 1
    assert store.record_event(token, "2026-10-29", "visit", "entry")
    with store.connect() as db:
        db.execute("UPDATE web_sessions SET expires = 0")
    assert not store.record_event(token, "2026-10-30", "visit", "entry")
    assert store.purge_expired() == 1
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
        assert db.execute("SELECT sum(count) FROM metric_counts").fetchone()[0] == 2


def test_existing_database_upgrades_without_changing_profile(tmp_path):
    path = tmp_path / "old.sqlite3"
    token = secrets.token_hex(32)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE web_sessions (id TEXT PRIMARY KEY, expires INTEGER NOT NULL, profile TEXT)")
        db.execute("INSERT INTO web_sessions VALUES (?, ?, ?)",
                   (WebStore.key(token), int(time.time()) + 86400, json.dumps(PROFILE, ensure_ascii=False)))
    new = WebStore(path)
    assert new.find(token)["profile"] == PROFILE
    assert new.record_event(token, "2026-10-28", "visit", "entry")
    assert token.encode() not in path.read_bytes()


def test_measurement_failure_does_not_block_registration(app, monkeypatch):
    def unavailable(*_args):
        raise sqlite3.OperationalError("synthetic metric failure")
    monkeypatch.setattr(app.extensions["fortune_store"], "record_event", unavailable)
    client = app.test_client(); headers = session(client)
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
    assert client.get("/api/session").json["profile"]["birth_date"] == PROFILE["birth_date"]


def test_metric_day_rolls_over_in_reporting_zone_not_server_zone():
    assert metric_day(datetime(2026, 10, 28, 14, 59, tzinfo=timezone.utc)) == "2026-10-28"
    assert metric_day(datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)) == "2026-10-29"


def test_report_reads_aggregates_only_without_mutating_the_database(tmp_path):
    path = tmp_path / "browser metrics.sqlite3"
    store = WebStore(path)
    token = store.create(86400); store.save(token, PROFILE)
    store.record_event(token, "2026-10-28", "visit", "entry")
    before = path.read_bytes()
    assert read_counts(path) == [{"day": "2026-10-28", "event": "visit", "view": "entry", "count": 1}]
    assert path.read_bytes() == before
    missing = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        read_counts(missing)
    assert not missing.exists()
