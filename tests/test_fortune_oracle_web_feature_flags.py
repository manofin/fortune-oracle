"""Reserved web features stay unavailable until separate, explicit opt-ins.

All profiles and stores are synthetic. Reopening a SQLite store exercises the
on-to-off transition without migrating or silently deleting existing fields.
"""

import secrets
from itertools import count
from pathlib import Path
import sqlite3

import pytest

from test_fortune_oracle_web import PROFILE, session
from fortune_web import create_app, service


FLAGS = ("INTEGRATED_ENABLED", "BIRTH_LOCATION_ENABLED")
LOCATION = {"birthplace_text": "가상 저장 도시", "latitude": 37.5665, "longitude": 126.978}


@pytest.fixture(autouse=True)
def no_ambient_opt_in(monkeypatch):
    for flag in FLAGS:
        monkeypatch.delenv("FORTUNE_WEB_" + flag, raising=False)


@pytest.fixture
def make_app(tmp_path):
    serial = count()
    signing_key = secrets.token_hex(32)
    def factory(**options):
        return create_app({
            "TESTING": True, "SECRET_KEY": signing_key,
            "WEB_STORE": str(tmp_path / f"flags-{next(serial)}.sqlite3"),
            "COOKIE_SECURE": False, **options,
        })
    return factory


def register(app, extra=None):
    client = app.test_client()
    headers = session(client)
    response = client.put("/api/profile", headers=headers, json={**PROFILE, **(extra or {})})
    assert response.status_code == 200
    return client, headers


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [None, "", "0", "false", "true", "yes", " 1 ", "1"])
def test_only_literal_environment_one_enables_each_feature(make_app, monkeypatch, flag, value):
    if value is not None:
        monkeypatch.setenv("FORTUNE_WEB_" + flag, value)
    app = make_app()
    assert app.config[flag] is (value == "1")
    assert app.config[next(other for other in FLAGS if other != flag)] is False


@pytest.mark.parametrize("value", [None, False, 0, 1, "", "0", "false", "true", "1", True])
def test_python_configuration_requires_actual_true(make_app, value):
    app = make_app(INTEGRATED_ENABLED=value, BIRTH_LOCATION_ENABLED=value)
    assert all(app.config[flag] is (value is True) for flag in FLAGS)


@pytest.mark.parametrize("integrated,location", [(False, False), (True, False), (False, True), (True, True)])
def test_opt_ins_are_independent_in_html_api_and_input(make_app, monkeypatch, integrated, location):
    app = make_app(INTEGRATED_ENABLED=integrated, BIRTH_LOCATION_ENABLED=location)
    client, headers = register(app)
    html = client.get("/").text
    assert ('data-view="integrated"' in html) is integrated
    assert ('src="/assets/integrated-card.js"' in html) is integrated
    for field in ('id="birthplace-text"', 'id="birth-latitude"', 'id="birth-longitude"'):
        assert (field in html) is location
    calls = []
    def report(profile):
        calls.append(profile.copy())
        return {"ok": True, "computed": True, "scope": "natal", "text": "가상 풀이"}
    monkeypatch.setattr(service, "integrated", report)
    assert client.get("/api/readings/integrated").status_code == (200 if integrated else 404)
    assert len(calls) == int(integrated)
    response = client.put("/api/profile", headers=headers, json={**PROFILE, **LOCATION})
    assert response.status_code == (200 if location else 400)
    saved = client.get("/api/session").json["profile"]
    assert (set(LOCATION) <= set(saved)) is location
    response = client.post("/api/events", headers=headers,
                           json={"event": "reading_viewed", "view": "integrated"})
    assert response.status_code == (202 if integrated else 400)


def test_default_disabled_route_rejects_before_authentication_or_calculation(make_app, monkeypatch):
    app = make_app()
    def forbidden(_):
        pytest.fail("A disabled feature must never invoke the report engine")
    monkeypatch.setattr(service, "integrated", forbidden)
    anonymous = app.test_client()
    empty = app.test_client()
    session(empty)
    known, _ = register(app)
    for client in (anonymous, empty, known):
        for path in ("/api/readings/integrated", "/api/readings/integrated?enabled=1&user_id=other"):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json["error"] == "feature_unavailable"
            assert response.json["computed"] is False
        assert client.head("/api/readings/integrated").status_code == 404


@pytest.mark.parametrize("extra", [
    {"birthplace_text": ""}, {"birthplace_text": None}, {"birthplace_text": "가상 새 도시"},
    {"latitude": None}, {"longitude": None}, {"latitude": 0}, {"longitude": 0},
    {"latitude": ""}, {"longitude": ""}, {"latitude": None, "longitude": None},
    {"latitude": 0, "longitude": 0}, LOCATION,
])
def test_disabled_collection_rejects_even_empty_keys_without_mutating_store(make_app, extra):
    app = make_app()
    client, headers = register(app)
    token = client.get_cookie("fortune_session").value
    before = Path(app.config["WEB_STORE"]).read_bytes()
    response = client.put("/api/profile", headers=headers, json={**PROFILE, **extra})
    assert response.status_code == 400
    assert response.json["error"] == "invalid_profile"
    assert not set(app.extensions["fortune_store"].find(token)["profile"]) & set(LOCATION)
    assert Path(app.config["WEB_STORE"]).read_bytes() == before


@pytest.mark.parametrize("extra", [{}, {"birthplace_text": "옛 가상 도시"},
                                    {"latitude": 0, "longitude": 0}, LOCATION])
def test_existing_profile_survives_disabled_restart_and_edit_until_explicit_delete(make_app, extra):
    enabled = make_app(BIRTH_LOCATION_ENABLED=True)
    client, headers = register(enabled, extra)
    token = client.get_cookie("fortune_session").value
    stored = enabled.extensions["fortune_store"].find(token)["profile"]
    disabled = create_app({**enabled.config, "BIRTH_LOCATION_ENABLED": False})
    returning = disabled.test_client()
    returning.set_cookie("fortune_session", token)
    # Feature changes do not migrate, anonymize or discard the owner's profile.
    assert disabled.extensions["fortune_store"].find(token)["profile"] == stored
    assert returning.get("/api/session").json["profile"] == stored
    assert returning.get("/api/readings/today").json["computed"] is True
    response = returning.put("/api/profile", headers=headers,
                             json={**PROFILE, "display_name": "가상 수정 별명"})
    assert response.status_code == 200
    changed = disabled.extensions["fortune_store"].find(token)["profile"]
    assert changed["display_name"] == "가상 수정 별명"
    assert {key: changed[key] for key in LOCATION if key in changed} == extra
    assert returning.delete("/api/profile", headers=headers).status_code == 200
    assert disabled.extensions["fortune_store"].find(token) is None
    with sqlite3.connect(disabled.config["WEB_STORE"]) as db:
        assert db.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM metric_receipts").fetchone()[0] == 0


def test_disabled_reading_cannot_create_an_integrated_view_receipt(make_app):
    app = make_app()
    client, headers = register(app)
    response = client.post("/api/events", headers=headers,
                           json={"event": "reading_viewed", "view": "integrated"})
    assert response.status_code == 400
    with sqlite3.connect(app.config["WEB_STORE"]) as db:
        for table in ("metric_receipts", "metric_counts"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE view = ?", ("integrated",)).fetchone()[0] == 0
