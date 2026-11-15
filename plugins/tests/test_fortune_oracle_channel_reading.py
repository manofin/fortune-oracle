"""Short delivery contracts using synthetic charts, stores, and injected TTS."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_ext.fortune_oracle import daily_fortune_engine as engine, speech
from hermes_ext.fortune_oracle.daily_delivery import run_delivery
from hermes_ext.fortune_oracle.daily_reading import prepare_daily_reading
from hermes_ext.fortune_oracle.localization import localize_daily
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading
from hermes_ext.fortune_oracle.store import FortuneStore

PROFILE = {"birth_date": "1990-01-01"}
TARGET = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 0, tzinfo=timezone.utc)


def chart(stem="甲", basis=None):
    return SimpleNamespace(
        ok=True, eight_char={"year": "庚午", "month": "戊寅", "day": stem + "子"},
        elements={"목": 3, "화": 2, "토": 1, "금": 0, "수": 2},
        dayun=None, time_basis=basis or {},
    )


@pytest.mark.parametrize("stem", list("甲丙戊庚壬"))
def test_short_message_preserves_complete_action_caution_and_calculation(stem):
    reading = engine._daily_from_chart(PROFILE, chart(stem), TARGET, "종합")
    original = deepcopy(reading)
    text = engine.render_daily_channel_text(reading)
    action, caution = engine.RELATION_PRACTICE[reading["relation"]]
    assert f"해볼 일: {action}" in text and f"주의할 점: {caution}" in text
    assert reading["date"] in text and reading["day_pillar"] in text
    assert "계산된" in text.splitlines()[0] and "경험적 해석" in text.splitlines()[0]
    assert f"{reading['date']}의 키워드는" in text
    assert f"{reading['score']:.0f}점" in text
    assert "오락과 자기성찰용" in text and "예측 확률이 아닙니다" in text
    assert "같은 개수일 때는" not in text and "용신" not in text
    assert 5 <= len(text.splitlines()) <= 8
    assert len(text) < 400  # Reviewed Korean message/narration budget, not truncation.
    assert reading == original


@pytest.mark.parametrize("basis,notice", [
    ({"solar_terms": "civil_day_interval_confirmed"}, "시주·대운은 제외했습니다"),
    ({"solar_terms": "unresolved"}, "년·월주는 불확실합니다"),
])
def test_short_message_retains_birth_time_uncertainty(basis, notice):
    reading = engine._daily_from_chart(PROFILE, chart(basis=basis), TARGET, "종합")
    text = engine.render_daily_channel_text(reading)
    assert "출생시각 미확정" in text and notice in text
    assert len(text.splitlines()) <= 8


def test_detailed_action_override_is_labelled_without_mutating_or_using_positions():
    reading = engine._daily_from_chart(PROFILE, chart(), TARGET, "종합")
    reading["lines"].reverse()
    original = deepcopy(reading)
    lines = engine.daily_display_lines(reading, action_override="조건 하나를 메모하세요.")
    action, _ = engine.RELATION_PRACTICE[reading["relation"]]
    assert f"해볼 일: {action}" not in lines
    assert "해볼 일 (선택한 상황에 맞춘 제안 · 별도 점수·성공 확률 아님): 조건 하나를 메모하세요." in lines
    assert len(lines) == len(original["lines"])
    assert sum(a != b for a, b in zip(lines, original["lines"])) == 1
    assert reading == original
    general = engine.daily_display_lines(reading)
    assert general == reading["lines"] and general is not reading["lines"]


def test_action_override_rejects_unknown_paragraph_contract():
    reading = engine._daily_from_chart(PROFILE, chart(), TARGET, "종합")
    reading["lines"] = ["해볼 일: 다른 렌더러의 문장"]
    with pytest.raises(ValueError, match="action paragraph"):
        engine.daily_display_lines(reading, action_override="상황 제안")


@pytest.mark.parametrize("command,day,expected", [
    ("/today_fortune", "today", "2026-10-03"),
    ("/tomorrow_fortune", "tomorrow", "2026-10-04"),
])
def test_telegram_daily_uses_short_text_and_preserves_detailed_reading(command, day, expected):
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        full = prepare_daily_reading(PROFILE, day=day, now=NOW)
        delivered = prepare_reading(command, profile=PROFILE, now=NOW)
    assert delivered["reading"] == full["reading"]
    assert delivered["date"] == expected
    assert "같은 개수일 때는" in full["text"]
    assert "같은 개수일 때는" not in delivered["text"]
    assert "해볼 일:" in delivered["text"] and "주의할 점:" in delivered["text"]
    assert "오늘" not in delivered["text"]
    assert len(delivered["text"]) < len(full["text"])


def test_english_channel_keeps_existing_localized_lines():
    reading = localize_daily(engine._daily_from_chart(PROFILE, chart(), TARGET, "종합"), "en")
    original = deepcopy(reading)
    assert engine.render_daily_channel_text(reading) == "\n".join(
        [f"Interpretation of calculated chart data (heuristic) · {reading['date']}",
         *reading["lines"], reading["disclaimer"]])
    assert reading == original


@pytest.mark.parametrize("language", ["ko", "en"])
def test_channel_label_date_and_explicit_timezone_share_the_first_line(language):
    reading = localize_daily(engine._daily_from_chart(PROFILE, chart(), TARGET, "종합"), language)
    first = engine.render_daily_channel_text(reading, reading_timezone="Asia/Seoul").splitlines()[0]
    assert ("계산된" if language == "ko" else "calculated") in first
    assert ("경험적 해석" if language == "ko" else "heuristic") in first
    assert reading["date"] in first and first.endswith(" · Asia/Seoul")


@pytest.mark.parametrize("command,language", [
    ("/voice_fortune", "ko"),
    ("/voice_fortune tomorrow_fortune", "ko"),
    ("/voice_fortune tomorrow_fortune", "en"),
])
def test_dynamic_voice_narrates_same_short_delivery_text_once(command, language, tmp_path):
    calls = []

    def unavailable_tts(**kwargs):
        calls.append(kwargs)
        return {"success": False}

    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = prepare_reading(command, profile=PROFILE, language=language, now=NOW,
                                 tts=unavailable_tts, output_root=tmp_path)
    assert result["error"] == "tts_unavailable" and len(calls) == 1
    assert calls[0]["text"] == result["text_fallback"] == result["reading"]["text"]
    assert "같은 개수일 때는" not in calls[0]["text"]
    if language == "en":
        assert "English" in calls[0]["instructions"]
        assert not re.search("[가-힣]", calls[0]["text"])
    else:
        assert "해볼 일:" in calls[0]["text"] and "주의할 점:" in calls[0]["text"]
        assert "Korean" in calls[0]["instructions"]
    assert result["reading"]["date"] in calls[0]["text"]
    assert result["reading"]["reading_timezone"] in calls[0]["text"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("language", ["ko", "en"])
def test_direct_daily_voice_uses_compact_text_and_profile_language(language, tmp_path):
    calls = []

    def unavailable_tts(**kwargs):
        calls.append(kwargs)
        return {"success": False}

    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = speech.prepare_daily_voice({**PROFILE, "language": language}, target_date=TARGET,
                                            tts=unavailable_tts, output_root=tmp_path)
    assert len(calls) == 1 and result["error"] == "tts_unavailable"
    assert calls[0]["text"] == result["text_fallback"]
    assert result["reading"]["evidence"]["score"] == 66.2
    assert result["reading"]["language"] == language
    assert ("English" if language == "en" else "Korean") in calls[0]["instructions"]
    assert "같은 개수일 때는" not in calls[0]["text"]
    assert PROFILE["birth_date"] not in calls[0]["text"]


def test_daily_delivery_default_sends_compact_reading_with_opt_out(tmp_path):
    store = FortuneStore(tmp_path / "store.json")
    store.save_profile("telegram", "101", PROFILE)
    store.set_daily_push("telegram", "101", "07:00", target="101", now=NOW - timedelta(days=1))
    sent = []

    def sender(target, text):
        sent.append((target, text))
        return 1

    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile", return_value=chart()):
        result = run_delivery(store, send=True, sender=sender, now=NOW)
    assert result["sent"] == 1 and len(sent) == 1
    text = sent[0][1]
    assert "해볼 일:" in text and "주의할 점:" in text
    assert "같은 개수일 때는" not in text
    assert "/daily_off" in text and "예측 확률이 아닙니다" in text


def test_daily_delivery_accepts_existing_injected_renderer_signature(tmp_path):
    store = FortuneStore(tmp_path / "store.json")
    store.save_profile("telegram", "101", PROFILE)
    store.set_daily_push("telegram", "101", "07:00", target="101", now=NOW - timedelta(days=1))

    def renderer(profile, *, day, reading_timezone, now):
        return {"computed": False, "text": "계산 결과가 아님 — 계산 불가"}

    result = run_delivery(store, renderer=renderer, now=NOW)
    assert result["would_send"] == 1
