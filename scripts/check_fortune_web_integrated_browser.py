"""Loopback-only browser checks for explicitly enabled integrated readings.

Start the temporary preview with FORTUNE_WEB_INTEGRATED_ENABLED=1 and
FORTUNE_WEB_BIRTH_LOCATION_ENABLED=1. Both remain disabled by default.
"""
import argparse
import copy
import json
from pathlib import Path
import struct
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8884")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    origin = urlparse(args.url)
    assert origin.hostname in {"localhost", "127.0.0.1"}, "Temporary loopback preview only"
    args.output.mkdir(parents=True, exist_ok=True)
    errors, external, events, passed = [], [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        context.add_init_script("""
          window.reportInk = [];
          const fill = CanvasRenderingContext2D.prototype.fillText;
          CanvasRenderingContext2D.prototype.fillText = function(text, x, y, ...rest) {
            if (this.font.startsWith('38px ') && y >= 228 && y <= 1146) window.reportInk.push(String(text));
            return fill.call(this, text, x, y, ...rest);
          };
        """)
        def only_local(route):
            target = urlparse(route.request.url)
            if target.netloc != origin.netloc:
                external.append(target.netloc); route.abort(); return
            if target.path == "/api/events":
                events.append(route.request.post_data_json)
            route.continue_()
        context.route("**/*", only_local)
        page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        assert page.evaluate("fetch('/healthz').then(r=>r.json()).then(r=>r.version)") == "local-preview"
        expect(page.locator("#empty-state")).to_be_visible()
        assert page.locator("body").get_attribute("data-integrated-enabled") == "true", "Enable the preview's report flag explicitly"
        assert page.locator("body").get_attribute("data-birth-location-enabled") == "true", "Enable the preview's location flag explicitly"

        def register(unknown=False):
            page.locator("#display-name").fill("가상<나>")
            page.locator("#birth-date").fill("1996-04-18")
            page.locator("#gender").select_option("female")
            if not unknown:
                page.locator("#unknown-time").uncheck(); page.locator("#birth-time").fill("09:30")
            page.locator("#save-button").click()
            expect(page.locator("#daily-result")).to_be_visible(timeout=20000)

        def remove():
            page.locator("#delete-button").click(); page.locator("#confirm-delete").click()
            expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
            expect(page.locator("#delete-dialog")).to_be_hidden()

        register()
        page.locator('[data-view="integrated"]').click()
        expect(page.locator("#integrated-result")).to_be_visible(timeout=30000)
        expect(page.locator("#chart-section")).to_be_hidden()
        assert page.locator(".integrated-method").count() == 4
        actual = page.evaluate("fetch('/api/readings/integrated').then(r=>r.json())")
        assert actual["computed"] and actual["scope"] == "natal"
        assert page.locator("#integrated-text").text_content() == actual["text"]
        for private in ("가상<나>", "1996-04-18", "09:30"):
            assert private not in actual["text"]
        page.locator(".theme-evidence").first.locator("summary").click()
        expect(page.locator(".theme-claims").first).to_be_visible()
        passed.append("real integrated API shows four statuses, sourced natal themes and unchanged report text")

        for width, height, name in ((320, 640, "small-phone"), (390, 844, "mobile"), (1280, 900, "desktop")):
            page.set_viewport_size({"width":width, "height":height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator('[data-view="integrated"]').bounding_box()["height"] >= 44 - .01
            page.screenshot(path=str(args.output / f"{name}-integrated.png"), animations="disabled", full_page=True)
        page.set_viewport_size({"width":390, "height":844})
        passed.append("320px, mobile and desktop layouts fit without horizontal overflow and keep 44px tabs")

        page.evaluate("window.reportInk = []")
        page.locator("#open-integrated-share").click()
        expect(page.locator("#download-integrated-share")).to_be_enabled(timeout=60000)
        drawn = "".join(page.evaluate("window.reportInk"))
        assert drawn == actual["text"].replace("\n", ""), "Canvas body must preserve every original character"
        count = int(page.locator("#integrated-page-number").inner_text().split("/")[1])
        assert count > 1, "The full report must paginate instead of shrinking or truncating"
        with page.expect_download() as pending:
            page.locator("#download-integrated-share").click()
        path = args.output / "integrated-page-01.png"; pending.value.save_as(path)
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (1080, 1350)
        assert len(raw) > 20000
        page.locator("#integrated-page-next").click()
        expect(page.locator("#integrated-page-number")).to_have_text(f"2 / {count}")
        expect(page.locator("#integrated-page-prev")).to_be_enabled()
        page.screenshot(path=str(args.output / "mobile-integrated-share.png"), animations="disabled")
        page.locator("#close-integrated-share").click()
        passed.append("1080x1350 paginated PNG preserves every report character and page navigation/download work")

        boundary_text = "\n  공백과 줄바꿈 보존\r\n\n" + "긴단어己丑🙂가" * 90 + "\n\n끝  \n"
        pagination = page.evaluate("""async text => {
          window.reportInk = [];
          const pages = await FortuneIntegratedCard.render(text);
          return {source:pages.map(page=>page.text).join(''), ink:window.reportInk.join(''),
                  count:pages.length, sizes:pages.map(page=>page.blob.size)};
        }""", boundary_text)
        assert pagination["source"] == boundary_text
        assert pagination["ink"] == boundary_text.replace("\r", "").replace("\n", "")
        assert pagination["count"] > 1 and min(pagination["sizes"]) > 5000
        passed.append("PNG pagination preserves leading/trailing spaces, blank lines, CRLF, long words and Unicode graphemes")

        # New fields remain explicit, numeric and independent of the selected timezone.
        page.locator(".birth-location summary").click()
        page.locator("#birthplace-text").fill("가상 도시")
        page.locator("#birth-latitude").fill("37.5665")
        page.locator("#save-button").click()
        expect(page.locator("#form-error")).to_contain_text("위도와 경도를 함께")
        page.locator("#birth-longitude").fill("126.978")
        page.locator("#save-button").click(); expect(page.locator("#daily-result")).to_be_visible(timeout=20000)
        saved = page.evaluate("fetch('/api/session').then(r=>r.json()).then(r=>r.profile)")
        assert saved["latitude"] == 37.5665 and saved["longitude"] == 126.978
        assert saved["birthplace_text"] == "가상 도시" and saved["timezone"] == "Asia/Seoul"
        page.reload(); expect(page.locator("#daily-result")).to_be_visible(timeout=20000)
        expect(page.locator("#birth-latitude")).to_have_value("37.5665")
        passed.append("optional coordinates require both values, serialize as numbers and round-trip with city/timezone")

        # Partial data and text containing markup must render as text, never HTML.
        fixture = copy.deepcopy(actual)
        fixture["summary"] = ["가상 <img src=x onerror=alert(1)> 성찰 문장"]
        fixture["methods"][3].update(status="unavailable", used_in_reading=False, reason="가상 천체력 미설치")
        page.route("**/api/readings/integrated", lambda route: route.fulfill(json=fixture))
        page.locator('[data-view="integrated"]').click(); expect(page.locator("#integrated-result")).to_be_visible()
        expect(page.locator("#integrated-summary")).to_contain_text("<img src=x")
        assert page.locator("#integrated-summary img").count() == 0
        expect(page.locator(".integrated-method").nth(3)).to_contain_text("풀이에서 제외")
        page.unroute("**/api/readings/integrated")
        passed.append("partial system availability remains explicit and all interpretation text is escaped")

        page.route("**/api/readings/integrated", lambda route: route.fulfill(status=503, json={"ok":False, "computed":False, "text":"계산 근거가 없습니다."}))
        page.locator('[data-view="integrated"]').click()
        expect(page.locator("#reading-error")).to_contain_text("계산 근거가 없습니다")
        expect(page.locator("#integrated-result")).to_be_hidden()
        expect(page.locator("#integrated-text")).to_have_text("")
        page.unroute("**/api/readings/integrated")
        passed.append("failed integrated response clears the previous report and share state")

        mismatch = {**fixture, "schema_version":2}
        page.route("**/api/readings/integrated", lambda route: route.fulfill(json=mismatch))
        page.locator('[data-view="integrated"]').click()
        expect(page.locator("#reading-error")).to_contain_text("리포트 형식을 확인하지 못했습니다")
        page.locator('[data-view="today"]').click(); expect(page.locator("#daily-result")).to_be_visible(timeout=20000)
        page.unroute("**/api/readings/integrated")
        passed.append("unsupported report version fails safely while existing daily readings remain usable")

        for broken in (
            [],
            {**actual, "methods":[None] * 4},
            {**actual, "evidence":[None]},
            {**actual, "themes":[None]},
            {**actual, "themes":[{**actual["themes"][0], "claims":[None]}]},
            {**actual, "themes":[{**actual["themes"][0], "agreements":[None]}]},
            {**actual, "limitations":[{"private":"synthetic-internal-value"}]},
        ):
            page.route("**/api/readings/integrated", lambda route: route.fulfill(json=broken))
            page.locator('[data-view="integrated"]').click()
            expect(page.locator("#reading-error")).to_contain_text("리포트 형식을 확인하지 못했습니다")
            expect(page.locator("#integrated-result")).to_be_hidden()
            assert "synthetic-internal-value" not in page.locator("body").inner_text()
            page.unroute("**/api/readings/integrated")
        passed.append("malformed nested methods, themes, claims, evidence and limits fail before rendering or exporting")

        page.locator('[data-view="integrated"]').click(); expect(page.locator("#integrated-result")).to_be_visible(timeout=30000)
        page.evaluate("""() => {
          window.originalToBlob = HTMLCanvasElement.prototype.toBlob;
          HTMLCanvasElement.prototype.toBlob = function(callback) { callback(null); };
        }""")
        page.locator("#open-integrated-share").click()
        expect(page.locator("#integrated-share-status")).to_contain_text("이미지를 만들지 못했습니다")
        expect(page.locator("#download-integrated-share")).to_be_disabled()
        expect(page.locator("#integrated-share-canvas")).to_be_hidden()
        page.locator("#close-integrated-share").click()
        page.evaluate("() => { HTMLCanvasElement.prototype.toBlob = window.originalToBlob; }")
        passed.append("PNG encoder failure preserves readable text and provides no stale download")

        held = []
        page.route("**/api/readings/integrated", lambda route: held.append(route))
        page.locator('[data-view="integrated"]').click()
        expect(page.locator("#loading")).to_be_visible()
        page.wait_for_function("() => document.getElementById('loading').hidden === false")
        remove(); assert held
        held[0].fulfill(json=actual)
        page.unroute("**/api/readings/integrated")
        expect(page.locator("#integrated-result")).to_be_hidden()
        expect(page.locator("#integrated-text")).to_have_text("")
        expect(page.locator("#birthplace-text")).to_have_value("")
        passed.append("late integrated response cannot restore a deleted profile, result or location")

        register(unknown=True)
        page.locator('[data-view="integrated"]').click(); expect(page.locator("#integrated-result")).to_be_visible(timeout=30000)
        expect(page.locator(".integrated-method").nth(1)).to_contain_text("풀이에서 제외")
        passed.append("unknown birth time keeps available interpretations and visibly excludes Ziwei")
        page.evaluate("""() => {
          window.originalToBlob = HTMLCanvasElement.prototype.toBlob;
          HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
            return window.originalToBlob.call(this, blob => { window.releaseReport = () => callback(blob); }, ...args);
          };
        }""")
        page.locator("#open-integrated-share").click()
        page.wait_for_function("() => typeof window.releaseReport === 'function'")
        page.locator("#close-integrated-share").click(); remove()
        page.evaluate("() => { window.releaseReport(); HTMLCanvasElement.prototype.toBlob = window.originalToBlob; }")
        expect(page.locator("#integrated-share-dialog")).to_be_hidden()
        expect(page.locator("#download-integrated-share")).to_be_disabled()
        assert page.locator("#integrated-share-canvas").get_attribute("width") == "0"
        passed.append("late PNG encoding after close/deletion cannot restore pages or enable export")
        assert page.evaluate("localStorage.length + sessionStorage.length") == 0
        assert not errors and not external, {"errors":errors, "external":external}
        for event in events:
            assert set(event) == {"event", "view"}
        assert {"event":"reading_viewed", "view":"integrated"} in events
        passed.append("no browser persistence, external requests, JavaScript errors or personal metric labels")
        browser.close()
    result = {"passed":passed, "page_errors":errors, "external_requests":external,
              "scope":"local Chromium; synthetic profiles and explicit response fixtures; no production or native OS sharing"}
    (args.output / "integrated-browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
