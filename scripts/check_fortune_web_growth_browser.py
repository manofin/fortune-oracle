"""Local-only browser contracts for sharing, measurements, D-day and ephemeral compatibility."""
import argparse
import json
from pathlib import Path
import struct
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    origin = urlparse(args.url)
    assert origin.hostname in {"127.0.0.1", "localhost"}, "Use a temporary loopback preview"
    args.output.mkdir(parents=True, exist_ok=True)
    errors, external, events, passed = [], [], [], []

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        browser_version = browser.version
        context = browser.new_context(viewport={"width": 390, "height": 844},
                                      is_mobile=args.browser != "firefox", has_touch=True)
        # Native OS handoff is simulated; no third-party sharing or clipboard access occurs.
        context.add_init_script("""
            window.cardText = []; window.copied = []; window.handoffs = []; window.nativeMode = 'cancel';
            const fillText = CanvasRenderingContext2D.prototype.fillText;
            CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
              window.cardText.push(String(text)); return fillText.call(this, text, ...args);
            };
            Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:async text => { window.copied.push(text); }}});
            Object.defineProperty(navigator, 'canShare', {configurable:true, value:() => true});
            Object.defineProperty(navigator, 'share', {configurable:true, value:async data => {
              if (window.nativeMode === 'cancel') throw new DOMException('synthetic cancellation', 'AbortError');
              if (window.nativeMode === 'fail') throw new Error('synthetic unavailable app');
              window.handoffs.push({title:data.title, files:data.files.map(f => ({name:f.name, type:f.type, size:f.size}))});
            }});
        """)

        def only_local(route):
            target = urlparse(route.request.url)
            if target.netloc != origin.netloc:
                external.append(target.netloc); route.abort(); return
            if target.path == "/api/events":
                event = route.request.post_data_json
                assert set(event) == {"event", "view"}
                events.append(event)
            route.continue_()

        context.route("**/*", only_local)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.url)
        assert page.evaluate("fetch('/healthz').then(r => r.json()).then(r => r.version)") == "local-preview"
        expect(page.locator("#empty-state")).to_be_visible()

        def expect_share_preview():
            # PNG encoding runs asynchronously in the browser. Wait for the
            # actual rendered canvas before checking its content or actions.
            expect(page.locator("#share-canvas")).to_be_visible(timeout=15000)

        def register():
            page.locator("#display-name").fill("가상<친구>")
            page.locator("#birth-date").fill("1990-05-17")
            page.locator("#unknown-time").uncheck(); page.locator("#birth-time").fill("12:30")
            page.locator("#save-button").click()
            expect(page.locator("#daily-result")).to_be_visible(timeout=15000)

        def remove():
            page.locator("#delete-button").click(); page.locator("#confirm-delete").click()
            expect(page.locator("#empty-state")).to_be_visible()
            expect(page.locator("#delete-dialog")).to_be_hidden()

        register()
        expect(page.locator("#reading-title")).to_have_text("가상<친구>님의 하루")
        page.evaluate("history.replaceState({}, '', '?campaign=synthetic#private-result')")
        page.locator("#open-share").click()
        expect_share_preview()
        assert page.evaluate("document.fonts.check('40px FortuneKorean', '오늘의키워드')")
        for width, height, label in ((320, 640, "small-phone"), (390, 844, "mobile"), (1280, 900, "desktop")):
            page.set_viewport_size({"width":width, "height":height})
            geometry = page.evaluate("""() => {
                const ids = ['share-canvas', 'close-share', 'native-share', 'download-share', 'copy-share-link'];
                return ids.map(id => {
                  const r = document.getElementById(id).getBoundingClientRect();
                  return {id, x:r.x, y:r.y, right:r.right, bottom:r.bottom, width:r.width, height:r.height};
                });
            }""")
            for box in geometry:
                assert box["x"] >= 0 and box["right"] <= width and box["y"] >= 0 and box["bottom"] <= height, (label, box)
                if box["id"] != "share-canvas":
                    # DOMRect subtraction may round 44 CSS px down by a few ulps.
                    assert box["height"] >= 44 - 0.01, (label, box)
            page.screenshot(path=str(args.output / f"{label}-share-layout.png"), animations="disabled")
        page.set_viewport_size({"width":390, "height":844})
        passed.append("320px phone, mobile and desktop previews keep card and actions visible with 44px touch targets")
        drawn = page.evaluate("window.cardText")
        for private in ("가상<친구>", "1990-05-17", "12:30", "Asia/Seoul", "壬午"):
            assert private not in "\n".join(drawn)
        assert "예측 확률이 아닙니다" in "\n".join(drawn)
        rendered_keywords = page.locator("#keywords .kw").all_text_contents()
        assert rendered_keywords and all(keyword in drawn for keyword in rendered_keywords), {
            "displayed_keywords": rendered_keywords, "canvas_text": drawn,
        }
        with page.expect_download() as pending:
            page.locator("#download-share").click()
        download = pending.value
        path = args.output / "share-card.png"; download.save_as(path)
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (1080, 1350)
        assert len(raw) > 20000
        colors = page.evaluate("""() => {
            const pixels = document.querySelector('#share-canvas').getContext('2d').getImageData(0,0,1080,1350).data;
            const colors = new Set(); for(let i=0;i<pixels.length;i+=400) colors.add(`${pixels[i]},${pixels[i+1]},${pixels[i+2]}`);
            return colors.size;
        }""")
        assert colors > 10
        page.screenshot(path=str(args.output / "mobile-share.png"), animations="disabled")
        passed.append("1080x1350 nonblank Korean PNG; only date/keywords/index, no nickname, birth data or natal pillars")

        page.locator("#native-share").click()
        expect(page.locator("#share-status")).to_have_text("공유를 취소했습니다.")
        page.evaluate("window.nativeMode = 'fail'")
        page.locator("#native-share").click()
        expect(page.locator("#share-status")).to_contain_text("PNG를 다운로드")
        page.evaluate("window.nativeMode = 'success'")
        page.locator("#native-share").click()
        expect(page.locator("#share-status")).to_contain_text("실제 게시 여부")
        handoff = page.evaluate("window.handoffs")
        assert len(handoff) == 1 and handoff[0]["files"][0]["type"] == "image/png"
        page.locator("#copy-share-link").click()
        expect(page.locator("#share-status")).to_contain_text("홈 링크를 복사")
        assert page.evaluate("window.copied") == [f"{origin.scheme}://{origin.netloc}/?from=card"]
        passed.append("native sharing cancellation/failure/handoff distinguished; home link has only fixed from=card, no fragment or personal result")
        page.locator("#close-share").click()
        page.evaluate("Object.defineProperty(navigator, 'share', {value:undefined, configurable:true})")
        page.locator("#open-share").click()
        expect_share_preview()
        expect(page.locator("#native-share")).to_be_hidden()
        expect(page.locator("#download-share")).to_be_enabled()
        page.locator("#close-share").click()
        passed.append("browsers without native file sharing retain PNG download and home link")

        page.evaluate("""() => {
            window.normalToBlob = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function(callback) { callback(null); };
        }""")
        page.locator("#open-share").click()
        expect(page.locator("#share-status")).to_contain_text("이미지를 만들지 못했습니다")
        expect(page.locator("#download-share")).to_be_disabled()
        expect(page.locator("#share-canvas")).to_be_hidden()
        page.locator("#close-share").click()
        page.evaluate("() => { HTMLCanvasElement.prototype.toBlob = window.normalToBlob; }")
        passed.append("PNG encoding failure leaves no preview or downloadable file")

        def older_session(route):
            response = route.fetch(); data = response.json(); data.pop("reading_window", None)
            route.fulfill(response=response, json=data)
        page.route("**/api/session", older_session)
        page.reload()
        expect(page.locator("#daily-result")).to_be_visible()
        expect(page.locator("#date-submit")).to_be_disabled()
        expect(page.locator("#date-zone")).to_contain_text("오늘·내일 풀이는 계속")
        page.unroute("**/api/session")
        page.reload(); expect(page.locator("#daily-result")).to_be_visible()
        expect(page.locator("#date-submit")).to_be_enabled()
        passed.append("mixed-version session without date capability preserves daily readings and disables D-day")

        # A valid engine response may have five keywords; exercise it independently of today's element.
        def five_keyword_reading(route):
            response = route.fetch(); data = response.json()
            data["reading"]["keywords"] = ["속도", "표현", "관심", "행동", "관계의 온도"]
            data["text"] = "키워드: 속도 · 표현 · 관심 · 행동 · 관계의 온도\n" + data["text"]
            relation = next(section for section in data["sections"]["evidence"] if section["id"] == "relation")
            relation["paragraphs"][-1] = "키워드: 속도 · 표현 · 관심 · 행동 · 관계의 온도"
            route.fulfill(response=response, json=data)
        page.route("**/api/readings/tomorrow", five_keyword_reading)
        page.locator('[data-view="tomorrow"]').click()
        expect(page.locator("#keywords")).to_have_text("속도 · 표현 · 관심")
        expect(page.locator("#daily-evidence")).to_contain_text("관계의 온도")
        page.locator("#open-share").click(); expect_share_preview()
        expect(page.locator("#download-share")).to_be_enabled()
        page.locator("#close-share").click(); page.unroute("**/api/readings/tomorrow")
        passed.append("five-keyword response keeps all details but projects exactly three keywords into summary and PNG")

        page.locator(".special-readings > details").first.locator("summary").click()
        target = page.locator("#target-date").get_attribute("max")
        page.locator("#target-date").fill(target); page.locator("#scenario").select_option("exam")
        with page.expect_response(lambda response: urlparse(response.url).path == "/api/readings/date") as dated_response:
            page.locator("#date-submit").click()
        expect(page.locator("#reading-date")).to_have_text(target)
        expect(page.locator("#keyword-title")).to_have_text("그날을 준비하는 키워드")
        dated = dated_response.value.json()
        expect(page.locator("#day-relation")).to_have_text(dated["sections"]["theme"]["text"])
        expect(page.locator("#daily-action")).to_have_text(dated["sections"]["action"]["text"])
        expect(page.locator("#daily-practice-qualifiers")).to_contain_text("선택한 상황에 맞춘 제안")
        expect(page.locator("#open-share")).to_be_enabled()
        page.screenshot(path=str(args.output / "mobile-dday.png"))
        page.locator("#open-share").click(); expect_share_preview()
        expect(page.locator("#download-share")).to_be_enabled()
        page.locator("#close-share").click()
        passed.append("D-day computes the inclusive maximum date, preserves the basic interpretation and labels the selected situation action")

        page.locator("#compat-details summary").click()
        page.locator("#partner-date").fill("1997-08-19")
        expect(page.locator("#partner-zone")).to_have_value("한국 시간")
        page.locator("#partner-zone").fill("America/New_York")
        page.locator("#compat-submit").click()
        expect(page.locator("#compat-result")).to_be_visible()
        expect(page.locator("#partner-date")).to_have_value("")
        expect(page.locator("#compat-text")).to_contain_text("부분 비교")
        expect(page.locator("#compat-text")).to_contain_text("미국 동부 시간")
        assert "1997-08-19" not in page.locator("#compat-text").inner_text()
        assert page.evaluate("localStorage.length + sessionStorage.length") == 0
        page.screenshot(path=str(args.output / "mobile-compat.png"))
        passed.append("compatibility uses partner time zone, omits unknown hour and clears partner fields without browser storage")

        page.route("**/api/compat", lambda route: route.fulfill(status=503, content_type="application/json",
            body=json.dumps({"ok":False, "computed":False, "text":"계산 결과가 아님\n가상 실패"})))
        page.locator("#partner-date").fill("1997-08-19"); page.locator("#compat-submit").click()
        expect(page.locator("#reading-error")).to_contain_text("계산 결과가 아님")
        expect(page.locator("#compat-result")).to_be_hidden(); expect(page.locator("#compat-text")).to_have_text("")
        page.unroute("**/api/compat")
        passed.append("failed comparison clears old result and does not record a successful reading")

        page.route("**/api/compat", lambda route: route.fulfill(status=502, content_type="text/html", body="<html>private-upstream-path</html>"))
        page.locator("#partner-date").fill("1997-08-19"); page.locator("#compat-submit").click()
        expect(page.locator("#reading-error")).to_contain_text("응답을 읽지 못했습니다")
        assert "private-upstream-path" not in page.locator("body").inner_text()
        expect(page.locator("#compat-result")).to_be_hidden()
        page.unroute("**/api/compat")
        passed.append("malformed upstream JSON produces a plain retry message without leaking the body")

        held = []
        page.route("**/api/readings/date", lambda route: held.append((route, route.fetch())))
        page.locator("#date-submit").click()
        expect(page.locator("#date-submit")).to_be_disabled()
        page.wait_for_function("() => document.getElementById('loading').hidden === false")
        remove()
        assert len(held) == 1
        held[0][0].fulfill(response=held[0][1])
        page.unroute("**/api/readings/date")
        expect(page.locator("#reading-panel")).to_be_hidden(); expect(page.locator("#birth-date")).to_have_value("")
        passed.append("a completed D-day response arriving after deletion cannot restore the old result")

        register()
        page.evaluate("""() => {
            window.originalToBlob = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
              return window.originalToBlob.call(this, blob => { window.releaseCard = () => callback(blob); }, ...args);
            };
        }""")
        page.locator("#open-share").click(); page.wait_for_function("() => typeof window.releaseCard === 'function'")
        page.locator("#close-share").click(); remove()
        page.evaluate("() => { window.releaseCard(); HTMLCanvasElement.prototype.toBlob = window.originalToBlob; }")
        expect(page.locator("#share-dialog")).to_be_hidden(); expect(page.locator("#share-canvas")).to_be_hidden()
        expect(page.locator("#download-share")).to_be_disabled()
        assert page.locator("#share-canvas").get_attribute("width") == "0"
        passed.append("late PNG generation after deletion never reopens preview or enables download")

        assert not errors and not external, {"errors":errors, "external":external}
        names = {event["event"] for event in events}
        assert {"form_started", "reading_viewed", "share_card_opened", "share_requested", "share_cancelled",
                "share_failed", "share_handoff", "share_download_requested", "share_link_copied"} <= names
        assert "share_completed" not in names
        assert sum(event == {"event":"reading_viewed", "view":"compat"} for event in events) == 1
        assert sum(event == {"event":"reading_viewed", "view":"dday"} for event in events) == 1
        for value in ("1990-05-17", "1997-08-19", "가상<친구>", "12:30", "America/New_York"):
            assert value not in json.dumps(events, ensure_ascii=False)
        passed.append("allowlisted events contain no personal inputs; failed/stale responses are not measured as viewed")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        passed.append("no horizontal overflow, JavaScript errors or external requests")
        browser.close()

    result = {"passed":passed, "events":events, "page_errors":errors, "external_requests":external,
              "browser": args.browser, "browser_version": browser_version,
              "scope":f"local {args.browser} + real API; synthetic data; OS sharing/clipboard simulated; no deployment",
              "device_scope":"Linux browser with phone viewport/touch; not physical iPhone or Safari"}
    (args.output / "growth-browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
