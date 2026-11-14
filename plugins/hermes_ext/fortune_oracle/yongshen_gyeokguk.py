#!/usr/bin/env python3
"""Fortune Oracle — Yongshen Gyeokguk (格局) 1차 매핑 Wrapper (Gate 3.5).

월지 장간 1차 매핑만 구현.
투출(透出) 여부 판단은 이번 범위에서 완전 제외.

wrapper 계층 전용.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .yongshen import _HIDDEN_STEMS, _STEM_ELEMENT

_SIMPLE_GYEOKGUK_RULES = [
    "건록격", "양인격", "정인격", "편인격",
    "식신격", "상관격", "정재격", "편재격"
]

_INTERNAL_GYEOKGUK_MAP = {
    "건록격": lambda dm, hidden: bool(hidden) and hidden[0] == dm,
    "양인격": lambda dm, hidden: bool(hidden) and hidden[0] in ["丙", "戊", "庚", "壬"] and hidden[0] != dm,
    "정인격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "목" and dm in ["丙", "丁"],
    "편인격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "토" and dm in ["丙", "丁"],
    "식신격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "화" and dm in ["甲", "乙"],
    "상관격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "토" and dm in ["甲", "乙"],
    "정재격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "금" and dm in ["甲", "乙"],
    "편재격": lambda dm, hidden: bool(hidden) and _STEM_ELEMENT.get(hidden[0]) == "수" and dm in ["甲", "乙"],
}

@dataclass
class GyeokgukAnalysis:
    ok: bool = False
    month_branch: str = ""
    primary_hidden_stem: str = ""
    gyeokguk: Optional[str] = None
    reasoning: List[str] = field(default_factory=list)
    confidence_label: str = "rule_based_low"
    disclaimer: str = (
        "이 격국 분석은 월지 장간 1차 매핑만을 기준으로 한 rule-based 참고입니다. "
        "투출(透出) 여부 판단은 포함되지 않으며, 실제 격국 판단에는 한계가 있습니다. "
        "억부·조후·통관 결과와 병렬로 참고하십시오."
    )
    warnings: List[str] = field(default_factory=list)


def build_gyeokguk_analysis(eight_char: Dict[str, str]) -> GyeokgukAnalysis:
    """월지 장간 1차 매핑만 수행 (투출 판단 없음)."""
    if not eight_char:
        return GyeokgukAnalysis(ok=False, warnings=["eight_char 없음"])

    month_gz = eight_char.get("month", "")
    if len(month_gz) < 2:
        return GyeokgukAnalysis(ok=True, warnings=["월지 정보 부족"])

    branch = month_gz[1]
    hidden = _HIDDEN_STEMS.get(branch, [])
    if not hidden:
        return GyeokgukAnalysis(ok=True, warnings=["지장간 정보 없음"])

    primary_hidden = hidden[0]
    day_stem = eight_char.get("day", "")[:1] if eight_char.get("day") else ""

    gyeokguk = None
    reasoning = [f"월지 {branch} 주 지장간: {primary_hidden} (1차 매핑)"]

    for name in _SIMPLE_GYEOKGUK_RULES:
        func = _INTERNAL_GYEOKGUK_MAP.get(name)
        if func and func(day_stem, hidden):
            gyeokguk = name
            reasoning.append(f"1차 매핑 결과: {name}")
            break

    if not gyeokguk:
        reasoning.append("1차 매핑으로 해당 내격을 특정할 수 없음")

    return GyeokgukAnalysis(
        ok=True,
        month_branch=branch,
        primary_hidden_stem=primary_hidden,
        gyeokguk=gyeokguk,
        reasoning=reasoning,
        confidence_label="rule_based_low",
    )


def build_gyeokguk_note(analysis: GyeokgukAnalysis, max_lines: int = 4) -> str:
    if not analysis.ok:
        return ""

    lines = [f"격국(1차 매핑): {analysis.gyeokguk or '미식별'}"]
    lines.extend([f"  {r}" for r in analysis.reasoning[:2]])
    lines.append(analysis.disclaimer)

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n[격국 참고]\n{body}"


def build_show_profile_gyeokguk_note(eight_char: Optional[Dict[str, str]], max_lines: int = 2) -> str:
    if not eight_char:
        return ""
    try:
        analysis = build_gyeokguk_analysis(eight_char)
        return build_gyeokguk_note(analysis, max_lines=max_lines)
    except Exception:
        return ""
