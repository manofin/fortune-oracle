"""Integrated natal HTTP boundary; synthetic inputs and isolated SQLite only."""
import json
from pathlib import Path

import pytest

from test_fortune_oracle_web import app as base_app, session, PROFILE
from fortune_web import service


LOCATED = {**PROFILE, "birthplace_text": "가상 출생 도시", "latitude": 37.5665, "longitude": 126.9780}


@pytest.fixture
def app(base_app):
    # Only these opt-in contracts enable the reserved features. Free web tests
    # keep the application's default-off configuration.
    base_app.config.update(INTEGRATED_ENABLED=True, BIRTH_LOCATION_ENABLED=True)
    return base_app


def registered(app, profile=LOCATED):
    client = app.test_client()
    headers = session(client)
    assert client.put("/api/profile", headers=headers, json=profile).status_code == 200
    return client, headers


@pytest.mark.parametrize("location", [
    {"latitude": 1}, {"longitude": 1}, {"latitude": 1, "longitude": None},
    {"latitude": "37", "longitude": 127}, {"latitude": True, "longitude": 127},
    {"latitude": [], "longitude": 127}, {"latitude": 37, "longitude": {}},
    {"latitude": 90.0001, "longitude": 0}, {"latitude": -90.0001, "longitude": 0},
    {"latitude": 0, "longitude": 180.0001}, {"latitude": 0, "longitude": -180.0001},
    {"latitude": float("nan"), "longitude": 0},
    {"latitude": 0, "longitude": float("inf")},
    {"latitude": 10 ** 1000, "longitude": 0},
    {"birthplace_text": None}, {"birthplace_text": "x" * 81},
    {"birthplace_text": "city\nother"}, {"user_id": "other"},
])
def test_invalid_location_preserves_existing_profile(app, location):
    client, headers = registered(app)
    before = client.get("/api/session").json["profile"]
    response = client.put("/api/profile", headers=headers, json={**PROFILE, **location})
    assert response.status_code == 400
    assert client.get("/api/session").json["profile"] == before


@pytest.mark.parametrize("lat,lon", [(0, 0), (-90, -180), (90, 180), (37.5665, 126.978)])
def test_coordinates_and_unicode_roundtrip_and_explicit_removal(app, lat, lon):
    profile = {**LOCATED, "birthplace_text": "가상 도시 · São Paulo", "latitude": lat, "longitude": lon}
    client, headers = registered(app, profile)
    saved = client.get("/api/session").json["profile"]
    assert (saved["latitude"], saved["longitude"]) == (lat, lon)
    assert saved["birthplace_text"] == profile["birthplace_text"]
    assert json.loads(json.dumps(saved, ensure_ascii=False)) == saved
    client.put("/api/profile", headers=headers, json=PROFILE)
    saved = client.get("/api/session").json["profile"]
    assert not set(saved) & {"latitude", "longitude", "birthplace_text"}


@pytest.mark.parametrize("extra", [{}, {"latitude": None, "longitude": None}, {"birthplace_text": "서울"}])
def test_old_profile_and_city_label_never_guess_coordinates(app, extra):
    client, _ = registered(app, {**PROFILE, **extra})
    saved = client.get("/api/session").json["profile"]
    assert "latitude" not in saved and "longitude" not in saved


def test_report_requires_session_profile_and_cannot_select_another_owner(app, monkeypatch):
    seen = []
    def report(profile):
        seen.append(profile.copy())
        return {"ok": True, "computed": True, "kind": "integrated", "text": "synthetic report"}
    monkeypatch.setattr(service, "integrated", report)
    client = app.test_client()
    assert client.get("/api/readings/integrated").status_code == 401
    headers = session(client)
    assert client.get("/api/readings/integrated").status_code == 409
    assert not seen
    client.put("/api/profile", headers=headers, json=LOCATED)
    other, _ = registered(app, {**PROFILE, "birth_date": "1990-05-15"})
    response = client.get("/api/readings/integrated?user_id=other&birth_date=1990-05-15")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert seen[0]["birth_date"] == LOCATED["birth_date"]
    other.get("/api/readings/integrated")
    assert seen[1]["birth_date"] == "1990-05-15"
    token = client.get_cookie("fortune_session").value
    client.delete("/api/profile", headers=headers)
    client.set_cookie("fortune_session", token)
    assert client.get("/api/readings/integrated").status_code == 401
    assert len(seen) == 2


def test_all_failed_report_has_no_success_status_and_exceptions_are_private(app, monkeypatch):
    client, _ = registered(app)
    monkeypatch.setattr(service, "integrated", lambda _: {"ok": False, "computed": False, "text": "계산 불가"})
    response = client.get("/api/readings/integrated")
    assert response.status_code == 503 and response.json["computed"] is False
    def broken(_):
        raise RuntimeError("secret-profile-marker /private/location")
    monkeypatch.setattr(service, "integrated", broken)
    response = client.get("/api/readings/integrated")
    assert response.status_code == 500 and response.json["computed"] is False
    assert "secret-profile-marker" not in response.text and "/private/location" not in response.text


def test_real_report_is_natal_provenanced_private_and_not_persisted(app):
    client, _ = registered(app)
    before = Path(app.config["WEB_STORE"]).read_bytes()
    response = client.get("/api/readings/integrated")
    assert response.status_code == 200
    report = response.json
    assert report["computed"] and report["scope"] == "natal" and report["schema_version"] == 1
    assert {m["method"] for m in report["methods"]} == {"bazi", "ziwei", "western", "vedic"}
    ids = {e["id"] for e in report["evidence"]}
    claims = [c for t in report["themes"] for c in t["claims"]]
    assert claims and ids
    assert all(c["rule_id"] and c["time_scope"] == "natal" and c["evidence_ids"]
               and set(c["evidence_ids"]) <= ids for c in claims)
    body = json.dumps(report, ensure_ascii=False)
    for private in (PROFILE["birth_date"], PROFILE["display_name"], LOCATED["birthplace_text"],
                    "37.5665", "126.978"):
        assert private not in body
    assert json.loads(body) == report
    assert Path(app.config["WEB_STORE"]).read_bytes() == before


def test_unknown_time_does_not_become_midnight_in_new_report(app):
    client, _ = registered(app, {**PROFILE, "birth_time": ""})
    response = client.get("/api/readings/integrated")
    report = response.json
    assert response.status_code == 200 and report["computed"]  # Bazi partial is usable
    methods = {m["method"]: m for m in report["methods"]}
    assert methods["bazi"]["used_in_reading"]
    assert all(not methods[m]["used_in_reading"] for m in ("ziwei", "western", "vedic"))
    assert all(c["method"] == "bazi" for t in report["themes"] for c in t["claims"])


def test_integrated_metric_is_fixed_label_and_share_label_remains_restricted(app):
    client, headers = registered(app)
    event = {"event": "reading_viewed", "view": "integrated"}
    assert client.post("/api/events", headers=headers, json=event).status_code == 202
    assert client.post("/api/events", headers=headers, json={**event, "text": "report"}).status_code == 400
    assert client.post("/api/events", headers=headers,
                       json={"event": "share_handoff", "view": "integrated"}).status_code == 400
