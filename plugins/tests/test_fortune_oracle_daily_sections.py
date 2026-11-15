"""Structured Korean display contracts; existing text remains a stable fallback."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_ext.fortune_oracle import daily_fortune_engine as engine
from hermes_ext.fortune_oracle.localization import localize_daily

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "web"))
from fortune_web import service

PROFILE = {"birth_date": "1990-01-01"}
TARGET = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)

# Frozen text from the pre-sections implementation (6b892e5), synthetic chart.
LEGACY_LINES = [
    "종합 운세 · 66점 — 순풍",
    "이날의 해석: 쓸 수 있는 자원과 맡을 책임을 살피는 주제로 읽습니다.",
    "해볼 일: 지출이나 약속을 앞두고 있다면 조건 하나를 확인해 보세요.",
    "주의할 점: 금전적 이익이나 손실을 예고하는 뜻은 아니니 중요한 결정은 실제 정보로 판단하세요.",
    "해석 근거: 일간(나를 나타내는 기준) 목 · 일진 경술의 지지(날짜의 아래 글자) 토. "
    "내 오행이 날짜의 오행을 제어하는 관계이므로, 자원과 책임을 점검하는 주제로 읽습니다.",
    "점수 근거: 계산된 오행 수는 목 3 · 화 2 · 토 1 · 금 0 · 수 2입니다. 개수가 적은 순서로 두 오행을 선택하고, "
    "같은 개수일 때는 목·화·토·금·수 순서를 따릅니다.",
    "이 점수 규칙에서 선택한 오행은 금·토입니다. 해당 날짜의 오행(토)이 포함되어 가점됩니다. 정밀한 용신 분석은 아닙니다.",
    "2026-10-03의 키워드는 안정 · 묵묵함 · 시작입니다.",
    "대운 보정 미적용: 계산 결과에서 이 날짜에 적용할 대운 구간을 확인하지 못했습니다.",
]
LEGACY_DISCLAIMER = (
    "해석의 한계: 점수와 조언은 경험적 해석이며 예측 확률이 아닙니다. 실제 성격·상황이나 미래를 확인한 결과가 아닙니다. "
    "이 운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
)


def chart(stem="甲", *, basis=None, dayun=None):
    return SimpleNamespace(
        ok=True, eight_char={"year": "庚午", "month": "戊寅", "day": stem + "子"},
        elements={"목": 3, "화": 2, "토": 1, "금": 0, "수": 2},
        dayun=dayun, time_basis=basis or {},
    )


def test_sections_do_not_change_legacy_lines_disclaimer_or_web_text():
    reading = engine._daily_from_chart(PROFILE, chart(), TARGET, "종합")
    assert reading["lines"] == LEGACY_LINES
    assert reading["disclaimer"] == LEGACY_DISCLAIMER
    assert reading["score"] == 66.2
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = service.daily(PROFILE, "today", now=NOW)
    assert result["text"] == "\n".join([
        "계산된 사주·일진을 바탕으로 한 해석입니다.", "2026-10-03 · Asia/Seoul",
        *LEGACY_LINES, LEGACY_DISCLAIMER,
    ])
    assert result["sections"] == result["reading"]["sections"]
    assert result["sections"] is not result["reading"]["sections"]


@pytest.mark.parametrize("stem", list("甲丙戊庚壬"))
def test_sections_schema_preserves_each_content_body_once(stem):
    reading = engine._daily_from_chart(PROFILE, chart(stem), TARGET, "종합")
    sections = reading["sections"]
    assert set(sections) == {"schema_version", "theme", "action", "caution", "evidence"}
    assert sections["schema_version"] == 1
    for key, title in (("theme", "이날의 해석"), ("action", "해볼 일"), ("caution", "주의할 점")):
        assert set(sections[key]) == {"title", "text", "qualifier"}
        assert sections[key]["title"] == title and sections[key]["qualifier"] == ""
        assert f"{title}: {sections[key]['text']}" in reading["lines"]
    evidence = {item["id"]: item for item in sections["evidence"]}
    assert set(evidence) == {"relation", "score", "cycle", "limitations"}
    for item in evidence.values():
        assert set(item) == {"id", "title", "paragraphs"}
        assert all(isinstance(text, str) and text for text in item["paragraphs"])
        assert all(not text.startswith(item["title"] + ":") for text in item["paragraphs"])
    bodies = [paragraph for item in evidence.values() for paragraph in item["paragraphs"]]
    assert len(bodies) == len(set(bodies))
    assert reading["lines"][0] in evidence["score"]["paragraphs"]
    keyword_line = f"{reading['date']}의 키워드는 {' · '.join(reading['keywords'])}입니다."
    assert bodies.count(keyword_line) == 1
    assert f"해석의 한계: {evidence['limitations']['paragraphs'][0]}" == reading["disclaimer"]
    assert json.loads(json.dumps(sections, ensure_ascii=False)) == sections


@pytest.mark.parametrize("basis,expected", [
    ({"solar_terms": "birth_instant_utc_plus_8"}, "진태양시 보정은 적용하지 않았습니다"),
    ({"solar_terms": "civil_day_interval_confirmed"}, "시주와 대운은 제외합니다"),
    ({"solar_terms": "unresolved"}, "절기 경계의 년·월주는 불확실합니다"),
])
def test_time_evidence_keeps_the_complete_uncertainty_notice(basis, expected):
    reading = engine._daily_from_chart(PROFILE, chart(basis=basis), TARGET, "종합")
    time = next(item for item in reading["sections"]["evidence"] if item["id"] == "time")
    assert expected in "\n".join(time["paragraphs"])
    assert all(paragraph in reading["lines"] for paragraph in time["paragraphs"])


def test_cycle_evidence_preserves_available_cycle_and_adjustment():
    dayun = {"cycles": [{"pillar": "戊寅", "start_year": 2020, "end_year": 2029}]}
    reading = engine._daily_from_chart(PROFILE, chart(dayun=dayun), TARGET, "종합")
    cycle = next(item for item in reading["sections"]["evidence"] if item["id"] == "cycle")
    assert cycle["paragraphs"] == ["절기 기반 대운 戊寅(토) · 연도 구간 2020–2029 · 해석 보정 +1점 (예측 확률이 아님)."]
    assert cycle["paragraphs"][0] in reading["lines"]


def test_display_sections_are_deep_copies_even_without_scenario_overrides():
    reading = engine._daily_from_chart(PROFILE, chart(), TARGET, "종합")
    original = deepcopy(reading)
    display = engine.daily_display_sections(reading)
    display["action"]["text"] = "display edit"
    display["evidence"][0]["paragraphs"].append("display-only paragraph")
    assert reading == original


@pytest.mark.parametrize("scenario", ["general", "exam", "meeting"])
def test_dated_display_sections_match_text_and_leave_raw_reading_unchanged(scenario):
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        daily = service.daily(PROFILE, "today", now=NOW)
        dated = service.dated_reading(PROFILE, {"date": TARGET.isoformat(), "scenario": scenario}, now=NOW)
    assert dated["reading"] == daily["reading"]
    assert dated["reading"]["lines"] == LEGACY_LINES
    display = dated["sections"]
    assert display["theme"] == dated["reading"]["sections"]["theme"]
    assert display["evidence"] == dated["reading"]["sections"]["evidence"]
    for key in ("action", "caution"):
        section = display[key]
        qualifier = f" ({section['qualifier']})" if section["qualifier"] else ""
        expected = f"{section['title']}{qualifier}: {section['text']}"
        assert dated["text"].count(expected) == 1
    if scenario == "general":
        assert display == dated["reading"]["sections"]
        assert dated["text"] == daily["text"]
    else:
        assert display["action"]["text"] == service.SCENARIO_PRACTICES[scenario][0]
        assert display["caution"]["text"] == service.SCENARIO_PRACTICES[scenario][1]
        assert display["action"]["qualifier"] == "선택한 상황에 맞춘 제안 · 별도 점수·성공 확률 아님"
        assert display["caution"]["qualifier"] == "선택한 상황에 맞춘 제안"
        assert dated["reading"]["sections"]["action"]["qualifier"] == ""
        assert dated["reading"]["sections"]["caution"]["qualifier"] == ""


def test_english_retains_exact_existing_copy_and_omits_korean_sections():
    korean = engine._daily_from_chart(PROFILE, chart(), TARGET, "종합")
    original = deepcopy(korean)
    english = localize_daily(korean, "en")
    assert "sections" not in english and korean == original
    assert english["lines"] == [
        "Overall · 66/100 — Supportive",
        "Day pillar Geng-Xu (Earth) · A useful theme is reviewing resources and responsibilities.",
        "Reflection keywords: stability · steadiness · beginnings.",
        "Ten-year cycle adjustment omitted: required inputs or an applicable cycle are unavailable.",
        "This score is an interpretive index, not a predicted probability.",
    ]
    assert english["disclaimer"] == "For entertainment and self-reflection. Not medical, investment or legal advice."
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = service.daily({**PROFILE, "language": "en"}, "today", now=NOW)
    assert "sections" not in result and "sections" not in result["reading"]


def test_failed_and_weekly_readings_have_no_top_level_sections():
    assert "sections" not in service.daily({}, "today", now=NOW)
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        week = service.daily(PROFILE, "week", now=NOW)
    assert week["computed"] and "sections" not in week
