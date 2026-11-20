"""Local Chromium checks for public samples, anonymous interest, and deletion.

Use only the temporary preview. Captures fixed event labels; never supplies a
birth profile, contacts, payment information, or an external network request.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, expect, sync_playwright


PRODUCTS = ("self_manual_v1", "conversation_guide_v1", "four_perspectives_v1")
VIEWED = "product_sample_viewed"
INTEREST = "product_sample_interest"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    origin = urlsplit(base)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, external, requests, events = [], [], [], [], []
    state = {"event": INTEREST, "mode": "pass", "held": []}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})

        def only_local(route):
            if urlsplit(route.request.url).netloc != origin.netloc:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", only_local)
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))

        def capture(request):
            requests.append((request.method, urlsplit(request.url).path))
            if urlsplit(request.url).path == "/api/events":
                events.append(request.post_data_json)

        page.on("request", capture)

        def event_transport(route):
            payload = route.request.post_data_json
            if payload.get("event") != state["event"] or state["mode"] == "pass":
                route.fallback()
            elif state["mode"] == "hold":
                state["held"].append(route)
            elif state["mode"] == "failure":
                route.fulfill(status=503, json={"ok": False, "text": "PRIVATE /private/marker"})
            elif state["mode"] == "wrong_status":
                route.fulfill(status=200, json={"ok": True})
            elif state["mode"] == "false_ack":
                route.fulfill(status=202, json={"ok": False})
            elif state["mode"] == "bad_json":
                route.fulfill(status=202, content_type="application/json", body="not-json")
            elif state["mode"] == "expired":
                route.fulfill(status=401, json={"ok": False, "error": "session_expired"})

        page.route("**/api/events", event_transport)
        assert context.request.get(base + "/healthz").json()["version"] == "local-preview"
        page.goto(base + "/samples")
        page.wait_for_load_state("networkidle")
        assert not context.cookies()
        assert not [path for _, path in requests if path.startswith("/api/")]
        assert page.locator('input[type="date"], input[type="email"], input[type="tel"]').count() == 0
        assert page.locator("[data-sample-open]").count() == 3
        body = page.locator("body").inner_text()
        for text in ("내 사용설명서", "싸우기 전에 읽는 대화집", "네 관점 교차 리포트", "9,900", "12,900", "19,900", "가설"):
            assert text in body
        passed.append("Three editorial samples and hypothesis prices load without birth inputs, cookies, or API calls")

        def opener(product):
            return page.locator(f'[data-sample-open="{product}"]')

        def button(product):
            return page.locator(f'[data-sample-interest="{product}"]')

        def adult(product):
            return page.locator(f'[data-sample-adult="{product}"]')

        def status(product):
            return page.locator(f'[data-sample-status="{product}"]')

        def matching(event, product):
            return [e for e in events if e == {"event": event, "view": product}]

        def open_sample(product):
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/events"
                                      and r.request.post_data_json == {"event": VIEWED, "view": product}) as receipt:
                opener(product).click()
            assert receipt.value.status == 202
            summary = page.locator(f"#sp-report-{product} > summary")
            expect(summary).to_be_focused()
            assert 0 <= summary.bounding_box()["y"] <= 32

        def inspect_report(product):
            for width, height in ((320, 640), (390, 844), (1280, 960)):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                report = page.locator(f"#sp-report-{product}")
                assert report.locator(".report-body").is_visible()
                assert report.locator(".report-review li").count() == 3
                assert float(report.locator(".report-body").evaluate("el => parseFloat(getComputedStyle(el).fontSize)")) >= 16
                if product == PRODUCTS[-1] and width <= 390:
                    table = report.locator(".perspective-table")
                    expect(table).to_have_role("table")
                    assert table.get_by_role("rowheader").all_text_contents() == ["사주", "자미두수", "서양", "베딕"]
                    # Each sentence gets the row's reading width, rather than a
                    # narrow third of the 320px screen. No content is clipped.
                    assert table.locator("tbody td").evaluate_all("""nodes => nodes.every(el => {
                        const row = el.closest('tr').getBoundingClientRect();
                        return el.getBoundingClientRect().width >= row.width - 3
                          && el.scrollWidth <= el.clientWidth;
                    })""")
                    assert table.locator(".mobile-cell-label:visible").count() == 8
                report.screenshot(path=str(args.output / f"{product}-{width}.png"))
            page.set_viewport_size({"width": 390, "height": 844})

        for width, height in ((320, 640), (390, 844), (1280, 960)):
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            boxes = page.locator("[data-sample-open]").evaluate_all("""els => els.map(el => {
                const r = el.getBoundingClientRect(); return {height:r.height,left:r.left,right:r.right};
            })""")
            assert all(b["height"] >= 44 and b["left"] >= 0 and b["right"] <= width + .1 for b in boxes)
            page.screenshot(path=str(args.output / f"catalog-{width}.png"), full_page=True)
        passed.append("320/390/1280px catalog fits without horizontal overflow; sample actions have 44px targets")

        page.set_viewport_size({"width": 390, "height": 844})
        first, second, third = PRODUCTS
        # Failed collection must not block reading. A keyboard reader keeps focus
        # in the opened report even while its original action is disabled.
        state.update(event=VIEWED, mode="failure")
        opener(first).focus()
        page.keyboard.press("Enter")
        expect(status(first)).to_contain_text("본문은 읽을 수 있어요")
        expect(page.locator(f"#sp-report-{first} > summary")).to_be_focused()
        adult(first).check()
        expect(button(first)).to_be_disabled()
        assert "/private/marker" not in status(first).inner_text()
        close_first = page.locator(f'[data-sample-close="{first}"]')
        close_first.focus()
        page.keyboard.press("Enter")
        expect(opener(first)).to_be_focused()
        expect(page.locator(f"#sp-report-{first}")).not_to_have_attribute("open", "")
        adult(first).uncheck()
        state.update(event=INTEREST, mode="pass")
        open_sample(first)
        inspect_report(first)
        view_count = len(matching(VIEWED, first))
        close_first.focus()
        page.keyboard.press("Enter")
        expect(opener(first)).to_be_focused()
        opener(first).press("Enter")
        expect(page.locator(f"#sp-report-{first} > summary")).to_be_focused()
        page.keyboard.press("Space")
        expect(opener(first)).to_have_attribute("aria-expanded", "false")
        page.keyboard.press("Space")
        expect(opener(first)).to_have_attribute("aria-expanded", "true")
        assert len(matching(VIEWED, first)) == view_count
        expect(opener(first)).to_have_accessible_name("내 사용설명서 · 샘플 닫기")
        passed.append("View failure preserves readable body; keyboard open/close keeps focus and reopening adds no duplicate view")
        expect(button(first)).to_be_disabled()
        adult(first).check()
        expect(button(first)).to_be_enabled()
        button(first).focus()
        with page.expect_response(lambda r: urlsplit(r.url).path == "/api/events"
                                  and r.request.post_data_json == {"event": INTEREST, "view": first}) as receipt:
            page.keyboard.press("Space")
        assert receipt.value.status == 202 and receipt.value.json() == {"ok": True}
        expect(status(first)).to_contain_text("관심")
        before = len(matching(INTEREST, first))
        button(first).evaluate("node => node.click()")
        assert len(matching(INTEREST, first)) == before
        assert context.request.get(base + "/api/session").json()["profile"] is None
        page.screenshot(path=str(args.output / "manual-confirmed-mobile.png"), full_page=True)
        passed.append("Actual anonymous view and adult self-confirmation enable keyboard interest; duplicate clicks send once")

        # Server KST boundaries have separate HTTP tests; here move only the UI
        # clock to verify that an old confirmation cannot authorize a new day.
        page.clock.set_fixed_time("2026-11-10T14:59:59Z")
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.clock.set_fixed_time("2026-11-10T15:00:01Z")
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect(button(first)).to_be_disabled()
        expect(adult(first)).not_to_be_checked()
        open_sample(first)
        adult(first).check()
        expect(button(first)).to_be_enabled()
        passed.append("KST midnight clears confirmations and requires a fresh view plus adult self-confirmation")

        # A successful sample view is necessary for an honest interest response.
        open_sample(second)
        inspect_report(second)
        adult(second).check()
        for mode in ("failure", "wrong_status", "false_ack", "bad_json"):
            state["mode"] = mode
            button(second).click()
            expect(button(second)).to_be_enabled()
            assert status(second).inner_text()
            assert "/private/marker" not in status(second).inner_text()
            assert "기록했" not in status(second).inner_text()
        state["mode"] = "pass"
        button(second).click()
        expect(status(second)).to_contain_text("관심")
        expect(button(second)).to_be_disabled()
        passed.append("503, HTTP200, false ACK and malformed JSON allow retry without false success; retry succeeds")

        open_sample(third)
        inspect_report(third)
        adult(third).check()
        state["mode"] = "expired"
        button(third).click()
        expect(status(third)).to_contain_text("세션")
        expect(button(third)).to_be_disabled()
        expect(adult(third)).not_to_be_checked()
        state["mode"] = "pass"
        open_sample(third)
        adult(third).check()
        expect(button(third)).to_be_enabled()
        passed.append("A401 invalidates prior view and adult state; an explicit reopen restores a usable session")
        state["mode"] = "hold"
        button(third).click()
        expect(button(third)).to_be_disabled()
        button(third).evaluate("node => {node.click(); node.click();}")
        assert len(state["held"]) == 1
        expect(button(third)).to_be_enabled(timeout=12000)
        assert "기록했" not in status(third).inner_text()
        for held in state["held"]:
            try:
                held.fulfill(status=202, json={"ok": True})
            except Error:
                pass
        state["held"].clear()
        expect(button(third)).to_be_enabled()
        passed.append("Stalled interest times out; double click and delayed ACK cannot create false confirmation")

        # Remove the anonymous session while an acknowledgement is still pending.
        button(third).click()
        expect(button(third)).to_be_disabled()
        page.locator("#sp-delete-button").click()
        expect(page.locator("#sp-delete-dialog")).to_be_visible()
        expect(page.locator("#sp-delete-dialog")).to_contain_text("출생정보")
        with page.expect_response(lambda r: urlsplit(r.url).path == "/api/profile"
                                  and r.request.method == "DELETE") as deletion:
            page.locator("#sp-delete-confirm").click()
        assert deletion.value.status == 200
        expect(page.locator("#sp-delete-status")).to_contain_text("삭제했어요")
        page.locator("#sp-delete-cancel").click()
        expect(page.locator("#sp-delete-dialog")).to_be_hidden()
        for held in state["held"]:
            try:
                held.fulfill(status=202, json={"ok": True})
            except Error:
                pass
        state["held"].clear()
        assert not context.cookies()
        for product in PRODUCTS:
            expect(adult(product)).not_to_be_checked()
            expect(button(product)).to_be_disabled()
        passed.append("Confirmed deletion clears the anonymous session and pending UI without automatically recreating a cookie")

        # Rapid collapse while bootstrap or the event receipt is pending must
        # leave a usable keyboard target and must not issue another session GET.
        pending_context = browser.new_context(viewport={"width": 390, "height": 844})
        pending_context.route("**/*", only_local)
        pending = pending_context.new_page()
        pending.on("pageerror", lambda err: errors.append(str(err)))
        bootstrap, pending_receipts, pending_events = [], [], []
        pending.route("**/api/session", lambda route: bootstrap.append(route))
        pending.route("**/api/events", lambda route: pending_receipts.append(route))
        pending.on("request", lambda request: pending_events.append(request.post_data_json)
                   if urlsplit(request.url).path == "/api/events" else None)
        pending.goto(base + "/samples")
        pending_open = pending.locator(f'[data-sample-open="{first}"]')
        pending_close = pending.locator(f'[data-sample-close="{first}"]')
        pending_summary = pending.locator(f"#sp-report-{first} > summary")
        pending_open.focus()
        pending.keyboard.press("Enter")
        expect(pending_open).to_be_disabled()
        assert len(bootstrap) == 1

        def collapse_while_pending():
            pending_close.focus()
            pending.keyboard.press("Enter")
            expect(pending_summary).to_be_focused()
            expect(pending_summary).to_be_visible()
            pending.keyboard.press("Shift+Tab")
            assert pending.evaluate("document.activeElement.tagName !== 'BODY' && !document.activeElement.disabled")
            pending_summary.focus()
            pending.keyboard.press("Enter")
            expect(pending_summary).to_be_focused()
            assert len(bootstrap) == 1

        collapse_while_pending()
        with pending.expect_request(lambda request: urlsplit(request.url).path == "/api/events"):
            bootstrap[0].continue_()
        expect(pending_open).to_be_disabled()
        assert len(pending_receipts) == 1
        collapse_while_pending()
        pending_receipts[0].fulfill(status=503, json={"ok": False})
        expect(pending_open).to_be_enabled()
        expect(pending.locator(f'[data-sample-status="{first}"]')).to_contain_text("본문은 읽을 수 있어요")
        pending_close.focus()
        pending.keyboard.press("Enter")
        expect(pending_open).to_be_focused()
        assert len(pending_events) == 1 and len(bootstrap) == 1
        pending_context.close()
        passed.append("Rapid close and Shift+Tab keep usable focus during bootstrap, pending view and failed acknowledgement without duplicate requests")

        # Two opens share one cookie-creating GET. Deletion must drain that GET
        # before deleting, or its Set-Cookie could replace the deleted session.
        race_context = browser.new_context(viewport={"width": 390, "height": 844})
        race_context.route("**/*", only_local)
        race = race_context.new_page()
        race.on("pageerror", lambda err: errors.append(str(err)))
        held_sessions, race_events, race_deletes = [], [], []
        race.route("**/api/session", lambda route: held_sessions.append(route))

        def capture_race(request):
            path = urlsplit(request.url).path
            if path == "/api/events":
                race_events.append(request.post_data_json)
            elif path == "/api/profile" and request.method == "DELETE":
                race_deletes.append(request)

        race.on("request", capture_race)
        race.goto(base + "/samples")
        race.locator(f'[data-sample-open="{first}"]').click()
        race.locator(f'[data-sample-open="{second}"]').click()
        expect(race.locator(f'[data-sample-open="{second}"]')).to_be_disabled()
        assert len(held_sessions) == 1
        race.locator("#sp-delete-button").click()
        race.locator("#sp-delete-confirm").click()
        expect(race.locator("#sp-delete-cancel")).to_be_disabled()
        race.keyboard.press("Escape")
        expect(race.locator("#sp-delete-dialog")).to_be_visible()
        assert not race_events and not race_deletes
        held_sessions.pop().continue_()
        expect(race.locator("#sp-delete-status")).to_contain_text("삭제했어요")
        assert len(race_deletes) == 1 and not race_events and not race_context.cookies()
        passed.append("Concurrent opens share bootstrap; deletion drains the pending cookie request and prevents late event writes")
        race_context.close()

        # The full editorial examples remain usable when JavaScript is disabled.
        # Native details do not create a session or quietly collect a view.
        plain_context = browser.new_context(java_script_enabled=False, viewport={"width": 320, "height": 640})
        plain_context.route("**/*", only_local)
        plain = plain_context.new_page()
        plain_requests = []
        plain.on("request", lambda r: plain_requests.append(urlsplit(r.url).path))
        plain.goto(base + "/samples")
        for product in PRODUCTS:
            report = plain.locator(f"#sp-report-{product}")
            report.locator("summary").click()
            expect(report.locator(".report-review")).to_be_visible()
            expect(report.locator("[data-sample-close]")).to_be_hidden()
        assert not plain_context.cookies()
        assert not [path for path in plain_requests if path.startswith("/api/")]
        plain_context.close()
        passed.append("All complete examples and review prompts remain readable without JavaScript, API calls or cookies")

        assert all(set(e) == {"event", "view"} and e["event"] in {VIEWED, INTEREST}
                   and e["view"] in PRODUCTS for e in events)
        assert not [path for method, path in requests if method == "PUT"]
        assert not [path for _, path in requests if path.startswith(("/api/readings", "/api/compat", "/api/chart"))]
        assert page.evaluate("localStorage.length === 0 && sessionStorage.length === 0")
        assert not errors and not external
        passed.append("Only fixed event labels sent; no profile writes, calculations, browser persistence, external requests, or JS errors")
        passed.append("All three reports fit 320/390/1280px; mobile comparison rows retain full-width sentences and table semantics")
        browser.close()

    result = {"passed": passed, "page_errors": errors, "external_requests": external,
              "events": events, "source": "actual local Chromium; anonymous temporary sessions; not public deployment"}
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
