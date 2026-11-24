#!/usr/bin/env python3
"""Fortune Oracle — Relation Trace helpers (Phase 36).

Structures the existing BaziRelationReport output into a traceable
format. Does NOT replace the relation detection engine — purely an
explainability layer.

Principles:
- Deterministic, fail-open
- No external network/AI calls
- No raw dataclass repr in user output
- No medical/investment/legal/career/parent determinative claims

This result is for self-reflection and option-checking reference only.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Dict, List
from .natal_pillars import confirmed_pillars

from hermes_ext.fortune_oracle.bazi_relations import (
    BaziRelationReport,
    detect_relations,
)
from hermes_ext.fortune_oracle.bazi_trace import (
    BaziRelationTrace,
    RelationSummary,
)

# 천간 오합의 문자 쌍만 대조한다. 합화 조건은 평가하지 않는다.
_TIANGAN_HE_PAIRS = {
    "甲": "己", "乙": "庚", "丙": "辛",
    "丁": "壬", "戊": "癸",
}
_PILLAR_LABELS = {"year": "년간", "month": "월간", "day": "일간", "time": "시간"}


def valid_trace_pillars(eight_char):
    """Return confirmed sexagenary pillars without guessing missing values."""
    if eight_char is None:
        return {}, []
    if not isinstance(eight_char, Mapping):
        return {}, ["팔자 입력 형식을 확인할 수 없어 근거 계산을 생략했습니다."]
    pillars, _, invalid = confirmed_pillars(eight_char)
    warnings = [f"{_PILLAR_LABELS[key]}의 간지 형식이 유효하지 않아 해당 기둥을 제외했습니다."
                for key in invalid]
    return pillars, warnings


# ---------------------------------------------------------------------------
# BaziRelationReport → BaziRelationTrace
# ---------------------------------------------------------------------------

def _detect_tiangan_he(eight_char: Dict[str, str]) -> List[str]:
    """Match stem pairs, retaining positions; no transformation inference."""
    result: List[str] = []
    pillars, _ = valid_trace_pillars(eight_char)
    stems = [(key, value[0]) for key, value in pillars.items()]
    for i, (key1, stem1) in enumerate(stems):
        for key2, stem2 in stems[i + 1:]:
            for first, second in _TIANGAN_HE_PAIRS.items():
                if (stem1, stem2) in ((first, second), (second, first)):
                    result.append(f"{_PILLAR_LABELS[key1]} {stem1} ↔ {_PILLAR_LABELS[key2]} {stem2} ({first}{second}合)")

    return result


def relation_report_to_trace(report: BaziRelationReport) -> BaziRelationTrace:
    """BaziRelationReport → BaziRelationTrace 변환.

    기존 BaziRelationReport를 구조화된 trace로 변환한다.
    계산 결과를 변경하지 않는다.
    """
    trace = BaziRelationTrace()
    if not report.ok:
        return trace

    # 지지 육합
    for entry in report.liu_he:
        b_str = "·".join(entry.branches)
        trace.dizhi_liuhe.append(f"{b_str}({entry.combined_element})")

    # 삼합
    for entry in report.san_he:
        b_str = "·".join(entry.branches)
        trace.sanhe.append(f"{b_str}({entry.combined_element})")

    # 반합 (warnings에서 추출)
    for w in report.warnings:
        if "반합" in w:
            trace.banhe.append(w)

    # 육충
    for entry in report.liu_chong:
        b_str = "·".join(entry.branches)
        trace.chong.append(b_str)

    # 형
    for entry in report.xing:
        b_str = "·".join(entry.branches)
        xing_type = entry.xing_type if entry.xing_type else ""
        trace.xing.append(f"{b_str}({xing_type})")

    # 자형
    for b in report.self_xing:
        trace.xing.append(f"{b}(자형)")

    # 해
    for entry in report.hai:
        b_str = "·".join(entry.branches)
        trace.hai.append(b_str)

    # 파
    for entry in report.po:
        b_str = "·".join(entry.branches)
        trace.po.append(b_str)

    # 중복 지지
    trace.repeated_branches = report.duplicate_branches

    # warnings
    trace.warnings = report.warnings

    return trace


# ---------------------------------------------------------------------------
# BaziRelationTrace → RelationSummary (BaziTrace용)
# ---------------------------------------------------------------------------

def trace_to_relation_summary(trace: BaziRelationTrace) -> RelationSummary:
    """BaziRelationTrace → RelationSummary (BaziTrace에 넣을 요약)."""
    return RelationSummary(
        liuhe=trace.dizhi_liuhe,
        sanhe=trace.sanhe,
        chong=trace.chong,
        xing=trace.xing,
        hai=trace.hai,
        po=trace.po,
        repeated_branches=trace.repeated_branches,
        tiangan_he=list(trace.tiangan_he),
    )


# ---------------------------------------------------------------------------
# End-to-end: eight_char → BaziRelationTrace
# ---------------------------------------------------------------------------

def detect_relation_trace(eight_char: Dict[str, str]) -> BaziRelationTrace:
    """eight_char → BaziRelationTrace (detect_relations + 구조화).

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}

    Returns:
        BaziRelationTrace
    """
    pillars, warnings = valid_trace_pillars(eight_char)
    if not pillars:
        return BaziRelationTrace(warnings=warnings)

    try:
        report = detect_relations(pillars)
        if not report.ok:
            return BaziRelationTrace(warnings=["관계 탐지 실패"])
        trace = relation_report_to_trace(report)
        trace.tiangan_he = _detect_tiangan_he(pillars)
        trace.warnings = [*warnings, *trace.warnings]
        return trace
    except Exception:
        return BaziRelationTrace(warnings=["관계 탐지 중 예외 발생"])
