"""Real loopback browser contract; synthetic inputs and no external requests."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import sys
import os

import pytest
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web import create_app


@contextmanager
def preview(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "WEB_STORE": str(tmp_path / "browser.sqlite3"), "COOKIE_SECURE": False})
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_lunar_register_reload_edit_partner_and_solar_reset(tmp_path, width):
    with preview(tmp_path) as url, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        def route(request):
            if not request.request.url.startswith(url + "/"):
                external.append(request.request.url)
                request.abort()
            else:
                request.continue_()
        page.route("**/*", route)
        page.goto(url)
        expect(page.locator("#birth-calendar")).to_be_visible()
        page.locator("#birth-calendar").select_option("lunar")
        # A lunar February 30 must not be constrained by Gregorian type=date.
        page.locator("#birth-date").fill("2023-02-30")
        assert page.locator("#birth-date").evaluate("e => e.checkValidity()")
        page.locator("#birth-date").fill("2023-02-01")
        page.locator("#birth-leap-month").check()
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        if os.environ.get("LUNAR_SCREENSHOTS"):
            output = Path(os.environ["LUNAR_SCREENSHOTS"])
            output.mkdir(parents=True, exist_ok=True)
            page.locator(".form-card").screenshot(path=str(output / f"lunar-form-{width}.png"))
        page.locator('#birth-form button[type="submit"]').click()
        expect(page.locator("#form-error")).to_be_hidden()
        expect(page.locator("#save-button")).to_be_enabled()
        result = page.request.get(url + "/api/session").json()["profile"]
        assert result["birth_date"] == "2023-03-22"
        page.reload()
        expect(page.locator("#birth-date")).to_have_value("2023-02-01")
        expect(page.locator("#birth-leap-month")).to_be_checked()
        page.locator("#display-name").fill("가상 음력")
        with page.expect_response("**/api/profile"):
            page.locator('#birth-form button[type="submit"]').click()
        assert page.request.get(url + "/api/session").json()["profile"]["birth_date"] == "2023-03-22"
        page.locator("#compat-details > summary").click()
        page.locator("#partner-calendar").select_option("lunar")
        page.locator("#partner-date").fill("2017-05-01")
        page.locator("#partner-leap-month").check()
        with page.expect_response("**/api/compat") as response:
            page.locator("#compat-submit").click()
        assert response.value.status == 200
        assert response.value.json()["computed"]
        expect(page.locator("#partner-calendar")).to_have_value("solar")
        assert page.locator("#partner-date").get_attribute("type") == "date"
        page.locator("#birth-calendar").select_option("solar")
        expect(page.locator("#birth-leap-month")).not_to_be_checked()
        page.locator("#birth-date").fill("2023-03-22")
        with page.expect_response("**/api/profile"):
            page.locator('#birth-form button[type="submit"]').click()
        result = page.request.get(url + "/api/session").json()["profile"]
        assert result["birth_calendar"] == "solar" and not result["birth_leap_month"]
        assert not errors and not external
        browser.close()
