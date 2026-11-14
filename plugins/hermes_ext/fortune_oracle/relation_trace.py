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

from typing import Dict, List, Optional

from hermes_ext.fortune_oracle.bazi_relations import (
    BaziRelationReport,
    detect_relations,
)
from hermes_ext.fortune_oracle.bazi_trace import (
    BaziRelationTrace,
    RelationSummary,
)

# 천간 합 (六合天干) — tiangan_he 추적용
_TIANGAN_HE_PAIRS = {
    "甲": "己", "乙": "庚", "丙": "辛",
    "丁": "壬", "戊": "癸",
}


# ---------------------------------------------------------------------------
# BaziRelationReport → BaziRelationTrace
# ---------------------------------------------------------------------------

def _detect_tiangan_he(eight_char: Dict[str, str]) -> List[str]:
    """천간 간의 합(天干合)을 탐지.

    Returns:
        [("甲己合", "토"), ("乙庚合", "금"), ...]
    """
    result: List[str] = []
    if not eight_char:
        return result

    stems = []
    for pillar_key in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar_key, "")
        if gz:
            stems.append(gz[0])

    # 천간 합화 오행 매핑
    he_element = {
        "甲己": "토", "乙庚": "금", "丙辛": "물",
        "丁壬": "목", "戊癸": "화",
    }

    for i, s1 in enumerate(stems):
        for s2 in stems[i + 1:]:
            pair = "".join(sorted([s1, s2], key=lambda x: "甲乙丙丁戊己庚辛壬癸".index(x) if x in "甲乙丙丁戊己庚辛壬癸" else 99))
            elem = he_element.get(pair, "")
            if elem:
                result.append(f"{pair}合({elem})")

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
    if not eight_char:
        return BaziRelationTrace()

    try:
        report = detect_relations(eight_char)
        if not report.ok:
            return BaziRelationTrace(warnings=["관계 탐지 실패"])
        return relation_report_to_trace(report)
    except Exception:
        return BaziRelationTrace(warnings=["관계 탐지 중 예외 발생"])
