"""Loopback-only contracts for contact-free premium theme interest.

Uses invented profiles in the temporary preview and intercepts only failure
responses. No real launch notifications, payments or third-party requests.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, expect, sync_playwright


THEMES = ("relationships", "resources", "career", "study", "western", "ziwei")
CONFIRMED = "관심을 기록했어요. 알림은 발송되지 않아요."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:49127")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    origin = urlsplit(base)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, external, events, geometry = [], [], [], [], []
    state = {"mode": "pass", "held": []}

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
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def capture(request):
            if urlsplit(request.url).path == "/api/events":
                events.append(request.post_data_json)

        page.on("request", capture)

        def interest_transport(route):
            if urlsplit(route.request.url).netloc != origin.netloc:
                route.fallback()
                return
            payload = route.request.post_data_json
            if payload.get("event") != "premium_interest":
                route.fallback()
                return
            mode = state["mode"]
            if mode == "hold":
                state["held"].append(route)
            elif mode == "server_failure":
                route.fulfill(status=503, json={"ok": False, "error": "interest_unavailable", "text": "内部 /private/marker"})
            elif mode == "wrong_status":
                route.fulfill(status=200, json={"ok": True})
            elif mode == "false_ack":
                route.fulfill(status=202, json={"ok": False})
            elif mode == "bad_json":
                route.fulfill(status=202, content_type="application/json", body="not-json")
            else:
                route.fallback()

        page.route("**/api/events", interest_transport)
        assert context.request.get(base + "/healthz").json()["version"] == "local-preview"
        page.goto(base)
        expect(page.locator("#empty-state")).to_be_visible()
        section = page.locator("#premium-interest")
        expect(section).to_be_hidden()
        assert page.locator("input[type=email],input[type=tel]").count() == 0
        assert not [event for event in events if event.get("event") == "premium_interest"]
        passed.append("No interest cards or contact inputs before a free reading; no automatic interest event")

        # Registration alone must not promote a forthcoming product when its free
        # reading failed. The subsequent retry uses the real local calculation.
        page.route("**/api/readings/today", lambda route: route.fulfill(
            status=503, json={"ok": False, "computed": False, "text": "가상 무료 풀이 실패"}))
        page.locator("#display-name").fill("가상<관심검증>")
        page.locator("#birth-date").fill("1990-05-17")
        page.locator("#unknown-time").uncheck()
        page.locator("#birth-time").fill("12:30")
        page.locator("#gender").select_option("female")
        page.locator("#save-button").click()
        expect(page.locator("#reading-error")).to_contain_text("가상 무료 풀이 실패")
        expect(section).to_be_hidden()
        page.unroute("**/api/readings/today")
        page.locator('[data-view="today"]').click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=20000)
        expect(section).to_be_visible()
        assert section.locator("article.premium-card").count() == 6
        assert section.locator("[data-premium-interest]").evaluate_all(
            "buttons => buttons.map(button => button.dataset.premiumInterest)") == list(THEMES)
        assert page.evaluate("""() => {
            const premium = document.querySelector('#premium-interest');
            return !!(document.querySelector('#daily-result').compareDocumentPosition(premium) & Node.DOCUMENT_POSITION_FOLLOWING)
              && !!(document.querySelector('.special-readings').compareDocumentPosition(premium) & Node.DOCUMENT_POSITION_FOLLOWING);
        }""")
        text = section.inner_text()
        assert "준비 중" in text and "유료" in text
        assert section.locator(".premium-privacy").inner_text() == (
            "연락처는 받지 않으며 알림도 보내지 않습니다. "
            "관심은 이 브라우저 세션 기준으로 테마별 하루 한 번 집계하고, "
            "정보 삭제나 만료 후에는 날짜별 합계만 남습니다."
        )
        assert "출시 알림 받기" not in text and "19.9" not in text
        passed.append("Six forthcoming paid-reflection themes appear only after a successful free result, after More readings")

        for width, height, label in ((320, 640, "small-phone"), (390, 844, "mobile"), (1280, 960, "desktop")):
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            boxes = section.locator("[data-premium-interest]").evaluate_all("""buttons => buttons.map(button => {
                const r = button.getBoundingClientRect();
                return {left:r.left, right:r.right, height:r.height, width:r.width};
            })""")
            assert all(box["height"] >= 43.99 and box["width"] >= 43.99
                       and box["left"] >= 0 and box["right"] <= width + .01 for box in boxes), (label, boxes)
            if width == 320:
                assert len({round(box["left"], 1) for box in boxes}) == 1, "Small phone cards need one column"
            geometry.append({"viewport": label, "width": width, "buttons": boxes})
            section.screenshot(path=str(args.output / f"{label}-premium-cards.png"), animations="disabled")
            page.screenshot(path=str(args.output / f"{label}-full-page.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        passed.append("320/390/1280px layouts fit; small phone has one column and all six controls have at least44px targets")

        def button(theme):
            return page.locator(f'[data-premium-interest="{theme}"]')

        def status(theme):
            return page.locator(f"#premium-status-{theme}")

        def premium_events(theme=None):
            return [e for e in events if e.get("event") == "premium_interest"
                    and (theme is None or e["view"] == theme)]

        button("relationships").focus()
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/events"
                                  and response.request.post_data_json == {"event": "premium_interest", "view": "relationships"}) as receipt:
            page.keyboard.press("Space")
        assert receipt.value.status == 202 and receipt.value.json()["ok"] is True
        expect(button("relationships")).to_have_text("관심 보냈어요")
        expect(status("relationships")).to_have_text(CONFIRMED)
        assert status("relationships").get_attribute("role") == "status"
        section.screenshot(path=str(args.output / "mobile-confirmed-interest.png"), animations="disabled")
        before = len(premium_events("relationships"))
        button("relationships").click()
        expect(status("relationships")).to_contain_text("하루 한 번")
        assert len(premium_events("relationships")) == before
        passed.append("Keyboard activation confirms only after the real202 ACK; repeated same-day interest does not send again")

        state["mode"] = "hold"
        button("resources").click()
        expect(button("resources")).to_be_disabled()
        expect(button("career")).to_be_enabled()
        assert CONFIRMED not in status("resources").inner_text()
        # Direct repeated clicks while awaiting ACK cannot enqueue duplicates.
        button("resources").evaluate("node => { node.click(); node.click(); }")
        assert len(premium_events("resources")) == 1
        assert len(state["held"]) == 1
        state["held"].pop().fulfill(status=503, json={"ok": False, "error": "interest_unavailable", "text": "内部 /private/marker"})
        expect(button("resources")).to_be_enabled()
        expect(button("resources")).to_have_text("관심 있어요")
        expect(status("resources")).not_to_have_text(CONFIRMED)
        assert status("resources").inner_text()
        assert "/private/marker" not in status("resources").inner_text()
        section.screenshot(path=str(args.output / "mobile-retry-interest.png"), animations="disabled")
        state["mode"] = "pass"
        button("resources").click()
        expect(status("resources")).to_have_text(CONFIRMED)
        expect(page.locator("#daily-result")).to_be_visible()
        passed.append("Pending state is card-local, duplicate clicks are suppressed,503 shows safe retry and successful retry records interest")

        for mode in ("wrong_status", "false_ack", "bad_json"):
            state["mode"] = mode
            button("career").click()
            expect(button("career")).to_be_enabled()
            expect(button("career")).to_have_text("관심 있어요")
            expect(status("career")).not_to_have_text(CONFIRMED)
            assert status("career").inner_text()
        state["mode"] = "pass"
        button("career").click()
        expect(status("career")).to_have_text(CONFIRMED)
        passed.append("HTTP200,202 with okfalse and malformed JSON never become a false acknowledgement; retry succeeds")

        state["mode"] = "hold"
        button("study").click()
        expect(button("study")).to_be_disabled()
        expect(button("study")).to_be_enabled(timeout=11000)
        expect(button("study")).to_have_text("관심 있어요")
        assert CONFIRMED not in status("study").inner_text()
        for held in state["held"]:
            try:
                held.fulfill(status=202, json={"ok": True})
            except Error:
                pass  # An aborted request no longer has a live route.
        state["held"].clear()
        expect(button("study")).to_have_text("관심 있어요")
        state["mode"] = "pass"
        button("study").click()
        expect(status("study")).to_have_text(CONFIRMED)
        passed.append("Stalled interest request times out and allows retry; a late ACK cannot overwrite the timed-out state")

        # Fixed browser wall time moves only UI deduplication to another KST day;
        # the server's real day deduplication has independent HTTP regression tests.
        page.clock.set_fixed_time("2026-11-07T14:59:59Z")
        button("western").click()
        expect(status("western")).to_have_text(CONFIRMED)
        before = len(premium_events("western"))
        button("western").click()
        expect(status("western")).to_contain_text("하루 한 번")
        assert len(premium_events("western")) == before
        page.clock.set_fixed_time("2026-11-07T15:00:01Z")
        button("western").click()
        expect(status("western")).to_have_text(CONFIRMED)
        assert len(premium_events("western")) == before + 1
        passed.append("In-memory confirmation resets at KST midnight; no new browser persistence is introduced")

        state["mode"] = "hold"
        button("ziwei").click()
        expect(button("ziwei")).to_be_disabled()
        assert len(state["held"]) == 1
        page.locator('[data-view="tomorrow"]').click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=20000)
        expect(section).to_be_visible()
        try:
            state["held"].pop().fulfill(status=202, json={"ok": True})
        except Error:
            pass
        expect(button("ziwei")).to_have_text("관심 있어요")
        assert CONFIRMED not in status("ziwei").inner_text()
        passed.append("Changing free-reading view cancels pending interest; stale view acknowledgement is ignored")

        button("ziwei").click()
        expect(button("ziwei")).to_be_disabled()
        assert len(state["held"]) == 1
        page.locator("#delete-button").click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        expect(page.locator("#delete-dialog")).to_be_hidden()
        try:
            state["held"].pop().fulfill(status=202, json={"ok": True})
        except Error:
            pass
        expect(section).to_be_hidden()
        for theme in THEMES:
            expect(status(theme)).to_have_text("")
            expect(button(theme)).to_have_text("관심 있어요")
        passed.append("Deleting the synthetic profile clears interest UI and ignores delayed acknowledgement")

        captured = premium_events()
        assert {event["view"] for event in captured} == set(THEMES)
        assert all(set(event) == {"event", "view"} and event["view"] in THEMES for event in captured)
        serialized = json.dumps(captured, ensure_ascii=False)
        assert all(private not in serialized for private in ("1990-05-17", "12:30", "가상<관심검증>", "Asia/Seoul", "email", "phone"))
        assert page.evaluate("localStorage.length + sessionStorage.length") == 0
        assert not errors and not external
        passed.append("Only fixed event/theme labels leave the browser; no contacts, profile values, browser storage or external requests")
        context.close()
        browser.close()

    result = {"passed": passed, "page_errors": errors, "external_requests": external,
              "premium_event_count": len(captured), "theme_labels": list(THEMES), "geometry": geometry,
              "scope": "Local Chromium with synthetic profile, real local ACKs and intercepted error/delay responses. No production data or notifications."}
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
