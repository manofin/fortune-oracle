"""Observe real browser flows against an already running, isolated loopback preview."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8765")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
origin = urlparse(args.url)
assert origin.hostname in {"127.0.0.1", "localhost"}, "Use an isolated local preview, never a production store"
args.output.mkdir(parents=True, exist_ok=True)
errors, external, passed = [], [], []

with sync_playwright() as p:
    browser = p.chromium.launch()
    mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=1, has_touch=True)
    desktop = browser.new_context(viewport={"width": 1280, "height": 960})
    for context in (mobile, desktop):
        def allow_local(route):
            parsed = urlparse(route.request.url)
            if parsed.netloc == origin.netloc:
                route.continue_()
            else:
                external.append(parsed.netloc)
                route.abort()
        context.route("**/*", allow_local)
    a, b = mobile.new_page(), desktop.new_page()
    for page in (a, b):
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.url)
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.fonts.check('14px FortuneKorean', '가나다甲乙')")
        expect(page.locator("#empty-state")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    a.screenshot(path=str(args.output / "mobile-entry.png"), full_page=True)
    b.screenshot(path=str(args.output / "desktop-entry.png"), full_page=True)
    passed.append("mobile and desktop layout without horizontal overflow")

    def register(page, name, birthday, clock="12:30"):
        page.locator("#display-name").fill(name)
        page.locator("#birth-date").fill(birthday)
        page.locator("#unknown-time").set_checked(not clock)
        if clock:
            page.locator("#birth-time").fill(clock)
        page.locator("#gender").select_option("male")
        page.locator("#save-button").click()

    register(a, "가상가", "1990-05-17")
    expect(a.locator("#daily-result")).to_be_visible(timeout=15000)
    expect(a.locator("#reading-title")).to_have_text("가상가님의 하루")
    assert "壬午" in a.locator("#pillars").inner_text()
    current = date.fromisoformat(a.locator("#reading-date").inner_text())
    a.screenshot(path=str(args.output / "mobile-reading.png"))
    expect(b.locator("#birth-date")).to_have_value("")
    passed.append("one registration produces an actual calculated reading; second browser stays empty")

    a.locator('[data-view="tomorrow"]').click()
    expect(a.locator("#reading-date")).to_have_text((current + timedelta(days=1)).isoformat())
    expect(a.locator("#keyword-title")).to_have_text("내일을 바라보는 키워드")
    passed.append("tomorrow is calculated for the next date")
    a.locator('[data-view="month"]').click()
    expect(a.locator("#kline-chart svg")).to_be_visible()
    assert a.locator("#kline-chart rect").count() >= 28
    for viewport_width in (320, 390, 620, 800, 1280, 390):
        a.set_viewport_size({"width": viewport_width, "height":844})
        a.wait_for_function("""() => {
          const svg = document.querySelector('#kline-chart svg');
          return svg && Math.abs(svg.viewBox.baseVal.width - svg.getBoundingClientRect().width) < 1;
        }""")
        boxes = a.locator('#kline-chart text').evaluate_all("""nodes => nodes.map(el => {
          const m = el.getScreenCTM(), r = el.getBoundingClientRect();
          return {size:parseFloat(getComputedStyle(el).fontSize)*Math.hypot(m.a,m.b),
                  x:r.x,right:r.right,y:r.y,text:el.textContent};
        })""")
        assert all(b['size'] >= 12 - .01 for b in boxes), (viewport_width, boxes)
        labels = sorted((b for b in boxes if '-' in b['text']), key=lambda b:b['x'])
        assert all(a['right'] + 2 <= b['x'] for a,b in zip(labels,labels[1:])), labels
        assert all(b['x'] >= 0 and b['right'] <= viewport_width for b in boxes), boxes
        assert a.evaluate('document.documentElement.scrollWidth <= innerWidth')
    passed.append("chart text stays at least 12 CSS px with nonoverlapping dates through 320–1280px resize")
    a.screenshot(path=str(args.output / "mobile-month.png"))
    passed.append("monthly chart uses real engine candles")

    register(b, "가상나", "1990-05-15", "07:30")
    expect(b.locator("#daily-result")).to_be_visible()
    a.reload()
    expect(a.locator("#reading-title")).to_have_text("가상가님의 하루")
    expect(a.locator("#daily-result")).to_be_visible()
    passed.append("return visit restores only its own browser profile")

    b.route("**/api/chart", lambda route: route.fulfill(status=503, content_type="application/json", body=json.dumps({"text":"계산 결과가 아님\n일시적인 계산 실패"})))
    register(b, "수정검증", "1991-05-15", "07:30")
    expect(b.locator("#reading-error")).to_contain_text("계산 결과가 아님")
    expect(b.locator("#chart-section")).to_be_hidden()
    expect(b.locator("#pillars")).to_have_text("")
    b.unroute("**/api/chart")
    register(b, "가상나", "1990-05-15", "07:30")
    expect(b.locator("#daily-result")).to_be_visible()
    passed.append("failed recalculation never shows the previous profile's chart")

    register(a, "경계검증", "2024-02-04", "")
    expect(a.locator("#reading-error")).to_contain_text("계산 결과가 아님")
    expect(a.locator("#daily-result")).to_be_hidden()
    expect(a.locator("#pillars")).to_contain_text("戊戌")
    assert a.locator("#pillars").inner_text().count("미산출") == 3
    passed.append("unknown-time boundary retains registration and calculated day pillar, no invented daily result")

    held = []
    def hold_delete(route):
        if route.request.method == "DELETE":
            held.append((route, route.fetch()))
        else:
            route.continue_()
    a.route("**/api/profile", hold_delete)
    a.expose_function("__fortuneDeletionCaptured", lambda: bool(held))
    a.locator("#delete-button").click()
    a.locator("#confirm-delete").click()
    # Client controls lock before route.fetch() has captured the server reply.
    # Keep that real reply held before exercising cancellation of committed deletion.
    a.wait_for_function("() => window.__fortuneDeletionCaptured()", timeout=15000)
    expect(a.locator("#cancel-delete")).to_be_disabled()
    expect(a.locator("#save-button")).to_be_disabled()
    expect(a.locator('[data-view="tomorrow"]')).to_be_disabled()
    a.keyboard.press("Escape")
    expect(a.locator("#delete-dialog")).to_be_visible()
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    expect(a.locator("#empty-state")).to_be_visible()
    expect(a.locator("#birth-date")).to_have_value("")
    assert "경계검증" not in a.locator("body").inner_text()
    b.reload()
    expect(b.locator("#reading-title")).to_have_text("가상나님의 하루")
    expect(b.locator("#daily-result")).to_be_visible()
    passed.append("deleting one browser revokes its profile without affecting the other")
    passed.append("committed deletion cannot be interrupted by Escape, navigation or another save")
    def lose_delete_reply(route):
        if route.request.method == "DELETE":
            route.fetch(); route.abort()
        else:
            route.continue_()
    b.route("**/api/profile", lose_delete_reply)
    b.locator("#delete-button").click(); b.locator("#confirm-delete").click()
    expect(b.locator("#empty-state")).to_be_visible()
    expect(b.locator("#status")).to_contain_text("삭제된 것을 확인")
    passed.append("lost deletion reply is reconciled with the server before reporting success")
    assert not errors and not external, {"page_errors": errors, "external_requests": external}
    passed.append("no browser JS errors or external requests; synthetic profiles removed")
    browser.close()

result = {"passed": passed, "page_errors": errors, "external_requests": external,
          "source": "actual local Chromium pages; synthetic profiles; not public deployment",
          "mobile_viewport": [390, 844], "desktop_viewport": [1280, 960]}
(args.output / "browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
