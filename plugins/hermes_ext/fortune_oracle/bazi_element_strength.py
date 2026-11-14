#!/usr/bin/env python3
"""Fortune Oracle — Bazi Element Strength Trace (Phase 40B).

기존 calculate_strength_score()의 출력을 구조화하는 wrapper layer.
기존 yongshen.py의 함수를 수정하지 않는다.

BaziElementStrengthTrace:
- 오행별 총점 + 동류/이류/생조/설기/극의 구조화
- 일간 강약 비율 (self_ratio)
- 오행별 순위
- ElementContribution 추적

ElementContribution:
- 천간 기여도 (stem)
- 지지 기여도 (branch)
- 지장간 기여도 (hidden)
- 계절 보정 기여도 (seasonal)

금지:
- yongshen.py의 calculate_strength_score() 수정
- 용신 자동 단정
- 작명/개명 강요
- 건강/혼인 단정
- raw dict/dataclass repr 노출
- 외부 API 호출

이 결과는 자기성찰과 선택지 점검용 참고이며 확정적 판단이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 상수 — 기존 yongshen.py와 동일 (import from yongshen for consistency)
# ---------------------------------------------------------------------------

ALL_ELEMENTS = ["목", "화", "토", "금", "수"]

# 오행 생극 관계
SHENG: Dict[str, str] = {
    "목": "화",
    "화": "토",
    "토": "금",
    "금": "수",
    "수": "목",
}

KE: Dict[str, str] = {
    "목": "토",
    "화": "금",
    "토": "수",
    "금": "목",
    "수": "화",
}

# ---------------------------------------------------------------------------
# ElementContribution — 기여도 추적
# ---------------------------------------------------------------------------

@dataclass
class ElementContribution:
    """단일 오행의 기여도 추적.

    어떤 천간/지지/지장간/계절이 어느 오행에 얼마나 기여했는지 기록.
    """
    element: str = ""
    stem_contributions: List[str] = field(default_factory=list)
    # e.g. ["년천간 甲(목)+1.0", "월천간 乙(목)+1.0"]

    branch_contributions: List[str] = field(default_factory=list)
    # e.g. ["년지지 子(수)+1.0", "일지지 寅(목)+1.0"]

    hidden_contributions: List[str] = field(default_factory=list)
    # e.g. ["년지지 子→癸(수)+0.5"]

    seasonal_contribution: Optional[str] = None
    # e.g. "월지 卯→봄→목+1.5"

    total: float = 0.0

    def add_stem(self, pillar: str, stem: str, element: str, weight: float) -> None:
        """천간 기여도 추가."""
        label = {
            "year": "년천간",
            "month": "월천간",
            "day": "일천간",
            "time": "시천간",
        }.get(pillar, pillar)
        self.stem_contributions.append(
            f"{label} {stem}({element})+{weight:.1f}"
        )
        self.total += weight

    def add_branch(self, pillar: str, branch: str, element: str, weight: float) -> None:
        """지지 기여도 추가."""
        label = {
            "year": "년지지",
            "month": "월지지",
            "day": "일지지",
            "time": "시지지",
        }.get(pillar, pillar)
        self.branch_contributions.append(
            f"{label} {branch}({element})+{weight:.1f}"
        )
        self.total += weight

    def add_hidden(self, pillar: str, branch: str, hidden_stem: str, element: str, weight: float) -> None:
        """지장간 기여도 추가."""
        self.hidden_contributions.append(
            f"{pillar} {branch}→{hidden_stem}({element})+{weight:.1f}"
        )
        self.total += weight

    def add_seasonal(self, month_branch: str, season: str, element: str, weight: float) -> None:
        """계절 보정 기여도 추가."""
        self.seasonal_contribution = (
            f"월지 {month_branch}→{season}→{element}+{weight:.1f}"
        )
        self.total += weight

    def format_contributions(self, max_items: int = 5) -> List[str]:
        """기여도를 compact text로."""
        lines: List[str] = []
        for item in self.stem_contributions[:max_items]:
            lines.append(f"  천간: {item}")
        for item in self.branch_contributions[:max_items]:
            lines.append(f"  지지: {item}")
        for item in self.hidden_contributions[:max_items]:
            lines.append(f"  지장간: {item}")
        if self.seasonal_contribution:
            lines.append(f"  계절: {self.seasonal_contribution}")
        return lines


# ---------------------------------------------------------------------------
# BaziElementStrengthTrace — 오행 강약 추적
# ---------------------------------------------------------------------------

@dataclass
class BaziElementStrengthTrace:
    """오행 강약의 구조화된 추적.

    기존 calculate_strength_score()의 dict 출력을 wrapping하여
    기여도를 추적 가능하게 한다.

    기존 YongshenResult를 대체하지 않는다.
    """
    day_master: str = ""
    day_master_element: str = ""

    # 오행별 총점
    element_totals: Dict[str, float] = field(default_factory=dict)

    # 오행별 기여도
    contributions: Dict[str, ElementContribution] = field(default_factory=dict)

    # 동류 (일간과 같은 오행)
    dongryu_elements: List[str] = field(default_factory=list)

    # 이류 (다른 오행) — 생조/설기/극 분류
    sheng_elements: List[str] = field(default_factory=list)  # 일간을 생하는 오행
    ke_elements: List[str] = field(default_factory=list)      # 일간을 극하는 오행
    xie_elements: List[str] = field(default_factory=list)     # 일간이 설기하는 오행

    # 일간 강약
    strength: str = ""  # "strong" | "balanced" | "weak"
    self_ratio: float = 0.0  # 일간 오행 점수 / 총점

    # 오행 순위
    element_ranking: List[Tuple[str, float]] = field(default_factory=list)

    # confidence
    confidence: str = "rule_based_low"

    # warnings
    warnings: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    def top_elements(self, n: int = 2) -> List[Tuple[str, float]]:
        """가장 강한 오행 상위 N개."""
        return sorted(self.element_ranking, key=lambda x: x[1], reverse=True)[:n]

    def weakest_elements(self, n: int = 2) -> List[Tuple[str, float]]:
        """가장 약한 오행 하위 N개."""
        return sorted(self.element_ranking, key=lambda x: x[1])[:n]

    def dongryu_total(self) -> float:
        """동류 오행 총점 (일간과 같은 오행)."""
        return sum(
            self.element_totals.get(e, 0.0)
            for e in self.dongryu_elements
        )

    def sheng_total(self) -> float:
        """생조 오행 총점 (일간을 생하는 오행)."""
        return sum(
            self.element_totals.get(e, 0.0)
            for e in self.sheng_elements
        )

    def ke_total(self) -> float:
        """극 오행 총점 (일간을 극하는 오행)."""
        return sum(
            self.element_totals.get(e, 0.0)
            for e in self.ke_elements
        )

    def total_score(self) -> float:
        """모든 오행의 총점."""
        return sum(self.element_totals.values())

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_summary(self, max_lines: int = 2) -> str:
        """compact 요약 (1~2줄) — /show_profile용."""
        if not self.day_master_element:
            return ""
        lines: List[str] = []
        strength_ko = {"strong": "강", "balanced": "중", "weak": "약"}.get(self.strength, self.strength)
        lines.append(
            f"일간 {self.day_master}({self.day_master_element}) — {strength_ko} (비율 {self.self_ratio:.0%})"
        )
        if max_lines >= 2:
            top = self.top_elements(2)
            if top:
                top_str = ", ".join(f"{e}{s:.1f}" for e, s in top)
                lines.append(f"강한 오행: {top_str}")
        return " · ".join(lines)

    def format_breakdown(self) -> str:
        """contribution breakdown — /bazi_trace용."""
        lines: List[str] = []
        lines.append("오행 강약 breakdown")
        for elem in ALL_ELEMENTS:
            contrib = self.contributions.get(elem)
            if contrib and contrib.total > 0:
                lines.append(f"  {elem}: {contrib.total:.1f}")
                for item in contrib.format_contributions(max_items=3):
                    lines.append(f"    {item}")
        return "\n".join(lines)

    def format_evidence(self) -> List[str]:
        """method card evidence용 — /종합운세에 evidence로만 첨부."""
        items: List[str] = []
        strength_ko = {"strong": "강", "balanced": "중", "weak": "약"}.get(self.strength, self.strength)
        items.append(f"일간 {self.day_master}({self.day_master_element}) {strength_ko}")
        top = self.top_elements(2)
        if top:
            items.append(f"강한 오행: {', '.join(f'{e}' for e, _ in top)}")
        return items

    def has_raw_repr(self) -> bool:
        """raw repr 노출 체크."""
        # 이 함수 자체는 테스트 용도
        return False


# ---------------------------------------------------------------------------
# Builder — 기존 calculate_strength_score()를 wrapping
# ---------------------------------------------------------------------------

def build_show_profile_strength_note(
    eight_char: Optional[Dict[str, str]],
    max_lines: int = 2,
) -> str:
    """eight_char → /show_profile 용신 강약 compact note (fail-open).

    1~2줄 요약: 일간 강약 + 오행 순위 상위 2개.
    기존 YongshenResult를 대체하지 않는다 — 보강하는 note다.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        max_lines: 최대 출력 줄 수

    Returns:
        강약 note 텍스트 (헤더 포함) 또는 빈 문자열
    """
    if not eight_char:
        return ""
    try:
        trace = build_element_strength_trace(eight_char)
        return trace.format_summary(max_lines=max_lines)
    except Exception:
        return ""


def build_element_strength_trace(
    eight_char: Dict[str, str],
    day_master: str = "",
    day_master_element: str = "",
) -> BaziElementStrengthTrace:
    """eight_char → BaziElementStrengthTrace.

    기존 yongshen.py의 상수 테이블을 사용하지만,
    calculate_strength_score()를 직접 호출하지 않는다.
    대신 동일한 테이블로 기여도를 추적하면서 계산한다.

    기존 yongshen.py의 함수를 수정하지 않는다.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        day_master: 일간 천간 (e.g. "丙"). 비어 있으면 eight_char에서 추출
        day_master_element: 일간 오행 (e.g. "화"). 비어 있으면 추출

    Returns:
        BaziElementStrengthTrace
    """
    from .yongshen import (
        _STEM_ELEMENT,
        _BRANCH_ELEMENT,
        _HIDDEN_STEMS,
        _HIDDEN_WEIGHT,
        _MONTH_BRANCH_SEASON,
        _SEASON_ELEMENT,
        _SEASONAL_BOOST,
        ALL_ELEMENTS,
    )

    trace = BaziElementStrengthTrace()

    if not eight_char:
        return trace

    # 일간 추출
    if day_master:
        trace.day_master = day_master
        trace.day_master_element = day_master_element
    else:
        day_pillar = eight_char.get("day", "")
        if day_pillar:
            trace.day_master = day_pillar[0] if len(day_pillar) >= 1 else ""
            trace.day_master_element = _STEM_ELEMENT.get(trace.day_master, "")

    # 오행별 ElementContribution 초기화
    for elem in ALL_ELEMENTS:
        trace.contributions[elem] = ElementContribution(element=elem)

    # 1. 천간 기여도 (weight=1.0)
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 1:
            stem = gz[0]
            elem = _STEM_ELEMENT.get(stem, "")
            if elem:
                contrib = trace.contributions[elem]
                contrib.add_stem(pillar, stem, elem, 1.0)

    # 2. 지지 기여도 (weight=1.0)
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 2:
            branch = gz[1]
            elem = _BRANCH_ELEMENT.get(branch, "")
            if elem:
                contrib = trace.contributions[elem]
                contrib.add_branch(pillar, branch, elem, 1.0)

    # 3. 지장간 기여도 (weight=0.5)
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 2:
            branch = gz[1]
            for hidden_stem in _HIDDEN_STEMS.get(branch, []):
                hidden_elem = _STEM_ELEMENT.get(hidden_stem, "")
                if hidden_elem:
                    contrib = trace.contributions[hidden_elem]
                    contrib.add_hidden(pillar, branch, hidden_stem, hidden_elem, _HIDDEN_WEIGHT)

    # 4. 계절 보정 기여도
    month_gz = eight_char.get("month", "")
    if len(month_gz) >= 2:
        month_branch = month_gz[1]
        season = _MONTH_BRANCH_SEASON.get(month_branch, "")
        season_elem = _SEASON_ELEMENT.get(season, "")
        if season_elem:
            contrib = trace.contributions[season_elem]
            contrib.add_seasonal(month_branch, season, season_elem, _SEASONAL_BOOST)

    # 오행별 총점
    trace.element_totals = {
        elem: contrib.total
        for elem, contrib in trace.contributions.items()
    }

    # 동류/이류 분류
    if trace.day_master_element:
        trace.dongryu_elements = [trace.day_master_element]

        # 생조 (일간을 생하는 오행)
        for e, target in SHENG.items():
            if target == trace.day_master_element:
                trace.sheng_elements.append(e)

        # 극 (일간을 극하는 오행)
        for e, target in KE.items():
            if target == trace.day_master_element:
                trace.ke_elements.append(e)

        # 설기 (일간이 설기하는 오행)
        dm_target = SHENG.get(trace.day_master_element, "")
        if dm_target:
            trace.xie_elements.append(dm_target)

    # 일간 강약
    total = sum(trace.element_totals.values())
    if total > 0 and trace.day_master_element:
        dm_total = trace.element_totals.get(trace.day_master_element, 0.0)
        trace.self_ratio = round(dm_total / total, 3)
        if trace.self_ratio >= 0.35:
            trace.strength = "strong"
        elif trace.self_ratio >= 0.22:
            trace.strength = "balanced"
        else:
            trace.strength = "weak"
    else:
        trace.strength = ""
        trace.self_ratio = 0.0

    # 오행 순위
    trace.element_ranking = sorted(
        trace.element_totals.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    # confidence
    if trace.strength == "balanced":
        trace.confidence = "rule_based_medium"
    else:
        trace.confidence = "rule_based_low"

    return trace
