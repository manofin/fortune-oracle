"""Public editorial samples and anonymous, receipt-backed interest contracts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from test_fortune_oracle_web import app, session
from metrics_report import read_counts


SAMPLES = ("self_manual_v1", "conversation_guide_v1", "four_perspectives_v1")
EVENTS = ("product_sample_viewed", "product_sample_interest")


def payload(event=EVENTS[0], view=SAMPLES[0]):
    return {"event": event, "view": view}


def anonymous(app):
    client = app.test_client()
    return client, {**session(client), "Origin": "http://localhost"}


def counts(app):
    return [row for row in read_counts(app.config["WEB_STORE"]) if row["event"] in EVENTS]


def post(client, headers, event=EVENTS[0], view=SAMPLES[0]):
    return client.post("/api/events", headers=headers, json=payload(event, view))


@pytest.mark.parametrize("path", ["/samples", "/samples/"])
def test_public_samples_do_not_touch_session_database_or_calculation(app, monkeypatch, path):
    from fortune_web import service
    store = app.extensions["fortune_store"]

    def forbidden(*_args, **_kwargs):
        pytest.fail("Public samples must only read the static document")

    monkeypatch.setattr(store, "connect", forbidden)
    for name in ("daily", "chart", "kline", "dated_reading", "compatibility", "reading_window"):
        monkeypatch.setattr(service, name, forbidden)
    client = app.test_client()
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Set-Cookie" not in response.headers
    assert client.get_cookie("fortune_session") is None
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize("view", SAMPLES)
def test_anonymous_view_then_interest_and_duplicates_are_acknowledged_once(app, view):
    client, headers = anonymous(app)
    for event in EVENTS:
        for _ in range(2):
            response = post(client, headers, event, view)
            assert response.status_code == 202 and response.json == {"ok": True}
    assert [(r["event"], r["view"], r["count"]) for r in counts(app)] == [
        ("product_sample_interest", view, 1), ("product_sample_viewed", view, 1)]
    assert client.get("/api/session").json["profile"] is None
    assert client.post("/api/events", headers=headers,
                       json={"event": "premium_interest", "view": "career"}).json["error"] == "profile_required"
    assert client.get("/api/readings/today").json["error"] == "profile_required"


@pytest.mark.parametrize("event", EVENTS)
def test_new_events_require_live_browser_session_csrf_and_explicit_same_origin(app, event):
    client = app.test_client()
    assert post(client, {}, event).status_code == 401
    headers = session(client)
    assert post(client, {"Origin": "http://localhost"}, event).status_code == 403
    assert post(client, headers, event).json["error"] == "origin_invalid"
    assert post(client, {**headers, "Origin": "https://other.example"}, event).status_code == 403
    assert counts(app) == []


@pytest.mark.parametrize("bad", [
    payload(view="self_manual"), payload(view="self_manual_v2"), payload(view="career"),
    payload(view="today"), payload(view=None), payload(view=[]), payload(view={}),
    {**payload(), "email": "synthetic@example.test"},
    {**payload(), "birth_date": "1990-05-17"}, {**payload(), "text": "free text"},
    {**payload(), "price": 9900}, {**payload(), "version": "v1"},
    payload(event="product_sample_purchase"),
    {"event": "premium_interest", "view": SAMPLES[0]},
])
def test_fixed_allowlist_rejects_unknown_versions_cross_event_ids_and_extra_input(app, bad):
    client, headers = anonymous(app)
    response = client.post("/api/events", headers=headers, json=bad)
    assert response.status_code == 400 and response.json["error"] == "invalid_event"
    assert not counts(app)


def test_interest_needs_same_product_and_same_browser_receipt(app):
    first, headers = anonymous(app)
    response = post(first, headers, EVENTS[1])
    assert response.status_code == 409 and response.json["error"] == "sample_not_viewed"
    assert post(first, headers).status_code == 202
    assert post(first, headers, EVENTS[1], SAMPLES[1]).status_code == 409
    other, other_headers = anonymous(app)
    assert post(other, other_headers, EVENTS[1]).status_code == 409
    assert post(first, headers, EVENTS[1]).status_code == 202
    assert all(r["count"] == 1 for r in counts(app))


def test_kst_boundary_requires_fresh_view_and_separates_daily_counts(app):
    client, headers = anonymous(app)
    app.config["NOW"] = datetime(2026, 11, 7, 14, 59, tzinfo=timezone.utc)
    assert post(client, headers).status_code == 202
    assert post(client, headers, EVENTS[1]).status_code == 202
    app.config["NOW"] = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
    assert post(client, headers, EVENTS[1]).status_code == 409
    assert post(client, headers).status_code == 202
    assert post(client, headers, EVENTS[1]).status_code == 202
    assert {(r["day"], r["event"], r["count"]) for r in counts(app)} == {
        (day, event, 1) for day in ("2026-11-07", "2026-11-08") for event in EVENTS}


@pytest.mark.parametrize("event", EVENTS)
def test_concurrent_retries_insert_one_receipt_and_count(app, event):
    client, headers = anonymous(app)
    token = client.get_cookie("fortune_session").value
    if event == EVENTS[1]:
        assert post(client, headers).status_code == 202

    def retry(_):
        with app.test_client() as browser:
            browser.set_cookie("fortune_session", token)
            response = post(browser, headers, event)
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(retry, range(12)))
    assert results == [(202, {"ok": True})] * 12
    assert [r["count"] for r in counts(app) if r["event"] == event] == [1]


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("revoke", ["delete", "expire"])
def test_revocation_between_authentication_and_transaction_cannot_acknowledge(app, monkeypatch, event, revoke):
    client, headers = anonymous(app)
    store = app.extensions["fortune_store"]
    if event == EVENTS[1]:
        assert post(client, headers).status_code == 202
    before = counts(app)
    original = store.record_sample_event

    def revoke_then_record(token, *args):
        if revoke == "delete":
            store.delete(token)
        else:
            with store.connect() as db:
                db.execute("UPDATE web_sessions SET expires = 0")
        return original(token, *args)

    monkeypatch.setattr(store, "record_sample_event", revoke_then_record)
    response = post(client, headers, event)
    assert response.status_code == 401 and response.json["error"] == "session_expired"
    assert counts(app) == before


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("failure", ["find", "record_sample_event"])
def test_database_failure_returns_retry_without_private_exception(app, monkeypatch, caplog, event, failure):
    client, headers = anonymous(app)
    if event == EVENTS[1]:
        assert post(client, headers).status_code == 202
    before = counts(app)
    marker = "SYNTHETIC_PRIVATE /private/db/path birth_date=1990-05-17"

    def broken(*_args):
        raise sqlite3.OperationalError(marker)

    monkeypatch.setattr(app.extensions["fortune_store"], failure, broken)
    response = post(client, headers, event)
    assert response.status_code == 503 and not response.json["ok"]
    assert "다시" in response.json["text"]
    assert marker not in response.text and marker not in caplog.text
    assert counts(app) == before


def test_receipt_and_aggregate_rollback_together_on_write_failure(app):
    client, headers = anonymous(app)
    store = app.extensions["fortune_store"]
    with store.connect() as db:
        db.execute("""CREATE TRIGGER fail_sample_count BEFORE INSERT ON metric_counts
            WHEN NEW.event = 'product_sample_viewed'
            BEGIN SELECT RAISE(ABORT, 'synthetic transaction failure'); END""")
    assert post(client, headers).status_code == 503
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM metric_receipts WHERE event = ?", (EVENTS[0],)).fetchone()[0] == 0
        db.execute("DROP TRIGGER fail_sample_count")
    assert post(client, headers, EVENTS[1]).status_code == 409
    assert post(client, headers).status_code == 202
    assert counts(app)[0]["count"] == 1


@pytest.mark.parametrize("revoke", ["delete", "expire"])
def test_receipts_vanish_on_revocation_while_private_free_counts_survive(app, revoke):
    client, headers = anonymous(app)
    token = client.get_cookie("fortune_session").value
    store = app.extensions["fortune_store"]
    for event in EVENTS:
        assert post(client, headers, event).status_code == 202
    if revoke == "delete":
        assert client.delete("/api/profile", headers=headers).status_code == 200
        client.set_cookie("fortune_session", token)
    else:
        with store.connect() as db:
            db.execute("UPDATE web_sessions SET expires = 0")
        store.purge_expired()
    assert post(client, headers, EVENTS[1]).status_code == 401
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
    exported = counts(app)
    assert len(exported) == 2 and all(r["count"] == 1 for r in exported)
    assert all(set(r) == {"day", "event", "view", "count"} for r in exported)
    assert token not in json.dumps(exported) and store.key(token) not in json.dumps(exported)
    fresh_headers = {**session(client), "Origin": "http://localhost"}
    assert post(client, fresh_headers, EVENTS[1]).status_code == 409
