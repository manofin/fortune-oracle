"""Tests — Phase 14C: 용신/희신 rule-based skeleton.

최소 20개 테스트.
"""
from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path("plugins"))

import pytest
from hermes_ext.fortune_oracle.yongshen import (
    ALL_ELEMENTS,
    YongshenResult,
    calculate_yongshen,
    count_elements_from_eight_char,
    extract_day_master,
)
from hermes_ext.fortune_oracle.yongshen_interpreter import (
    build_show_profile_yongshen_note,
    build_yongshen_note,
)

_UNSAFE_PHRASES = [
    "반드시 파산합니다",
    "피할 수 없는 파국",
    "이혼한다",
    "사고가 난다",
    "병이 생긴다",
    "투자하면 손해",
    "반드시 Y 직업을 가져야",
    "건강 문제가 생긴다",
    "소송하면 무조건",
]

_SENSITIVE_FIELDS = ["birth_date", "birth_time", "name_hanja"]

# ---------------------------------------------------------------------------
# 1. day_master extraction
# ---------------------------------------------------------------------------

def test_extract_day_master_bing():
    """丙 일간 추출."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    stem, elem = extract_day_master(ec)
    assert stem == "丙"
    assert elem == "화"

def test_extract_day_master_jia():
    """甲 일간 추출."""
    ec = {"year": "甲子", "month": "乙丑", "day": "甲午", "time": "丁卯"}
    stem, elem = extract_day_master(ec)
    assert stem == "甲"
    assert elem == "목"

def test_extract_day_master_no_day():
    """일주 없음 → 빈 문자열."""
    ec = {"year": "甲子", "month": "乙丑"}
    stem, elem = extract_day_master(ec)
    assert stem == ""
    assert elem == ""

# ---------------------------------------------------------------------------
# 2. element mapping
# ---------------------------------------------------------------------------

def test_element_mapping_all_stems():
    """천간 10개 오행 매핑."""
    from hermes_ext.fortune_oracle.yongshen import _STEM_ELEMENT
    assert _STEM_ELEMENT["甲"] == "목"
    assert _STEM_ELEMENT["丙"] == "화"
    assert _STEM_ELEMENT["戊"] == "토"
    assert _STEM_ELEMENT["庚"] == "금"
    assert _STEM_ELEMENT["壬"] == "수"

def test_count_elements_from_eight_char():
    """오행 집계 기본 동작."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    counts = count_elements_from_eight_char(ec)
    assert isinstance(counts, dict)
    assert all(k in ALL_ELEMENTS for k in counts)
    assert sum(counts.values()) > 0

def test_count_elements_total_8():
    """팔자 8글자 기준 오행 합계 = 8."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    counts = count_elements_from_eight_char(ec)
    assert sum(counts.values()) == 8

# ---------------------------------------------------------------------------
# 3. strength classification
# ---------------------------------------------------------------------------

def test_strength_is_valid_value():
    """strength 값이 유효한 값 중 하나."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert r.strength in {"balanced", "weak", "strong", "unknown"}

def test_yongshen_result_ok():
    """정상 입력 → ok=True."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert r.ok

# ---------------------------------------------------------------------------
# 4. favorable/caution elements deterministic
# ---------------------------------------------------------------------------

def test_favorable_elements_is_list():
    """favorable_elements는 list."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert isinstance(r.favorable_elements, list)

def test_caution_elements_is_list():
    """caution_elements는 list."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert isinstance(r.caution_elements, list)

def test_deterministic_same_input_same_output():
    """동일 입력 → 동일 결과 (deterministic)."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r1 = calculate_yongshen(ec)
    r2 = calculate_yongshen(ec)
    assert r1.favorable_elements == r2.favorable_elements
    assert r1.strength == r2.strength
    assert r1.confidence == r2.confidence

# ---------------------------------------------------------------------------
# 5. reasoning 포함
# ---------------------------------------------------------------------------

def test_reasoning_not_empty():
    """reasoning 리스트에 내용 있음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert len(r.reasoning) >= 1

def test_reasoning_contains_day_master():
    """reasoning에 일간 정보 포함."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    combined = " ".join(r.reasoning)
    assert r.day_master_element in combined or r.day_master in combined

# ---------------------------------------------------------------------------
# 6. confidence 표시
# ---------------------------------------------------------------------------

def test_confidence_is_valid():
    """confidence 값이 유효한 rule_based_* 값."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    assert r.confidence in {"rule_based_low", "rule_based_medium"}

# ---------------------------------------------------------------------------
# 7. unsafe phrase 없음
# ---------------------------------------------------------------------------

def test_yongshen_note_no_unsafe_phrase():
    """용신 note에 unsafe phrase 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    note = build_yongshen_note(r, max_lines=5)
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in note, f"Unsafe phrase found: {phrase}"

def test_yongshen_disclaimer_in_note():
    """용신 note에 rule-based 참고 disclaimer 포함."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    note = build_yongshen_note(r)
    assert "rule-based" in note or "참고" in note

# ---------------------------------------------------------------------------
# 8. birth 민감정보 미노출
# ---------------------------------------------------------------------------

def test_yongshen_result_no_sensitive_fields_in_reasoning():
    """reasoning에 birth_date/birth_time/name_hanja 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    for field in _SENSITIVE_FIELDS:
        for line in r.reasoning:
            assert field not in line

def test_yongshen_note_no_sensitive_fields():
    """용신 note에 민감정보 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = calculate_yongshen(ec)
    note = build_yongshen_note(r)
    for field in _SENSITIVE_FIELDS:
        assert field not in note

# ---------------------------------------------------------------------------
# 9. fail-open
# ---------------------------------------------------------------------------

def test_empty_eight_char_not_ok():
    """empty eight_char → ok=False."""
    r = calculate_yongshen({})
    assert not r.ok

def test_show_profile_yongshen_note_empty():
    """eight_char 없음 → 빈 문자열."""
    note = build_show_profile_yongshen_note(None)
    assert note == ""

def test_show_profile_yongshen_note_normal():
    """정상 입력 → note 생성."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    note = build_show_profile_yongshen_note(ec)
    assert "용신" in note
