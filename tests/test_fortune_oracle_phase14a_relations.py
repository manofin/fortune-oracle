"""Tests — Phase 14A: 형·해·파 관계 탐지 (bazi_relations.py 확장).

최소 20개 테스트.
"""
from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path("plugins"))

import pytest
from hermes_ext.fortune_oracle.bazi_relations import (
    BaziRelationReport,
    HAI,
    PO,
    RelationEntry,
    XING_PAIR,
    XING_TRIO,
    _SELF_XING,
    detect_relations,
)
from hermes_ext.fortune_oracle.bazi_relation_interpreter import (
    _compact_lines,
    build_show_profile_relation_note,
)

# ---------------------------------------------------------------------------
# 1. Table completeness
# ---------------------------------------------------------------------------

def test_xing_pair_table_has_zimao():
    """자묘형 테이블 존재."""
    key = frozenset({"子", "卯"})
    assert key in XING_PAIR

def test_xing_trio_table_has_yinsi_shen():
    """인사신 삼형 테이블 존재."""
    key = frozenset({"寅", "巳", "申"})
    assert key in XING_TRIO

def test_xing_trio_table_has_chou_xu_wei():
    """축술미 삼형 테이블 존재."""
    key = frozenset({"丑", "戌", "未"})
    assert key in XING_TRIO

def test_hai_table_completeness():
    """해 테이블 6쌍 모두 존재."""
    expected_pairs = [
        frozenset({"子", "未"}),
        frozenset({"丑", "午"}),
        frozenset({"寅", "巳"}),
        frozenset({"卯", "辰"}),
        frozenset({"申", "亥"}),
        frozenset({"酉", "戌"}),
    ]
    for pair in expected_pairs:
        assert pair in HAI, f"{pair} 해 테이블 누락"

def test_po_table_completeness():
    """파 테이블 6쌍 모두 존재."""
    expected_pairs = [
        frozenset({"子", "酉"}),
        frozenset({"丑", "辰"}),
        frozenset({"寅", "亥"}),
        frozenset({"卯", "午"}),
        frozenset({"巳", "申"}),
        frozenset({"未", "戌"}),
    ]
    for pair in expected_pairs:
        assert pair in PO, f"{pair} 파 테이블 누락"

def test_self_xing_set():
    """자형 후보: 辰午酉亥."""
    assert _SELF_XING == {"辰", "午", "酉", "亥"}

# ---------------------------------------------------------------------------
# 2. 형 탐지
# ---------------------------------------------------------------------------

def test_detect_xing_zimao():
    """子·卯 → 형 탐지."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙寅", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    relations = [e.relation for e in r.xing]
    assert "형" in relations

def test_detect_xing_trio_yinsi_shen():
    """寅·巳·申 삼형 탐지."""
    ec = {"year": "甲寅", "month": "乙巳", "day": "丙申", "time": "丁子"}
    r = detect_relations(ec)
    assert r.ok
    xing_types = [e.xing_type for e in r.xing]
    assert "인사신형" in xing_types

def test_detect_xing_trio_chou_xu_wei():
    """丑·戌·未 삼형 탐지."""
    ec = {"year": "甲丑", "month": "乙戌", "day": "丙未", "time": "丁子"}
    r = detect_relations(ec)
    assert r.ok
    xing_types = [e.xing_type for e in r.xing]
    assert "축술미형" in xing_types

def test_detect_self_xing_chen():
    """辰 중복 → 자형 탐지."""
    ec = {"year": "甲辰", "month": "乙辰", "day": "丙子", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert "辰" in r.self_xing

def test_detect_self_xing_wu():
    """午 중복 → 자형 탐지."""
    ec = {"year": "甲午", "month": "乙午", "day": "丙子", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert "午" in r.self_xing

# ---------------------------------------------------------------------------
# 3. 해 탐지
# ---------------------------------------------------------------------------

def test_detect_hai_zi_wei():
    """子·未 해 탐지."""
    ec = {"year": "甲子", "month": "乙未", "day": "丙寅", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.hai) >= 1
    assert r.hai[0].relation == "해"

def test_detect_hai_chou_wu():
    """丑·午 해 탐지."""
    ec = {"year": "甲丑", "month": "乙午", "day": "丙申", "time": "丁酉"}
    r = detect_relations(ec)
    assert r.ok
    assert any(set(e.branches) == {"丑", "午"} for e in r.hai)

def test_detect_hai_you_xu():
    """酉·戌 해 탐지."""
    ec = {"year": "甲酉", "month": "乙戌", "day": "丙子", "time": "丁丑"}
    r = detect_relations(ec)
    assert r.ok
    assert any(set(e.branches) == {"酉", "戌"} for e in r.hai)

# ---------------------------------------------------------------------------
# 4. 파 탐지
# ---------------------------------------------------------------------------

def test_detect_po_zi_you():
    """子·酉 파 탐지."""
    ec = {"year": "甲子", "month": "乙酉", "day": "丙寅", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.po) >= 1
    assert r.po[0].relation == "파"

def test_detect_po_chou_chen():
    """丑·辰 파 탐지."""
    ec = {"year": "甲丑", "month": "乙辰", "day": "丙子", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert any(set(e.branches) == {"丑", "辰"} for e in r.po)

def test_detect_po_wei_xu():
    """未·戌 파 탐지."""
    ec = {"year": "甲未", "month": "乙戌", "day": "丙子", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    assert any(set(e.branches) == {"未", "戌"} for e in r.po)

# ---------------------------------------------------------------------------
# 5. no relation, multiple relation
# ---------------------------------------------------------------------------

def test_no_xing_hai_po():
    """형·해·파 없는 경우 empty list."""
    # 子·丑·寅·卯 구성:
    # 子·丑 = 육합 (OK), 子·卯 = 자묘형 존재 → 형 있음
    # 형·해·파 없는 구성: 午·未·申·酉 → 午·未 육합, 해/파 없음
    ec = {"year": "甲午", "month": "乙未", "day": "丙申", "time": "丁酉"}
    r = detect_relations(ec)
    assert r.ok
    # 午·未 육합, 형/해/파 없음 확인
    assert r.xing == []
    assert r.hai == []
    assert r.po == []

def test_multiple_relations_detected():
    """형·해·파 복수 탐지 — 子卯(형) + 子未(해) + 子酉(파) 공존."""
    # 子·卯·未·酉 구성
    ec = {"year": "甲子", "month": "乙卯", "day": "丙未", "time": "丁酉"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.xing) >= 1   # 子·卯 형
    assert len(r.hai) >= 1    # 子·未 해
    assert len(r.po) >= 1     # 子·酉 파

# ---------------------------------------------------------------------------
# 6. compact interpreter output
# ---------------------------------------------------------------------------

def test_compact_lines_xing():
    """형 탐지 시 compact note에 '형' 포함."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙寅", "time": "丁亥"}
    r = detect_relations(ec)
    lines = _compact_lines(r, max_lines=5)
    assert any("형" in l for l in lines)

def test_compact_lines_hai():
    """해 탐지 시 compact note에 '해' 포함."""
    ec = {"year": "甲子", "month": "乙未", "day": "丙寅", "time": "丁亥"}
    r = detect_relations(ec)
    lines = _compact_lines(r, max_lines=5)
    assert any("해" in l for l in lines)

def test_compact_lines_po():
    """파 탐지 시 compact note에 '파' 포함."""
    ec = {"year": "甲子", "month": "乙酉", "day": "丙寅", "time": "丁亥"}
    r = detect_lines = detect_relations(ec)
    lines = _compact_lines(r, max_lines=5)
    assert any("파" in l for l in lines)

def test_compact_lines_max_4():
    """compact lines 최대 4줄 제한."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙未", "time": "丁酉"}
    r = detect_relations(ec)
    lines = _compact_lines(r, max_lines=4)
    assert len(lines) <= 4

# ---------------------------------------------------------------------------
# 7. Unsafe phrase 미포함
# ---------------------------------------------------------------------------

_UNSAFE_PHRASES = [
    "반드시 관계가 깨진다",
    "이혼한다",
    "사고가 난다",
    "병이 생긴다",
    "투자를 피해야 한다",
    "반드시 파산합니다",
    "피할 수 없는 파국",
]

def test_xing_note_no_unsafe_phrase():
    """형 note에 unsafe phrase 없음."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙未", "time": "丁酉"}
    r = detect_relations(ec)
    all_notes = " ".join(r.notes + r.warnings + [r.summary])
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in all_notes, f"Unsafe phrase found: {phrase}"

def test_show_profile_relation_note_no_unsafe():
    """show_profile relation note에 unsafe phrase 없음."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙未", "time": "丁酉"}
    note = build_show_profile_relation_note(ec, max_lines=5)
    for phrase in _UNSAFE_PHRASES:
        assert phrase not in note, f"Unsafe phrase found: {phrase}"

# ---------------------------------------------------------------------------
# 8. 기존 Phase 13 회귀 확인
# ---------------------------------------------------------------------------

def test_regression_liu_he_still_works():
    """육합 탐지 회귀 없음."""
    ec = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.liu_he) >= 1  # 子·丑 육합

def test_regression_san_he_still_works():
    """삼합 탐지 회귀 없음."""
    ec = {"year": "甲申", "month": "乙子", "day": "丙辰", "time": "丁卯"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.san_he) >= 1  # 申·子·辰 삼합

def test_regression_liu_chong_still_works():
    """육충 탐지 회귀 없음."""
    ec = {"year": "甲子", "month": "乙午", "day": "丙寅", "time": "丁卯"}
    r = detect_relations(ec)
    assert r.ok
    assert len(r.liu_chong) >= 1  # 子·午 충

def test_has_any_relation_includes_xing_hai_po():
    """has_any_relation이 형/해/파 포함."""
    ec = {"year": "甲子", "month": "乙卯", "day": "丙申", "time": "丁亥"}
    r = detect_relations(ec)
    assert r.ok
    # 형 또는 해 또는 파 중 하나라도 있으면 has_any_relation=True
    if r.xing or r.hai or r.po:
        assert r.has_any_relation()
