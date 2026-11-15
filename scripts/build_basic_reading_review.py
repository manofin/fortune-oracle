#!/usr/bin/env python3
"""Build reproducible, synthetic before/after reading samples for human review.

Run from a checkout containing the public baseline commit and Node dependencies.
No customer data, store, model provider, or network is used.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BASE = "2f10b1ee25127f8930082b5b8afd9e34b7603eac"
ENGINE = "plugins/hermes_ext/fortune_oracle/daily_fortune_engine.py"
DDAY_BASE = "05460a07be22635f70cc91746cd6882f31a43cbc"
UI_BASE = "6b892e5b50642c3f027f0fa3a0cc1d621a41ff9a"
SERVICE = "web/fortune_web/service.py"
DAILY_READING = "plugins/hermes_ext/fortune_oracle/daily_reading.py"
DDAY_NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
# Invented adult inputs, unrelated to customers or the operator.
PROFILES = [
    {"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male", "timezone": "Asia/Seoul"},
    {"birth_date": "1988-03-02", "birth_time_known": False, "gender": "unknown", "timezone": "Asia/Seoul"},
]
TARGETS = [date(2026, 10, 3), date(2026, 10, 4)]


def output_text(reading):
    return "\n".join([*reading["lines"], reading["disclaimer"]])


def public_module(commit, path, module_name):
    source = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        text=True, capture_output=True, check=True,
    ).stdout
    module = ModuleType(module_name)
    exec(compile(source, f"public-baseline:{path}", "exec"), module.__dict__)
    return module


def build(output):
    sys.path.insert(0, str(ROOT / "plugins"))
    from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as current

    # Fixed public baseline: never read an operator's private Git history.
    baseline = public_module(BASE, ENGINE, "hermes_ext.fortune_oracle._review_baseline")
    samples, comparisons = [], 0
    for index, (profile, target) in enumerate(zip(PROFILES, TARGETS), 1):
        chart = bazi_bridge.calculate_bazi_from_profile(profile)
        if not chart.ok:
            raise RuntimeError(f"Synthetic sample {index}: chart unavailable")
        # Check every non-prose field, including all score components, over a month.
        for offset in range(30):
            day = target + timedelta(days=offset)
            for aspect in current.ASPECT_TITLE:
                before = baseline._daily_from_chart(profile, chart, day, aspect)
                after = current._daily_from_chart(profile, chart, day, aspect)
                facts = lambda value: {k: v for k, v in value.items() if k not in {"lines", "disclaimer", "sections"}}
                if facts(before) != facts(after):
                    raise AssertionError(f"Non-prose fields changed: sample {index}, {day}, {aspect}")
                comparisons += 1
        before = baseline._daily_from_chart(profile, chart, target, "종합")
        after = current._daily_from_chart(profile, chart, target, "종합")
        samples.append({"id": index, "synthetic_input": profile, "date": target.isoformat(),
                        "before": before, "after": after,
                        "channel_text": current.render_daily_channel_text(after)})

    # Controlled charts test all relation themes; they are not real birth charts.
    matrix = []
    for stem in "甲丙戊庚壬":
        chart = SimpleNamespace(ok=True, eight_char={"year": "庚午", "month": "戊寅", "day": stem + "子"},
                                elements={"목": 3, "화": 2, "토": 1, "금": 0, "수": 2},
                                dayun=None, time_basis={})
        reading = current._daily_from_chart(PROFILES[0], chart, TARGETS[0], "종합")
        matrix.append({"stem": stem, "relation": reading["relation"], "score": reading["score"],
                       **{key: f'{reading["sections"][key]["title"]}: {reading["sections"][key]["text"]}'
                          for key in ("theme", "action", "caution")}})

    output.mkdir(parents=True, exist_ok=True)
    data = {"baseline": BASE, "synthetic_only": True, "non_prose_comparisons": comparisons,
            "display_fields_excluded": ["lines", "disclaimer", "sections"],
            "samples": samples, "relation_matrix": matrix}
    (output / "basic-reading-samples.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 기본 풀이 전후 샘플", "", "이 자료는 전부 가상 성인 입력입니다. 고민·외부 모델·고객 자료를 사용하지 않았습니다.", "",
             f"기준: 공개 `main` 커밋 `{BASE}`. 변경 후는 이 문서와 함께 검토하는 변경분입니다.", "",
             "재생성: `python scripts/build_basic_reading_review.py` (기본 Node 의존성 필요).",
             f"자동 비교: 가상 프로필 2개 × 30일 × 5영역 = **{comparisons}건**, 표시 필드(`lines`, `disclaimer`, `sections`) 외 모든 반환 필드 동일.", "",
             "점수 유지 확인은 문장의 효용이나 점술의 예측 타당성을 검증한 결과가 아닙니다.", ""]
    for sample in samples:
        lines.extend([f"## 가상 사례 {sample['id']}", "", f"입력: `{json.dumps(sample['synthetic_input'], ensure_ascii=False)}`",
                      f"풀이 날짜: {sample['date']}", ""])
        for key, label in (("before", "변경 전"), ("after", "변경 후")):
            lines.extend([f"### {label}", "", "```text", output_text(sample[key]), "```", ""])
        lines.extend(["### 메시지·직접 음성용 요약 (보완본)", "",
                      "웹의 상세 풀이와 별도 표시입니다. Telegram과 시간대를 지정한 음성 경로에는 풀이 시간대도 표시합니다.", "",
                      "```text", sample["channel_text"], "```", ""])
    lines.extend(["## 관계별 문구 확인용 합성 차트", "", "아래 차트는 분기를 확인하기 위한 가공 입력이며 실제 출생 계산 사례가 아닙니다.", "",
                  "| 관계 | 이날의 해석 | 해볼 일 | 주의할 점 |", "| --- | --- | --- | --- |"])
    lines.extend(f"| {r['relation']} | {r['theme']} | {r['action']} | {r['caution']} |" for r in matrix)
    lines.extend(["", "## 가림 평가 운영자용 대응표", "", "평가자에게는 아래 대응표와 전후 문서를 주지 않고 `basic-reading-blind.md`만 전달합니다.",
                  "첫 사례는 변경 후→전, 둘째는 전→후로 순서를 상쇄했습니다. 소규모 준비 자료이며 무작위 사용자 실험을 실행한 결과가 아닙니다.", "",
                  "| 평가 표기 | 대응 |", "| --- | --- |", "| 1-X | 사례 1 변경 후 |", "| 1-Y | 사례 1 변경 전 |",
                  "| 2-X | 사례 2 변경 전 |", "| 2-Y | 사례 2 변경 후 |", ""])
    (output / "basic-reading-samples.md").write_text("\n".join(lines))

    blind = ["# 기본 풀이 읽기 평가용", "", "가상 사례별 두 글을 읽고 각각 평가합니다. 버전의 출처나 변경 순서는 공개하지 않습니다.",
             "개인적으로 느껴지는 정도와 근거의 납득도는 별개로 점수를 매깁니다. 1=전혀 그렇지 않음, 5=매우 그러함.",
             "실제 자신에 대한 적중도를 묻는 평가가 아닙니다. 근거가 납득된다는 응답도 예측의 타당성을 입증하지 않습니다. 서로 상의하기 전에 응답을 기록합니다.", "",
             "각 글: 고민 입력 없이 읽을 가치가 있음 __/5 · 이해하기 쉬움 __/5 · 행동의 실행 가능성 __/5 · 개인적으로 느껴짐 __/5 · 근거 납득도 __/5",
             "해볼 일 하나를 본인 말로 적어주세요: ____________________",
             "단정으로 느껴진 문장 / 부담스러운 행동 / 실제로 도움이 된 문장: ____________________", "",
             "각 쌍: 더 유용한 글 X / Y / 차이 없음 / 판단 어려움 · 이유: ____________________", ""]
    for sample, order in zip(samples, [("after", "before"), ("before", "after")]):
        for label, key in zip("XY", order):
            blind.extend([f"## {sample['id']}-{label}", "", "```text", output_text(sample[key]), "```", ""])
            blind.extend(["읽을 가치 __/5 · 이해하기 쉬움 __/5 · 행동 실행 가능성 __/5 · 개인적으로 느껴짐 __/5 · 근거 납득도 __/5",
                          "해볼 일 하나를 본인 말로: ____________________",
                          "도움이 된 문장 / 부담스럽거나 단정적인 문장: ____________________", ""])
    (output / "basic-reading-blind.md").write_text("\n".join(blind))
    print(f"Wrote 2 synthetic comparisons and 5 relation themes; {comparisons} non-prose comparisons passed.")


def build_dday(output):
    """Compare the public D-day baseline and this checkout using real calculations."""
    sys.path[:0] = [str(ROOT / "plugins"), str(ROOT / "web")]
    from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as current
    from fortune_web import service

    baseline_engine = public_module(DDAY_BASE, ENGINE, "hermes_ext.fortune_oracle._dday_baseline")
    baseline_service = public_module(DDAY_BASE, SERVICE, "fortune_web._dday_baseline")
    baseline_service.build_personalized_daily = baseline_engine.build_personalized_daily
    baseline_service.daily_display_lines = baseline_engine.daily_display_lines
    profile = dict(PROFILES[0])
    chart = bazi_bridge.calculate_bazi_from_profile(profile)
    if not chart.ok:
        raise RuntimeError("D-day synthetic chart unavailable")
    # The date is chosen by a fixed rule, never by the generator's wall clock.
    target = next(
        DDAY_NOW.date() + timedelta(days=offset)
        for offset in range(1, 31)
        if current._daily_from_chart(profile, chart, DDAY_NOW.date() + timedelta(days=offset), "종합")["relation"] == "wealth"
    )
    scenarios = []
    for scenario in ("general", "exam", "meeting"):
        request = {"date": target.isoformat(), "scenario": scenario}
        before = baseline_service.dated_reading(profile, request, now=DDAY_NOW)
        after = service.dated_reading(profile, request, now=DDAY_NOW)
        assert before["ok"] and after["ok"]
        assert before["reading"] == {key: value for key, value in after["reading"].items() if key != "sections"}, "D-day calculation or legacy reading changed"
        assert before["reflection"] == after["reflection"]
        paragraphs = {}
        for version, payload in (("before", before), ("after", after)):
            actions = [line for line in payload["text"].splitlines() if line.startswith("해볼 일")]
            cautions = [line for line in payload["text"].splitlines() if line.startswith("주의할 점")]
            assert len(actions) == len(cautions) == 1, "Expected one action and one caution"
            paragraphs[version] = {"action": actions[0], "caution": cautions[0]}
        if scenario == "general":
            assert before["text"] == after["text"], "General D-day display changed"
        else:
            assert all("선택한 상황" in paragraph for paragraph in paragraphs["after"].values())
        scenarios.append({"scenario": scenario, "request": request,
                          "before": before, "after": after, "paragraphs": paragraphs,
                          "legacy_reading_unchanged": True,
                          "action_paragraph_count": 1, "caution_paragraph_count": 1})
    assert all(item["after"]["reading"] == scenarios[0]["after"]["reading"] for item in scenarios)
    meeting = scenarios[-1]["paragraphs"]
    assert "금전적 이익이나 손실" in meeting["before"]["caution"]
    assert "금전적 이익이나 손실" not in meeting["after"]["caution"]
    data = {
        "baseline": DDAY_BASE, "synthetic_only": True,
        "after_source": "Current branch content accompanying this report; not a deployed revision",
        "after_code_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                              for path in (ENGINE, SERVICE)},
        "synthetic_input": profile, "fixed_now": DDAY_NOW.isoformat(),
        "date_selection": "First wealth relation in days 1 through 30 after fixed_now",
        "selected_date": target.isoformat(), "relation": "wealth",
        "legacy_reading_unchanged_before_after_and_across_scenarios": True,
        "new_display_fields_excluded": ["sections"],
        "scenarios": scenarios,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "basic-reading-dday.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# D-day 상황별 행동·주의 문구 전후 샘플", "",
        "이 자료는 고정된 가상 성인 프로필의 실제 Node 계산 결과입니다. 고객 자료·고민 원문·외부 모델을 사용하지 않았습니다.", "",
        f"변경 전: 공개 커밋 `{DDAY_BASE}`의 엔진과 웹 service를 함께 실행했습니다.",
        "변경 후: 이 문서와 함께 검토하는 현재 브랜치의 보완본입니다. 배포 상태를 뜻하지 않습니다.",
        "전체 응답과 변경 후 코드 파일의 SHA-256은 [JSON](basic-reading-dday.json)에 있습니다.", "",
        "재생성: 해당 기준 커밋을 포함한 checkout에서 `python scripts/build_basic_reading_review.py`를 실행합니다. 기본 Node 의존성이 필요합니다.", "",
        f"가상 입력: `{json.dumps(profile, ensure_ascii=False)}`",
        f"고정 시각: `{DDAY_NOW.isoformat()}`. 다음 30일 중 첫 `wealth` 관계 날짜: **{target.isoformat()}**.",
        "`wealth`는 이 엔진의 오행 관계 분류입니다. 실제 재산·금전 상황을 확인한 값이 아닙니다.", "",
        "자동 확인: 신규 표시 필드 `sections`를 제외한 기존 `reading` 필드는 세 상황 모두 전후 같으며, 상황 사이에서도 동일합니다. 점수뿐 아니라 계산 근거·원래 상세 문구도 보존됩니다.",
        "화면용 본문에는 행동 1개·주의 1개만 있습니다. 시험·만남의 두 문단에는 선택한 상황에 따른 제안이라는 출처 표시를 붙입니다.",
        "general 본문은 그대로 유지됩니다. 아래는 비교에 필요한 두 문단만 발췌했으며 전체 본문은 JSON에 있습니다.", "",
    ]
    for item in scenarios:
        lines.extend([f"## {item['scenario']}", ""])
        for version, label in (("before", "변경 전"), ("after", "변경 후")):
            lines.extend([f"### {label}", "", "```text", item["paragraphs"][version]["action"],
                          item["paragraphs"][version]["caution"], "```", ""])
    lines.extend([
        "## 검토할 점", "",
        "만남 사례는 행동만 만남으로 바뀌고 주의에는 금전 예고 문구가 남던 상태에서, 두 문단 모두 만남에 관한 제안으로 바뀝니다.",
        "시험 사례도 행동과 주의의 주제를 함께 맞춥니다. 상황 선택은 계산값이나 성공 확률을 바꾸지 않습니다.",
        "이는 문구 연결과 반환값 보존의 자동 확인입니다. 실제 사용자 효용·입력 부담·개인적으로 느껴지는 정도·판매 가능성을 평가한 결과는 아닙니다.",
        "이 생성기는 화면·PDF·실제 기기·TTS·운영 전송을 검사하지 않습니다.", "",
    ])
    (output / "basic-reading-dday.md").write_text("\n".join(lines))
    print(f"Wrote 3 synthetic D-day comparisons for {target}; legacy readings unchanged (sections added).")


def build_ui_contract(output):
    """Compare every existing field and text with the fixed pre-UI revision."""
    from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as current, localization
    from fortune_web import service

    baseline = public_module(UI_BASE, ENGINE, "hermes_ext.fortune_oracle._ui_engine_baseline")
    baseline_daily = public_module(UI_BASE, DAILY_READING, "hermes_ext.fortune_oracle._ui_daily_baseline")
    baseline_daily.build_personalized_daily = baseline.build_personalized_daily
    baseline_daily.build_personalized_series = baseline.build_personalized_series
    baseline_daily.render_daily_channel_text = baseline.render_daily_channel_text
    baseline_service = public_module(UI_BASE, SERVICE, "fortune_web._ui_service_baseline")
    baseline_service.prepare_daily_reading = baseline_daily.prepare_daily_reading
    baseline_service.build_personalized_daily = baseline.build_personalized_daily
    baseline_service.daily_display_lines = baseline.daily_display_lines

    def legacy_payload(payload):
        result = {key: value for key, value in payload.items() if key != "sections"}
        if "reading" in result:
            result["reading"] = {key: value for key, value in result["reading"].items() if key != "sections"}
        if "readings" in result:
            result["readings"] = [{key: value for key, value in reading.items() if key != "sections"}
                                  for reading in result["readings"]]
        return result

    engine_cases, channel_cases, payload_cases = 0, 0, []
    for index, (profile, target) in enumerate(zip(PROFILES, TARGETS), 1):
        chart = bazi_bridge.calculate_bazi_from_profile(profile)
        assert chart.ok
        for offset in range(30):
            for aspect in current.ASPECT_TITLE:
                day = target + timedelta(days=offset)
                before = baseline._daily_from_chart(profile, chart, day, aspect)
                after = current._daily_from_chart(profile, chart, day, aspect)
                assert before == legacy_payload(after), (index, day, aspect)
                engine_cases += 1
                for language in ("ko", "en"):
                    old = localization.localize_daily(before, language)
                    new = localization.localize_daily(after, language)
                    assert baseline.render_daily_channel_text(old, reading_timezone="Asia/Seoul") == current.render_daily_channel_text(new, reading_timezone="Asia/Seoul")
                    channel_cases += 1
        for language in ("ko", "en"):
            localized = dict(profile, language=language)
            for view in ("today", "tomorrow", "week"):
                before = baseline_service.daily(localized, view, now=DDAY_NOW)
                after = service.daily(localized, view, now=DDAY_NOW)
                assert before["ok"] and after["ok"]
                assert before == legacy_payload(after), (index, language, view)
                payload_cases.append({"sample": index, "language": language, "view": view})
        for scenario in ("general", "exam", "meeting"):
            request = {"date": "2026-11-24", "scenario": scenario}
            before = baseline_service.dated_reading(profile, request, now=DDAY_NOW)
            after = service.dated_reading(profile, request, now=DDAY_NOW)
            assert before["ok"] and after["ok"]
            assert before == legacy_payload(after), (index, scenario)
            payload_cases.append({"sample": index, "language": "ko", "view": "dday", "scenario": scenario})
    data = {"baseline": UI_BASE, "synthetic_only": True,
            "new_display_field_excluded": "sections", "includes_lines_disclaimer_and_text": True,
            "engine_comparisons": engine_cases, "channel_text_comparisons": channel_cases,
            "service_payload_comparisons": payload_cases,
            "after_code_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                  for path in (ENGINE, SERVICE, DAILY_READING)}}
    (output / "basic-reading-ui-compatibility.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"UI contract: {engine_cases} complete legacy readings, {channel_cases} channel texts, {len(payload_cases)} API payloads unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reviews")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="fortune-reading-samples-") as temporary:
        for key in list(os.environ):
            if key.startswith(("FORTUNE_", "HERMES_SESSION_", "OPENAI_")) or any(
                word in key for word in ("TOKEN", "API_KEY", "SECRET")
            ):
                os.environ.pop(key)
        os.environ.update(HERMES_HOME=temporary, FORTUNE_ORACLE_STORE=str(Path(temporary) / "store.json"),
                          FORTUNE_DEEP_ANALYSIS="0", PYTHONDONTWRITEBYTECODE="1")
        build(args.output)
        build_dday(args.output)
        build_ui_contract(args.output)


if __name__ == "__main__":
    main()
