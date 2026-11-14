"""Tests — Phase 14B: 대운 skeleton (dayun.py + dayun_interpreter.py).

최소 15개 테스트.
"""
from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path("plugins"))

import pytest
from hermes_ext.fortune_oracle.dayun import (
    DayunResult,
    calculate_dayun_skeleton,
    _determine_direction,
    _year_stem_yin_yang,
)
from hermes_ext.fortune_oracle.dayun_interpreter import (
    build_dayun_note,
    build_show_profile_dayun_note,
)

_UNSAFE_PHRASES = [
    "반드시 파산합니다",
    "피할 수 없는 파국",
    "이혼한다",
    "사고가 난다",
    "병이 생긴다",
    "투자하면 손해",
    "소송하면 무조건",
]

# ---------------------------------------------------------------------------
# 1. gender unknown → direction unknown + warning
# ---------------------------------------------------------------------------

def test_gender_unknown_direction_unknown():
    """gender=None → direction=unknown."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender=None)
    assert r.ok
    assert r.direction == "unknown"

def test_gender_unknown_has_warning():
    """gender=None → warning 포함."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender=None)
    assert len(r.warnings) >= 1

def test_gender_unknown_cycles_empty():
    """gender unknown → cycles 비어 있음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender=None)
    assert r.cycles == []

def test_gender_unknown_note_contains_guidance():
    """gender unknown note → 성별 정보 안내 포함."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender=None)
    note = build_dayun_note(r)
    assert "성별" in note

# ---------------------------------------------------------------------------
# 2. 방향 계산 (양간 남성 → 순행)
# ---------------------------------------------------------------------------

def test_male_yang_year_forward():
    """남성·양년 → 순행."""
    direction, reason = _determine_direction("남", "양")
    assert direction == "forward"

def test_female_yang_year_reverse():
    """여성·양년 → 역행."""
    direction, reason = _determine_direction("여", "양")
    assert direction == "reverse"

def test_male_yin_year_reverse():
    """남성·음년 → 역행."""
    direction, reason = _determine_direction("남", "음")
    assert direction == "reverse"

def test_female_yin_year_forward():
    """여성·음년 → 순행."""
    direction, reason = _determine_direction("여", "음")
    assert direction == "forward"

# ---------------------------------------------------------------------------
# 3. 연간 음양 판별
# ---------------------------------------------------------------------------

def test_year_stem_yang():
    """甲(양간) → 양."""
    assert _year_stem_yin_yang("甲子") == "양"

def test_year_stem_yin():
    """乙(음간) → 음."""
    assert _year_stem_yin_yang("乙丑") == "음"

# ---------------------------------------------------------------------------
# 4. cycles 정상 생성
# ---------------------------------------------------------------------------

def test_cycles_length_with_gender():
    """gender 지정 시 cycles 8개 생성."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender="남")
    assert r.ok
    assert len(r.cycles) == 8

def test_cycles_age_progression():
    """대운 나이 10년 간격."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender="남")
    for i, c in enumerate(r.cycles[:-1]):
        assert r.cycles[i + 1].age_from == c.age_from + 10

def test_start_age_precision_approx():
    """start_age_precision = approx (절기 기반 미확정)."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender="남")
    assert r.start_age_precision == "approx"

# ---------------------------------------------------------------------------
# 5. current cycle detection
# ---------------------------------------------------------------------------

def test_current_cycle_detection():
    """현재 나이 기준 대운 사이클 감지."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender="남")
    c = r.current_cycle(20)  # 20세
    assert c is not None
    assert c.age_from <= 20 <= c.age_to

# ---------------------------------------------------------------------------
# 6. output에 decision directive 없음
# ---------------------------------------------------------------------------

def test_dayun_note_no_unsafe_phrase_gender_unknown():
    """대운 note (gender unknown)에 unsafe phrase 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender=None)
    note = build_dayun_note(r)
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in note

def test_dayun_note_no_unsafe_phrase_with_gender():
    """대운 note (gender 있음)에 unsafe phrase 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_dayun_skeleton(ec, gender="남")
    note = build_dayun_note(r, birth_year=1986)
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in note

# ---------------------------------------------------------------------------
# 7. fail-open / missing data
# ---------------------------------------------------------------------------

def test_empty_eight_char_returns_not_ok():
    """empty eight_char → ok=False."""
    r = calculate_dayun_skeleton({})
    assert not r.ok

def test_show_profile_dayun_note_empty_eight_char():
    """eight_char 없음 → 빈 문자열 반환."""
    note = build_show_profile_dayun_note(None)
    assert note == ""
