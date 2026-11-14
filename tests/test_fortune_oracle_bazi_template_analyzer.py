"""tests/test_fortune_oracle_bazi_template_analyzer.py

Phase 4 — Template Analyzer 테스트
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
from hermes_ext.fortune_oracle.bazi_template_analyzer import (
    TemplateAnalysisResult,
    TemplateSection,
    _DISCLAIMER,
    analyze_bazi_template,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ok_bazi() -> BaziResult:
    return BaziResult(
        ok=True,
        engine="lunar-javascript",
        eight_char={"year": "己巳", "month": "丙子", "day": "丙寅", "time": "壬辰"},
        elements={"목(木)": 2, "화(火)": 1, "수(水)": 3},
        zodiac="뱀띠",
        lunar={"year": 1989, "month": 12, "day": 5},
    )


def _fail_bazi() -> BaziResult:
    return BaziResult.error("INVALID_INPUT", "테스트 오류")


# ---------------------------------------------------------------------------
# 정상 경로
# ---------------------------------------------------------------------------

def test_analyze_ok_returns_ok_true():
    result = analyze_bazi_template(_ok_bazi())
    assert result.ok is True


def test_sections_exist():
    result = analyze_bazi_template(_ok_bazi())
    assert len(result.sections) >= 3


def test_section_titles_present():
    result = analyze_bazi_template(_ok_bazi())
    titles = [s.title for s in result.sections]
    assert "기본 기질" in titles


def test_disclaimer_section_present():
    result = analyze_bazi_template(_ok_bazi())
    disclaimer_sections = [s for s in result.sections if s.confidence == "disclaimer"]
    assert len(disclaimer_sections) >= 1
    assert _DISCLAIMER in disclaimer_sections[0].summary


def test_disclaimer_text_in_sections():
    result = analyze_bazi_template(_ok_bazi())
    all_text = " ".join(s.summary for s in result.sections)
    assert "오락" in all_text or "자기성찰" in all_text


# ---------------------------------------------------------------------------
# 금지 문구 검증
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = [
    "반드시 죽", "사망", "파산할", "이혼할 것",
    "투자하세요", "법적으로", "의학적으로 치료",
]


def test_no_forbidden_phrases_in_sections():
    result = analyze_bazi_template(_ok_bazi())
    all_text = " ".join(s.summary + s.title for s in result.sections)
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in all_text, f"금지 문구 발견: '{phrase}'"


# ---------------------------------------------------------------------------
# fallback (bazi 실패)
# ---------------------------------------------------------------------------

def test_fallback_on_bazi_failure():
    result = analyze_bazi_template(_fail_bazi())
    # ok=False이지만 sections(fallback)은 존재해야 한다
    assert len(result.sections) > 0


def test_fallback_disclaimer_present():
    result = analyze_bazi_template(_fail_bazi())
    all_text = " ".join(s.summary for s in result.sections)
    assert "오락" in all_text or "자기성찰" in all_text


# ---------------------------------------------------------------------------
# kline_summary 연결
# ---------------------------------------------------------------------------

def test_kline_summary_attached_when_provided():
    result = analyze_bazi_template(_ok_bazi(), kline_summary="5월 운세: 에너지 상승 중")
    titles = [s.title for s in result.sections]
    assert "이번 달 운세 K선과의 연결" in titles


def test_kline_summary_absent_when_not_provided():
    result = analyze_bazi_template(_ok_bazi())
    titles = [s.title for s in result.sections]
    assert "이번 달 운세 K선과의 연결" not in titles


# ---------------------------------------------------------------------------
# to_telegram_summary
# ---------------------------------------------------------------------------

def test_telegram_summary_length():
    result = analyze_bazi_template(_ok_bazi())
    summary = result.to_telegram_summary(max_chars=800)
    assert len(summary) <= 800


def test_telegram_summary_not_empty():
    result = analyze_bazi_template(_ok_bazi())
    summary = result.to_telegram_summary()
    assert len(summary) > 0


def test_telegram_summary_fallback_on_failure():
    result = analyze_bazi_template(_fail_bazi())
    summary = result.to_telegram_summary()
    assert len(summary) > 0
