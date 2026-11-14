"""Local-only browser regressions for session readiness and client state."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, expect, sync_playwright


def discard_routes(routes):
    for route in routes:
        try:
            route.abort()
        except Error:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8782")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    origin = urlsplit(base)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, external = [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})

        def only_local(route):
            if urlsplit(route.request.url).netloc == origin.netloc:
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        context.route("**/*", only_local)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        profile_puts = []
        page.on("request", lambda request: profile_puts.append(request)
                if urlsplit(request.url).path == "/api/profile" and request.method == "PUT" else None)

        def fill_form(name):
            page.locator("#display-name").fill(name)
            page.locator("#birth-date").fill("1990-05-17")
            page.locator("#unknown-time").uncheck()
            page.locator("#birth-time").fill("12:30")
            page.locator("#birth-zone").fill("Asia/Seoul")
            page.locator("#gender").select_option("male")

        held = []
        page.route("**/api/session", lambda route: held.append(route))
        page.goto(base)
        fill_form("새세션대기")
        expect(page.locator("#save-button")).to_be_disabled()
        page.locator("#save-button").evaluate("node => node.click()")
        page.locator("#display-name").press("Enter")
        page.wait_for_timeout(150)
        assert len(profile_puts) == 0
        assert len(held) == 1
        held.pop().continue_()
        page.unroute("**/api/session")
        page.locator("#save-button").click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(page.locator("#reading-title")).to_have_text("새세션대기님의 하루")
        assert len(profile_puts) == 1
        passed.append("fresh cookie: delayed session permits no PUT; one click after ready saves exactly once")

        page.route("**/api/session", lambda route: held.append(route))
        page.reload()
        expect(page.locator("#save-button")).to_be_disabled()
        fill_form("기존세션대기")
        page.locator("#display-name").press("Enter")
        page.locator("#birth-form").evaluate("node => node.requestSubmit()")
        page.wait_for_timeout(150)
        assert len(profile_puts) == 1
        assert len(held) == 1
        held.pop().continue_()
        page.unroute("**/api/session")
        expect(page.locator("#reading-title")).to_have_text("기존세션대기님의 하루")
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        assert len(profile_puts) == 2
        passed.append("existing cookie: a guarded submit waits for bootstrap and saves exactly once")

        retry = browser.new_context(viewport={"width": 390, "height": 844})
        retry.route("**/*", only_local)
        retry_page = retry.new_page()
        retry_page.on("pageerror", lambda error: errors.append(str(error)))
        retry_puts = []
        retry_sessions = []
        retry_page.on("request", lambda request: retry_puts.append(request)
                      if urlsplit(request.url).path == "/api/profile" and request.method == "PUT" else None)

        def fail_first_session(route):
            retry_sessions.append(route.request)
            if len(retry_sessions) == 1:
                retry_held.append(route)
            else:
                route.continue_()

        retry_held = []
        retry_page.route("**/api/session", fail_first_session)
        retry_page.goto(base)
        retry_page.locator("#display-name").fill("세션재시도")
        retry_page.locator("#birth-date").fill("1990-05-17")
        retry_page.locator("#display-name").press("Enter")
        retry_page.locator("#birth-form").evaluate("node => node.requestSubmit()")
        expect(retry_page.locator("#save-button")).to_be_disabled()
        assert len(retry_held) == 1
        retry_held.pop().fulfill(status=503, json={"ok": False, "text": "가상 세션 실패"})
        expect(retry_page.locator("#form-error")).to_be_visible()
        expect(retry_page.locator("#save-button")).to_be_enabled()
        assert len(retry_puts) == 0
        retry_page.locator("#save-button").click()
        expect(retry_page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(retry_page.locator("#reading-title")).to_have_text("세션재시도님의 하루")
        assert len(retry_sessions) == 2
        assert len(retry_puts) == 1
        passed.append("failed session leaves a working same-form retry; second session and first PUT succeed without reload")
        retry.close()

        page.route("**/api/session", lambda route: held.append(route))
        page.locator("#delete-button").click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        expect(page.locator("#save-button")).to_be_disabled()
        fill_form("삭제후재초기화")
        page.locator("#display-name").press("Enter")
        page.wait_for_timeout(150)
        assert len(profile_puts) == 2
        assert len(held) == 1
        held.pop().continue_()
        page.unroute("**/api/session")
        page.locator("#save-button").click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(page.locator("#reading-title")).to_have_text("삭제후재초기화님의 하루")
        assert len(profile_puts) == 3
        passed.append("post-delete session reinitialization blocks early PUT and accepts one fresh registration")

        observations = {"invalid_save_statuses": [], "successful_save_statuses": []}
        page.locator("#open-share").click()
        expect(page.locator("#share-canvas")).to_be_visible()
        expect(page.locator("#download-share")).to_be_enabled()
        page.locator("#close-share").click()
        page.locator("#birth-zone").fill("Not/A_Real_Zone")
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/profile"
                                  and response.request.method == "PUT") as invalid_daily:
            page.locator("#save-button").click()
        assert invalid_daily.value.status == 400
        observations["invalid_save_statuses"].append(invalid_daily.value.status)
        expect(page.locator("#form-error")).to_be_visible()
        expect(page.locator("#daily-result")).to_be_visible()
        expect(page.locator("#save-button")).to_be_enabled()
        assert page.evaluate("shareSource !== null")
        page.locator("#open-share").click()
        expect(page.locator("#share-dialog")).to_be_visible()
        expect(page.locator("#share-canvas")).to_be_visible()
        expect(page.locator("#download-share")).to_be_enabled()
        page.evaluate("window.failedSaveSource = shareSource")
        page.locator("#close-share").click()
        passed.append("real PUT 400 preserves the visible daily result and its working share card")

        fill_form("성공재저장")
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/profile"
                                  and response.request.method == "PUT") as saved_daily:
            page.locator("#save-button").click()
        assert saved_daily.value.status == 200
        observations["successful_save_statuses"].append(saved_daily.value.status)
        expect(page.locator("#reading-title")).to_have_text("성공재저장님의 하루")
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        assert page.evaluate("shareSource !== window.failedSaveSource && shareFile === null && !document.getElementById('share-dialog').open")
        passed.append("successful profile replacement invalidates the previous share source and file")

        page.set_viewport_size({"width": 1280, "height": 960})
        page.locator('[data-view="month"]').click()
        expect(page.locator("#kline-chart svg")).to_be_visible(timeout=15000)
        page.wait_for_function("""() => {
          const svg = document.querySelector('#kline-chart svg');
          return Math.abs(svg.viewBox.baseVal.width - svg.getBoundingClientRect().width) < 1;
        }""")
        page.locator("#birth-zone").fill("Not/A_Real_Zone")
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/profile"
                                  and response.request.method == "PUT") as invalid_month:
            page.locator("#save-button").click()
        assert invalid_month.value.status == 400
        observations["invalid_save_statuses"].append(invalid_month.value.status)
        expect(page.locator("#form-error")).to_be_visible()
        expect(page.locator("#month-result")).to_be_visible()
        assert page.evaluate("monthResizeObserver !== null")
        page.set_viewport_size({"width": 320, "height": 844})
        page.wait_for_function("""() => {
          const svg = document.querySelector('#kline-chart svg');
          return Math.abs(svg.viewBox.baseVal.width - svg.getBoundingClientRect().width) < 1;
        }""")
        font_sizes = page.locator("#kline-chart text").evaluate_all("""nodes => nodes.map(el => {
          const matrix = el.getScreenCTM();
          return parseFloat(getComputedStyle(el).fontSize) * Math.hypot(matrix.a, matrix.b);
        })""")
        assert font_sizes and min(font_sizes) >= 12 - .01
        observations["month_resize"] = {"from": 1280, "to": 320,
                                       "minimum_text_css_px": min(font_sizes),
                                       "observer_alive": page.evaluate("monthResizeObserver !== null")}
        passed.append("real PUT 400 keeps the month observer alive; 1280-to-320 resize retains at least 12px text")

        fill_form("월간복구")
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/profile"
                                  and response.request.method == "PUT") as saved_month:
            page.locator("#save-button").click()
        assert saved_month.value.status == 200
        observations["successful_save_statuses"].append(saved_month.value.status)
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(page.locator("#month-result")).to_be_hidden()
        assert page.evaluate("monthResizeObserver === null")
        page.evaluate("window.beforeDeleteSource = shareSource")
        page.locator("#delete-button").click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        assert page.evaluate("profile === null && shareSource === null && shareFile === null && !document.getElementById('share-dialog').open")
        expect(page.locator("#daily-result")).to_be_hidden()
        expect(page.locator("#pillars")).to_have_text("")
        passed.append("successful resave and deletion discard old chart, share and profile state")

        stalled_session = []
        page.route("**/api/session", lambda route: stalled_session.append(route))
        page.reload()
        fill_form("세션시간복구")
        expect(page.locator("#save-button")).to_be_disabled()
        expect(page.locator("#form-error")).to_contain_text("응답이 지연", timeout=20000)
        expect(page.locator("#save-button")).to_be_enabled()
        discard_routes(stalled_session)
        page.unroute("**/api/session")
        page.locator("#save-button").click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(page.locator("#reading-title")).to_have_text("세션시간복구님의 하루")
        passed.append("stalled session times out, re-enables the form and retries without reload")

        stalled_reading = []
        page.route("**/api/readings/today", lambda route: stalled_reading.append(route))
        page.locator('[data-view="today"]').click()
        expect(page.locator("#reading-error")).to_contain_text("응답이 지연", timeout=20000)
        expect(page.locator('[data-view="today"]')).to_be_enabled()
        discard_routes(stalled_reading)
        page.unroute("**/api/readings/today")
        page.locator('[data-view="today"]').click()
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        expect(page.locator("#reading-error")).to_be_hidden()
        passed.append("stalled reading times out with a visible error and a successful same-view retry")

        stalled_put = []
        def hold_profile_put(route):
            if route.request.method == "PUT":
                stalled_put.append(route)
            else:
                route.continue_()
        page.route("**/api/profile", hold_profile_put)
        page.locator("#display-name").fill("저장시간초과")
        page.locator("#save-button").click()
        expect(page.locator("#form-error")).to_contain_text("응답이 지연", timeout=20000)
        expect(page.locator("#save-button")).to_be_enabled()
        expect(page.locator("#reading-title")).to_have_text("세션시간복구님의 하루")
        assert page.evaluate("shareSource !== null")
        discard_routes(stalled_put)
        page.unroute("**/api/profile", hold_profile_put)
        page.locator("#display-name").fill("저장시간복구")
        page.locator("#save-button").click()
        expect(page.locator("#reading-title")).to_have_text("저장시간복구님의 하루")
        expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
        passed.append("stalled profile PUT times out without destroying old results and a later save succeeds")

        failed_share_events = []
        held_share_events = []
        page.on("requestfailed", lambda request: failed_share_events.append(request)
                if urlsplit(request.url).path == "/api/events" and request.post_data_json == {"event":"share_card_opened", "view":"today"} else None)
        def hold_share_event(route):
            if route.request.post_data_json == {"event":"share_card_opened", "view":"today"}:
                held_share_events.append(route)
            else:
                route.continue_()
        page.route("**/api/events", hold_share_event)
        page.locator("#open-share").click()
        expect(page.locator("#share-canvas")).to_be_visible()
        expect(page.locator("#download-share")).to_be_enabled()
        for _ in range(500):
            if failed_share_events:
                break
            page.wait_for_timeout(20)
        assert len(failed_share_events) == 1
        discard_routes(held_share_events)
        page.unroute("**/api/events", hold_share_event)
        page.locator("#close-share").click()
        observations["timed_out_share_events"] = len(failed_share_events)
        passed.append("stalled telemetry times out without blocking or invalidating the share card")

        late_save = []
        def hold_completed_put(route):
            if route.request.method == "PUT":
                late_save.append((route, route.fetch()))
            else:
                route.continue_()
        page.route("**/api/profile", hold_completed_put)
        page.locator("#display-name").fill("삭제전늦은저장")
        page.locator("#save-button").click()
        for _ in range(250):
            if late_save:
                break
            page.wait_for_timeout(20)
        assert len(late_save) == 1
        page.locator("#delete-button").click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        try:
            late_save[0][0].fulfill(response=late_save[0][1])
        except Error:
            pass
        page.unroute("**/api/profile", hold_completed_put)
        assert page.evaluate("profile === null && shareSource === null && document.getElementById('display-name').value === ''")
        passed.append("deletion cancels an in-flight save and a late completed PUT cannot restore personal state")

        assert not errors and not external, {"page_errors": errors, "external_requests": external}
        context.close()
        browser.close()

    result = {"passed": passed, "observations": observations, "page_errors": errors, "external_requests": external,
              "scope": "local Chromium, temporary preview store and synthetic profiles"}
    (args.output / "client-state-browser-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
