"""Verified browser isolation, bounded unauthenticated work, and HTTP contracts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import sys

import pytest
from werkzeug.exceptions import TooManyRequests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web import create_app
from fortune_web.rate_limit import FixedWindowLimiter


@pytest.fixture
def limited_app(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3"), "COOKIE_SECURE": False,
                      "RATE_LIMIT_REQUESTS": 2, "RATE_LIMIT_INGRESS_REQUESTS": 100})
    now = [0.0]
    for name in ("fortune_rate_limiter", "fortune_ingress_limiter"):
        app.extensions[name]._clock = lambda: now[0]
    app.extensions["test_clock"] = now
    return app


def test_sessions_behind_one_proxy_do_not_share_browser_budget(limited_app):
    first, second = limited_app.test_client(), limited_app.test_client()
    assert first.get("/api/session").status_code == 200
    assert second.get("/api/session").status_code == 200
    for _ in range(2):
        assert first.get("/api/session").status_code == 200
    blocked = first.get("/api/session")
    assert blocked.status_code == 429 and blocked.json["error"] == "rate_limited"
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.headers["Cache-Control"] == "no-store"
    for _ in range(2):
        assert second.get("/api/session").status_code == 200
    assert second.get("/api/session").status_code == 429


def test_forged_cookies_and_forwarded_headers_do_not_create_new_budgets(limited_app):
    client = limited_app.test_client()
    for index, expected in enumerate((401, 401, 429)):
        client.set_cookie("fortune_session", secrets.token_hex(32))
        response = client.get("/api/chart", headers={"X-Forwarded-For": f"198.51.100.{index + 1}"})
        assert response.status_code == expected
    assert response.json["computed"] is False


def test_deleted_cookie_cannot_keep_a_verified_session_budget(limited_app):
    client = limited_app.test_client()
    assert client.get("/api/session").status_code == 200
    cookie = client.get_cookie("fortune_session").value
    limited_app.extensions["fortune_store"].delete(cookie)
    assert client.get("/api/chart").status_code == 401
    assert client.get("/api/chart").status_code == 429


def test_untrusted_forwarding_cannot_split_one_verified_session(limited_app):
    client = limited_app.test_client()
    assert client.get("/api/session").status_code == 200
    for index, expected in enumerate((200, 200, 429)):
        response = client.get("/api/session", headers={"X-Forwarded-For": f"192.0.2.{index + 1}"})
        assert response.status_code == expected


def test_retry_after_and_reset_follow_original_window(limited_app):
    client = limited_app.test_client()
    assert client.get("/api/session").status_code == 200
    for _ in range(2):
        assert client.get("/api/session").status_code == 200
    limited_app.extensions["test_clock"][0] = 59.5
    assert client.get("/api/session").headers["Retry-After"] == "1"
    limited_app.extensions["test_clock"][0] = 60.0
    assert client.get("/api/session").status_code == 200


def test_transport_ceiling_stops_database_lookups_before_access(limited_app, monkeypatch):
    ingress = limited_app.extensions["fortune_ingress_limiter"]
    ingress.requests = 3
    store = limited_app.extensions["fortune_store"]
    original_find, lookups = store.find, []
    def counted_find(value):
        lookups.append(True)
        return original_find(value)
    monkeypatch.setattr(store, "find", counted_find)
    client = limited_app.test_client()
    for _ in range(8):
        client.set_cookie("fortune_session", secrets.token_hex(32))
        response = client.get("/api/chart")
    assert response.status_code == 429
    assert len(lookups) == 3


def test_limiter_retains_no_raw_session_cookie(limited_app):
    client = limited_app.test_client()
    client.get("/api/session")
    cookie = client.get_cookie("fortune_session").value
    client.get("/api/session")
    keys = limited_app.extensions["fortune_rate_limiter"]._buckets
    assert ("session", limited_app.extensions["fortune_store"].key(cookie)) in keys
    assert all(cookie not in str(key) for key in keys)


def test_capacity_does_not_evict_live_budgets_and_expiry_frees_space():
    now = [0.0]
    limiter = FixedWindowLimiter(requests=2, capacity=1, clock=lambda: now[0])
    assert limiter.consume("first").error is None
    assert limiter.consume("second").error == "busy"
    assert limiter.consume("first").error is None
    assert limiter.consume("first").error == "rate_limited"
    now[0] = 60.0
    assert limiter.consume("second").error is None


def test_parallel_calls_cannot_exceed_one_budget():
    limiter = FixedWindowLimiter(requests=7, clock=lambda: 0.0)
    with ThreadPoolExecutor(max_workers=16) as pool:
        decisions = list(pool.map(lambda _: limiter.consume("same"), range(64)))
    assert sum(decision.error is None for decision in decisions) == 7
    assert sum(decision.error == "rate_limited" for decision in decisions) == 57


@pytest.mark.parametrize("field", ["requests", "window", "capacity"])
@pytest.mark.parametrize("value", [0, -1, True, "120", 1.5])
def test_invalid_limiter_config_is_not_silently_coerced(field, value):
    with pytest.raises(ValueError):
        FixedWindowLimiter(**{field: value})


def test_framework_retry_header_survives_private_json_body(limited_app):
    @limited_app.get("/test-http-error")
    def reject():
        raise TooManyRequests(description="PRIVATE_ERROR_DETAIL", retry_after=17)
    response = limited_app.test_client().get("/test-http-error")
    assert response.status_code == 429 and response.headers["Retry-After"] == "17"
    assert response.is_json and response.json["error"] == "request_failed"
    assert "PRIVATE_ERROR_DETAIL" not in response.get_data(as_text=True)
