#!/usr/bin/env python3
"""Fortune Oracle — Yongshen Eopbu (抑扶法) Advanced Wrapper (Gate 3.2).

기존 yongshen.py / calculate_yongshen() 절대 수정 금지.
bazi_element_strength.py의 trace를 재사용하여 3단계 억부법 고도화.

3단계 로직:
1. Detailed strength judgment (self_ratio + sheng/ke/xie/seasonal + hidden support 종합)
2. Shenqiang(身强)/Shenruo(身弱)/Junghwa(中和) 분류 (기존 ratio보다 정교한 신호 사용)
3. 전통 억부 용신 선택 (신약: 印+比, 신강: 食傷+官, 중화: 상생 흐름)

모든 결과는 "rule-based 참고"이며, 기존 YongshenResult를 대체하지 않는다.
병렬 분석으로만 제공. numeric confidence는 Gate 3.6에서.

금지:
- yongshen.py의 어떤 함수도 수정/호출하지 않음 (상수 import만)
- 기존 build_yongshen_note / calculate_yongshen 출력 변경 금지
- 용신 자동 단정, 작명/건강/투자 지시 금지
- raw dataclass repr 노출 금지
- 외부 API 호출 금지

이 결과는 자기성찰과 선택지 점검용 참고입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .bazi_element_strength import (
    BaziElementStrengthTrace,
    build_element_strength_trace,
)
from .yongshen import (
    ALL_ELEMENTS,
    _KE,
    _SHENG,
    _STEM_ELEMENT,
)

# ---------------------------------------------------------------------------#
# Eopbu 분석 결과
# ---------------------------------------------------------------------------#

@dataclass
class EopbuAnalysis:
    ok: bool = False
    day_master_element: str = ""
    eopbu_strength: str = ""          # "신강" | "신약" | "중화" | "unknown"
    eopbu_favorable: List[str] = field(default_factory=list)
    eopbu_caution: List[str] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    confidence_label: str = "rule_based_low"
    disclaimer: str = "이 억부법 분석은 rule-based 참고이며, 전통 정통 판정이 아닙니다. 기존 용신 결과와 병렬로 참고하십시오."
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------#
# 1단계: 상세 강약 판단 (trace 기반 다중 신호)
# ---------------------------------------------------------------------------#

def _detailed_strength_judgment(trace: BaziElementStrengthTrace) -> Dict[str, float]:
    """기존 ratio + 추가 신호로 정교한 판단 지표 반환."""
    if not trace.day_master_element or trace.total_score() <= 0:
        return {"ratio": 0.0, "pressure": 0.0, "support": 0.0, "seasonal_align": 0.0}

    dm = trace.day_master_element
    total = trace.total_score()
    self_score = trace.element_totals.get(dm, 0.0)
    ratio = self_score / total if total > 0 else 0.0

    # 생조 (지원)
    support = trace.sheng_total() + trace.dongryu_total()

    # 압력 (극 + 설기 반대)
    pressure = trace.ke_total()

    # 계절 정렬 (월지 계절이 일간을 도와주는가) — trace의 ElementContribution 사용
    seasonal_align = 0.0
    dm_contrib = trace.contributions.get(dm)
    if dm_contrib and dm_contrib.seasonal_contribution:
        if dm in dm_contrib.seasonal_contribution:
            seasonal_align = 0.8
        else:
            seasonal_align = 0.3

    return {
        "ratio": round(ratio, 3),
        "pressure": round(pressure / total, 3) if total > 0 else 0.0,
        "support": round(support / total, 3) if total > 0 else 0.0,
        "seasonal_align": round(seasonal_align, 2),
    }


# ---------------------------------------------------------------------------#
# 2단계: 신강/신약/중화 분류 (3단계 정교화)
# ---------------------------------------------------------------------------#

def _classify_shenqiang_shenruo(judgment: Dict[str, float], dm_element: str) -> str:
    """ratio + pressure/support/seasonal 종합으로 신강/신약/중화 판정."""
    ratio = judgment.get("ratio", 0.0)
    pressure = judgment.get("pressure", 0.0)
    support = judgment.get("support", 0.0)
    seasonal = judgment.get("seasonal_align", 0.0)

    # 기존 0.35/0.22 기준을 기본으로 하되, 다중 신호 보정
    base = "중화"
    if ratio >= 0.38 or (ratio >= 0.32 and support > pressure * 1.2):
        base = "신강"
    elif ratio < 0.18 or (ratio < 0.22 and pressure > support * 1.1):
        base = "신약"
    else:
        base = "중화"

    # 계절 보정 (계절이 강하게 도와주면 신강 쪽으로)
    if seasonal > 0.7 and base == "중화":
        base = "신강"
    if seasonal < 0.2 and base == "중화" and pressure > 0.25:
        base = "신약"

    return base


# ---------------------------------------------------------------------------#
# 3단계: 억부 용신 선택 (전통 방향)
# ---------------------------------------------------------------------------#

def _determine_eopbu_favorable(
    dm_element: str,
    strength: str,
    judgment: Dict[str, float],
) -> tuple[List[str], List[str], List[str]]:
    """신약/신강/중화에 따른 억부 용신 후보 반환."""
    if not dm_element:
        return ([], [], ["일간 정보 부족"])

    reasoning = [f"억부법 3단계: {strength} (ratio={judgment.get('ratio', 0):.2f})"]

    sheng_of_dm = next((e for e, t in _SHENG.items() if t == dm_element), None)  # 인
    dm_sheng_target = _SHENG.get(dm_element, "")  # 식상
    ke_by_dm = next((e for e, t in _KE.items() if t == dm_element), None)      # 관 (일간을 극하는)

    if strength == "신약":
        # 약한 몸 → 印(생) + 比(동류)로 보강
        favorable = [e for e in [sheng_of_dm, dm_element] if e]
        caution = [ke_by_dm, dm_sheng_target] if ke_by_dm else []
        reasoning.append("신약 — 印(자원)과 比(동류)로 몸을 키운다")
    elif strength == "신강":
        # 강한 몸 → 食傷(설기) + 官(극)으로 균형
        favorable = [e for e in [dm_sheng_target, ke_by_dm] if e]
        caution = [sheng_of_dm, dm_element] if sheng_of_dm else []
        reasoning.append("신강 — 食傷(설기)과 官(제한)으로 과도한 기운을 다스린다")
    else:  # 중화
        favorable = [e for e in [sheng_of_dm, dm_sheng_target] if e]
        caution = []
        reasoning.append("중화 — 상생 흐름 유지, 과도한 극/설기 주의")

    favorable = list(dict.fromkeys([e for e in favorable if e]))
    caution = list(dict.fromkeys([e for e in caution if e]))

    return favorable, caution, reasoning


# ---------------------------------------------------------------------------#
# 메인 API (wrapper 전용)
# ---------------------------------------------------------------------------#

def build_eopbu_analysis(eight_char: Dict[str, str]) -> EopbuAnalysis:
    """eight_char → EopbuAnalysis (3단계 억부법).

    기존 calculate_yongshen과 완전히 독립. trace만 재사용.
    """
    if not eight_char:
        return EopbuAnalysis(ok=False, warnings=["eight_char 없음"])

    try:
        trace = build_element_strength_trace(eight_char)
        if not trace.day_master_element:
            return EopbuAnalysis(
                ok=True,
                warnings=["일간 정보 없음 — 억부 판단 보류"],
                confidence_label="rule_based_low",
            )

        judgment = _detailed_strength_judgment(trace)
        strength = _classify_shenqiang_shenruo(judgment, trace.day_master_element)
        favorable, caution, reasoning = _determine_eopbu_favorable(
            trace.day_master_element, strength, judgment
        )

        # confidence: judgment가 명확할수록 medium
        conf = "rule_based_medium" if strength != "중화" and judgment["ratio"] not in (0.0, 1.0) else "rule_based_low"

        return EopbuAnalysis(
            ok=True,
            day_master_element=trace.day_master_element,
            eopbu_strength=strength,
            eopbu_favorable=favorable,
            eopbu_caution=caution,
            reasoning=reasoning,
            confidence_label=conf,
        )
    except Exception as e:
        return EopbuAnalysis(
            ok=False,
            warnings=[f"억부 분석 실패: {str(e)[:80]}"],
            confidence_label="rule_based_low",
        )


def build_eopbu_note(analysis: EopbuAnalysis, max_lines: int = 4) -> str:
    """EopbuAnalysis → compact note (새 함수, 기존 노트 절대 영향 없음)."""
    if not analysis.ok or not analysis.day_master_element:
        return ""

    lines: List[str] = []
    lines.append(f"억부법: 일간 {analysis.day_master_element} — {analysis.eopbu_strength} ({analysis.confidence_label})")

    for elem in analysis.eopbu_favorable[:2]:
        lines.append(f"  {elem} 기운 보강 권장 (억부)")

    if analysis.eopbu_caution:
        lines.append(f"  과다 시 주의: {', '.join(analysis.eopbu_caution[:1])}")

    lines.append(analysis.disclaimer)

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n[억부법 참고]\n{body}"


def build_show_profile_eopbu_note(eight_char: Optional[Dict[str, str]], max_lines: int = 2) -> str:
    """fail-open wrapper for show_profile."""
    if not eight_char:
        return ""
    try:
        analysis = build_eopbu_analysis(eight_char)
        return build_eopbu_note(analysis, max_lines=max_lines)
    except Exception:
        return ""
