#!/usr/bin/env python3
"""Fortune Oracle — Yongshen Tonggwan (通關法) Wrapper (Gate 3.4).

팔자 내 오행 극(剋) 충돌 구조 탐지 및 통관 오행 도출.
wrapper 계층 전용 신규 파일.

- A가 B를 극하는 관계가 실제 팔자에 존재할 때만 충돌로 인정.
- 충돌 발견 시 A와 B를 중재하는 통관 오행 자동 도출 (A → 통관 → B 구조).
- 충돌 없거나 통관 오행이 도출되지 않으면 None 반환 (fail-open).
- 억부/조후와 완전 병렬 제시, 어떤 결과도 덮어쓰지 않음.

기존 yongshen.py의 어떤 계산 로직도 사용/수정하지 않음 (상수 import만).

이 결과는 rule-based 참고이며, 기존 용신과 병렬로만 사용하십시오.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .yongshen import (
    ALL_ELEMENTS,
    _KE,
    _SHENG,
    _STEM_ELEMENT,
    _BRANCH_ELEMENT,
)

@dataclass
class TonggwanAnalysis:
    ok: bool = False
    conflicts: List[Tuple[str, str]] = field(default_factory=list)  # (controller, controlled)
    tonggwan_element: Optional[str] = None
    reasoning: List[str] = field(default_factory=list)
    confidence_label: str = "rule_based_low"
    disclaimer: str = "이 통관법 분석은 rule-based 참고이며, 억부/조후와 병렬 제시됩니다. 충돌 구조가 없거나 중재 오행을 찾을 수 없으면 None을 반환합니다."
    warnings: List[str] = field(default_factory=list)


def _collect_present_elements(eight_char: Dict[str, str]) -> set:
    """팔자에 실제 존재하는 오행 집합 (천간 + 지지)."""
    present: set = set()
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 1:
            elem = _STEM_ELEMENT.get(gz[0])
            if elem:
                present.add(elem)
        if len(gz) >= 2:
            elem = _BRANCH_ELEMENT.get(gz[1])
            if elem:
                present.add(elem)
    return present


def build_tonggwan_analysis(eight_char: Dict[str, str]) -> TonggwanAnalysis:
    """eight_char → TonggwanAnalysis (극 충돌 탐지 + 통관 도출, fail-open)."""
    if not eight_char:
        return TonggwanAnalysis(ok=False, warnings=["eight_char 없음"])

    present = _collect_present_elements(eight_char)
    if not present:
        return TonggwanAnalysis(ok=True, warnings=["오행 정보 부족"])

    conflicts: List[Tuple[str, str]] = []
    for controller, controlled in _KE.items():
        if controller in present and controlled in present:
            conflicts.append((controller, controlled))

    if not conflicts:
        return TonggwanAnalysis(
            ok=True,
            conflicts=[],
            tonggwan_element=None,
            reasoning=["극(剋) 충돌 구조가 팔자 내에 존재하지 않음"],
            confidence_label="rule_based_low",
        )

    # 충돌이 있으면 첫 번째 충돌에 대해 통관 도출 시도
    # 통관 = controller가 생하는 오행 (A → 통관 → B)
    controller, controlled = conflicts[0]
    tonggwan = _SHENG.get(controller)

    reasoning = [
        f"통관법: {controller}이(가) {controlled}을(를) 극하는 충돌 구조 탐지",
    ]

    if tonggwan and tonggwan in present:
        reasoning.append(f"중재 오행(通關): {tonggwan} ({controller} → {tonggwan} → {controlled})")
        tonggwan_result = tonggwan
        conf = "rule_based_medium"
    else:
        reasoning.append("중재 가능한 통관 오행을 팔자 내에서 찾을 수 없음")
        tonggwan_result = None
        conf = "rule_based_low"

    return TonggwanAnalysis(
        ok=True,
        conflicts=conflicts,
        tonggwan_element=tonggwan_result,
        reasoning=reasoning,
        confidence_label=conf,
    )


def build_tonggwan_note(analysis: TonggwanAnalysis, max_lines: int = 4) -> str:
    """TonggwanAnalysis → compact note (병렬 제시용)."""
    if not analysis.ok:
        return ""

    lines: List[str] = []
    if analysis.tonggwan_element:
        lines.append(f"통관법: {analysis.tonggwan_element} (중재)")
    else:
        lines.append("통관법: 충돌 구조 없음 또는 중재 오행 미발견 (None)")

    for line in analysis.reasoning[:2]:
        lines.append(f"  {line}")

    lines.append(analysis.disclaimer)

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n[통관법 참고]\n{body}"


def build_show_profile_tonggwan_note(eight_char: Optional[Dict[str, str]], max_lines: int = 2) -> str:
    """fail-open wrapper."""
    if not eight_char:
        return ""
    try:
        analysis = build_tonggwan_analysis(eight_char)
        return build_tonggwan_note(analysis, max_lines=max_lines)
    except Exception:
        return ""
