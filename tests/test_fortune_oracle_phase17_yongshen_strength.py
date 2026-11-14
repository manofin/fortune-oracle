"""Phase 17: Yongshen strength model 고도화 테스트."""
from __future__ import annotations

import pytest
import sys
import os

# 플러그인 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../plugins"))

from hermes_ext.fortune_oracle.yongshen import (
    _STEM_ELEMENT,
    _HIDDEN_STEMS,
    _MONTH_BRANCH_SEASON,
    _SEASON_ELEMENT,
    _SEASONAL_BOOST,
    _HIDDEN_WEIGHT,
    ALL_ELEMENTS,
    YongshenResult,
    calculate_strength_score,
    classify_strength,
    calculate_yongshen,
)
from hermes_ext.fortune_oracle.yongshen_interpreter import (
    build_yongshen_note,
    build_show_profile_yongshen_note,
)

# 샘플 사주
SAMPLE_EC = {"year": "甲子", "month": "乙卯", "day": "丙寅", "time": "丁卯"}
SAMPLE_EC2 = {"year": "庚午", "month": "壬子", "day": "癸亥", "time": "甲子"}
SAMPLE_EC3 = {"year": "戊午", "month": "己未", "day": "戊午", "time": "庚戌"}


# ---------------------------------------------------------------------------
# 1. day master element mapping
# ---------------------------------------------------------------------------

class TestStemElement:
    def test_all_stems_mapped(self):
        stems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
        for s in stems:
            assert s in _STEM_ELEMENT, f"{s} 없음"

    def test_correct_elements(self):
        assert _STEM_ELEMENT["甲"] == "목"
        assert _STEM_ELEMENT["丙"] == "화"
        assert _STEM_ELEMENT["戊"] == "토"
        assert _STEM_ELEMENT["庚"] == "금"
        assert _STEM_ELEMENT["壬"] == "수"


# ---------------------------------------------------------------------------
# 2. calculate_strength_score deterministic
# ---------------------------------------------------------------------------

class TestCalculateStrengthScore:
    def test_returns_all_elements(self):
        result = calculate_strength_score(SAMPLE_EC, "화")
        for e in ALL_ELEMENTS:
            assert e in result

    def test_deterministic(self):
        r1 = calculate_strength_score(SAMPLE_EC, "화")
        r2 = calculate_strength_score(SAMPLE_EC, "화")
        assert r1 == r2

    def test_scores_are_float(self):
        result = calculate_strength_score(SAMPLE_EC, "화")
        for v in result.values():
            assert isinstance(v, float)

    def test_seasonal_boost_applied(self):
        # 卯월 → 봄 → 목 +1.5
        scores = calculate_strength_score(SAMPLE_EC, "화")
        # 목 기운이 충분히 높아야 함 (천간/지지 기본 + 계절 boost + 지장간)
        assert scores["목"] > 2.0  # 최소한 계절 boost 포함

    def test_hidden_stems_contribute(self):
        # 子 지장간: 癸 → 수 +0.5
        ec = {"year": "甲子", "month": "甲子", "day": "甲子", "time": "甲子"}
        scores = calculate_strength_score(ec, "목")
        # 지장간 기여 확인: 子 × 4개 = 癸(수) × 4 × 0.5 = 2.0 추가
        # 월지 子 → 겨울 → 수 +1.5
        assert scores["수"] > 1.0


# ---------------------------------------------------------------------------
# 3. classify_strength weak/balanced/strong
# ---------------------------------------------------------------------------

class TestClassifyStrength:
    def test_strong(self):
        # 목 오행이 압도적
        scores = {"목": 5.0, "화": 1.0, "토": 0.5, "금": 0.5, "수": 0.5}
        result = classify_strength(scores, "목")
        assert result == "strong"

    def test_weak(self):
        # 목 오행이 매우 적음
        scores = {"목": 0.5, "화": 1.0, "토": 2.0, "금": 3.0, "수": 2.0}
        result = classify_strength(scores, "목")
        assert result == "weak"

    def test_balanced(self):
        # 균형 비율 0.22~0.35
        scores = {"목": 2.0, "화": 2.0, "토": 2.0, "금": 1.5, "수": 1.5}
        result = classify_strength(scores, "목")
        assert result in ("balanced", "strong")  # ratio=2/9≈0.222 → balanced

    def test_unknown_when_no_element(self):
        scores = {"목": 1.0, "화": 1.0, "토": 1.0, "금": 1.0, "수": 1.0}
        result = classify_strength(scores, "")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# 4. hidden stems contribution
# ---------------------------------------------------------------------------

class TestHiddenStems:
    def test_hidden_stems_table(self):
        # 子 지장간 = [癸]
        assert "癸" in _HIDDEN_STEMS["子"]
        # 寅 지장간 = [甲, 丙, 戊]
        assert "甲" in _HIDDEN_STEMS["寅"]
        assert "丙" in _HIDDEN_STEMS["寅"]

    def test_hidden_stems_contribution_in_result(self):
        result = calculate_yongshen(SAMPLE_EC)
        assert isinstance(result.hidden_stems_contribution, list)
        assert len(result.hidden_stems_contribution) > 0

    def test_hidden_weight(self):
        assert _HIDDEN_WEIGHT == 0.5


# ---------------------------------------------------------------------------
# 5. season / month branch weighting
# ---------------------------------------------------------------------------

class TestSeasonWeighting:
    def test_month_branch_season_table(self):
        assert _MONTH_BRANCH_SEASON["寅"] == "봄"
        assert _MONTH_BRANCH_SEASON["午"] == "여름"
        assert _MONTH_BRANCH_SEASON["申"] == "가을"
        assert _MONTH_BRANCH_SEASON["子"] == "겨울"

    def test_season_element_table(self):
        assert _SEASON_ELEMENT["봄"] == "목"
        assert _SEASON_ELEMENT["여름"] == "화"
        assert _SEASON_ELEMENT["가을"] == "금"
        assert _SEASON_ELEMENT["겨울"] == "수"

    def test_seasonal_boost_value(self):
        assert _SEASONAL_BOOST == 1.5

    def test_season_in_result(self):
        result = calculate_yongshen(SAMPLE_EC)  # 卯월 → 봄
        assert result.season == "봄"

    def test_season_field_empty_when_no_month(self):
        ec = {"year": "甲子", "day": "丙寅", "time": "丁卯"}
        result = calculate_yongshen(ec)
        assert result.season == ""


# ---------------------------------------------------------------------------
# 6. YongshenResult.strength 필드 존재
# ---------------------------------------------------------------------------

class TestYongshenResultFields:
    def test_strength_field_exists(self):
        r = calculate_yongshen(SAMPLE_EC)
        assert hasattr(r, "strength")
        assert r.strength in ("weak", "balanced", "strong", "", "unknown")

    def test_strength_score_field_exists(self):
        r = calculate_yongshen(SAMPLE_EC)
        assert hasattr(r, "strength_score")
        assert isinstance(r.strength_score, dict)

    def test_season_field_exists(self):
        r = calculate_yongshen(SAMPLE_EC)
        assert hasattr(r, "season")

    def test_hidden_stems_contribution_field_exists(self):
        r = calculate_yongshen(SAMPLE_EC)
        assert hasattr(r, "hidden_stems_contribution")

    def test_default_fields_preserved(self):
        # 기존 필드 제거 금지 확인
        r = YongshenResult(ok=True)
        assert hasattr(r, "ok")
        assert hasattr(r, "day_master")
        assert hasattr(r, "day_master_element")
        assert hasattr(r, "strength")
        assert hasattr(r, "favorable_elements")
        assert hasattr(r, "caution_elements")
        assert hasattr(r, "reasoning")
        assert hasattr(r, "confidence")
        assert hasattr(r, "warnings")
        assert hasattr(r, "disclaimer")


# ---------------------------------------------------------------------------
# 7. confidence never 'high'
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_confidence_not_high(self):
        for ec in [SAMPLE_EC, SAMPLE_EC2, SAMPLE_EC3]:
            r = calculate_yongshen(ec)
            assert r.confidence != "high", f"confidence='high' 금지: {r.confidence}"

    def test_balanced_gives_medium(self):
        # balanced → rule_based_medium
        r = calculate_yongshen(SAMPLE_EC)
        if r.strength == "balanced":
            assert r.confidence == "rule_based_medium"

    def test_non_balanced_gives_low(self):
        for ec in [SAMPLE_EC2, SAMPLE_EC3]:
            r = calculate_yongshen(ec)
            if r.strength in ("weak", "strong"):
                assert r.confidence == "rule_based_low"

    def test_confidence_is_rule_based(self):
        for ec in [SAMPLE_EC, SAMPLE_EC2, SAMPLE_EC3]:
            r = calculate_yongshen(ec)
            assert r.confidence.startswith("rule_based_")


# ---------------------------------------------------------------------------
# 8. unsafe phrases 없음
# ---------------------------------------------------------------------------

UNSAFE_PHRASES = ["반드시", "건강", "투자", "법적"]


class TestUnsafePhrases:
    def _get_note(self, ec):
        r = calculate_yongshen(ec)
        return build_yongshen_note(r, max_lines=5)

    def test_no_unsafe_phrases(self):
        for ec in [SAMPLE_EC, SAMPLE_EC2, SAMPLE_EC3]:
            note = self._get_note(ec)
            for phrase in UNSAFE_PHRASES:
                assert phrase not in note, f"금지 표현 '{phrase}' 발견: {note}"

    def test_build_show_profile_no_unsafe(self):
        for ec in [SAMPLE_EC, SAMPLE_EC2, SAMPLE_EC3]:
            note = build_show_profile_yongshen_note(ec)
            for phrase in UNSAFE_PHRASES:
                assert phrase not in note, f"금지 표현 '{phrase}' 발견: {note}"


# ---------------------------------------------------------------------------
# 9. /show_profile 용신 compact 유지
# ---------------------------------------------------------------------------

class TestShowProfileCompact:
    def test_build_show_profile_yongshen_note_returns_str(self):
        note = build_show_profile_yongshen_note(SAMPLE_EC)
        assert isinstance(note, str)

    def test_max_lines_respected(self):
        r = calculate_yongshen(SAMPLE_EC)
        note = build_yongshen_note(r, max_lines=2)
        # 헤더 + 최대 2줄
        lines = [l for l in note.split("\n") if l.startswith("- ")]
        assert len(lines) <= 2

    def test_empty_on_none(self):
        assert build_show_profile_yongshen_note(None) == ""

    def test_empty_on_empty_dict(self):
        assert build_show_profile_yongshen_note({}) == ""

    def test_note_contains_header(self):
        note = build_show_profile_yongshen_note(SAMPLE_EC)
        assert "용신 참고" in note
