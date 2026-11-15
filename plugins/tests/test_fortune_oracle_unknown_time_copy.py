"""Clock notices describe actual calculated pillars, never an assumed hour."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest

from hermes_ext.fortune_oracle import bazi_bridge as bridge, daily_fortune_engine as engine
from hermes_ext.fortune_oracle.localization import localize_daily

TARGET = date(2026, 10, 4)
PROFILES = {
    "unknown": {"birth_date": "1988-03-02", "timezone": "Asia/Seoul", "gender": "male"},
    "midnight": {"birth_date": "1988-03-02", "birth_time": "00:00", "timezone": "Asia/Seoul", "gender": "male"},
    "no_gender": {"birth_date": "1988-03-02", "birth_time": "07:30", "timezone": "Asia/Seoul"},
    "year_boundary": {"birth_date": "2024-02-04", "timezone": "America/New_York"},
    "month_boundary": {"birth_date": "2024-03-05", "timezone": "Asia/Seoul"},
}


@pytest.fixture(scope="module")
def charts():
    results = {name: bridge.calculate_bazi_from_profile(profile) for name, profile in PROFILES.items()}
    assert all(result.ok for result in results.values())
    return results


def test_unknown_stable_day_reports_six_actual_characters_without_hour_or_cycle(charts):
    chart = charts["unknown"]
    assert chart.time_basis["solar_terms"] == "civil_day_interval_confirmed"
    assert chart.eight_char["time"] == "" and chart.dayun is None
    assert sum(chart.elements.values()) == sum(len(value) for value in chart.eight_char.values()) == 6
    reading = engine._daily_from_chart(PROFILES["unknown"], chart, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "출생 일주는 현지 민간 날짜 기준이며 진태양시 보정은 적용하지 않았습니다." in text
    assert "출생 일·시주는" not in text
    assert "시주를 제외한 년·월·일주 6글자의 오행 수는" in text
    assert "대운 보정 미적용: 출생시각이 미상이라 대운을 계산하지 않았습니다." in text
    evidence = {item["id"]: item for item in reading["sections"]["evidence"]}
    assert "6글자" in "\n".join(evidence["score"]["paragraphs"])
    assert evidence["cycle"]["paragraphs"] == ["출생시각이 미상이라 대운을 계산하지 않았습니다."]
    assert all("일·시주는" not in line for line in evidence["time"]["paragraphs"])
    assert reading["dayun_adjustment"] == 0


def test_unknown_summary_and_node_warning_agree_with_the_omitted_hour(charts):
    chart = charts["unknown"]
    summary = chart.format_summary()
    assert "일주는 출생지 민간 날짜 기준" in summary and "일·시주는" not in summary
    assert "시주·대운은 계산하지 않았습니다" in summary
    assert "오행은 시주를 제외한 년·월·일주 6글자 기준입니다" in summary
    assert any("일주는 출생지 민간 날짜 기준" in warning for warning in chart.warnings)
    assert all("일·시주는" not in warning for warning in chart.warnings)


@pytest.mark.parametrize("name,count,scope", [
    ("year_boundary", 2, "일주"), ("month_boundary", 4, "년·일주"),
])
def test_boundary_summary_counts_only_confirmed_pillars_and_daily_stays_unavailable(charts, name, count, scope):
    chart = charts[name]
    assert chart.time_basis["solar_terms"] == "date_only_uncertain"
    assert chart.eight_char["month"] == chart.eight_char["time"] == ""
    assert sum(chart.elements.values()) == count
    summary = chart.format_summary()
    assert f"시주를 제외한 {scope} {count}글자 기준" in summary
    assert "월주는 절기 날짜 기준" not in summary
    assert "일·시주는" not in summary and "시주·대운은 계산하지 않았습니다" in summary
    with patch.object(bridge, "calculate_bazi_from_profile", return_value=chart):
        assert engine.build_personalized_daily(PROFILES[name], target_date=TARGET) is None


def test_known_midnight_keeps_hour_and_existing_clock_copy(charts):
    chart = charts["midnight"]
    assert chart.time_basis["solar_terms"] == "birth_instant_utc_plus_8"
    assert chart.eight_char["time"] and chart.dayun
    assert sum(chart.elements.values()) == 8
    reading = engine._daily_from_chart(PROFILES["midnight"], chart, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "출생 일·시주는 현지 민간시 기준이며 진태양시 보정은 적용하지 않았습니다." in text
    assert "출생시각이 미상이라" not in text and "6글자" not in text
    assert "일·시주는 출생지 민간시 기준" in chart.format_summary()
    assert any("일·시주는 출생지 민간시 기준" in warning for warning in chart.warnings)


def test_missing_cycle_for_another_reason_does_not_claim_unknown_birth_time(charts):
    chart = charts["no_gender"]
    assert chart.eight_char["time"] and chart.dayun is None
    reading = engine._daily_from_chart(PROFILES["no_gender"], chart, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "계산 결과에서 이 날짜에 적용할 대운 구간을 확인하지 못했습니다" in text
    assert "출생시각이 미상이라" not in text
    assert "출생시각 미상" not in chart.format_summary()


@pytest.mark.parametrize("basis", [{}, {"solar_terms": "unrecognized"}, {"solar_terms": []}])
def test_missing_or_unknown_metadata_does_not_supply_a_clock_or_omission_reason(charts, basis):
    chart = deepcopy(charts["unknown"])
    chart.time_basis = basis
    reading = engine._daily_from_chart(PROFILES["unknown"], chart, TARGET, "종합")
    text = "\n".join(reading["lines"])
    assert "6글자" not in text and "출생시각이 미상이라" not in text
    assert "민간" not in text and "진태양시" not in text
    assert "민간" not in chart.format_summary()
    assert "출생시각 미상" not in chart.format_summary()
    english = localize_daily(reading, "en")
    assert "Birth day/hour" not in "\n".join(english["lines"])
    assert "birth time is unknown" not in "\n".join(english["lines"])


@pytest.mark.parametrize("patch_basis", [
    {"day_hour": "unverified"}, {"true_solar_time": "false"}, {"true_solar_time": True},
])
def test_civil_time_and_no_correction_are_not_inferred_from_unverified_metadata(charts, patch_basis):
    chart = deepcopy(charts["unknown"])
    chart.time_basis.update(patch_basis)
    reading = engine._daily_from_chart(PROFILES["unknown"], chart, TARGET, "종합")
    assert "진태양시 보정은 적용하지 않았습니다" not in "\n".join(reading["lines"])
    assert "진태양시 보정은 적용하지 않았습니다" not in chart.format_summary()
    assert "correction is not applied" not in "\n".join(localize_daily(reading, "en")["lines"])


def test_character_scope_is_not_a_hardcoded_six_when_counts_disagree(charts):
    chart = deepcopy(charts["unknown"])
    key = next(iter(chart.elements))
    chart.elements[key] += 1
    reading = engine._daily_from_chart(PROFILES["unknown"], chart, TARGET, "종합")
    assert "글자의 오행 수는" not in "\n".join(reading["lines"])
    assert "글자 기준" not in chart.format_summary()


def test_english_and_channel_notices_distinguish_unknown_and_known_birth_time(charts):
    for name in ("unknown", "midnight"):
        reading = engine._daily_from_chart(PROFILES[name], charts[name], TARGET, "종합")
        original = deepcopy(reading)
        english = localize_daily(reading, "en")
        text = "\n".join(english["lines"])
        if name == "unknown":
            assert "Birth day uses the local civil date" in text and "Birth day/hour" not in text
            assert "birth time is unknown, so no ten-year cycle was calculated" in text
            assert "출생시각 미상으로 대운 보정 미적용" in engine.render_daily_channel_text(reading)
        else:
            assert "Birth day/hour use local civil time; true solar time correction is not applied." in text
            assert "birth time is unknown" not in text
        assert reading == original
