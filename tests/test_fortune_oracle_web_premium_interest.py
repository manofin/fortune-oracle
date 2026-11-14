"""Contact-free interest counts: honest acknowledgement and private aggregation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from test_fortune_oracle_web import app, session, PROFILE
from metrics_report import read_counts


THEMES = ("relationships", "resources", "career", "study", "western", "ziwei")


def interest(theme="relationships"):
    return {"event": "premium_interest", "view": theme}


def registered(app):
    client = app.test_client()
    headers = session(client)
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
    return client, headers


def counts(app):
    return [row for row in read_counts(app.config["WEB_STORE"])
            if row["event"] == "premium_interest"]


@pytest.mark.parametrize("payload", [
    None, [], {}, "premium_interest",
    {"event": "premium_interest"}, {"view": "relationships"},
    interest(""), interest("today"), interest("health"), interest("custom-theme"),
    interest(None), interest([]), interest({}),
    {**interest(), "email": "synthetic-only@example.test"},
    {**interest(), "birth_date": PROFILE["birth_date"]},
    {**interest(), "text": "가상 자유 입력"},
    {"event": "premium_interest:relationships", "view": "relationships"},
    {"event": "reading_viewed", "view": "relationships"},
])
def test_invalid_or_contact_bearing_event_never_changes_aggregates(app, payload):
    client, headers = registered(app)
    before = read_counts(app.config["WEB_STORE"])
    response = client.post("/api/events", headers=headers, json=payload)
    assert response.status_code == 400
    assert response.json["error"] == "invalid_event"
    assert read_counts(app.config["WEB_STORE"]) == before


def test_interest_requires_live_profile_session_csrf_and_origin(app):
    client = app.test_client()
    assert client.post("/api/events", json=interest()).status_code == 401
    headers = session(client)
    assert client.post("/api/events", json=interest()).status_code == 403
    assert client.post("/api/events", json=interest(), headers={
        **headers, "Origin": "https://elsewhere.example.test",
    }).status_code == 403
    assert client.post("/api/events", json=interest(), headers=headers).status_code == 409
    assert not counts(app)


def test_write_failure_is_not_reported_as_recorded_and_does_not_expose_input(app, monkeypatch, caplog):
    client, headers = registered(app)
    before = counts(app)
    marker = "SYNTHETIC_PRIVATE_EXCEPTION /private/store/path"

    def broken(*_args):
        raise sqlite3.OperationalError(marker)

    monkeypatch.setattr(app.extensions["fortune_store"], "record_event", broken)
    response = client.post("/api/events", headers=headers, json=interest())
    assert response.status_code == 503
    assert response.json["ok"] is False
    assert response.json["error"] == "interest_unavailable"
    assert "다시" in response.json["text"]
    assert marker not in response.text and marker not in caplog.text
    assert PROFILE["birth_date"] not in response.text
    assert counts(app) == before
    assert client.get("/api/session").json["profile"]["birth_date"] == PROFILE["birth_date"]
    # Existing passive metrics retain their best-effort response contract.
    assert client.post("/api/events", headers=headers,
                       json={"event": "reading_viewed", "view": "today"}).status_code == 202


def test_deletion_between_authentication_and_recording_gets_no_false_ack(app, monkeypatch):
    client, headers = registered(app)
    store = app.extensions["fortune_store"]
    original = store.record_event

    def delete_then_record(token, *args):
        store.delete(token)
        return original(token, *args)

    monkeypatch.setattr(store, "record_event", delete_then_record)
    response = client.post("/api/events", headers=headers, json=interest())
    assert response.status_code == 401
    assert response.json["error"] == "session_expired"
    assert not counts(app)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0


@pytest.mark.parametrize("theme", THEMES)
def test_each_allowlisted_theme_acknowledges_insert_and_duplicate_once(app, theme):
    client, headers = registered(app)
    before_profile = client.get("/api/session").json["profile"]
    for _ in range(2):
        response = client.post("/api/events", headers=headers, json=interest(theme))
        assert response.status_code == 202 and response.json == {"ok": True}
        assert response.headers["Cache-Control"] == "no-store"
    assert [(r["view"], r["count"]) for r in counts(app)] == [(theme, 1)]
    assert client.get("/api/session").json["profile"] == before_profile


def test_counts_separate_browsers_and_themes_without_contact_or_profile_export(app):
    clients = [registered(app), registered(app)]
    cookies = []
    for client, headers in clients:
        cookies.append(client.get_cookie("fortune_session").value)
        for theme in THEMES:
            assert client.post("/api/events", headers=headers, json=interest(theme)).status_code == 202
    exported = counts(app)
    assert {row["view"]: row["count"] for row in exported} == {theme: 2 for theme in THEMES}
    assert all(set(row) == {"day", "event", "view", "count"} for row in exported)
    text = json.dumps(exported, ensure_ascii=False)
    for value in (*cookies, PROFILE["display_name"], PROFILE["birth_date"], PROFILE["birth_time"]):
        assert value not in text


def test_kst_day_boundary_allows_next_day_count_without_resetting_session(app):
    app.config["NOW"] = datetime(2026, 11, 7, 14, 59, tzinfo=timezone.utc)
    client, headers = registered(app)
    for _ in range(2):
        assert client.post("/api/events", headers=headers, json=interest()).status_code == 202
    app.config["NOW"] = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
    assert client.post("/api/events", headers=headers, json=interest()).status_code == 202
    assert [(r["day"], r["count"]) for r in counts(app)] == [("2026-11-07", 1), ("2026-11-08", 1)]


def test_concurrent_retries_for_one_browser_count_once(app):
    client, headers = registered(app)
    token = client.get_cookie("fortune_session").value

    def post(_):
        with app.test_client() as retry:
            retry.set_cookie("fortune_session", token)
            response = retry.post("/api/events", headers=headers, json=interest("study"))
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(post, range(12)))
    assert results == [(202, {"ok": True})] * 12
    assert [(r["view"], r["count"]) for r in counts(app)] == [("study", 1)]


@pytest.mark.parametrize("revoke", ["delete", "expire"])
def test_revocation_removes_receipts_and_blocks_late_interest_but_keeps_aggregate(app, revoke):
    client, headers = registered(app)
    token = client.get_cookie("fortune_session").value
    store = app.extensions["fortune_store"]
    assert client.post("/api/events", headers=headers, json=interest()).status_code == 202
    if revoke == "delete":
        assert client.delete("/api/profile", headers=headers).status_code == 200
        client.set_cookie("fortune_session", token)
    else:
        with store.connect() as db:
            db.execute("UPDATE web_sessions SET expires = 0")
    response = client.post("/api/events", headers=headers, json=interest())
    assert response.status_code == 401
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
    assert [(r["view"], r["count"]) for r in counts(app)] == [("relationships", 1)]
