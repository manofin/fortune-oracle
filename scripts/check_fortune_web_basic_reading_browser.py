"""Review basic readings in local Chromium using synthetic adult profiles.

Run against web/preview.py. This checks layout and records scroll measurements;
it does not assess interpretation quality, physical devices, or a PDF product.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    origin = urlsplit(args.url)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    errors, external, observations = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844},
                                      is_mobile=True, has_touch=True, device_scale_factor=1)

        def only_local(route):
            if urlsplit(route.request.url).netloc == origin.netloc:
                route.continue_()
            else:
                external.append(urlsplit(route.request.url).netloc)
                route.abort()

        context.route("**/*", only_local)
        assert context.request.get(args.url.rstrip("/") + "/healthz").json()["version"] == "local-preview"
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.fonts.check('14px FortuneKorean', '가나다甲乙')")
        for sample, birthday, clock, gender in (
            ("synthetic-a", "1990-05-15", "07:30", "male"),
            ("synthetic-b", "1988-03-02", "", "unknown"),
        ):
            page.locator("#display-name").fill("가상검토")
            page.locator("#birth-date").fill(birthday)
            page.locator("#unknown-time").set_checked(not clock)
            if clock:
                page.locator("#birth-time").fill(clock)
            page.locator("#gender").select_option(gender)
            page.locator("#save-button").click()
            expect(page.locator("#daily-result")).to_be_visible(timeout=15000)
            expect(page.locator("#save-button")).to_be_enabled()
            card = page.locator("#daily-result")
            details = card.locator(".full-reading")
            for width in (320, 390, 430):
                page.set_viewport_size({"width": width, "height": 844})
                for expanded in (False, True):
                    details.evaluate("(el, open) => { el.open = open; }", expanded)
                    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                    card.scroll_into_view_if_needed()
                    layout = card.evaluate("""card => {
                      const r = card.getBoundingClientRect();
                      const full = card.querySelector('#full-text');
                      const f = full.getBoundingClientRect();
                      const range = document.createRange(); range.selectNodeContents(full);
                      const boxes = [...range.getClientRects()].filter(b => b.height && b.width);
                      const textOutside = boxes.some(b => b.left < f.left - 1 || b.right > f.right + 1);
                      return {
                        viewportWidth: innerWidth, viewportHeight: innerHeight,
                        pageOverflow: document.documentElement.scrollWidth > innerWidth,
                        cardHeight: Math.round(r.height), fullTextHeight: Math.round(f.height),
                        cardScreenfuls: +(r.height / innerHeight).toFixed(2),
                        textOutside, textFontSize: getComputedStyle(full).fontSize,
                        textLineHeight: getComputedStyle(full).lineHeight,
                        readingDate: card.querySelector('#reading-date').textContent,
                        summary: card.querySelector('#day-relation').textContent,
                        semanticSubheadings: full.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
                        paragraphs: full.textContent.split(/\\n\\s*\\n/).map(s => s.length)
                      };
                    }""")
                    assert not layout["pageOverflow"], layout
                    assert not layout["textOutside"], layout
                    filename = f"{sample}-{width}-{'expanded' if expanded else 'collapsed'}.png"
                    card.screenshot(path=str(args.output / filename))
                    observations.append({"sample": sample, "expanded": expanded,
                                         "screenshot": filename, **layout})
            page.locator("#delete-button").click()
            page.locator("#confirm-delete").click()
            expect(page.locator("#empty-state")).to_be_visible()
        assert not errors and not external, {"errors": errors, "external": external}
        browser_version = browser.version
        browser.close()
    result = {"source": "local Chromium mobile viewport emulation; synthetic adult profiles",
              "browserVersion": browser_version, "physicalDeviceTested": False,
              "pdfTested": False, "pageErrors": errors, "externalRequests": external,
              "observations": observations}
    (args.output / "basic-reading-browser.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
