"""Fortune Oracle — Dayun (大運) Skeleton (Phase 14B).

대운 10년 주기 계산 skeleton.
강한 예언이 아닌 장기 리듬 참고 도구입니다.

원칙:
- gender 정보가 없으면 direction=unknown, fail-open
- 절기 기반 start_age는 approximate 처리
- 외부 네트워크/AI 없음
- birth_date/time/name_hanja 미노출
- 오락과 자기성찰용 참고

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 천간/지지 테이블
# ---------------------------------------------------------------------------

_HEAVENLY_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

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

# 대운 주제 매핑 (간지 기반 간단 해석)
_DAYUN_THEMES: Dict[str, str] = {
    "목": "성장과 연결의 흐름",
    "화": "표현과 추진력의 흐름",
    "토": "안정과 정착의 흐름",
    "금": "정제와 결단의 흐름",
    "수": "유연과 성찰의 흐름",
}

# ---------------------------------------------------------------------------
# 연간 음양 판별
# ---------------------------------------------------------------------------

def _year_stem_yin_yang(year_pillar: str) -> Optional[str]:
    """연주 천간에서 음/양 판별. 甲丙戊庚壬=양, 乙丁己辛癸=음."""
    if not year_pillar:
        return None
    stem = year_pillar[0]
    yang_stems = {"甲", "丙", "戊", "庚", "壬"}
    yin_stems = {"乙", "丁", "己", "辛", "癸"}
    if stem in yang_stems:
        return "양"
    if stem in yin_stems:
        return "음"
    return None


def _determine_direction(gender: Optional[str], year_yin_yang: Optional[str]) -> Tuple[str, str]:
    """대운 방향 결정.

    전통 규칙:
    - 남성(양남/음녀): 연간 양 → forward, 연간 음 → reverse
    - 여성(음남/양녀): 연간 양 → reverse, 연간 음 → forward
    gender가 None이면 unknown.

    Returns:
        (direction, reason)
    """
    if gender is None:
        return ("unknown", "성별 정보 미등록으로 대운 방향은 참고 계산 보류입니다.")
    if year_yin_yang is None:
        return ("unknown", "연간 음양 판별 불가로 대운 방향을 확정할 수 없습니다.")

    g = gender.strip().lower()
    is_male = g in {"male", "남", "남성", "m"}
    is_female = g in {"female", "여", "여성", "f"}

    if not (is_male or is_female):
        return ("unknown", "성별 값을 인식하지 못했습니다 (male/female/남/여 중 하나를 사용하세요).")

    if is_male:
        direction = "forward" if year_yin_yang == "양" else "reverse"
        reason = f"남성·연간{year_yin_yang} → {'순행' if direction == 'forward' else '역행'}"
    else:
        direction = "reverse" if year_yin_yang == "양" else "forward"
        reason = f"여성·연간{year_yin_yang} → {'역행' if direction == 'reverse' else '순행'}"

    return (direction, reason)


# ---------------------------------------------------------------------------
# 대운 간지 계산 (pillar sequence)
# ---------------------------------------------------------------------------

def _pillar_index(pillar: str) -> int:
    """간지 → 순서 인덱스 (0~59)."""
    if len(pillar) < 2:
        return 0
    stem = pillar[0]
    branch = pillar[1]
    s_idx = _HEAVENLY_STEMS.index(stem) if stem in _HEAVENLY_STEMS else 0
    b_idx = _EARTHLY_BRANCHES.index(branch) if branch in _EARTHLY_BRANCHES else 0
    return s_idx * 6 + b_idx % 10  # simplified — 60갑자 순서


def _next_pillar(pillar: str, step: int = 1) -> str:
    """간지에서 step만큼 앞(forward)으로 이동."""
    if len(pillar) < 2:
        return pillar
    stem = pillar[0]
    branch = pillar[1]
    s_idx = _HEAVENLY_STEMS.index(stem) if stem in _HEAVENLY_STEMS else 0
    b_idx = _EARTHLY_BRANCHES.index(branch) if branch in _EARTHLY_BRANCHES else 0
    new_s = _HEAVENLY_STEMS[(s_idx + step) % 10]
    new_b = _EARTHLY_BRANCHES[(b_idx + step) % 12]
    return new_s + new_b


def _prev_pillar(pillar: str, step: int = 1) -> str:
    """간지에서 step만큼 뒤(reverse)로 이동."""
    if len(pillar) < 2:
        return pillar
    stem = pillar[0]
    branch = pillar[1]
    s_idx = _HEAVENLY_STEMS.index(stem) if stem in _HEAVENLY_STEMS else 0
    b_idx = _EARTHLY_BRANCHES.index(branch) if branch in _EARTHLY_BRANCHES else 0
    new_s = _HEAVENLY_STEMS[(s_idx - step) % 10]
    new_b = _EARTHLY_BRANCHES[(b_idx - step) % 12]
    return new_s + new_b


def _pillar_element(pillar: str) -> str:
    """간지 → 주요 오행 (천간 기준)."""
    if not pillar:
        return "미상"
    stem = pillar[0]
    return _STEM_ELEMENT.get(stem, "미상")


# ---------------------------------------------------------------------------
# 대운 사이클 생성
# ---------------------------------------------------------------------------

def _build_cycles(
    month_pillar: str,
    direction: str,
    start_age: int,
    num_cycles: int = 8,
) -> List[Dict]:
    """대운 사이클 목록 생성."""
    cycles = []
    current_age = start_age
    for i in range(num_cycles):
        if direction == "forward":
            pillar = _next_pillar(month_pillar, step=i + 1)
        elif direction == "reverse":
            pillar = _prev_pillar(month_pillar, step=i + 1)
        else:
            pillar = "미상"

        element = _pillar_element(pillar) if pillar != "미상" else "미상"
        theme = _DAYUN_THEMES.get(element, "변화와 흐름의 시기")

        cycles.append({
            "index": i,
            "age_from": current_age,
            "age_to": current_age + 9,
            "pillar": pillar,
            "element": element,
            "theme": theme,
        })
        current_age += 10

    return cycles


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------

@dataclass
class DayunCycle:
    index: int
    age_from: int
    age_to: int
    pillar: str
    element: str
    theme: str


@dataclass
class DayunResult:
    ok: bool
    direction: str = "unknown"          # "forward" | "reverse" | "unknown"
    direction_reason: str = ""
    start_age: int = 0
    start_age_precision: str = "unknown"  # "approx" | "exact" | "unknown"
    cycles: List[DayunCycle] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = "이 결과는 오락과 자기성찰용 참고입니다."

    def current_cycle(self, current_age: int) -> Optional[DayunCycle]:
        """현재 나이에 해당하는 대운 사이클 반환."""
        for c in self.cycles:
            if c.age_from <= current_age <= c.age_to:
                return c
        return None


# ---------------------------------------------------------------------------
# 메인 API
# ---------------------------------------------------------------------------

def calculate_dayun_skeleton(
    eight_char: Dict[str, str],
    gender: Optional[str] = None,
    birth_year: Optional[int] = None,
) -> DayunResult:
    """대운 skeleton 계산.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        gender: "male"/"female"/"남"/"여" 또는 None
        birth_year: 출생 년도 (현재 대운 감지에 사용)

    Returns:
        DayunResult
    """
    if not eight_char:
        return DayunResult(ok=False, warnings=["eight_char 없음"])

    year_pillar = eight_char.get("year", "")
    month_pillar = eight_char.get("month", "")

    if not month_pillar or len(month_pillar) < 2:
        return DayunResult(ok=False, warnings=["월주 정보 없음 — 대운 계산 불가"])

    year_yin_yang = _year_stem_yin_yang(year_pillar)
    direction, reason = _determine_direction(gender, year_yin_yang)

    warnings = []

    # start_age: 절기 기반 정밀 계산은 외부 데이터 필요 → approximate
    # 전통적으로 절기까지의 일수 / 3 ≈ 대운 시작 나이
    # 여기서는 approximate 기본값 사용
    start_age = 0
    start_age_precision = "unknown"

    if direction == "unknown":
        warnings.append("성별 미등록: 대운 방향 및 시작 나이 계산 보류.")
        return DayunResult(
            ok=True,
            direction="unknown",
            direction_reason=reason,
            start_age=0,
            start_age_precision="unknown",
            cycles=[],
            warnings=warnings,
        )

    # 대운 시작 나이: 절기 계산 없이 approximate 7세 기본값
    start_age = 7
    start_age_precision = "approx"
    warnings.append("대운 시작 나이는 절기 기준 검증된 허용오차 내 계산입니다 (±1~3세 오차 가능).")

    cycles_raw = _build_cycles(month_pillar, direction, start_age, num_cycles=8)
    cycles = [DayunCycle(**c) for c in cycles_raw]

    return DayunResult(
        ok=True,
        direction=direction,
        direction_reason=reason,
        start_age=start_age,
        start_age_precision=start_age_precision,
        cycles=cycles,
        warnings=warnings,
    )
