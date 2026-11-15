"""Review basic readings in local Chromium using synthetic adult profiles.

Run against web/preview.py. This checks layout and records scroll measurements;
it does not assess interpretation quality, physical devices, or a PDF product.
"""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


SCENARIO_CAUTIONS = {
    "exam": "풀이 점수로 시험 결과를 예상하거나, 준비 계획을 무리하게 바꾸지 마세요.",
    "meeting": "풀이 점수로 상대의 마음이나 만남의 결과를 단정하지 말고, 상대의 뜻은 대화로 확인하세요.",
}


def visibility(locator):
    """Measure CSS/DOM visibility separately from full viewport containment."""
    return locator.evaluate("""el => {
      const r = el.getBoundingClientRect();
      const cssVisible = el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
      const displayed = cssVisible && r.width > 0 && r.height > 0;
      return {displayed, inViewport: displayed && r.top >= 0 && r.left >= 0 &&
              r.bottom <= innerHeight && r.right <= innerWidth,
              top: +r.top.toFixed(2), bottom: +r.bottom.toFixed(2), height: +r.height.toFixed(2)};
    }""")


def inspect_reading(page, result, view, sample, semantic):
    """Compare rendered meaning with the actual response, not just geometry."""
    reading = result["reading"]
    card = page.locator("#daily-result")
    details = card.locator(".full-reading")
    expect(card).to_be_visible(timeout=15000)
    expect(page.locator("#save-button")).to_be_enabled()
    sections = result["sections"]
    expect(page.locator("#day-relation")).to_have_text(sections["theme"]["text"])
    expect(page.locator("#daily-action")).to_have_text(sections["action"]["text"])
    expect(page.locator("#daily-caution")).to_have_text(sections["caution"]["text"])
    expect(page.locator("#reading-date")).to_have_text(result["date"])
    expect(page.locator("#reading-timezone")).to_have_text(result["reading_timezone"])
    expect(page.locator("#keyword-title")).to_have_text({
        "today": "오늘을 바라보는 키워드", "tomorrow": "내일을 바라보는 키워드",
        "dday": "그날을 준비하는 키워드",
    }[view])
    expect(page.locator("#full-text")).to_have_text("")
    text = result["text"]
    actions = [line for line in text.splitlines() if line.startswith("해볼 일")]
    cautions = [line for line in text.splitlines() if line.startswith("주의할 점")]
    assert len(actions) == 1, actions
    assert len(cautions) == 1, cautions
    base_action = next(line for line in reading["lines"] if line.startswith("해볼 일"))
    base_caution = next(line for line in reading["lines"] if line.startswith("주의할 점"))
    scenario = result.get("scenario")
    if scenario in {"exam", "meeting"}:
        assert result["reflection"] in actions[0]
        assert text.count(result["reflection"]) == 1
        assert base_action not in text
        expected_caution = f"주의할 점 (선택한 상황에 맞춘 제안): {SCENARIO_CAUTIONS[scenario]}"
        assert cautions == [expected_caution]
        assert text.count(SCENARIO_CAUTIONS[scenario]) == 1
        assert base_caution not in text
    else:
        assert actions == [base_action]
        assert cautions == [base_caution]
        if scenario == "general":
            assert result["reflection"] not in text
    assert text.count(reading["disclaimer"]) == 1
    assert text.count("점수와 조언은 경험적 해석이며 예측 확률이 아닙니다.") == 1
    assert "상황별 성찰 질문" not in text
    details.evaluate("el => { el.open = false; }")
    card.evaluate("el => el.scrollIntoView({block: 'start'})")
    expect(page.locator("#day-relation")).to_be_visible()
    expect(page.locator("#daily-evidence")).to_be_hidden()
    collapsed = {key: visibility(page.locator(f"#daily-{key}")) for key in ("action", "caution")}
    assert all(item["displayed"] and item["inViewport"] for item in collapsed.values()), collapsed
    details.locator("summary").click()
    expect(page.locator("#daily-evidence")).to_be_visible()
    groups = page.locator("#daily-evidence > section")
    assert groups.count() == len(sections["evidence"]) >= 4
    for index, evidence in enumerate(sections["evidence"]):
        group = groups.nth(index)
        assert group.get_attribute("data-evidence") == evidence["id"]
        expect(group.locator("h4")).to_have_text(evidence["title"])
        assert group.locator("p").all_text_contents() == evidence["paragraphs"]
    for key in ("theme", "action", "caution"):
        assert card.inner_text().count(sections[key]["text"]) == 1
    assert card.inner_text().count("점수와 조언은 경험적 해석이며 예측 확률이 아닙니다.") == 1
    expanded = {key: visibility(page.locator(f"#daily-{key}")) for key in ("action", "caution")}
    assert all(item["displayed"] for item in expanded.values()), expanded
    semantic.append({"sample": sample, "view": view, "scenario": scenario,
                     "date": result["date"], "relation": reading["relation"], "summary": sections["theme"]["text"],
                     "primaryAction": actions[0], "primaryActionCount": len(actions),
                     "caution": cautions[0], "cautionCount": len(cautions),
                     "disclaimerCount": card.inner_text().count("점수와 조언은 경험적 해석이며 예측 확률이 아닙니다."),
                     "baseInterpretationVisible": page.locator("#day-relation").is_visible(),
                     "actionVisibleWhenExpanded": expanded["action"]["displayed"],
                     "actionVisibleWhenCollapsed": collapsed["action"]["displayed"],
                     "collapsedVisibility": collapsed, "expandedVisibility": expanded,
                     "evidenceHeadings": groups.locator("h4").all_text_contents()})


def submit_dated(page):
    with page.expect_response(lambda response: urlsplit(response.url).path == "/api/readings/date") as captured:
        page.locator("#date-submit").click()
    assert captured.value.status == 200
    return captured.value.json()


def inspect_fallbacks(page, result, checks):
    """Mixed-version and malformed data cannot retain the previous guidance."""
    for case in ("absent", "partial", "duplicate_evidence", "unknown_version"):
        payload = deepcopy(result)
        if case == "absent":
            payload.pop("sections")
        elif case == "partial":
            del payload["sections"]["caution"]
        elif case == "duplicate_evidence":
            payload["sections"]["evidence"][1] = payload["sections"]["evidence"][0]
        else:
            payload["sections"]["schema_version"] = 99
        # Prime with valid scenario data before each malformed response.
        page.evaluate("result => drawDaily(result, 'dday')", result)
        expect(page.locator("#daily-action")).to_be_visible()
        page.evaluate("result => drawDaily(result, 'dday')", payload)
        expect(page.locator("#daily-guidance")).to_be_hidden()
        expect(page.locator("#daily-evidence")).to_have_text("")
        for identifier in ("daily-action", "daily-caution", "day-relation", "daily-practice-qualifiers"):
            expect(page.locator("#" + identifier)).to_have_text("")
        expect(page.locator("#full-text")).to_have_text(result["text"])
        page.locator("#daily-details").evaluate("el => { el.open = true; }")
        expect(page.locator("#full-text")).to_be_visible()
        checks.append({"check": f"{case}_sections_uses_complete_text_and_clears_guidance", "passed": True})
    page.evaluate("result => drawDaily(result, 'dday')", result)
    expect(page.locator("#full-text")).to_have_text("")
    expect(page.locator("#daily-action")).to_have_text(result["sections"]["action"]["text"])


def inspect_scenario_layouts(page, result, sample, observations):
    """Measure the longer selected-situation captions at the same five widths."""
    card = page.locator("#daily-result")
    for width in (320, 360, 390, 412, 430):
        page.set_viewport_size({"width": width, "height": 844})
        for expanded in (False, True):
            page.locator("#daily-details").evaluate("(el, value) => {el.open = value}", expanded)
            card.evaluate("el => el.scrollIntoView({block: 'start'})")
            geometry = card.evaluate("""el => ({
              cardHeight: Math.round(el.getBoundingClientRect().height),
              pageOverflow: document.documentElement.scrollWidth > innerWidth,
              clipped: [...el.querySelectorAll('p')].some(p =>
                p.scrollHeight > p.clientHeight + 1 && ['hidden','clip'].includes(getComputedStyle(p).overflowY))
            })""")
            measured = {key: visibility(page.locator(f"#daily-{key}")) for key in ("action", "caution")}
            assert not geometry["pageOverflow"] and not geometry["clipped"], geometry
            if not expanded:
                assert geometry["cardHeight"] <= 844, (sample, result["scenario"], width, geometry)
                assert all(item["displayed"] and item["inViewport"] for item in measured.values()), measured
            elif width == 390:
                assert geometry["cardHeight"] <= 1050, (sample, result["scenario"], geometry)
            observations.append({"sample": sample, "scenario": result["scenario"], "date": result["date"],
                                 "viewportWidth": width, "expanded": expanded, "guidanceVisibility": measured,
                                 **geometry})
    page.set_viewport_size({"width": 390, "height": 844})


def find_wealth_date(page, today):
    # One twelve-day branch cycle covers every daily element. Use real API results
    # to select the content regression case, then render it through the form below.
    for offset in range(12):
        target = (today + timedelta(days=offset)).isoformat()
        result = page.evaluate("""async target => {
          const response = await fetch('/api/readings/date', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
            body: JSON.stringify({date: target, scenario: 'general'})
          });
          if (!response.ok) throw new Error(`Date selection failed: ${response.status}`);
          return response.json();
        }""", target)
        assert result["ok"] and result["computed"]
        if result["reading"]["relation"] == "wealth":
            return target, offset + 1
    raise AssertionError("No wealth relation found in the next twelve available dates")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sources = ["web/fortune_web/static/index.html", "web/fortune_web/static/app.js",
               "web/fortune_web/static/style.css", "web/fortune_web/service.py",
               "plugins/hermes_ext/fortune_oracle/daily_fortune_engine.py",
               "scripts/check_fortune_web_basic_reading_browser.py"]
    fingerprints = lambda: {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in sources}
    source_hashes = fingerprints()
    origin = urlsplit(args.url)
    assert origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    args.output.mkdir(parents=True, exist_ok=True)
    errors, external, observations, semantic, state_checks = [], [], [], [], []
    context_observations = []
    scenario_layouts = []
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
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/readings/today") as captured:
                page.locator("#save-button").click()
            today_result = captured.value.json()
            inspect_reading(page, today_result, "today", sample, semantic)
            card = page.locator("#daily-result")
            details = card.locator(".full-reading")
            for width in (320, 360, 390, 412, 430):
                page.set_viewport_size({"width": width, "height": 844})
                for expanded in (False, True):
                    details.evaluate("(el, open) => { el.open = open; }", expanded)
                    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                    card.evaluate("el => el.scrollIntoView({block: 'start'})")
                    layout = card.evaluate("""card => {
                      const r = card.getBoundingClientRect();
                      const full = card.querySelector('#daily-evidence');
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
                        paragraphs: [...full.querySelectorAll('p')].map(p => p.textContent.length),
                        clipped: [...card.querySelectorAll('p')].some(p =>
                          p.scrollHeight > p.clientHeight + 1 && ['hidden','clip'].includes(getComputedStyle(p).overflowY))
                      };
                    }""")
                    assert not layout["pageOverflow"], layout
                    assert not layout["textOutside"], layout
                    assert not layout["clipped"], layout
                    measured = {key: visibility(page.locator(f"#daily-{key}")) for key in ("action", "caution")}
                    if not expanded:
                        assert layout["cardHeight"] <= 844, layout
                        assert all(item["displayed"] and item["inViewport"] for item in measured.values()), measured
                    elif width == 390:
                        assert layout["cardHeight"] <= 1050, layout
                    layout["guidanceVisibility"] = measured
                    filename = f"{sample}-{width}-{'expanded' if expanded else 'collapsed'}.png"
                    card.screenshot(path=str(args.output / filename))
                    observations.append({"sample": sample, "expanded": expanded,
                                         "screenshot": filename, **layout})
            page.set_viewport_size({"width": 390, "height": 844})
            today = date.fromisoformat(today_result["date"])
            for view, offset in (("tomorrow", 1), ("today", 0)):
                with page.expect_response(lambda response: urlsplit(response.url).path == f"/api/readings/{view}") as captured:
                    page.locator(f'[data-view="{view}"]').click()
                result = captured.value.json()
                assert result["date"] == (today + timedelta(days=offset)).isoformat()
                inspect_reading(page, result, view, sample, semantic)

            page.locator('details[data-icon="日"]').evaluate("el => { el.open = true; }")
            # Editing a D-day form must not invalidate an unrelated visible today result.
            page.locator("#target-date").fill((today + timedelta(days=1)).isoformat())
            page.locator("#scenario").select_option("exam")
            expect(card).to_be_visible()
            expect(page.locator("#daily-action")).to_have_text(today_result["sections"]["action"]["text"])
            state_checks.append({"sample": sample, "check": "editing_date_and_scenario_preserves_today", "passed": True})
            page.locator("#scenario").select_option("general")
            for scenario, offset in (("general", 1), ("exam", 1), ("exam", 2), ("meeting", 2)):
                changed = page.locator("#scenario").input_value() != scenario or page.locator("#target-date").input_value() != (today + timedelta(days=offset)).isoformat()
                if page.locator("#scenario").input_value() != scenario:
                    page.locator("#scenario").select_option(scenario)
                if page.locator("#target-date").input_value() != (today + timedelta(days=offset)).isoformat():
                    page.locator("#target-date").fill((today + timedelta(days=offset)).isoformat())
                if changed:
                    expect(card).to_be_hidden()
                    expect(page.locator("#full-text")).to_have_text("")
                    expect(page.locator("#daily-action")).to_have_text("")
                    expect(page.locator("#daily-caution")).to_have_text("")
                    assert page.evaluate("shareSource === null")
                result = submit_dated(page)
                assert result["date"] == (today + timedelta(days=offset)).isoformat()
                assert result["scenario"] == scenario
                inspect_reading(page, result, "dday", sample, semantic)
                if scenario != "exam" or offset == 1:
                    inspect_scenario_layouts(page, result, sample, scenario_layouts)
                if sample == "synthetic-a" and scenario == "exam" and offset == 1:
                    card.screenshot(path=str(args.output / "synthetic-a-dday-exam-390-expanded.png"))
            state_checks.append({"sample": sample, "check": "submitted_date_and_scenario_replace_old_content", "passed": True})

            if sample == "synthetic-a":
                for edit in ("scenario", "date"):
                    held = []

                    def hold_response(route):
                        held.append((route, route.fetch()))

                    page.route("**/api/readings/date", hold_response)
                    page.locator("#date-submit").click()
                    expect(card).to_be_hidden()
                    expect(page.locator("#full-text")).to_have_text("")
                    deadline = time.monotonic() + 5
                    while not held and time.monotonic() < deadline:
                        page.wait_for_timeout(20)
                    assert held, "The dated request was not intercepted"
                    with page.expect_event("requestfailed", predicate=lambda request: urlsplit(request.url).path == "/api/readings/date"):
                        if edit == "scenario":
                            page.locator("#scenario").select_option("exam")
                        else:
                            page.locator("#target-date").fill((today + timedelta(days=3)).isoformat())
                    expect(page.locator("#loading")).to_be_hidden()
                    expect(page.locator("#date-submit")).to_be_enabled()
                    route, response = held.pop()
                    route.fulfill(response=response)
                    page.unroute("**/api/readings/date", hold_response)
                    # The cancelled response cannot restore either the old text or its share card.
                    expect(card).to_be_hidden()
                    expect(page.locator("#full-text")).to_have_text("")
                    assert page.evaluate("shareSource === null")
                    result = submit_dated(page)
                    assert result["date"] == page.locator("#target-date").input_value()
                    assert result["scenario"] == page.locator("#scenario").input_value()
                    inspect_reading(page, result, "dday", sample, semantic)
                    state_checks.append({"sample": sample, "check": f"editing_{edit}_cancels_late_dated_reply", "passed": True})
                target, inspected_dates = find_wealth_date(page, today)
                page.locator("#target-date").fill(target)
                page.locator("#scenario").select_option("meeting")
                result = submit_dated(page)
                assert result["reading"]["relation"] == "wealth"
                inspect_reading(page, result, "dday", sample, context_observations)
                context_observations[-1].update({
                    "case": "meeting_with_wealth_relation", "datesInspected": inspected_dates,
                    "baseFinancialCautionAbsent": "금전적 이익이나 손실" not in result["text"],
                })
                assert context_observations[-1]["baseFinancialCautionAbsent"]
                inspect_scenario_layouts(page, result, sample, scenario_layouts)
                card.screenshot(path=str(args.output / "synthetic-a-dday-meeting-wealth-390-expanded.png"))
                inspect_fallbacks(page, result, state_checks)
            page.locator("#delete-button").click()
            page.locator("#confirm-delete").click()
            expect(page.locator("#empty-state")).to_be_visible()
            expect(page.locator("#daily-action")).to_have_text("")
            expect(page.locator("#daily-caution")).to_have_text("")
        assert not errors and not external, {"errors": errors, "external": external}
        browser_version = browser.version
        browser.close()
    assert source_hashes == fingerprints(), "Source changed during browser measurements; rerun against one revision"
    result = {"source": "local Chromium mobile viewport emulation; synthetic adult profiles",
              "source_sha256": source_hashes,
              "browserVersion": browser_version, "physicalDeviceTested": False,
              "pdfTested": False, "pageErrors": errors, "externalRequests": external,
              "observations": observations, "semanticObservations": semantic,
              "stateChecks": state_checks, "contextObservations": context_observations,
              "scenarioLayoutObservations": scenario_layouts}
    (args.output / "basic-reading-browser.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
