#!/usr/bin/env python3
"""Fortune Oracle — Yongshen Confidence Score (Gate 3.6).

4가지 방법(억부/조후/통관/격국) 결과를 받아 가중치 기반 신뢰도 계산.
wrapper 계층 전용.

확정 스펙:
- 가중치: 억부 0.40 / 조후 0.30 / 통관 0.15 / 격국 0.15
- 사용자 출력: "신뢰도 72% · 중상"
- None 3개 이상 → "판단 보류 (데이터 부족)"
- 단순 다수결은 내부 검증용만 (사용자 미노출)
- "높음" 라벨 사용 금지

기존 yongshen.py 및 이전 wrapper 함수 절대 수정 금지.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

WEIGHTS = {
    "eopbu": 0.40,
    "johu": 0.30,
    "tonggwan": 0.15,
    "gyeokguk": 0.15,
}

LABEL_MAP = {
    (85, 100): "매우 높음",
    (70, 84): "중상",
    (55, 69): "중간",
    (40, 54): "중하",
    (0, 39): "낮음",
}

def _get_label(score: int) -> str:
    for (low, high), label in LABEL_MAP.items():
        if low <= score <= high:
            return label
    return "낮음"

@dataclass
class ConfidenceResult:
    score: Optional[int] = None          # 0-100 또는 None
    display_text: str = ""               # 사용자에게 보여줄 문자열
    internal_majority: int = 0           # 내부 검증용 (단순 다수결)
    reasoning: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.reasoning is None:
            self.reasoning = []
        if self.warnings is None:
            self.warnings = []

def calculate_confidence(
    eopbu_elem: Optional[str],
    johu_elem: Optional[str],
    tonggwan_elem: Optional[str],
    gyeokguk_elem: Optional[str],
) -> ConfidenceResult:
    """
    4가지 방법 결과로 Confidence Score 계산 (가중치 방식)
    """
    methods = {
        "eopbu": eopbu_elem,
        "johu": johu_elem,
        "tonggwan": tonggwan_elem,
        "gyeokguk": gyeokguk_elem,
    }

    none_count = sum(1 for v in methods.values() if v is None)
    valid_methods = {k: v for k, v in methods.items() if v is not None}

    result = ConfidenceResult()

    # None이 3개 이상인 경우
    if none_count >= 3:
        result.display_text = "판단 보류 (데이터 부족)"
        result.reasoning.append(f"유효한 방법 {len(valid_methods)}개 (None {none_count}개)")
        result.warnings.append("3개 이상의 방법에서 결과를 산출하지 못함")
        return result

    if not valid_methods:
        result.display_text = "판단 보류 (데이터 부족)"
        return result

    # 가중치 기반 점수 계산
    weighted_score = 0.0
    total_weight = 0.0

    for method, elem in valid_methods.items():
        w = WEIGHTS.get(method, 0.0)
        weighted_score += w
        total_weight += w

    if total_weight == 0:
        result.display_text = "판단 보류 (데이터 부족)"
        return result

    raw_score = (weighted_score / 1.0) * 100   # 전체 가중치 합 = 1.0
    score = int(round(raw_score))
    score = max(0, min(100, score))

    # 내부 검증용 단순 다수결 (사용자 미노출)
    from collections import Counter
    elem_counts = Counter(valid_methods.values())
    majority_count = max(elem_counts.values()) if elem_counts else 0
    result.internal_majority = int(round((majority_count / len(valid_methods)) * 100))

    label = _get_label(score)
    result.score = score
    result.display_text = f"신뢰도 {score}% · {label}"
    result.reasoning.append(f"가중치 합: {weighted_score:.2f} / 유효 방법: {len(valid_methods)}개")

    return result
