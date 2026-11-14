"""Date and two-profile web contracts: fail closed and never persist the guest."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from test_fortune_oracle_web import app, session, PROFILE
from fortune_web import service


PARTNER = {"birth_date": "1997-08-19", "birth_time": "07:45", "timezone": "America/New_York", "gender": "unknown"}


def registered(app, profile=PROFILE):
    client = app.test_client(); headers = session(client)
    assert client.put("/api/profile", json=profile, headers=headers).status_code == 200
    return client, headers


@pytest.mark.parametrize("payload", [
    None, [], {}, {"date": 20261028}, {"date": "2026-2-01"}, {"date": "20261028"},
    {"date": "2026-W44-3"}, {"date": "2027-02-29"}, {"date": "2026-10-27"},
    {"date": "2027-10-29"}, {"date": "2026-10-28", "scenario": []},
    {"date": "2026-10-28", "scenario": "win_lottery"},
    {"date": "2026-10-28", "user_id": "other"},
])
def test_invalid_date_is_rejected_before_engine_and_preserves_profile(app, monkeypatch, payload):
    client, headers = registered(app)
    def forbidden(*_args, **_kwargs):
        pytest.fail("Invalid date must never reach the engine")
    monkeypatch.setattr(service, "build_personalized_daily", forbidden)
    response = client.post("/api/readings/date", json=payload, headers=headers)
    assert response.status_code == 400 and not response.json["computed"]
    assert "reading" not in response.json
    assert client.get("/api/session").json["profile"]["birth_date"] == PROFILE["birth_date"]


@pytest.mark.parametrize("offset", [0, 1, 365])
def test_inclusive_date_limits_and_same_daily_score(app, offset):
    client, headers = registered(app)
    target = (app.config["NOW"].date() + timedelta(days=offset)).isoformat()
    response = client.post("/api/readings/date", json={"date": target, "scenario": "exam"}, headers=headers)
    assert response.status_code == 200
    data = response.json
    assert data["date"] == target and data["computed"] and data["scenario"] == "exam"
    assert "별도 점수·성공 확률 아님" in data["text"]
    assert "예측 확률이 아닙니다" in data["text"]
    if offset < 2:
        regular = client.get("/api/readings/" + ("today" if offset == 0 else "tomorrow")).json
        assert data["reading"] == regular["reading"]
    general = client.post("/api/readings/date", json={"date": target, "scenario": "meeting"}, headers=headers).json
    assert general["reading"] == data["reading"]  # scenario adds a reflection, no invented score


@pytest.mark.parametrize("zone, expected", [("Asia/Seoul", "2026-10-29"), ("America/New_York", "2026-10-28")])
def test_date_bounds_follow_the_explicit_profile_zone(app, zone, expected):
    app.config["NOW"] = datetime(2026, 10, 28, 23, tzinfo=timezone.utc)
    client, headers = registered(app, {**PROFILE, "timezone": zone})
    window = client.get("/api/session").json["reading_window"]
    assert window["timezone"] == zone and window["min"] == expected
    assert client.post("/api/readings/date", json={"date": expected}, headers=headers).status_code == 200
    before = (datetime.fromisoformat(expected).date() - timedelta(days=1)).isoformat()
    assert client.post("/api/readings/date", json={"date": before}, headers=headers).status_code == 400


def test_leap_day_and_no_hidden_date_storage(app):
    app.config["NOW"] = datetime(2028, 2, 28, 1, tzinfo=timezone.utc)
    client, headers = registered(app)
    assert client.post("/api/readings/date", json={"date": "2028-02-29"}, headers=headers).json["computed"]
    assert b"2028-02-29" not in Path(app.config["WEB_STORE"]).read_bytes()


def test_ambiguous_birth_boundary_stays_uncomputed_for_dday(app):
    client, headers = registered(app, {**PROFILE, "birth_date": "2024-02-04", "birth_time": ""})
    response = client.post("/api/readings/date", json={"date": "2026-10-28"}, headers=headers)
    assert response.status_code == 503 and response.json["computed"] is False
    assert "reading" not in response.json and "score" not in response.json


@pytest.mark.parametrize("payload", [
    None, [], {}, {"partner": None}, {"partner": []}, {"partner": PARTNER, "owner": PROFILE},
    {"partner": {**PARTNER, "display_name": "민감 이름"}},
    {"partner": {**PARTNER, "user_id": "telegram:other"}},
    {"partner": {**PARTNER, "birth_date": "1997-02-30"}},
    {"partner": {**PARTNER, "birth_time": None}},
    {"partner": {**PARTNER, "timezone": "../../etc"}},
    {"partner": {**PARTNER, "birth_date": "2024-11-03", "birth_time": "01:30"}},
])
def test_invalid_partner_never_reaches_engine_or_storage(app, monkeypatch, payload):
    client, headers = registered(app)
    before = client.get("/api/session").json["profile"]
    def forbidden(*_args, **_kwargs):
        pytest.fail("Invalid guest must never reach the engine")
    monkeypatch.setattr(service, "build_compatibility", forbidden)
    response = client.post("/api/compat", json=payload, headers=headers)
    assert response.status_code == 400 and not response.json["computed"]
    assert client.get("/api/session").json["profile"] == before


@pytest.mark.parametrize("birth_time", ["07:45", ""])
def test_real_comparison_uses_own_profile_and_guest_timezone_without_persistence(app, birth_time):
    a, ha = registered(app)
    b, hb = registered(app, {**PROFILE, "birth_date": "1990-05-15", "display_name": "가상나"})
    partner = {**PARTNER, "birth_time": birth_time}
    for client, headers, day_master in ((a, ha, "壬"), (b, hb, "庚")):
        stored = client.get("/api/session").json["profile"]
        response = client.post("/api/compat", json={"partner": partner}, headers=headers)
        assert response.status_code == 200
        data = response.json
        assert data["computed"] and data["charts"][0]["day_master"] == day_master
        assert data["charts"][1]["birth_timezone"] == PARTNER["timezone"]
        assert data["status"] == ("runnable" if birth_time else "partial")
        assert ("time" in data["charts"][1]["pillars"]) == bool(birth_time)
        assert "score" not in data and "성공 확률을 예측하지 않습니다" in data["text"]
        assert client.get("/api/session").json["profile"] == stored
        assert PROFILE["display_name"] not in json.dumps(data, ensure_ascii=False)
        assert PARTNER["birth_date"] not in json.dumps(data)
    raw = Path(app.config["WEB_STORE"]).read_bytes()
    assert PARTNER["birth_date"].encode() not in raw and b"07:45" not in raw


@pytest.mark.parametrize("path, payload", [
    ("/api/compat", {"partner": PARTNER}), ("/api/readings/date", {"date": "2026-10-28"}),
])
def test_new_routes_require_session_profile_csrf_and_origin(app, path, payload):
    client = app.test_client()
    assert client.post(path, json=payload).status_code == 401
    headers = session(client)
    assert client.post(path, json=payload, headers=headers).status_code == 409
    client.put("/api/profile", json=PROFILE, headers=headers)
    assert client.post(path, json=payload).status_code == 403
    assert client.post(path, json=payload, headers={**headers, "Origin": "https://other.test"}).status_code == 403
    cookie = client.get_cookie("fortune_session").value
    client.delete("/api/profile", headers=headers)
    client.set_cookie("fortune_session", cookie)
    assert client.post(path, json=payload, headers=headers).status_code == 401


@pytest.mark.parametrize("engine, path, payload", [
    ("build_compatibility", "/api/compat", {"partner": PARTNER}),
    ("build_personalized_daily", "/api/readings/date", {"date": "2026-10-28"}),
])
@pytest.mark.parametrize("raises", [True, False])
def test_engine_failure_returns_no_synthetic_result_or_sensitive_error(app, monkeypatch, engine, path, payload, raises):
    client, headers = registered(app)
    def fail(*_args, **_kwargs):
        if raises:
            raise RuntimeError("sensitive 1997-08-19 /private/path")
        return None if engine == "build_personalized_daily" else {"ok": False}
    monkeypatch.setattr(service, engine, fail)
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 503 and not response.json["computed"]
    assert response.json["text"].startswith("계산 결과가 아님")
    assert not set(response.json) & {"reading", "score", "charts"}
    assert "sensitive" not in response.text and PARTNER["birth_date"] not in response.text


def test_profile_serialization_round_trip_keeps_unicode_and_unknown_time(app):
    client, headers = registered(app, {**PROFILE, "display_name": "가상 🪴 <별명>", "birth_time": "", "gender": "unknown"})
    saved = client.get("/api/session").json["profile"]
    assert saved == json.loads(json.dumps(saved, ensure_ascii=False))
    assert saved["display_name"] == "가상 🪴 <별명>" and saved["birth_time"] == ""
    with app.extensions["fortune_store"].connect() as db:
        stored = json.loads(db.execute("SELECT profile FROM web_sessions").fetchone()[0])
    assert stored == saved


def test_korean_zone_labels_preserve_canonical_calculation_identity(app):
    client, headers = registered(app, {**PROFILE, "timezone": "한국 시간"})
    assert client.get("/api/session").json["profile"]["timezone"] == "Asia/Seoul"
    partner = {key: value for key, value in PROFILE.items() if key != "display_name"}
    partner["timezone"] = "일본 시간"
    response = client.post("/api/compat", json={"partner": partner}, headers=headers)
    assert response.status_code == 200
    assert "A 출생 시간대: 한국 시간" in response.json["text"]
    assert "B 출생 시간대: 일본 시간" in response.json["text"]
    assert "Asia/Seoul" not in response.json["text"]
