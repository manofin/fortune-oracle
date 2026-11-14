"""Fortune Oracle — Bazi Reference Tables (Phase 12).

Source: jinchenma94/bazi-skill (MIT License)
  https://github.com/jinchenma94/bazi-skill
  references/heavenly_stems.md, earthly_branches.md, ten_gods.md,
  five_elements.md, solar_terms.md

Adaptation notes:
- Career/health/organ 항목은 "참고 기질" 수준으로만 사용
- deterministic table lookup만 제공; 확정 예언/진단 금지
- 모든 해석 문구는 오락/자기성찰 톤으로 변환
- raw birth_date/birth_time/name_hanja 미노출
- 외부 네트워크/AI 호출 없음 — 순수 Python dict

이 모듈은 오락과 자기성찰 용도이며
의학, 투자, 법률 결정을 지시하지 않습니다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. 천간 (Heavenly Stems) — 10개
# ---------------------------------------------------------------------------

HEAVENLY_STEMS: Dict[str, Dict] = {
    "甲": {
        "kor": "갑",
        "element": "목",
        "polarity": "양",
        "season": "봄",
        "direction": "동",
        "color": "청록",
        "organ_ref": "담",          # 참고용 — 진단 아님
        "traits": "자립심, 성장 지향, 직선적",
        "tendency": "새로운 것을 개척하고 앞으로 나아가려는 성향",
    },
    "乙": {
        "kor": "을",
        "element": "목",
        "polarity": "음",
        "season": "봄",
        "direction": "동",
        "color": "초록",
        "organ_ref": "간",
        "traits": "유연성, 예술 감각, 외교적",
        "tendency": "상황에 맞게 적응하며 관계를 중시하는 성향",
    },
    "丙": {
        "kor": "병",
        "element": "화",
        "polarity": "양",
        "season": "여름",
        "direction": "남",
        "color": "빨강",
        "organ_ref": "소장",
        "traits": "열정, 표현력, 관대함",
        "tendency": "밝고 따뜻하게 주변을 이끄는 성향",
    },
    "丁": {
        "kor": "정",
        "element": "화",
        "polarity": "음",
        "season": "여름",
        "direction": "남",
        "color": "자주",
        "organ_ref": "심장",
        "traits": "집중력, 섬세함, 직관",
        "tendency": "한 가지에 깊이 몰입하며 내면을 중시하는 성향",
    },
    "戊": {
        "kor": "무",
        "element": "토",
        "polarity": "양",
        "season": "사계절 전환기",
        "direction": "중앙",
        "color": "황색",
        "organ_ref": "위",
        "traits": "안정감, 신뢰성, 보호 본능",
        "tendency": "묵묵히 자리를 지키며 중심을 잡는 성향",
    },
    "己": {
        "kor": "기",
        "element": "토",
        "polarity": "음",
        "season": "사계절 전환기",
        "direction": "중앙",
        "color": "황색",
        "organ_ref": "비장",
        "traits": "세심함, 돌봄, 꼼꼼함",
        "tendency": "세부에 주의를 기울이며 타인을 배려하는 성향",
    },
    "庚": {
        "kor": "경",
        "element": "금",
        "polarity": "양",
        "season": "가을",
        "direction": "서",
        "color": "흰색/은색",
        "organ_ref": "대장",
        "traits": "결단력, 원칙, 정의감",
        "tendency": "명확한 기준으로 결정하고 실행하는 성향",
    },
    "辛": {
        "kor": "신",
        "element": "금",
        "polarity": "음",
        "season": "가을",
        "direction": "서",
        "color": "흰색/금색",
        "organ_ref": "폐",
        "traits": "섬세함, 심미안, 예리함",
        "tendency": "아름다움과 정확함을 추구하는 성향",
    },
    "壬": {
        "kor": "임",
        "element": "수",
        "polarity": "양",
        "season": "겨울",
        "direction": "북",
        "color": "검정/짙은 남색",
        "organ_ref": "방광",
        "traits": "전략적 사고, 유연성, 모험심",
        "tendency": "큰 그림을 보고 유연하게 적응하는 성향",
    },
    "癸": {
        "kor": "계",
        "element": "수",
        "polarity": "음",
        "season": "겨울",
        "direction": "북",
        "color": "검정/회색",
        "organ_ref": "신장",
        "traits": "직관, 공감 능력, 신중함",
        "tendency": "깊이 느끼고 조심스럽게 관찰하는 성향",
    },
}

# 천간합 (Stem Combinations) — 합화 오행
STEM_COMBINATIONS: Dict[Tuple[str, str], str] = {
    ("甲", "己"): "토",
    ("乙", "庚"): "금",
    ("丙", "辛"): "수",
    ("丁", "壬"): "목",
    ("戊", "癸"): "화",
}

# 천간충 (Stem Clashes)
STEM_CLASHES: List[Tuple[str, str]] = [
    ("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"),
]

# ---------------------------------------------------------------------------
# 2. 지지 (Earthly Branches) — 12개
# ---------------------------------------------------------------------------

EARTHLY_BRANCHES: Dict[str, Dict] = {
    "子": {
        "kor": "자",
        "zodiac": "쥐",
        "element": "수",
        "polarity": "양",
        "month_approx": 12,
        "hour_range": "23:00–01:00",
        "hour_start": 23,
        "hour_end": 1,
        "hidden_stems": ["癸"],
        "traits": "영민함, 적응력, 사교성",
    },
    "丑": {
        "kor": "축",
        "zodiac": "소",
        "element": "토",
        "polarity": "음",
        "month_approx": 1,
        "hour_range": "01:00–03:00",
        "hour_start": 1,
        "hour_end": 3,
        "hidden_stems": ["己", "癸", "辛"],
        "traits": "성실함, 인내심, 신뢰감",
    },
    "寅": {
        "kor": "인",
        "zodiac": "호랑이",
        "element": "목",
        "polarity": "양",
        "month_approx": 2,
        "hour_range": "03:00–05:00",
        "hour_start": 3,
        "hour_end": 5,
        "hidden_stems": ["甲", "丙", "戊"],
        "traits": "용감함, 자신감, 경쟁심",
    },
    "卯": {
        "kor": "묘",
        "zodiac": "토끼",
        "element": "목",
        "polarity": "음",
        "month_approx": 3,
        "hour_range": "05:00–07:00",
        "hour_start": 5,
        "hour_end": 7,
        "hidden_stems": ["乙"],
        "traits": "온화함, 예술적 감각, 외교적",
    },
    "辰": {
        "kor": "진",
        "zodiac": "용",
        "element": "토",
        "polarity": "양",
        "month_approx": 4,
        "hour_range": "07:00–09:00",
        "hour_start": 7,
        "hour_end": 9,
        "hidden_stems": ["戊", "乙", "癸"],
        "traits": "포부, 카리스마, 상상력",
    },
    "巳": {
        "kor": "사",
        "zodiac": "뱀",
        "element": "화",
        "polarity": "음",
        "month_approx": 5,
        "hour_range": "09:00–11:00",
        "hour_start": 9,
        "hour_end": 11,
        "hidden_stems": ["丙", "庚", "戊"],
        "traits": "지혜, 직관, 우아함",
    },
    "午": {
        "kor": "오",
        "zodiac": "말",
        "element": "화",
        "polarity": "양",
        "month_approx": 6,
        "hour_range": "11:00–13:00",
        "hour_start": 11,
        "hour_end": 13,
        "hidden_stems": ["丁", "己"],
        "traits": "활력, 자유로움, 열정",
    },
    "未": {
        "kor": "미",
        "zodiac": "양",
        "element": "토",
        "polarity": "음",
        "month_approx": 7,
        "hour_range": "13:00–15:00",
        "hour_start": 13,
        "hour_end": 15,
        "hidden_stems": ["己", "丁", "乙"],
        "traits": "창의성, 공감 능력, 온화함",
    },
    "申": {
        "kor": "신",
        "zodiac": "원숭이",
        "element": "금",
        "polarity": "양",
        "month_approx": 8,
        "hour_range": "15:00–17:00",
        "hour_start": 15,
        "hour_end": 17,
        "hidden_stems": ["庚", "壬", "戊"],
        "traits": "영리함, 다재다능함, 발명적 사고",
    },
    "酉": {
        "kor": "유",
        "zodiac": "닭",
        "element": "금",
        "polarity": "음",
        "month_approx": 9,
        "hour_range": "17:00–19:00",
        "hour_start": 17,
        "hour_end": 19,
        "hidden_stems": ["辛"],
        "traits": "꼼꼼함, 정확성, 관찰력",
    },
    "戌": {
        "kor": "술",
        "zodiac": "개",
        "element": "토",
        "polarity": "양",
        "month_approx": 10,
        "hour_range": "19:00–21:00",
        "hour_start": 19,
        "hour_end": 21,
        "hidden_stems": ["戊", "辛", "丁"],
        "traits": "충성스러움, 정직함, 용감함",
    },
    "亥": {
        "kor": "해",
        "zodiac": "돼지",
        "element": "수",
        "polarity": "음",
        "month_approx": 11,
        "hour_range": "21:00–23:00",
        "hour_start": 21,
        "hour_end": 23,
        "hidden_stems": ["壬", "甲"],
        "traits": "너그러움, 솔직함, 의지력",
    },
}

# 지지 → 오행 단순 매핑 (판정기용)
BRANCH_ELEMENT: Dict[str, str] = {
    k: v["element"] for k, v in EARTHLY_BRANCHES.items()
}

# 야자시 경계 — 子時는 23:00~01:00 (전날 자정 포함)
_YAJASHI_START_HOUR = 23  # 23:00 이후 출생 → 야자시 가능성 경고

# 지지합 (Six Harmonies 六合)
BRANCH_SIX_HARMONIES: Dict[Tuple[str, str], str] = {
    ("子", "丑"): "토",
    ("寅", "亥"): "목",
    ("卯", "戌"): "화",
    ("辰", "酉"): "금",
    ("巳", "申"): "수",
    ("午", "未"): "화토",
}

# 삼합 (Three Harmonies 三合)
BRANCH_THREE_HARMONIES: Dict[Tuple[str, str, str], str] = {
    ("申", "子", "辰"): "수",
    ("亥", "卯", "未"): "목",
    ("寅", "午", "戌"): "화",
    ("巳", "酉", "丑"): "금",
}

# 六冲 (Six Clashes)
BRANCH_CLASHES: List[Tuple[str, str]] = [
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
]

# ---------------------------------------------------------------------------
# 3. 오행 관계 (Five Elements)
# ---------------------------------------------------------------------------

# 상생 (Generating Cycle)
ELEMENT_GENERATES: Dict[str, str] = {
    "목": "화",
    "화": "토",
    "토": "금",
    "금": "수",
    "수": "목",
}

# 상극 (Controlling Cycle)
ELEMENT_CONTROLS: Dict[str, str] = {
    "목": "토",
    "토": "수",
    "수": "화",
    "화": "금",
    "금": "목",
}

# 오행 → 천간 매핑
ELEMENT_TO_STEMS: Dict[str, List[str]] = {
    "목": ["甲", "乙"],
    "화": ["丙", "丁"],
    "토": ["戊", "己"],
    "금": ["庚", "辛"],
    "수": ["壬", "癸"],
}

# 오행 → 지지 주 기운 매핑 (primary hidden stem element)
ELEMENT_TO_BRANCH_PRIMARY: Dict[str, List[str]] = {
    "목": ["寅", "卯"],
    "화": ["巳", "午"],
    "토": ["丑", "辰", "未", "戌"],
    "금": ["申", "酉"],
    "수": ["子", "亥"],
}

# 오행 기질 설명 (자기성찰 톤)
ELEMENT_REFLECTIONS: Dict[str, str] = {
    "목": "성장과 연결 — 새로운 가능성을 열고 주변과 함께 뻗어나가는 기운",
    "화": "표현과 연결 — 따뜻함과 열정으로 빛을 나누는 기운",
    "토": "안정과 중심 — 묵묵히 자리를 지키며 균형을 잡는 기운",
    "금": "명료함과 정제 — 핵심을 가려내고 명확하게 나아가는 기운",
    "수": "깊이와 지혜 — 조용히 흐르며 깊은 곳을 탐색하는 기운",
}

# ---------------------------------------------------------------------------
# 4. 십신 (Ten Gods) — 일간과의 관계
# ---------------------------------------------------------------------------

# (관계 유형, 극성 일치 여부) → 십신
TEN_GODS_TABLE: Dict[Tuple[str, bool], Dict] = {
    ("self", True): {
        "name": "비견",
        "hanja": "比肩",
        "relation": "같은 오행·같은 극성",
        "traits": "자립심, 경쟁력",
        "reflection": "나와 비슷한 에너지를 가진 동료나 경쟁자와의 관계를 상징합니다.",
    },
    ("self", False): {
        "name": "겁재",
        "hanja": "劫財",
        "relation": "같은 오행·다른 극성",
        "traits": "사교성, 추진력",
        "reflection": "함께 무언가를 이루고 싶은 적극적 에너지를 상징합니다.",
    },
    ("output", True): {
        "name": "식신",
        "hanja": "食神",
        "relation": "일간이 생하는 오행·같은 극성",
        "traits": "창의성, 표현력, 낙관",
        "reflection": "재능을 즐기고 삶을 음미하는 기운을 상징합니다.",
    },
    ("output", False): {
        "name": "상관",
        "hanja": "傷官",
        "relation": "일간이 생하는 오행·다른 극성",
        "traits": "혁신, 예술성, 독창성",
        "reflection": "기존 틀을 넘어 새로운 방식을 탐색하는 기운을 상징합니다.",
    },
    ("wealth_indirect", True): {
        "name": "편재",
        "hanja": "偏財",
        "relation": "일간이 극하는 오행·같은 극성",
        "traits": "사교성, 유연한 재물 감각",
        "reflection": "예상치 못한 기회와 넓은 인간관계를 상징합니다.",
    },
    ("wealth_direct", False): {
        "name": "정재",
        "hanja": "正財",
        "relation": "일간이 극하는 오행·다른 극성",
        "traits": "성실함, 안정적 재물 감각",
        "reflection": "꾸준한 노력으로 쌓아가는 안정감을 상징합니다.",
    },
    ("power_indirect", True): {
        "name": "편관",
        "hanja": "七殺",
        "relation": "일간을 극하는 오행·같은 극성",
        "traits": "도전 정신, 리더십",
        "reflection": "압박 속에서 실력을 발휘하는 강인한 기운을 상징합니다.",
    },
    ("power_direct", False): {
        "name": "정관",
        "hanja": "正官",
        "relation": "일간을 극하는 오행·다른 극성",
        "traits": "책임감, 원칙, 명예",
        "reflection": "질서와 책임을 통해 신뢰를 쌓는 기운을 상징합니다.",
    },
    ("resource_indirect", True): {
        "name": "편인",
        "hanja": "偏印",
        "relation": "일간을 생하는 오행·같은 극성",
        "traits": "독립적 사고, 직관, 전문성",
        "reflection": "비주류 길을 통해 깊은 통찰을 얻는 기운을 상징합니다.",
    },
    ("resource_direct", False): {
        "name": "정인",
        "hanja": "正印",
        "relation": "일간을 생하는 오행·다른 극성",
        "traits": "학문, 공감, 윤리",
        "reflection": "배움과 지지를 통해 성장하는 기운을 상징합니다.",
    },
}

def _stem_polarity(stem: str) -> str:
    """천간 → 음/양."""
    data = HEAVENLY_STEMS.get(stem)
    return data["polarity"] if data else "?"

def _stem_element(stem: str) -> str:
    """천간 → 오행."""
    data = HEAVENLY_STEMS.get(stem)
    return data["element"] if data else "?"

def get_ten_god(day_master: str, other_stem: str) -> Optional[Dict]:
    """일간과 다른 천간 사이의 십신을 반환.

    Args:
        day_master: 일간 천간 (예: "甲")
        other_stem: 비교 대상 천간 (예: "丙")

    Returns:
        TEN_GODS_TABLE 항목 dict, 계산 불가 시 None
    """
    dm_elem = _stem_element(day_master)
    dm_pol = _stem_polarity(day_master)
    ot_elem = _stem_element(other_stem)
    ot_pol = _stem_polarity(other_stem)
    if dm_elem == "?" or ot_elem == "?":
        return None
    same_pol = (dm_pol == ot_pol)

    if ot_elem == dm_elem:
        key = ("self", same_pol)
    elif ELEMENT_GENERATES.get(dm_elem) == ot_elem:
        key = ("output", same_pol)
    elif ELEMENT_CONTROLS.get(dm_elem) == ot_elem:
        key = ("wealth_indirect" if same_pol else "wealth_direct", same_pol)
    elif ELEMENT_CONTROLS.get(ot_elem) == dm_elem:
        key = ("power_indirect" if same_pol else "power_direct", same_pol)
    elif ELEMENT_GENERATES.get(ot_elem) == dm_elem:
        key = ("resource_indirect" if same_pol else "resource_direct", same_pol)
    else:
        return None

    return TEN_GODS_TABLE.get(key)

# ---------------------------------------------------------------------------
# 5. 지장간 요약 (Hidden Stems quick lookup)
# ---------------------------------------------------------------------------

def get_hidden_stems(branch: str) -> List[str]:
    """지지 → 지장간 목록 (primary first)."""
    data = EARTHLY_BRANCHES.get(branch)
    return data["hidden_stems"] if data else []

# ---------------------------------------------------------------------------
# 6. 시진 (Shichen) 분류
# ---------------------------------------------------------------------------

SHICHEN_ORDER: List[str] = [
    "子", "丑", "寅", "卯", "辰", "巳",
    "午", "未", "申", "酉", "戌", "亥",
]

def get_shichen(hour: int, minute: int = 0) -> Tuple[str, bool]:
    """시각 → 시진 (지지), 야자시 여부 반환.

    야자시(夜子時): 23:00~00:00 출생은 일부 유파에서 다음 날 子時로 처리.
    Fortune Oracle에서는 경고만 하고 결정은 사용자에게 맡긴다.

    Returns:
        (branch, is_yajashi_boundary)
        is_yajashi_boundary = True이면 야자시 경계 경고
    """
    total_min = hour * 60 + minute
    is_boundary = (hour == 23)  # 23:00–24:00 → 야자시 경계

    # 시진 범위: 子 23:00–01:00, 丑 01:00–03:00, ..., 亥 21:00–23:00
    if total_min >= 23 * 60 or total_min < 1 * 60:
        return ("子", is_boundary)
    idx = (total_min - 60) // 120 + 1  # 丑=1, 寅=2, ...
    idx = max(0, min(idx, 11))
    return (SHICHEN_ORDER[idx], False)

# ---------------------------------------------------------------------------
# 7. 월간 간지 도출 — 년간 기반 (Month Stem Derivation)
# ---------------------------------------------------------------------------

# 년간 그룹 → 인월(寅月) 간 시작 천간
_MONTH_STEM_START: Dict[str, str] = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}

_STEM_SEQUENCE = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
# 寅月부터 순서대로 지지
_MONTH_BRANCH_FROM_YIN = [
    "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"
]

def get_month_ganzhi(year_stem: str, month_branch: str) -> Optional[str]:
    """년간 + 월지 → 월주 간지 (예: "丙寅").

    Args:
        year_stem: 년간 천간 (예: "甲")
        month_branch: 월지 (예: "寅")

    Returns:
        간지 문자열 (예: "丙寅") 또는 None
    """
    start_stem = _MONTH_STEM_START.get(year_stem)
    if not start_stem or month_branch not in _MONTH_BRANCH_FROM_YIN:
        return None
    branch_idx = _MONTH_BRANCH_FROM_YIN.index(month_branch)
    start_idx = _STEM_SEQUENCE.index(start_stem)
    stem_idx = (start_idx + branch_idx) % 10
    return _STEM_SEQUENCE[stem_idx] + month_branch

# ---------------------------------------------------------------------------
# 8. 오행 균형 helper
# ---------------------------------------------------------------------------

ELEMENT_KEYS_KOR = ["목", "화", "토", "금", "수"]

def analyze_element_balance(elements: Dict[str, int]) -> Dict:
    """오행 분포를 분석해 균형 정보 반환.

    Returns dict:
        dominant: 가장 많은 오행 (없으면 None)
        weak: 가장 적은 오행 (0인 경우)
        missing: 0개인 오행 목록
        balance_note: 짧은 설명 문자열
    """
    total = sum(elements.values())
    if total == 0:
        return {"dominant": None, "weak": None, "missing": [], "balance_note": "오행 정보 없음"}

    sorted_elems = sorted(elements.items(), key=lambda x: -x[1])
    dominant = sorted_elems[0][0] if sorted_elems[0][1] > 0 else None
    missing = [e for e, v in elements.items() if v == 0]
    weak = sorted_elems[-1][0] if sorted_elems[-1][1] == 0 else None

    # 균형 평가
    max_v = sorted_elems[0][1]
    min_v = sorted_elems[-1][1]
    if max_v - min_v <= 1:
        balance_note = "오행이 비교적 고르게 분포되어 있습니다."
    elif missing:
        balance_note = f"{'·'.join(missing)} 기운이 차트에서 비어 있습니다."
    else:
        balance_note = f"{dominant} 기운이 상대적으로 강하게 나타납니다."

    return {
        "dominant": dominant,
        "weak": weak,
        "missing": missing,
        "balance_note": balance_note,
    }

# ---------------------------------------------------------------------------
# 9. 출처/라이선스 메타
# ---------------------------------------------------------------------------

ATTRIBUTION = {
    "source_repo": "https://github.com/jinchenma94/bazi-skill",
    "license": "MIT",
    "adaptation": "Fortune Oracle Phase 12 — reference table only, deterministic lookup",
    "disclaimer": (
        "이 참고 자료는 오락과 자기성찰 용도이며 "
        "의학, 투자, 법률 결정을 지시하지 않습니다."
    ),
}
