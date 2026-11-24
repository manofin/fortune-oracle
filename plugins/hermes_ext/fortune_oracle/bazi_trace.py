#!/usr/bin/env python3
"""Fortune Oracle — Bazi Trace Layer (Phase 36).

Explainability layer that structures the reasoning behind existing bazi
interpretations. Does NOT replace the calculation engine.

Principles:
- Deterministic, fail-open
- No external network/AI calls
- No raw dataclass repr in user output
- No medical/investment/legal/career/parent determinative claims
- Every interpretation output includes a disclaimer

This result is for self-reflection and option-checking reference only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Core trace schemas
# ---------------------------------------------------------------------------

@dataclass
class TraceWarning:
    """A single warning in a trace."""
    message: str
    severity: str = "info"  # "info" | "warning" | "caution"


@dataclass
class ElementDistribution:
    """오행 분포 요약."""
    elements: Dict[str, int] = field(default_factory=dict)  # e.g. {"목": 2, "화": 3}
    dominant: List[str] = field(default_factory=list)        # 두드러진 오행


@dataclass
class TenGodSummary:
    """십신 요약."""
    summaries: List[str] = field(default_factory=list)  # e.g. ["甲 → 비견", "丙 → 식신"]


@dataclass
class HiddenStemSummary:
    """장간 요약."""
    summaries: List[str] = field(default_factory=list)  # e.g. ["丑: 己癸辛"]


@dataclass
class RelationSummary:
    """관계 note 요약."""
    liuhe: List[str] = field(default_factory=list)
    sanhe: List[str] = field(default_factory=list)
    chong: List[str] = field(default_factory=list)
    xing: List[str] = field(default_factory=list)
    hai: List[str] = field(default_factory=list)
    po: List[str] = field(default_factory=list)
    repeated_branches: List[str] = field(default_factory=list)
    # Append for compatibility with existing positional constructors.
    tiangan_he: List[str] = field(default_factory=list)


@dataclass
class YongshenTrace:
    """용신 판단 근거 보강 (기존 YongshenResult를 대체하지 않음).

    기존 계산 결과를 덮어쓰지 않고, 설명 근거만 계층화하여 보강한다.
    """
    primary_layer: str = ""        # 구조/격국 관점
    support_layer: str = ""        # 강약/부억 관점
    seasonal_layer: str = ""       # 계절/조후 관점
    hidden_stem_notes: List[str] = field(default_factory=list)
    final_hint: str = ""
    confidence: str = ""           # "rule_based_low" | "rule_based_medium"
    warnings: List[str] = field(default_factory=list)


@dataclass
class BaziRelationTrace:
    """기존 BaziRelationReport의 구조화 trace.

    기존 relation note와 충돌하지 않게 구조화만 한다.
    """
    tiangan_he: List[str] = field(default_factory=list)       # 천간 합
    dizhi_liuhe: List[str] = field(default_factory=list)      # 지지 육합
    sanhe: List[str] = field(default_factory=list)            # 삼합
    banhe: List[str] = field(default_factory=list)            # 반합
    chong: List[str] = field(default_factory=list)            # 육충
    xing: List[str] = field(default_factory=list)             # 형
    hai: List[str] = field(default_factory=list)              # 해
    po: List[str] = field(default_factory=list)               # 파
    repeated_branches: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TenGodTrace:
    """각 천간/지지별 십신 매핑 trace."""
    items: List[str] = field(default_factory=list)  # e.g. ["년천간 甲 → 비견", "월지지 丑 → 식신"]


@dataclass
class HiddenStemTrace:
    """각 지지별 장간 기여도 trace."""
    items: List[str] = field(default_factory=list)  # e.g. ["丑: 己(식신)·癸(편재)·辛(편인)"]


@dataclass
class BaziTrace:
    """전체 사주 해석의 근거 요약.

    기존 계산 엔진의 결과를 입력받아 구조화된 근거를 생성한다.
    계산 결과 자체는 변경하지 않는다.
    """
    day_master: str = ""
    pillars_summary: str = ""              # 네 기둥 요약 (e.g. "年甲子 月乙丑 日丙寅 時丁卯")
    element_distribution: ElementDistribution = field(default_factory=ElementDistribution)
    ten_god_summary: TenGodSummary = field(default_factory=TenGodSummary)
    hidden_stem_summary: HiddenStemSummary = field(default_factory=HiddenStemSummary)
    relation_summary: RelationSummary = field(default_factory=RelationSummary)
    yongshen_trace: Optional[YongshenTrace] = None
    confidence: str = ""                    # "rule_based_low" | "rule_based_medium" | "partial"
    completeness: float = 0.0              # 0.0 ~ 1.0, trace의 완성도
    warnings: List[TraceWarning] = field(default_factory=list)

    # ── convenience ──────────────────────────────────────────────

    def has_any_relation(self) -> bool:
        """관계 trace 중 하나라도 있는가."""
        rs = self.relation_summary
        return bool(rs.tiangan_he or rs.liuhe or rs.sanhe or rs.chong or rs.xing or rs.hai or rs.po)

    def get_warnings_text(self) -> List[str]:
        """TraceWarning → plain text 리스트."""
        return [w.message for w in self.warnings]

# ---------------------------------------------------------------------------
# Compact formatter helpers
# ---------------------------------------------------------------------------

def _element_distribution_text(dist: ElementDistribution) -> str:
    """오행 분포를 compact text로."""
    if not dist.elements:
        return ""
    parts = []
    for elem in ("목", "화", "토", "금", "수"):
        count = dist.elements.get(elem, 0)
        if count > 0:
            parts.append(f"{elem} {count}")
    return " · ".join(parts)


def _relation_summary_text(rs: RelationSummary) -> List[str]:
    """관계 요약을 bullet 리스트로."""
    lines: List[str] = []
    for entry in rs.liuhe:
        lines.append(f"육합: {entry}")
    for entry in rs.sanhe:
        lines.append(f"삼합: {entry}")
    for entry in rs.chong:
        lines.append(f"충: {entry}")
    for entry in rs.xing:
        lines.append(f"형: {entry}")
    for entry in rs.hai:
        lines.append(f"해: {entry}")
    for entry in rs.po:
        lines.append(f"파: {entry}")
    if rs.repeated_branches:
        lines.append(f"반복: {'·'.join(rs.repeated_branches)}")
    return lines


def build_trace_summary(
    trace: BaziTrace,
    max_lines: int = 5,
) -> str:
    """BaziTrace → /show_profile 하단에 붙일 compact 근거 요약.

    raw dataclass repr을 출력하지 않는다.
    """
    if not trace.day_master and not trace.warnings and not trace.pillars_summary:
        return ""

    lines: List[str] = []
    if trace.day_master:
        lines.append(f"일간: {trace.day_master}")
    if trace.warnings:
        lines.append("입력 범위: " + " ".join(trace.get_warnings_text()))

    elem_text = _element_distribution_text(trace.element_distribution)
    if elem_text:
        lines.append(f"오행 분포: {elem_text}")

    # Keep all matched positions on one line even in the compact command output.
    if trace.relation_summary.tiangan_he:
        lines.append("관계 참고: 천간합: " + " · ".join(trace.relation_summary.tiangan_he)
                     + " — 문자 쌍 대조이며 합화 성립·관계 의미는 판정하지 않았습니다.")

    # 장간 참고 (최대 2개)
    for note in trace.hidden_stem_summary.summaries[:2]:
        lines.append(f"장간 참고: {note}")

    for entry in _relation_summary_text(trace.relation_summary)[:2]:
        lines.append(f"관계 참고: {entry}")

    # 용신 참고 (1줄)
    yt = trace.yongshen_trace
    if yt and yt.final_hint:
        lines.append(f"용신 참고: {yt.final_hint}")

    # truncate to max_lines bullet items
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    body = "\n".join(f"- {l}" for l in lines)
    return f"해석 근거\n{body}"


# ---------------------------------------------------------------------------
# YongshenResult → YongshenTrace
# ---------------------------------------------------------------------------

def yongshen_result_to_trace(yongshen_result) -> YongshenTrace:
    """YongshenResult → YongshenTrace 변환.

    기존 YongshenResult를 덮어쓰지 않고, 설명 근거만 계층화하여 보강한다.
    """
    trace = YongshenTrace()
    if not yongshen_result or not yongshen_result.ok:
        return trace

    # primary_layer: 구조/격국 관점
    dominant = [e for e, c in yongshen_result.strength_score.items() if c >= 2.0]
    if dominant:
        trace.primary_layer = f"{'/'.join(dominant)} 기운이 두드러진 구조"
    else:
        trace.primary_layer = "특정 오행이 두드러지지 않은 균형 구조"

    # support_layer: 강약/부억 관점
    strength_map = {"strong": "강", "balanced": "중", "weak": "약"}
    trace.support_layer = f"일간 {yongshen_result.day_master_element}이(가) {strength_map.get(yongshen_result.strength, yongshen_result.strength)} — "
    if yongshen_result.strength == "weak":
        trace.support_layer += "생조(生助) 기운이 도움"
    elif yongshen_result.strength == "strong":
        trace.support_layer += "설기(泄氣)/극 기운이 균형"
    else:
        trace.support_layer += "상생 흐름이 안정을 유지"

    # seasonal_layer: 계절/조후 관점
    if yongshen_result.season:
        trace.seasonal_layer = f"{yongshen_result.season}계절 기준 조후"

    # hidden_stem_notes
    trace.hidden_stem_notes = yongshen_result.hidden_stems_contribution

    # final_hint
    if yongshen_result.favorable_elements:
        trace.final_hint = f"{'/'.join(yongshen_result.favorable_elements)} 보완 권장"

    # confidence
    trace.confidence = yongshen_result.confidence

    # warnings
    trace.warnings = yongshen_result.warnings

    return trace


# ---------------------------------------------------------------------------
# Full BaziTrace builder (end-to-end)
# ---------------------------------------------------------------------------

def build_bazi_trace(
    eight_char: dict,
    day_master_stem: str = "",
    yongshen_result=None,
) -> "BaziTrace":
    """eight_char → BaziTrace (전체 근거 요약 생성).

    기존 계산 엔진의 결과를 입력받아 구조화된 근거를 생성한다.
    계산 결과 자체는 변경하지 않는다.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        day_master_stem: 일간 천간 (e.g. "丙"). 비어 있으면 eight_char에서 추출
        yongshen_result: YongshenResult (선택). 있으면 YongshenTrace 보강

    Returns:
        BaziTrace
    """
    from hermes_ext.fortune_oracle.yongshen import count_elements_from_eight_char
    from hermes_ext.fortune_oracle.relation_trace import valid_trace_pillars

    trace = BaziTrace()
    eight_char, input_warnings = valid_trace_pillars(eight_char)
    trace.warnings = [TraceWarning(message, "warning") for message in input_warnings]
    if not eight_char:
        return trace

    # 일간 추출
    trace.day_master = eight_char.get("day", "")[:1]
    if day_master_stem and day_master_stem != trace.day_master:
        trace.warnings.append(TraceWarning("별도 일간 값이 확인된 일주와 일치하지 않아 사용하지 않았습니다.", "warning"))

    # 네 기둥 요약
    pillar_labels = {"year": "年", "month": "月", "day": "日", "time": "時"}
    pillars = []
    for key, label in pillar_labels.items():
        gz = eight_char.get(key, "")
        if gz:
            pillars.append(f"{label}{gz}")
    trace.pillars_summary = " ".join(pillars)

    # 오행 분포
    try:
        elem_counts = count_elements_from_eight_char(eight_char)
        trace.element_distribution = ElementDistribution(
            elements=elem_counts,
            dominant=[e for e, c in elem_counts.items() if c >= 2],
        )
    except Exception:
        pass

    # 십신 요약
    if trace.day_master:
        try:
            from hermes_ext.fortune_oracle.ten_god_trace import (
                build_ten_god_summary,
                build_hidden_stem_summary,
            )
            trace.ten_god_summary = build_ten_god_summary(eight_char, trace.day_master)
            trace.hidden_stem_summary = build_hidden_stem_summary(eight_char, trace.day_master)
        except Exception:
            pass

    # 관계 요약
    try:
        from hermes_ext.fortune_oracle.relation_trace import (
            detect_relation_trace,
            trace_to_relation_summary,
        )
        rel_trace = detect_relation_trace(eight_char)
        trace.relation_summary = trace_to_relation_summary(rel_trace)
    except Exception:
        pass

    # 용신 trace 보강
    if yongshen_result:
        try:
            trace.yongshen_trace = yongshen_result_to_trace(yongshen_result)
        except Exception:
            pass

    # confidence
    if yongshen_result and yongshen_result.ok:
        trace.confidence = yongshen_result.confidence
    else:
        trace.confidence = "partial"

    # completeness (trace 필드의 채움 정도)
    filled = 0
    total = 6  # day_master, pillars, elements, ten_god, hidden_stem, relation
    if trace.day_master:
        filled += 1
    if trace.pillars_summary:
        filled += 1
    if trace.element_distribution.elements:
        filled += 1
    if trace.ten_god_summary.summaries:
        filled += 1
    if trace.hidden_stem_summary.summaries:
        filled += 1
    if trace.has_any_relation() or trace.relation_summary.repeated_branches:
        filled += 1
    trace.completeness = round(filled / total, 2)

    return trace
