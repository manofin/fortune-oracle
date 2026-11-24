"""HTTP contracts with real engines, isolated browser identities, and a temporary DB."""
import secrets
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web import create_app


PROFILE = {"birth_date": "1990-05-17", "birth_time": "12:30", "display_name": "가상가",
           "timezone": "Asia/Seoul", "gender": "male"}


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                       "WEB_STORE": str(tmp_path / "web.sqlite3"), "COOKIE_SECURE": False,
                       "NOW": datetime(2026, 10, 28, 1, tzinfo=timezone.utc)})


def session(client):
    response = client.get("/api/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json["csrf"]}


def test_register_first_reading_return_delete_and_other_browser_isolation(app):
    a, b = app.test_client(), app.test_client()
    ha, hb = session(a), session(b)
    assert a.put("/api/profile", headers=ha, json=PROFILE).status_code == 200
    assert b.get("/api/session").json["profile"] is None
    assert b.get("/api/readings/today").status_code == 409
    other = {**PROFILE, "birth_date": "1990-05-15", "display_name": "가상나"}
    assert b.put("/api/profile", headers=hb, json=other).status_code == 200
    assert a.get("/api/session").json["profile"]["display_name"] == "가상가"
    today, tomorrow = a.get("/api/readings/today").json, a.get("/api/readings/tomorrow").json
    assert today["computed"] and tomorrow["computed"]
    assert today["date"] == "2026-10-28" and tomorrow["date"] == "2026-10-29"
    assert "경험적 해석" in today["text"] and "예측 확률이 아닙니다" in tomorrow["text"]
    chart = a.get("/api/chart").json
    assert chart["pillars"]["day"] == "壬午"
    markers = chart["natal_markers"]
    assert markers["coverage"]["complete"] is True
    by_rule = {rule["id"]: rule for rule in markers["rules"]}
    assert {"position": "day", "branch": "午"} in by_rule["dohwa_broad_branches"]["evidence"]
    assert "natal_markers" not in today["reading"]
    assert len(a.get("/api/kline").json["candles"]) == 31
    assert a.delete("/api/profile", headers=ha).status_code == 200
    assert a.get("/api/readings/today").status_code == 401
    assert b.get("/api/session").json["profile"]["display_name"] == "가상나"
    assert b.get("/api/readings/today").json["computed"]
    assert b.delete("/api/profile", headers=hb).status_code == 200
    raw = Path(app.config["WEB_STORE"]).read_bytes()
    assert "가상가".encode() not in raw and "가상나".encode() not in raw
    assert b"1990-05-17" not in raw and b"1990-05-15" not in raw


@pytest.mark.parametrize("change", [
    {"birth_date": "2026-02-31"}, {"birth_date": "2100-01-01"}, {"birth_time": "25:00"},
    {"birth_time": "12:65"}, {"timezone": "invalid/zone"}, {"birth_date": 19900517},
    {"display_name": "x" * 31}, {"gender": "bad"}, {"owner_id": "other"},
    {"display_name": "a\nb"},
    {"birth_date": "2024-11-03", "birth_time": "01:30", "timezone": "America/New_York"},
])
def test_bad_input_does_not_replace_profile(app, change):
    client = app.test_client(); headers = session(client)
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
    result = client.put("/api/profile", headers=headers, json={**PROFILE, **change})
    assert result.status_code == 400
    assert client.get("/api/session").json["profile"]["birth_date"] == PROFILE["birth_date"]


def test_unknown_birth_time_can_register_without_fabricated_daily_result(app):
    client = app.test_client(); headers = session(client)
    payload = {**PROFILE, "birth_date": "2024-02-04", "birth_time": ""}
    assert client.put("/api/profile", headers=headers, json=payload).status_code == 200
    chart = client.get("/api/chart").json
    assert chart["computed"] and chart["pillars"]["day"] == "戊戌"
    assert not chart["pillars"].get("time")
    markers = chart["natal_markers"]
    assert markers["coverage"]["available_positions"] == ["day"]
    assert all(rule["status"] == "insufficient_input" for rule in markers["rules"])
    for day in ("today", "tomorrow"):
        reading = client.get("/api/readings/" + day).json
        assert not reading["computed"] and reading["text"].startswith("계산 결과가 아님")
        assert "reading" not in reading
    assert client.get("/api/session").json["profile"]["birth_time"] == ""


def test_csrf_cross_origin_cookie_tamper_and_no_environment_profile_fallback(app, monkeypatch):
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:operator")
    monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", "1")
    client, stranger = app.test_client(), app.test_client()
    headers = session(client)
    assert client.put("/api/profile", json=PROFILE).status_code == 403
    assert client.put("/api/profile", json=PROFILE, headers={**headers, "Origin": "https://other.example"}).status_code == 403
    assert stranger.get("/api/readings/today").status_code == 401
    stranger.set_cookie("fortune_session", "a" * 64)
    assert stranger.get("/api/readings/today").status_code == 401
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
    response = client.get("/api/readings/today")
    assert response.json["computed"] and response.headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_deletion_revokes_old_cookie_and_no_plain_session_token_stored(app):
    client = app.test_client(); headers = session(client)
    cookie = client.get_cookie("fortune_session").value
    assert client.put("/api/profile", json=PROFILE, headers=headers).status_code == 200
    assert cookie.encode() not in Path(app.config["WEB_STORE"]).read_bytes()
    assert client.delete("/api/profile", headers=headers).status_code == 200
    client.set_cookie("fortune_session", cookie)
    assert client.put("/api/profile", json=PROFILE, headers=headers).status_code == 401
    assert client.get("/api/readings/today").status_code == 401


def test_production_cookie_and_no_implicit_storage_on_homepage(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3")})
    client = app.test_client()
    assert "Set-Cookie" not in client.get("/").headers
    cookie = client.get("/api/session", base_url="https://fortune.test").headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    with sqlite3.connect(app.config["WEB_STORE"]) as db:
        assert db.execute("SELECT profile FROM web_sessions").fetchall() == [(None,)]


def test_expired_personal_data_is_removed_without_a_new_browser_visit(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3"),
                      "START_CLEANUP": True, "CLEANUP_INTERVAL": .02})
    store = app.extensions["fortune_store"]
    stop, worker = app.extensions["fortune_cleanup"]
    try:
        token = store.create(86400)
        assert store.save(token, PROFILE)
        with store.connect() as db:
            db.execute("UPDATE web_sessions SET expires = 0")
        for _ in range(100):
            with store.connect() as db:
                count = db.execute("SELECT count(*) FROM web_sessions").fetchone()[0]
            if count == 0:
                break
            time.sleep(.01)
        assert count == 0
        assert b"1990-05-17" not in Path(app.config["WEB_STORE"]).read_bytes()
    finally:
        stop.set(); worker.join(timeout=2)


def test_https_proxy_origin_is_explicit_and_forwarded_headers_cannot_override_it(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3"),
                      "PUBLIC_ORIGIN": "https://fortune.test:10000"})
    client = app.test_client()
    response = client.get("/api/session", base_url="http://fortune.test:10000")
    headers = {"X-CSRF-Token": response.json["csrf"], "Origin": "https://fortune.test:10000"}
    assert "Secure" in response.headers["Set-Cookie"]
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert client.put("/api/profile", base_url="http://fortune.test:10000", headers=headers, json=PROFILE).status_code == 200
    for bad_origin in ("https://evil.test", "https://fortune.test", "http://fortune.test:10000"):
        spoofed = {**headers, "Origin": bad_origin, "X-Forwarded-Host": "evil.test", "X-Forwarded-Proto": "https"}
        assert client.put("/api/profile", base_url="http://fortune.test:10000", headers=spoofed, json=PROFILE).status_code == 403
    assert client.get("/api/session", base_url="http://evil.test").status_code == 400
    assert client.get("/healthz", base_url="http://127.0.0.1:8766").status_code == 200


@pytest.mark.parametrize("origin", ["http://fortune.test", "https://user:pass@fortune.test", "https://fortune.test/app", "https://fortune.test?x=1"])
def test_public_origin_rejects_unsafe_configuration(tmp_path, origin):
    with pytest.raises(RuntimeError):
        create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                    "WEB_STORE": str(tmp_path / "web.sqlite3"), "PUBLIC_ORIGIN": origin})
