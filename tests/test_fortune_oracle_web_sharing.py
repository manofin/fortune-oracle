"""Common previews and fixed-source visit metrics, without personal result URLs."""

import secrets
from html.parser import HTMLParser
from pathlib import Path
import struct

import pytest

from test_fortune_oracle_web import app, session, PROFILE
from fortune_web import create_app


class Metadata(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property", attrs.get("name"))] = attrs.get("content")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")


def test_common_og_html_uses_configured_origin_without_session_or_query(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "web.sqlite3"),
                      "PUBLIC_ORIGIN": "https://fortune.example"})
    client = app.test_client()
    response = client.get("/?from=card&name=PRIVATE_CANARY", headers={"X-Forwarded-Host": "evil.example"})
    assert response.status_code == 200 and "Set-Cookie" not in response.headers
    html = response.get_data(as_text=True)
    assert "PRIVATE_CANARY" not in html and "evil.example" not in html
    data = Metadata(html)
    assert data.canonical == data.meta["og:url"] == "https://fortune.example/"
    assert data.meta["og:type"] == "website" and data.meta["og:locale"] == "ko_KR"
    assert data.meta["og:image"] == "https://fortune.example/assets/share/fortune-oracle-og.png"
    assert data.meta["og:image:width"] == "1200" and data.meta["og:image:height"] == "630"
    assert "개인 결과" in data.meta["og:image:alt"]
    with app.extensions["fortune_store"].connect() as db:
        assert db.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM metric_counts").fetchone()[0] == 0
    image = client.get("/assets/share/fortune-oracle-og.png")
    assert image.status_code == 200 and image.mimetype == "image/png"
    assert image.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image.data[16:24]) == (1200, 630)
    assert "Set-Cookie" not in image.headers


def test_profile_never_changes_public_preview(app):
    client = app.test_client()
    before = client.get("/").data
    header = session(client)
    assert client.put("/api/profile", json=PROFILE, headers=header).status_code == 200
    assert client.get("/?from=card").data == before
    assert PROFILE["display_name"].encode() not in before
    assert PROFILE["birth_date"].encode() not in before


def test_shared_visit_before_registration_is_deduplicated_and_deleted_with_session(app):
    event = {"event": "shared_link_visit", "view": "card"}
    for _ in range(2):
        client = app.test_client(); header = session(client)
        assert client.post("/api/events", json=event).status_code == 403
        for _ in range(3):
            assert client.post("/api/events", json=event, headers=header).status_code == 202
        assert client.get("/api/session").json["profile"] is None
        assert client.delete("/api/profile", headers=header).status_code == 200
        assert client.post("/api/events", json=event, headers=header).status_code == 401
    with app.extensions["fortune_store"].connect() as db:
        assert db.execute("SELECT count FROM metric_counts WHERE event='shared_link_visit' AND view='card'").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM metric_receipts").fetchone()[0] == 0
    assert b"from=card" not in Path(app.config["WEB_STORE"]).read_bytes()


@pytest.mark.parametrize("event", [
    {"event": "shared_link_visit", "view": "unknown"},
    {"event": "shared_link_visit", "view": "https://personal.example/"},
    {"event": "shared_link_visit", "view": "card", "url": "https://personal.example/"},
    {"event": "shared_link_visit", "view": "card", "referrer": "PRIVATE_CANARY"},
    {"event": "shared_link_visit", "view": "card", "sender": "PRIVATE_CANARY"},
])
def test_source_metrics_reject_identifiers_and_unknown_values(app, event):
    client = app.test_client(); header = session(client)
    assert client.post("/api/events", json=event, headers=header).status_code == 400
    assert b"PRIVATE_CANARY" not in Path(app.config["WEB_STORE"]).read_bytes()
