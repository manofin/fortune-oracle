"""Local preview only: generic crawler metadata and no-profile referral landing."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    origin = urlsplit(args.url)
    assert origin.hostname in {"127.0.0.1", "localhost"}
    args.output.mkdir(parents=True, exist_ok=True)
    passed, errors, outside = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width":390, "height":844}, is_mobile=True)
        def only_local(route):
            if urlsplit(route.request.url).netloc == origin.netloc:
                route.continue_()
            else:
                outside.append(route.request.url); route.abort()
        context.route("**/*", only_local)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        assert context.request.get(args.url + "/healthz").json()["version"] == "local-preview"
        events = []
        page.on("request", lambda r: events.append(r.post_data_json) if urlsplit(r.url).path == "/api/events" else None)
        with page.expect_response(lambda r: urlsplit(r.url).path == "/api/events" and r.request.post_data_json == {"event":"shared_link_visit", "view":"card"}) as receipt:
            page.goto(args.url + "/?from=card&unrecognized=PRIVATE_CANARY")
        assert receipt.value.status == 202
        expect(page.locator("#empty-state")).to_be_visible()
        assert page.url == args.url + "/"
        assert page.locator('meta[property="og:url"]').get_attribute("content") == args.url + "/"
        image = page.locator('meta[property="og:image"]').get_attribute("content")
        response = context.request.get(image)
        assert response.status == 200 and response.headers["content-type"].startswith("image/png")
        assert events == [{"event":"shared_link_visit", "view":"card"}]
        passed.append("fixed shared-link visit accepted without a profile; unknown query stripped and never sent to metrics")
        page.reload()
        page.evaluate("document.fonts.ready")
        assert len(events) == 1
        passed.append("cleaned URL reload does not resend the entry marker")
        for query in ("?from=unknown", "?from=card&from=card", "?from=PRIVATE_CANARY"):
            page.goto(args.url + "/" + query)
            expect(page.locator("#save-button")).to_be_enabled()
            assert page.url == args.url + "/"
        assert len(events) == 1
        passed.append("unknown and repeated source markers are ignored")
        # A crawler sees the complete common metadata with JavaScript disabled.
        crawler = browser.new_context(java_script_enabled=False)
        crawler.route("**/*", only_local)
        preview = crawler.new_page(); preview.goto(args.url + "/?from=card")
        assert preview.locator('meta[property="og:image"]').get_attribute("content") == image
        assert not crawler.cookies()
        passed.append("JavaScript-free crawler receives generic image metadata without session cookies")
        await_cleanup = """async () => {
          const s = await fetch('/api/session').then(r=>r.json());
          const r = await fetch('/api/profile', {method:'DELETE',headers:{'X-CSRF-Token':s.csrf}});
          return r.ok;
        }"""
        assert page.evaluate(await_cleanup)
        assert not errors and not outside
        passed.append("zero JS errors/third-party requests; synthetic session deleted")
        crawler.close(); context.close(); browser.close()
    result = {"passed":passed, "page_errors":errors, "external_requests":outside,
              "scope":"local Chromium; no real Kakao/Instagram preview observation"}
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
