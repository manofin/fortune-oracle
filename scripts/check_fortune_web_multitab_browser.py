"""Synthetic loopback-only regressions for sibling tabs and interrupted delivery.

Reuses one browser context per scenario to exercise a shared HttpOnly cookie.
Linux browser coverage does not establish physical iPhone/Safari behavior.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, expect, sync_playwright


PRODUCT = "self_manual_v1"
INTEREST = {"event": "product_sample_interest", "view": PRODUCT}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8773")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    origin = urlsplit(base)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, external, events, broadcasts, history = [], [], [], [], [], []

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        browser_version = browser.version

        def local_only(route):
            if urlsplit(route.request.url).netloc == origin.netloc:
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        def new_context():
            context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
            context.route("**/*", local_only)
            context.add_init_script("""
              window.observedBroadcasts = [];
              if (window.BroadcastChannel) {
                const post = BroadcastChannel.prototype.postMessage;
                BroadcastChannel.prototype.postMessage = function(value) {
                  window.observedBroadcasts.push(value); return post.call(this, value);
                };
              }
              window.historyRestores = [];
              addEventListener('pageshow', event => window.historyRestores.push(event.persisted));
            """)
            return context

        def page_in(context, path="/"):
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: events.append(request.post_data_json)
                    if urlsplit(request.url).path == "/api/events" else None)
            page.goto(base + path)
            return page

        def register(page, name="가상여러탭"):
            page.locator("#display-name").fill(name)
            page.locator("#birth-date").fill("1990-05-17")
            page.locator("#save-button").click()
            expect(page.locator("#reading-title")).to_have_text(name + "님의 하루")
            expect(page.locator("#daily-result")).to_be_visible()

        def remove(page):
            page.locator("#delete-button").click()
            page.locator("#confirm-delete").click()
            expect(page.locator("#empty-state")).to_be_visible()
            expect(page.locator("#delete-dialog")).to_be_hidden()

        def private_state_cleared(page):
            expect(page.locator("#birth-date")).to_have_value("")
            expect(page.locator("#reading-panel")).to_be_hidden()
            expect(page.locator("#share-dialog")).to_be_hidden()
            expect(page.locator("#download-share")).to_be_disabled()
            assert page.evaluate("profile === null && shareSource === null && shareFile === null")

        def finish(context):
            for page in context.pages:
                assert page.evaluate("localStorage.length + sessionStorage.length") == 0
                broadcasts.extend(page.evaluate("window.observedBroadcasts"))
            context.close()

        def release(held):
            for route, response in held:
                try:
                    route.fulfill(response=response)
                except Error:
                    # Cancellation may have already closed the intercepted fetch.
                    pass

        context = new_context()
        assert context.request.get(base + "/healthz").json()["version"] == "local-preview"
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        sibling.locator("#open-share").click()
        expect(sibling.locator("#download-share")).to_be_enabled()
        remove(owner)
        private_state_cleared(sibling)
        sibling.screenshot(path=str(args.output / "sibling-delete-cleared.png"))
        passed.append("Sibling deletion immediately clears an existing profile, result, open PNG and download action")
        finish(context)

        for surface in ("main", "samples"):
            context = new_context()
            owner = page_in(context)
            register(owner)
            sibling = page_in(context)
            expect(sibling.locator("#daily-result")).to_be_visible()
            deleter = owner if surface == "main" else page_in(context, "/samples")
            held_delete = []
            def hold_delete(route):
                if route.request.method == "DELETE":
                    held_delete.append(route)
                    deleter.evaluate("window.deleteHeld = true")
                else:
                    route.fallback()
            deleter.route("**/api/profile", hold_delete)
            deleter.locator("#delete-button" if surface == "main" else "#sp-delete-button").click()
            deleter.locator("#confirm-delete" if surface == "main" else "#sp-delete-confirm").click()
            deleter.wait_for_function("() => window.deleteHeld === true")
            private_state_cleared(sibling)
            # The server has not committed yet; a reload can still see the old
            # profile. Completion must notify again, not only deletion start.
            sibling.reload()
            expect(sibling.locator("#daily-result")).to_be_visible()
            assert len(held_delete) == 1
            held_delete[0].continue_()
            if surface == "main":
                expect(deleter.locator("#delete-dialog")).to_be_hidden()
            else:
                expect(deleter.locator("#sp-delete-status")).to_contain_text("삭제했어요")
            private_state_cleared(sibling)
            passed.append(f"{surface} deletion completion invalidates a sibling that reloaded during a held precommit DELETE")
            finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        held_session, writes = [], []
        def hold_first_session(route):
            if not held_session:
                held_session.append((route, route.fetch()))
                sibling.evaluate("window.sessionHeld = true")
            else:
                route.fallback()
        sibling.route("**/api/session", hold_first_session)
        sibling.on("request", lambda request: writes.append(request.post_data_json["display_name"])
                   if urlsplit(request.url).path == "/api/profile" and request.method == "PUT" else None)
        sibling.reload()
        sibling.wait_for_function("() => window.sessionHeld === true")
        sibling.locator("#display-name").fill("가상오래된제출")
        sibling.locator("#birth-date").fill("1990-05-17")
        sibling.locator("#birth-form").evaluate("node => node.requestSubmit()")
        expect(sibling.locator("#save-button")).to_be_disabled()
        remove(owner)
        private_state_cleared(sibling)
        register(sibling, "가상새제출")
        release(held_session)
        expect(sibling.locator("#reading-title")).to_have_text("가상새제출님의 하루")
        assert writes == ["가상새제출"], writes
        remove(sibling)
        passed.append("Invalidation cancels a queued save and stale bootstrap; a new save cannot be overwritten by the abandoned submission")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        committed_put = []
        def hold_committed_put(route):
            if route.request.method == "PUT":
                committed_put.append((route, route.fetch()))
                owner.evaluate("window.putCommitted = true")
            else:
                route.fallback()
        owner.route("**/api/profile", hold_committed_put)
        owner.locator("#display-name").fill("가상먼저저장")
        owner.locator("#save-button").click()
        owner.wait_for_function("() => window.putCommitted === true")
        assert committed_put[0][1].status == 200
        register(sibling, "가상최종저장")
        private_state_cleared(owner)
        release(committed_put)
        private_state_cleared(sibling)
        private_state_cleared(owner)
        sibling.reload()
        expect(sibling.locator("#reading-title")).to_have_text("가상최종저장님의 하루")
        remove(sibling)
        passed.append("A late committed PUT acknowledgement still invalidates siblings without replacing the newer saved profile")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        waiting_delete = []
        def hold_overlapping_delete(route):
            if route.request.method == "DELETE":
                waiting_delete.append(route)
                owner.evaluate("window.deleteWaiting = true")
            else:
                route.fallback()
        owner.route("**/api/profile", hold_overlapping_delete)
        owner.locator("#delete-button").click()
        owner.locator("#confirm-delete").click()
        owner.wait_for_function("() => window.deleteWaiting === true")
        private_state_cleared(sibling)
        sibling.reload()
        expect(sibling.locator("#daily-result")).to_be_visible()
        register(sibling, "가상삭제전저장")
        private_state_cleared(owner)
        waiting_delete[0].continue_()
        private_state_cleared(sibling)
        expect(owner.locator("#delete-button")).to_be_enabled()
        sibling.reload()
        expect(sibling.locator("#empty-state")).to_be_visible()
        expect(sibling.locator("#birth-date")).to_have_value("")
        passed.append("An already submitted DELETE drains after a sibling PUT invalidates its UI and still clears the final result")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        held = []
        def hold_reading(route):
            held.append((route, route.fetch()))
            sibling.evaluate("window.readingHeld = true")
        sibling.route("**/api/readings/tomorrow", hold_reading)
        sibling.locator('[data-view="tomorrow"]').click()
        sibling.wait_for_function("() => window.readingHeld === true")
        assert len(held) == 1
        before = sum(event == {"event": "reading_viewed", "view": "tomorrow"} for event in events)
        remove(owner)
        release(held)
        private_state_cleared(sibling)
        assert sum(event == {"event": "reading_viewed", "view": "tomorrow"} for event in events) == before
        passed.append("A completed sibling reading delivered after deletion cannot restore a result or a viewed event")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        sibling.evaluate("""() => {
          const original = HTMLCanvasElement.prototype.toBlob;
          HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
            return original.call(this, blob => { window.releaseCard = () => callback(blob); }, ...args);
          };
        }""")
        sibling.locator("#open-share").click()
        sibling.wait_for_function("() => typeof window.releaseCard === 'function'")
        register(owner, "가상수정후")
        private_state_cleared(sibling)
        sibling.evaluate("window.releaseCard()")
        private_state_cleared(sibling)
        sibling.reload()
        expect(sibling.locator("#reading-title")).to_have_text("가상수정후님의 하루")
        remove(owner)
        passed.append("Sibling profile replacement cancels pending PNG encoding; reload shows only the updated profile")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sample = page_in(context, "/samples")
        sample.locator(f'[data-sample-open="{PRODUCT}"]').click()
        interest = sample.locator(f'[data-sample-interest="{PRODUCT}"]')
        status = sample.locator(f'[data-sample-status="{PRODUCT}"]')
        sample.locator(f'[data-sample-adult="{PRODUCT}"]').check()
        expect(interest).to_be_enabled()
        held = []
        def hold_interest(route):
            if route.request.post_data_json == INTEREST:
                held.append((route, route.fetch()))
                sample.evaluate("window.interestHeld = true")
            else:
                route.fallback()
        sample.route("**/api/events", hold_interest)
        interest.click()
        expect(interest).to_be_disabled()
        sample.wait_for_function("() => window.interestHeld === true")
        assert len(held) == 1 and held[0][1].status == 202
        remove(owner)
        release(held)
        expect(sample.locator(f'[data-sample-adult="{PRODUCT}"]')).not_to_be_checked()
        expect(interest).to_have_attribute("data-confirmed", "false")
        expect(interest).to_be_disabled()
        assert "관심을 기록했어요" not in status.inner_text()
        sample.unroute("**/api/events", hold_interest)
        sample.locator(f'[data-sample-open="{PRODUCT}"]').click()
        sample.locator(f'[data-sample-adult="{PRODUCT}"]').check()
        expect(interest).to_be_enabled()
        interest.click()
        expect(interest).to_have_attribute("data-confirmed", "true")
        sample.locator("#sp-delete-button").click()
        sample.locator("#sp-delete-confirm").click()
        expect(sample.locator("#sp-delete-status")).to_contain_text("삭제했어요")
        assert not context.cookies()
        passed.append("A real committed interest ACK arriving after sibling deletion stays unconfirmed; explicit reopen safely retries")
        finish(context)

        context = new_context()
        page = page_in(context, "/samples")
        page.locator(f'[data-sample-open="{PRODUCT}"]').click()
        adult = page.locator(f'[data-sample-adult="{PRODUCT}"]')
        interest = page.locator(f'[data-sample-interest="{PRODUCT}"]')
        adult.check()
        expect(interest).to_be_enabled()
        context.set_offline(True)
        interest.click()
        expect(page.locator(f'[data-sample-status="{PRODUCT}"]')).to_contain_text("확인하지 못했어요")
        expect(interest).to_have_attribute("data-confirmed", "false")
        expect(interest).to_be_enabled()
        context.set_offline(False)
        lost = []
        def lose_ack(route):
            if route.request.post_data_json == INTEREST:
                response = route.fetch()
                lost.append(response.status)
                route.abort("failed")
            else:
                route.fallback()
        page.route("**/api/events", lose_ack)
        interest.click()
        expect(page.locator(f'[data-sample-status="{PRODUCT}"]')).to_contain_text("확인하지 못했어요")
        expect(interest).to_have_attribute("data-confirmed", "false")
        expect(interest).to_be_enabled()
        assert lost == [202]
        page.unroute("**/api/events", lose_ack)
        interest.click()
        expect(interest).to_have_attribute("data-confirmed", "true")
        page.locator("#sp-delete-button").click()
        page.locator("#sp-delete-confirm").click()
        expect(page.locator("#sp-delete-status")).to_contain_text("삭제했어요")
        passed.append("Offline interest and a committed-but-lost ACK show no false success; reconnect and duplicate-safe retry succeed")
        finish(context)

        context = new_context()
        owner = page_in(context)
        register(owner)
        sibling = page_in(context)
        expect(sibling.locator("#daily-result")).to_be_visible()
        sibling.locator("#compat-details summary").click()
        sibling.locator("#partner-date").fill("1997-08-19")
        sibling.goto(base + "/samples")
        remove(owner)
        sibling.go_back()
        expect(sibling.locator("#birth-date")).to_have_value("")
        expect(sibling.locator("#partner-date")).to_have_value("")
        expect(sibling.locator("#reading-panel")).to_be_hidden()
        assert sibling.evaluate("profile === null && shareSource === null && shareFile === null")
        history.append({"real_navigation_pageshow": sibling.evaluate("window.historyRestores"),
                        "navigation_type": sibling.evaluate("performance.getEntriesByType('navigation')[0]?.type"),
                        "birth_field_empty": sibling.locator("#birth-date").input_value() == "",
                        "partner_field_empty": sibling.locator("#partner-date").input_value() == ""})
        sibling.screenshot(path=str(args.output / "history-back-cleared.png"))
        # Routing/no-store may prevent real BFCache in a given engine. Exercise
        # its persisted lifecycle separately without claiming a real cache hit.
        register(owner)
        sibling.reload()
        expect(sibling.locator("#daily-result")).to_be_visible()
        sibling.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))")
        private_state_cleared(sibling)
        remove(owner)
        sibling.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
        expect(sibling.locator("#save-button")).to_be_enabled()
        expect(sibling.locator("#birth-date")).to_have_value("")
        expect(sibling.locator("#reading-panel")).to_be_hidden()
        passed.append("Back navigation after sibling deletion shows no profile; persisted lifecycle scrubs before caching and revalidates on return")
        finish(context)

        assert not errors and not external, {"errors": errors, "external": external}
        assert broadcasts and all(value == "profile-invalidated" for value in broadcasts), broadcasts
        for event in events:
            assert set(event) == {"event", "view"}, event
        for private in ("가상여러탭", "가상수정후", "가상오래된제출", "가상새제출", "가상먼저저장", "가상최종저장", "가상삭제전저장", "1990-05-17"):
            assert private not in json.dumps(events + broadcasts, ensure_ascii=False)
        passed.append("Cross-tab coordination uses one transient fixed label; no personal data, browser storage or outside requests")
        browser.close()

    result = {"browser": args.browser, "browser_version": browser_version, "passed": passed,
              "page_errors": errors, "external_requests": external, "history": history,
              "scope": "Linux browser with phone viewport; no physical iPhone/Safari or production data"}
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
