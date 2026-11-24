"""Check natal-marker rendering in a temporary loopback preview.

Uses synthetic adult profiles and explicitly identified chart-response fixtures.
No production server, external requests, or real birth records are allowed.
All generated files, including the panel-only PNG, go inside --output.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
from hermes_ext.fortune_oracle.natal_markers import evaluate_natal_markers


SOURCES = (
    "plugins/hermes_ext/fortune_oracle/natal_markers.py",
    "plugins/hermes_ext/fortune_oracle/natal_pillars.py",
    "plugins/hermes_ext/fortune_oracle/bazi_bridge.py",
    "plugins/hermes_ext/fortune_oracle/scripts/life_kline_bazi_bridge.mjs",
    "web/fortune_web/service.py",
    "web/fortune_web/static/app.js",
    "web/fortune_web/static/index.html",
    "web/fortune_web/static/style.css",
    "scripts/check_fortune_web_natal_markers_browser.py",
)
LABELS = ["두 기둥의 지지 조합", "년지 기준", "일지 기준", "간이 기준 · 자·오·묘·유"]


def fingerprints():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def inspect_complete_reading(page, panel):
    """Check meaning and order against the known synthetic chart, not generated DOM."""
    values = page.locator("#natal-marker-results dd")
    expected = [
        "조건에 맞음 · 년주 오(午) ↔ 일주 축(丑)",
        "조건에 맞는 자리 없음",
        "조건에 맞음 · 년주 오(午)",
        "조건에 맞음 · 년주 오(午)",
    ]
    # Direct text includes the status span and matched positions; the separate
    # small element is the criterion below them, not part of the result line.
    visible_results = values.evaluate_all("""elements => elements.map(el =>
        [...el.childNodes].filter(node => node.nodeName !== 'SMALL')
            .map(node => node.textContent).join('').trim())""")
    assert visible_results == expected, visible_results
    criteria = values.locator("small.marker-criterion")
    assert criteria.all_text_contents() == [
        "년주 오(午) 기준으로 묘(卯) 자리를 찾습니다.",
        "일주 축(丑) 기준으로 오(午) 자리를 찾습니다.",
    ]
    criterion_layout = criteria.evaluate_all("""elements => elements.map(el => ({
        display: getComputedStyle(el).display,
        fontSize: parseFloat(getComputedStyle(el).fontSize),
        belowStatus: el.getBoundingClientRect().top >=
            el.parentElement.querySelector('span').getBoundingClientRect().bottom - 1
    }))""")
    assert all(item["display"] == "block" and item["belowStatus"]
               and item["fontSize"] >= 12 for item in criterion_layout), criterion_layout
    reflections = page.locator(".marker-reflection").all_text_contents()
    assert len(reflections) == 2
    assert "마음에 걸리는 말이 있다면" in reflections[0]
    assert "모임을 앞두고 있다면" in reflections[1]
    assert all(word not in panel.inner_text() for word in ("강도", "상위", "성공 확률"))
    return {"case": "actual_chart_complete", "passed": True, "rules": 4,
            "visible_results": visible_results, "criteria": criteria.all_text_contents(),
            "criterion_layout": criterion_layout, "conditional_reflections": 2}


def measure_panel(panel):
    return panel.evaluate("""el => {
        const box = el.getBoundingClientRect();
        const text = [...el.querySelectorAll('p, dt, dd, small')];
        return {
            width: innerWidth, pageWidth: document.documentElement.scrollWidth,
            panelWidth: box.width, panelHeight: box.height,
            textOutside: text.some(node => {
                const bounds = node.getBoundingClientRect();
                const range = document.createRange(); range.selectNodeContents(node);
                return [...range.getClientRects()].some(rect => rect.width && rect.height &&
                    (rect.left < bounds.left - 1 || rect.right > bounds.right + 1));
            }),
            clipped: text.some(node => node.scrollHeight > node.clientHeight + 1 &&
                ['hidden', 'clip'].includes(getComputedStyle(node).overflowY)),
            color: getComputedStyle(el).color,
            paper: getComputedStyle(document.documentElement).backgroundColor,
            reflections: [...el.querySelectorAll('.marker-reflection')].map(node => ({
                background: getComputedStyle(node).backgroundColor,
                borderWidth: parseFloat(getComputedStyle(node).borderInlineStartWidth)
            }))
        };
    }""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Temporary loopback preview origin")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    origin = urlsplit(args.url)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    assert origin.path in {"", "/"}, "Provide the preview origin without a path"
    base = args.url.rstrip("/")
    args.output.mkdir(parents=True, exist_ok=True)
    source_hashes = fingerprints()
    checks, layouts, errors, external = [], [], [], []
    state = {"override": None, "hold": False, "held": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844},
                                      color_scheme="light", is_mobile=True, has_touch=True)

        def only_local(route):
            if urlsplit(route.request.url).netloc != origin.netloc:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", only_local)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def chart_transport(route):
            if state["hold"]:
                state["held"].append(route)
            elif state["override"] is not None:
                route.fulfill(status=200, json=deepcopy(state["override"]))
            else:
                route.fallback()

        page.route("**/api/chart", chart_transport)
        assert context.request.get(base + "/healthz").json()["version"] == "local-preview"
        page.goto(base)
        page.evaluate("document.fonts.ready")
        panel = page.locator("#natal-markers")

        def open_panel():
            expect(panel).to_be_visible()
            if not panel.evaluate("el => el.open"):
                panel.locator("summary").click()
            expect(page.locator("#natal-marker-results")).to_be_visible()
            assert page.locator("#natal-marker-results h4").all_text_contents() == ["원진", "도화"]
            assert page.locator("#natal-marker-results dt").all_text_contents() == LABELS

        def save(birth, clock):
            page.locator("#display-name").fill("합성검토")
            page.locator("#birth-date").fill(birth)
            page.locator("#unknown-time").set_checked(not clock)
            if clock:
                page.locator("#birth-time").fill(clock)
            page.locator("#birth-zone").fill("Asia/Seoul")
            page.locator("#gender").select_option("unknown")
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/chart") as response:
                page.locator("#save-button").click()
            assert response.value.status == 200
            result = response.value.json()
            expect(page.locator("#save-button")).to_be_enabled(timeout=20000)
            open_panel()
            return result

        def assert_cleared():
            expect(panel).to_be_hidden()
            expect(page.locator("#natal-marker-results")).to_have_text("")
            expect(page.locator("#natal-coverage")).to_have_text("")
            assert not panel.evaluate("el => el.open")

        def next_view(view):
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/chart") as response:
                page.locator(f'[data-view="{view}"]').click()
            assert response.value.status == 200
            expect(page.locator(f'[data-view="{view}"]')).to_be_enabled(timeout=20000)

        actual = save("1990-05-24", "07:30")
        assert actual["pillars"] == {"year": "庚午", "month": "辛巳", "day": "己丑", "time": "戊辰"}
        assert actual["natal_markers"] == evaluate_natal_markers(actual["pillars"])
        checks.append(inspect_complete_reading(page, panel))

        for scheme in ("light", "dark"):
            page.emulate_media(color_scheme=scheme)
            for width in (320, 390):
                page.set_viewport_size({"width": width, "height": 844})
                panel.scroll_into_view_if_needed()
                geometry = measure_panel(panel)
                assert geometry["pageWidth"] <= width, geometry
                assert not geometry["textOutside"] and not geometry["clipped"], geometry
                assert all(item["background"] not in {"transparent", "rgba(0, 0, 0, 0)", geometry["paper"]}
                           and item["borderWidth"] >= 2 for item in geometry["reflections"]), geometry
                layouts.append({"scheme": scheme, **geometry})
        page.emulate_media(color_scheme="light")
        page.set_viewport_size({"width": 390, "height": 844})
        assert "합성검토" not in panel.inner_text() and "1990-05-24" not in panel.inner_text()
        assert not panel.locator("input").count()
        screenshot_name = "natal-markers-mobile.png"
        panel.screenshot(path=str(args.output / screenshot_name))

        unknown = save("1988-03-02", "")
        assert unknown["natal_markers"]["coverage"]["missing_positions"] == ["time"]
        assert all(rule["status"] == "insufficient_input" for rule in unknown["natal_markers"]["rules"])
        assert page.locator(".marker-reflection").count() == 0
        assert all("입력 부족" in text and "조건에 맞는 자리 없음" not in text
                   for text in page.locator("#natal-marker-results dd").all_text_contents())
        expect(page.locator("#natal-coverage")).to_contain_text("확인한 자리 년주·월주·일주.")
        checks.append({"case": "actual_unknown_hour_no_false_negative", "passed": True})

        boundary = save("1990-02-04", "")
        assert boundary["pillars"] == {"year": "", "month": "", "day": "庚子", "time": ""}
        assert boundary["natal_markers"]["coverage"]["missing_positions"] == ["year", "month", "time"]
        expect(page.locator("#natal-coverage")).to_contain_text("확인한 자리 일주.")
        expect(page.locator("#natal-marker-results dd").nth(1).locator("small")).to_have_text(
            "년주가 정해져야 기준 글자를 고를 수 있습니다.")
        expect(page.locator("#natal-marker-results dd").nth(3)).to_have_text("조건에 맞음 · 일주 자(子)")
        assert page.locator(".marker-reflection").count() == 1
        checks.append({"case": "actual_ipchun_unknown_year_month_hour", "passed": True,
                       "missing": ["year", "month", "time"]})

        month_boundary = save("1990-03-06", "")
        assert month_boundary["natal_markers"]["coverage"]["missing_positions"] == ["month", "time"]
        expect(page.locator("#natal-coverage")).to_contain_text("확인한 자리 년주·일주.")
        assert page.locator(".marker-reflection").count() == 1
        checks.append({"case": "actual_month_boundary_unknown_month_hour", "passed": True})

        # Injected chart fixture: every repeated position must survive rendering.
        repeated = deepcopy(actual)
        repeated["pillars"] = {"year": "甲子", "month": "乙未", "day": "甲子", "time": "乙未"}
        repeated["elements"] = {"목(木)": 4, "화(火)": 0, "토(土)": 2, "금(金)": 0, "수(水)": 2}
        repeated["natal_markers"] = evaluate_natal_markers(repeated["pillars"])
        state["override"] = repeated
        next_view("tomorrow")
        open_panel()
        first = page.locator("#natal-marker-results dd").first.inner_text()
        for text in ("년주 자(子) ↔ 월주 미(未)", "년주 자(子) ↔ 시주 미(未)",
                     "월주 미(未) ↔ 일주 자(子)", "일주 자(子) ↔ 시주 미(未)"):
            assert text in first
        page.set_viewport_size({"width": 320, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append({"case": "injected_repeated_positions_preserved", "passed": True, "wonjin_pairs": 4})

        # A new tab clears the previous facts before its pending chart returns.
        state["override"] = None
        state["hold"] = True
        with page.expect_request(lambda r: urlsplit(r.url).path == "/api/chart"):
            page.locator('[data-view="today"]').click()
        assert_cleared()
        assert len(state["held"]) == 1
        state["hold"] = False
        state["held"].pop().continue_()
        expect(page.locator('[data-view="today"]')).to_be_enabled(timeout=20000)
        open_panel()
        expect(page.locator("#natal-coverage")).to_contain_text("확인한 자리 년주·일주.")
        checks.append({"case": "tab_loading_clears_and_replaces_previous_marker_facts", "passed": True})

        legacy = deepcopy(actual)
        legacy.pop("natal_markers")
        state["override"] = legacy
        next_view("tomorrow")
        assert_cleared()
        expect(page.locator("#chart-section")).to_be_visible()
        checks.append({"case": "legacy_chart_keeps_chart_but_clears_marker_panel", "passed": True})

        for label in ("unknown_version", "partial_rules"):
            state["override"] = deepcopy(actual)
            next_view("today")
            open_panel()
            payload = deepcopy(actual)
            if label == "unknown_version":
                payload["natal_markers"]["schema_version"] = 99
            else:
                payload["natal_markers"]["rules"].pop()
            state["override"] = payload
            next_view("tomorrow")
            assert_cleared()
            checks.append({"case": f"injected_{label}_clears_marker_panel", "passed": True})

        state["override"] = None
        next_view("today")
        open_panel()
        page.locator("#delete-button").click()
        with page.expect_response(lambda r: r.request.method == "DELETE"
                                  and urlsplit(r.url).path == "/api/profile") as deletion:
            page.locator("#confirm-delete").click()
        assert deletion.value.status == 200
        expect(page.locator("#empty-state")).to_be_visible(timeout=15000)
        assert_cleared()
        assert context.request.get(base + "/api/session").json()["profile"] is None
        checks.append({"case": "actual_deletion_clears_marker_content_and_profile", "passed": True})
        browser_version = browser.version
        browser.close()

    assert not errors and not external, {"errors": errors, "external": external}
    assert source_hashes == fingerprints(), "Source changed during verification; rerun against one revision"
    report = {
        "source": "local Chromium; synthetic adult profiles and explicitly injected chart fixtures",
        "browser": browser_version, "physical_device_tested": False,
        "checks": checks, "layouts": layouts, "page_errors": errors, "external_requests": external,
        "source_sha256": source_hashes, "screenshot": screenshot_name,
    }
    (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"checks": len(checks), "layouts": len(layouts), "page_errors": errors,
                      "external_requests": external, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
