"""Loopback-only browser contracts for the default-disabled reserved features.

Run against web/preview.py with both opt-in environment variables unset. Uses
an invented profile, temporary preview storage and local requests only.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:49132")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    origin = urlsplit(base)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, external, requests, saves = [], [], [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        def only_local(route):
            if urlsplit(route.request.url).netloc != origin.netloc:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        context.route("**/*", only_local)
        assert context.request.get(base + "/healthz").json()["version"] == "local-preview"
        assert context.request.get(base + "/api/readings/integrated").status == 404
        passed.append("disabled API rejects anonymous direct access")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        def capture(request):
            path = urlsplit(request.url).path
            requests.append(path)
            if path == "/api/profile" and request.method == "PUT":
                saves.append(request.post_data_json)
        page.on("request", capture)
        page.goto(base)
        expect(page.locator("#empty-state")).to_be_visible()
        assert page.locator("body").get_attribute("data-integrated-enabled") == "false"
        assert page.locator("body").get_attribute("data-birth-location-enabled") == "false"
        assert page.locator('[data-view="integrated"], #birthplace-text, #birth-latitude, #birth-longitude').count() == 0
        assert "/assets/integrated-card.js" not in requests
        expect(page.locator("#premium-interest")).to_be_hidden()
        passed.append("default screen omits report tab, location inputs and optional PNG script")

        page.locator("#display-name").fill("가상 기본 사용자")
        page.locator("#birth-date").fill("1996-04-18")
        page.locator("#gender").select_option("female")
        page.locator("#unknown-time").uncheck()
        page.locator("#birth-time").fill("09:30")
        page.locator("#save-button").click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=30000)
        expect(page.locator("#premium-interest")).to_be_visible()
        assert not set(saves[-1]) & {"latitude", "longitude", "birthplace_text"}
        page.locator('[data-view="tomorrow"]').click()
        expect(page.locator("#keyword-title")).to_have_text("내일을 바라보는 키워드")
        passed.append("default registration, daily and tomorrow readings work without location keys")

        before = requests.count("/api/readings/integrated")
        page.evaluate("loadView('integrated')")
        assert requests.count("/api/readings/integrated") == before
        expect(page.locator("#integrated-result")).to_be_hidden()
        passed.append("disabled client route cannot issue report requests or display results")

        denied = page.evaluate("""async () => {
          const session = await fetch('/api/session').then(r => r.json());
          const response = await fetch('/api/readings/integrated?enabled=1');
          const event = await fetch('/api/events', {method:'POST',
            headers:{'Content-Type':'application/json', 'X-CSRF-Token':session.csrf},
            body:JSON.stringify({event:'reading_viewed', view:'integrated'})});
          return [response.status, (await response.json()).computed, event.status];
        }""")
        assert denied == [404, False, 400]
        passed.append("valid session cannot bypass disabled API or create a report-view event")

        # Forge a direct request, rather than relying only on missing form controls.
        rejected = page.evaluate("""async () => {
          const before = await fetch('/api/session').then(r => r.json());
          const profile = Object.fromEntries(['birth_date','birth_time','display_name','timezone','gender'].map(k => [k,before.profile[k]]));
          const response = await fetch('/api/profile', {method:'PUT',
            headers:{'Content-Type':'application/json','X-CSRF-Token':before.csrf},
            body:JSON.stringify({...profile,latitude:null,longitude:null,birthplace_text:''})});
          const after = await fetch('/api/session').then(r => r.json());
          return [response.status, JSON.stringify(before.profile) === JSON.stringify(after.profile)];
        }""")
        assert rejected == [400, True]
        passed.append("direct empty/null location payload is rejected without changing the saved profile")

        page.reload()
        expect(page.locator("#daily-result")).to_be_visible(timeout=30000)
        expect(page.locator("#display-name")).to_have_value("가상 기본 사용자")
        page.locator("#display-name").fill("가상 수정 사용자")
        page.locator("#save-button").click()
        expect(page.locator("#reading-title")).to_have_text("가상 수정 사용자님의 하루")
        expect(page.locator("#daily-result")).to_be_visible(timeout=30000)
        assert not set(saves[-1]) & {"latitude", "longitude", "birthplace_text"}
        passed.append("returning browser and ordinary profile edit work with location controls absent")

        button = page.locator('[data-premium-interest="study"]')
        button.click()
        expect(button).to_have_text("관심 보냈어요")
        expect(page.locator(".premium-privacy")).to_contain_text("브라우저 세션 기준")
        expect(page.locator(".premium-privacy")).to_contain_text("정보 삭제나 만료 후에는 날짜별 합계만")
        passed.append("interest acknowledgement and corrected session-retention notice remain available")

        for width, height in ((320, 640), (390, 844), (1280, 900)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(args.output / f"default-off-{width}.png"), full_page=True, animations="disabled")
        passed.append("default screen fits 320px, 390px and desktop widths")
        page.locator("#delete-button").click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        expect(page.locator("#premium-interest")).to_be_hidden()
        assert page.evaluate("fetch('/api/session').then(r => r.json()).then(r => r.profile)") is None
        assert not errors and not external, {"page_errors": errors, "external_requests": external}
        passed.append("explicit deletion works with both features disabled; no JavaScript errors or external requests")
        browser.close()
    result = {"passed": passed, "page_errors": errors, "external_requests": external,
              "scope": "local Chromium; default-disabled features; synthetic profiles and temporary store"}
    (args.output / "feature-flags-browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
