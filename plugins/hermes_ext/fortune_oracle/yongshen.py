"""Fortune Oracle — Yongshen (用神/喜神) Rule-Based Skeleton (Phase 17).

rule-based 참고 판정. 정통 완전 판정이 아님을 명시합니다.

원칙:
- 결과에는 confidence="rule_based_low/medium" 표시
- 의학/투자/법률 결정 지시 금지
- 공포 조장 금지
- birth_date/time/name_hanja 미노출
- 외부 네트워크/AI 없음
- deterministic — 동일 입력 → 동일 출력

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 오행 생극 관계
# ---------------------------------------------------------------------------

# 오행 상생 (生): A → B = A가 B를 생한다
_SHENG: Dict[str, str] = {
    "목": "화",
    "화": "토",
    "토": "금",
    "금": "수",
    "수": "목",
}

# 오행 상극 (克): A → B = A가 B를 극한다
_KE: Dict[str, str] = {
    "목": "토",
    "화": "금",
    "토": "수",
    "금": "목",
    "수": "화",
}

# 일간(日干) → 오행
_STEM_ELEMENT: Dict[str, str] = {
    "甲": "목", "乙": "목",
    "丙": "화", "丁": "화",
    "戊": "토", "己": "토",
    "庚": "금", "辛": "금",
    "壬": "수", "癸": "수",
}

_BRANCH_ELEMENT: Dict[str, str] = {
    "子": "수", "丑": "토", "寅": "목", "卯": "목",
    "辰": "토", "巳": "화", "午": "화", "未": "토",
    "申": "금", "酉": "금", "戌": "토", "亥": "수",
}

ALL_ELEMENTS = ["목", "화", "토", "금", "수"]

# ---------------------------------------------------------------------------
# 월지(月支) 계절 가중치
# ---------------------------------------------------------------------------

_MONTH_BRANCH_SEASON: Dict[str, str] = {
    "寅": "봄", "卯": "봄", "辰": "봄",
    "巳": "여름", "午": "여름", "未": "여름",
    "申": "가을", "酉": "가을", "戌": "가을",
    "亥": "겨울", "子": "겨울", "丑": "겨울",
}

_SEASON_ELEMENT: Dict[str, str] = {
    "봄": "목", "여름": "화", "가을": "금", "겨울": "수",
}

_SEASONAL_BOOST = 1.5  # 계절 기운 가중치

# ---------------------------------------------------------------------------
# 지장간(地藏干) 테이블
# ---------------------------------------------------------------------------

_HIDDEN_STEMS: Dict[str, list] = {
    "子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"],
    "卯": ["乙"], "辰": ["戊", "乙", "癸"], "巳": ["丙", "庚", "戊"],
    "午": ["丁", "己"], "未": ["己", "丁", "乙"], "申": ["庚", "壬", "戊"],
    "酉": ["辛"], "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"],
}

_HIDDEN_WEIGHT = 0.5  # 지장간 가중치


# ---------------------------------------------------------------------------
# 일간 추출
# ---------------------------------------------------------------------------

def extract_day_master(eight_char: Dict[str, str]) -> Tuple[str, str]:
    """일주 천간(일간)과 오행 반환.

    Returns:
        (day_master_stem, day_master_element)
    """
    day_pillar = eight_char.get("day", "")
    if not day_pillar:
        return ("", "")
    stem = day_pillar[0] if day_pillar else ""
    element = _STEM_ELEMENT.get(stem, "")
    return (stem, element)


# ---------------------------------------------------------------------------
# 오행 집계
# ---------------------------------------------------------------------------

def count_elements_from_eight_char(eight_char: Dict[str, str]) -> Dict[str, int]:
    """사주 팔자의 천간/지지에서 오행 개수 집계."""
    counts: Dict[str, int] = {e: 0 for e in ALL_ELEMENTS}

    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 1:
            stem_elem = _STEM_ELEMENT.get(gz[0], "")
            if stem_elem:
                counts[stem_elem] = counts.get(stem_elem, 0) + 1
        if len(gz) >= 2:
            branch_elem = _BRANCH_ELEMENT.get(gz[1], "")
            if branch_elem:
                counts[branch_elem] = counts.get(branch_elem, 0) + 1

    return counts


# ---------------------------------------------------------------------------
# 강도 점수 계산 (Phase 17)
# ---------------------------------------------------------------------------

def calculate_strength_score(
    eight_char: Dict[str, str],
    day_master_element: str,
) -> dict:
    """오행별 강도 점수 계산.

    - 천간/지지 기본 카운트 (weight=1.0)
    - 월지 계절 보정 (+_SEASONAL_BOOST)
    - 지장간 보정 (weight=_HIDDEN_WEIGHT)

    Returns:
        {element: score, ...} 형태 (float 값)
    """
    scores: Dict[str, float] = {e: 0.0 for e in ALL_ELEMENTS}

    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 1:
            stem_elem = _STEM_ELEMENT.get(gz[0], "")
            if stem_elem:
                scores[stem_elem] += 1.0
        if len(gz) >= 2:
            branch_elem = _BRANCH_ELEMENT.get(gz[1], "")
            if branch_elem:
                scores[branch_elem] += 1.0

    # 월지 계절 보정
    month_gz = eight_char.get("month", "")
    if len(month_gz) >= 2:
        month_branch = month_gz[1]
        season = _MONTH_BRANCH_SEASON.get(month_branch, "")
        season_elem = _SEASON_ELEMENT.get(season, "")
        if season_elem:
            scores[season_elem] += _SEASONAL_BOOST

    # 지장간 보정
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 2:
            branch = gz[1]
            for hidden_stem in _HIDDEN_STEMS.get(branch, []):
                hidden_elem = _STEM_ELEMENT.get(hidden_stem, "")
                if hidden_elem:
                    scores[hidden_elem] += _HIDDEN_WEIGHT

    return scores


def classify_strength(score_dict: dict, day_master_element: str) -> str:
    """강약 판별.

    Returns:
        'strong' | 'balanced' | 'weak'
    """
    if not day_master_element:
        return "unknown"
    dm_score = score_dict.get(day_master_element, 0.0)
    total = sum(score_dict.values())
    ratio = dm_score / total if total > 0 else 0.0
    if ratio >= 0.35:
        return "strong"
    elif ratio >= 0.22:
        return "balanced"
    else:
        return "weak"


# ---------------------------------------------------------------------------
# 강약 판별 (legacy wrapper, kept for compatibility)
# ---------------------------------------------------------------------------

def _classify_strength(
    day_master_element: str,
    element_counts: Dict[str, int],
) -> str:
    """일간 강약 판별 (rule-based, approximate) — legacy."""
    if not day_master_element:
        return "unknown"

    sheng_elem = next((e for e, t in _SHENG.items() if t == day_master_element), None)
    ke_target = _KE.get(day_master_element, "")
    ke_by = next((e for e, t in _KE.items() if t == day_master_element), None)

    self_count = element_counts.get(day_master_element, 0)
    sheng_count = element_counts.get(sheng_elem, 0) if sheng_elem else 0
    ke_by_count = element_counts.get(ke_by, 0) if ke_by else 0

    power = self_count + sheng_count
    pressure = ke_by_count

    total = sum(element_counts.values()) or 1

    if power / total >= 0.5:
        return "strong"
    elif pressure / total >= 0.4:
        return "weak"
    else:
        return "balanced"


# ---------------------------------------------------------------------------
# 용신/희신 결정
# ---------------------------------------------------------------------------

def _determine_favorable(
    day_master_element: str,
    strength: str,
    element_counts: Dict[str, int],
) -> Tuple[List[str], List[str], List[str]]:
    """favorable / caution / reasoning 결정.

    Returns:
        (favorable_elements, caution_elements, reasoning)
    """
    if not day_master_element or strength == "unknown":
        return ([], [], ["일간 정보 부족으로 용신 판단 보류"])

    reasoning: List[str] = [f"일간 {day_master_element} 기준"]

    sheng_of_dm = next((e for e, t in _SHENG.items() if t == day_master_element), None)
    ke_by_dm = next((e for e, t in _KE.items() if t == day_master_element), None)
    dm_sheng_target = _SHENG.get(day_master_element, "")
    ke_of_dm = next((e for e, t in _KE.items() if t == day_master_element), None)

    dominant = [e for e, c in element_counts.items() if c >= 2]
    if dominant:
        reasoning.append(f"{'/'.join(dominant)} 기운이 두드러짐")

    if strength == "weak":
        # 약한 일간 → 생해주는 기운이 favorable
        favorable = [e for e in [sheng_of_dm, day_master_element] if e]
        caution = [e for e in [ke_by_dm, dm_sheng_target] if e]
        reasoning.append("일간이 약함 — 생조(生助) 기운이 도움")
    elif strength == "strong":
        # 강한 일간 → 설기/극 기운이 favorable (억부)
        favorable = [e for e in [dm_sheng_target, ke_by_dm] if e]
        caution = [e for e in [sheng_of_dm, day_master_element] if e]
        reasoning.append("일간이 강함 — 설기(泄氣)/극 기운이 균형")
    else:  # balanced
        # 균형 → 상생 흐름 강화
        favorable = [e for e in [sheng_of_dm, dm_sheng_target] if e]
        caution = [e for e, c in element_counts.items() if c >= 3]
        reasoning.append("균형 — 상생 흐름이 안정을 유지")

    # 중복 제거
    favorable = list(dict.fromkeys([e for e in favorable if e]))
    caution = list(dict.fromkeys([e for e in caution if e]))

    if favorable:
        reasoning.append(f"{'/'.join(favorable)} 보완 권장")

    return (favorable, caution, reasoning)


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------

@dataclass
class YongshenResult:
    ok: bool
    day_master: str = ""
    day_master_element: str = ""
    strength: str = ""          # "balanced" | "weak" | "strong" | ""
    favorable_elements: List[str] = field(default_factory=list)
    caution_elements: List[str] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    confidence: str = "rule_based_low"   # "rule_based_low" | "rule_based_medium"
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = "이 판단은 rule-based 참고이며, 절대 판정은 아닙니다."
    # Phase 17 추가 필드
    strength_score: dict = field(default_factory=dict)
    season: str = ""                              # 월지 계절
    hidden_stems_contribution: list = field(default_factory=list)  # 지장간 기여 설명


# ---------------------------------------------------------------------------
# 메인 API
# ---------------------------------------------------------------------------

def calculate_yongshen(
    eight_char: Dict[str, str],
) -> YongshenResult:
    """용신/희신 rule-based skeleton 계산.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}

    Returns:
        YongshenResult
    """
    if not eight_char:
        return YongshenResult(ok=False, warnings=["eight_char 없음"])

    day_master, dm_element = extract_day_master(eight_char)
    if not day_master:
        return YongshenResult(
            ok=True,
            warnings=["일주 정보 없음 — 용신 판단 보류"],
            confidence="rule_based_low",
        )

    # Phase 17: 강도 점수 기반 강약 판별
    score_dict = calculate_strength_score(eight_char, dm_element)
    strength = classify_strength(score_dict, dm_element)

    # 월지 계절
    month_gz = eight_char.get("month", "")
    season = ""
    if len(month_gz) >= 2:
        month_branch = month_gz[1]
        season = _MONTH_BRANCH_SEASON.get(month_branch, "")

    # 지장간 기여 설명
    hidden_contrib: List[str] = []
    for pillar in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar, "")
        if len(gz) >= 2:
            branch = gz[1]
            stems = _HIDDEN_STEMS.get(branch, [])
            if stems:
                hidden_contrib.append(f"{branch}지장간: {','.join(stems)}")

    # element_counts (favorable/caution 결정에 활용)
    element_counts = count_elements_from_eight_char(eight_char)
    favorable, caution, reasoning = _determine_favorable(dm_element, strength, element_counts)

    # confidence: strength에 따라 결정
    if strength == "balanced":
        confidence = "rule_based_medium"
    else:
        confidence = "rule_based_low"

    return YongshenResult(
        ok=True,
        day_master=day_master,
        day_master_element=dm_element,
        strength=strength,
        favorable_elements=favorable,
        caution_elements=caution,
        reasoning=reasoning,
        confidence=confidence,
        strength_score=score_dict,
        season=season,
        hidden_stems_contribution=hidden_contrib,
    )
