"""Basic reading presentation; all charts and profiles here are synthetic."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_ext.fortune_oracle import daily_fortune_engine as engine
from hermes_ext.fortune_oracle.daily_reading import prepare_daily_reading

PROFILE = {"birth_date": "1990-01-01"}
TARGET = date(2026, 10, 3)


def chart(stem="甲", elements=None):
    return SimpleNamespace(ok=True, eight_char={"year": "庚午", "month": "戊寅", "day": stem + "子"},
                           elements=elements or {"목": 3, "화": 2, "토": 1, "금": 0, "수": 2},
                           dayun=None, time_basis={})


@pytest.mark.parametrize("stem", list("甲丙戊庚壬"))
def test_basic_reading_links_calculation_to_action_without_prediction(stem):
    reading = engine._daily_from_chart(PROFILE, chart(stem), TARGET, "종합")
    text = "\n".join(reading["lines"] + [reading["disclaimer"]])
    assert f"일간(나를 나타내는 기준) {engine._stem_element(stem)}" in text
    assert f"일진 {reading['day_pillar']}의 지지(날짜의 아래 글자) {reading['day_element']}" in text
    assert "목 3 · 화 2 · 토 1 · 금 0 · 수 2" in text
    assert "이 점수 규칙에서 선택한 오행은 금·토" in text
    assert "해볼 일:" in text
    assert "주의할 점:" in text
    assert "경험적 해석" in text and "예측 확률" in text
    assert "실제 성격·상황이나 미래를 확인한 결과가 아닙니다" in text
    assert "대운 보정 미적용" in text
    assert "좋은 날입니다" not in text and "잘 풀리는 날입니다" not in text
    assert PROFILE["birth_date"] not in text


@pytest.mark.parametrize("stem,relation,meaning,action,score", [
    ("甲", "wealth", "내 오행이 날짜의 오행을 제어", "금액이나 날짜", 66.2),
    ("丙", "output", "내 오행이 날짜의 오행을 돕는", "전할 말", 75.2),
    ("戊", "same", "같은 오행", "기준 하나", 78.2),
    ("庚", "input", "날짜의 오행이 내 오행을 돕는", "자료 하나", 73.2),
    ("壬", "pressure", "날짜의 오행이 내 오행을 제어", "언제까지 어디까지", 63.2),
])
def test_relation_meaning_and_practice_follow_actual_calculation(stem, relation, meaning, action, score):
    reading = engine._daily_from_chart(PROFILE, chart(stem), TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert reading["relation"] == relation
    assert reading["score"] == score
    assert meaning in text and action in text
    lines = reading["lines"]
    headings = ("이날의 해석:", "해볼 일:", "주의할 점:", "해석 근거:")
    positions = [next(i for i, line in enumerate(lines) if line.startswith(heading))
                 for heading in headings]
    assert positions == sorted(set(positions))
    assert action in lines[positions[1]] and meaning in lines[positions[3]]
    assert "주의할 점:" not in lines[positions[1]]
    assert "있다면" in lines[positions[1]]
    assert action not in lines[positions[0]]
    assert "보세요" not in lines[positions[0]] and "하세요" not in lines[positions[0]]
    assert reading["disclaimer"].startswith("해석의 한계:")


@pytest.mark.parametrize("elements,label,match", [
    ({"목": 3, "화": 2, "토": 1, "금": 0, "수": 2}, "금·토", "포함되어 가점"),
    ({"목": 0, "화": 1, "토": 3, "금": 2, "수": 2}, "목·화", "포함되지 않아 감점"),
    ({"목": 1, "화": 1, "토": 1, "금": 1, "수": 1}, "목·화", "포함되지 않아 감점"),
    ({"목": 3, "화": 2, "토": 1}, "금·수", "포함되지 않아 감점"),
])
def test_distribution_explanation_uses_actual_counts_and_canonical_ties(elements, label, match):
    reading = engine._daily_from_chart(PROFILE, chart(elements=elements), TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert f"이 점수 규칙에서 선택한 오행은 {label}" in text
    assert "같은 개수일 때는 목·화·토·금·수 순서를 따릅니다" in text
    assert "보완 대상" not in text and "적게 나타난 두 오행" not in text
    assert match in text
    assert "정밀한 용신 분석은 아닙니다" in text
    assert set(label.split("·")) == set(reading["favorable_elements"])


def test_daily_web_payload_preserves_explanation_and_failure_boundary():
    now = datetime(2026, 10, 3, 3, tzinfo=timezone.utc)
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = prepare_daily_reading(PROFILE, now=now)
        again = prepare_daily_reading(PROFILE, now=now)
    assert result == again
    assert result["computed"] is True
    assert result["reading"]["score"] == 66.2
    for line in result["reading"]["lines"]:
        assert line in result["text"]
    assert result["reading"]["disclaimer"] in result["text"]
    assert "해볼 일:" in result["text"]
    failure = prepare_daily_reading({}, now=now)
    assert failure["computed"] is False
    assert "해볼 일:" not in failure["text"]


def test_unavailable_time_does_not_gain_invented_cycle_or_lose_uncertainty():
    computed = chart()
    computed.time_basis = {"solar_terms": "civil_day_interval_confirmed"}
    reading = engine._daily_from_chart(PROFILE, computed, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "시주와 대운은 제외합니다" in text
    assert "대운 보정 미적용" in text
    assert reading["dayun_adjustment"] == 0


@pytest.mark.parametrize("dayun", [None, {}, {"cycles": []}, {"cycles": [
    {"pillar": "戊寅", "start_year": 2000, "end_year": 2009},
]}])
def test_missing_cycle_explanation_does_not_invent_an_input_failure(dayun):
    computed = chart()
    computed.dayun = dayun
    reading = engine._daily_from_chart(PROFILE, computed, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "계산 결과에서 이 날짜에 적용할 대운 구간을 확인하지 못했습니다" in text
    assert "필요한 입력" not in text
    assert reading["dayun_adjustment"] == 0
    assert reading["dayun_pillar"] == ""


def test_available_cycle_retains_its_interval_and_score_adjustment():
    computed = chart()
    computed.dayun = {"cycles": [
        {"pillar": "戊寅", "start_year": 2020, "end_year": 2029},
    ]}
    reading = engine._daily_from_chart(PROFILE, computed, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "절기 기반 대운 戊寅(토) · 연도 구간 2020–2029" in text
    assert "해석 보정 +1점" in text
    assert "대운 보정 미적용" not in text
    assert reading["dayun_adjustment"] == 1
    assert reading["score"] == 67.2


def test_date_changes_select_distinct_relation_themes_and_actions():
    readings = [engine._daily_from_chart(PROFILE, chart(), TARGET + timedelta(days=i), "종합")
                for i in range(12)]
    assert len({reading["relation"] for reading in readings}) == 5
    for heading in ("이날의 해석:", "해볼 일:"):
        paragraphs = {next(line for line in reading["lines"] if line.startswith(heading))
                      for reading in readings}
        assert len(paragraphs) == 5


def test_tomorrow_payload_uses_the_target_date_without_calling_it_today():
    now = datetime(2026, 10, 3, 3, tzinfo=timezone.utc)
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        today = prepare_daily_reading(PROFILE, now=now)
        tomorrow = prepare_daily_reading(PROFILE, day="tomorrow", now=now)
    assert today["date"] == "2026-10-03"
    assert tomorrow["date"] == "2026-10-04"
    assert tomorrow["reading"]["day_pillar"] == "신해"
    assert tomorrow["reading"]["relation"] == "input"
    assert tomorrow["reading"]["score"] == 59.2
    assert today["reading"]["relation"] != tomorrow["reading"]["relation"]
    assert "오늘" not in tomorrow["text"]
    assert "이날의 해석:" in tomorrow["text"]
    assert "해당 날짜의 오행(수)" in tomorrow["text"]


@pytest.mark.parametrize("selected_date,pillar", [
    (date(2026, 10, 4), "신해"),
    (date(2026, 10, 5), "임자"),
])
def test_explicit_date_reading_keeps_date_and_language_consistent(selected_date, pillar):
    reading = engine._daily_from_chart(PROFILE, chart(), selected_date, "종합")
    text = "\n".join(reading["lines"] + [reading["disclaimer"]])
    assert reading["date"] == selected_date.isoformat()
    assert reading["day_pillar"] == pillar
    assert selected_date.isoformat() in text and pillar in text
    assert "오늘" not in text
