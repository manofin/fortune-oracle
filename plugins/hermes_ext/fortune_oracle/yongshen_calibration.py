"""Fortune Oracle — Yongshen confidence calibration helpers (Phase 26)."""

from __future__ import annotations

from typing import Any, Dict

from .yongshen import calculate_yongshen

ALLOWED_CONFIDENCE = ("rule_based_low", "rule_based_medium")
FORBIDDEN_CONFIDENCE = "rule_based_high"
UNSAFE_DECISION_PHRASES = (
    "매수하세요",
    "매도하세요",
    "진단합니다",
    "소송하세요",
    "반드시",
    "피할 수 없는 파국",
)


def calibrate_yongshen_result(eight_char: Dict[str, str]) -> Dict[str, Any]:
    result = calculate_yongshen(eight_char)
    confidence = result.confidence if result.confidence in ALLOWED_CONFIDENCE else "rule_based_low"
    reasoning = list(result.reasoning)
    if result.season:
        reasoning.append(f"월지 계절: {result.season}")
    if result.hidden_stems_contribution:
        reasoning.append("지장간 보정: " + " / ".join(result.hidden_stems_contribution[:4]))
    reasoning.append("confidence는 rule_based_low/medium으로 제한하며 high 확정 판정은 사용하지 않습니다.")
    return {
        "ok": result.ok,
        "day_master": result.day_master,
        "day_master_element": result.day_master_element,
        "strength": result.strength,
        "strength_score": dict(result.strength_score),
        "favorable_elements": list(result.favorable_elements),
        "caution_elements": list(result.caution_elements),
        "confidence": confidence,
        "reasoning": reasoning,
        "disclaimer": result.disclaimer,
    }


def yongshen_deep_context_summary(eight_char: Dict[str, str]) -> str:
    calibrated = calibrate_yongshen_result(eight_char)
    fav = ", ".join(calibrated["favorable_elements"][:2]) or "보류"
    return (
        f"용신 rule-based summary: 일간={calibrated['day_master_element'] or '미상'}, "
        f"strength={calibrated['strength'] or 'unknown'}, favorable={fav}, "
        f"confidence={calibrated['confidence']}"
    )


def contains_unsafe_yongshen_phrase(text: str) -> bool:
    return any(phrase in (text or "") for phrase in UNSAFE_DECISION_PHRASES)
