"""Ziwei Doushu interpretation helper.

Generates a short Korean interpretation from ziwei chart facts.
Uses only the data already computed by ziwei_bridge (安星法 Step 1-3).
No new calculation — purely a text renderer for oracle_renderer consumption.

Policy:
- No definitive language ("반드시", "확정", "결정적", "흉하다" 등).
- Reference-level phrasing only ("경향이 있습니다", "참고됩니다", "작용합니다").
- Maximum ~5-6 lines of interpretation text.
- 14정성 + 사화 + 주요 4길성(좌보·우필·문창·문곡) + 주요 4살성(화성·영성·지공·지겁)만 기본 출력.
- 천괴·천월·녹존·경양·타라 등은 facts에 보관하되 기본 해석에서 생략.
"""

from __future__ import annotations

# 명궁 지지별 기본 성향 (간략, 기존 호환)
MING_GONG_TRAITS = {
    "子": "내면의 세계를 깊이 탐구하는 경향이 있습니다.",
    "丑": "꾸준하고 신중한 성향이 있습니다.",
    "寅": "능동적이고 변화에 적극적인 경향이 있습니다.",
    "卯": "교감과 소통을 중시하는 경향이 있습니다.",
    "辰": "현실감과 실용성을 중시하는 경향이 있습니다.",
    "巳": "전략적 사고가 돋보이는 경향이 있습니다.",
    "午": "열정적이고 표현력이 풍부한 경향이 있습니다.",
    "未": "온화하고 배려심 있는 경향이 있습니다.",
    "申": "분석적 사고와 실행력이 돋보이는 경향이 있습니다.",
    "酉": "세부 감각이 예리하고 정교함을 중시하는 경향이 있습니다.",
    "戌": "책임감과 인내심이 두드러지는 경향이 있습니다.",
    "亥": "유연하고 직관력이 풍부한 경향이 있습니다.",
}

# 명궁 주성별 특성 (14성, 기존 호환)
MAIN_STAR_TRAITS = {
    "紫微": "리더십과 통찰력이 있는 경향이 있습니다.",
    "天機": "민첩한 사고와 적응력이 돋보이는 경향이 있습니다.",
    "太陽": "개방적이고 포용적인 성향이 있습니다.",
    "武曲": "결단력과 실행력이 두드러지는 경향이 있습니다.",
    "天同": "평화와 조화를 추구하는 경향이 있습니다.",
    "廉貞": "원칙성과 자제력이 돋보이는 경향이 있습니다.",
    "天府": "안정감과 관리 능력이 두드러지는 경향이 있습니다.",
    "太陰": "내면의 깊이와 섬세함이 돋보이는 경향이 있습니다.",
    "貪狼": "호기심과 도전 정신이 풍부한 경향이 있습니다.",
    "巨門": "분석력과 통찰력이 있는 경향이 있습니다.",
    "天相": "조정 능력과 신뢰감이 두드러지는 경향이 있습니다.",
    "天梁": "보호 본심과 지혜가 돋보이는 경향이 있습니다.",
    "七殺": "독립성과 돌파력이 두드러지는 경향이 있습니다.",
    "破軍": "변화와 혁신을 추구하는 경향이 있습니다.",
}

# 사화별 기본 흐름 (별에 따라 차별화)
SIHUA_BASE = {
    "祿": "재물과 여유가 쌓이는 흐름",
    "權": "영향력과 추진력이 커지는 흐름",
    "科": "명예와 인정이 따르는 흐름",
    "忌": "주의가 필요한 흐름으로 신중한 접근",
}

# 별별 사화 키워드 (14정성 전부 커버, "로" 연결)
# 忌는 코드에서 "에서" 로 조정
SIHUA_STAR_FLAVOR = {
    "紫微": "리더십과 통찰력으로",
    "天機": "기획과 지혜로",
    "太陽": "개방과 포용으로",
    "武曲": "결단과 실행으로",
    "天同": "평화와 조화로",
    "廉貞": "교섭과 관계로",
    "天府": "안정감과 관리 능력으로",
    "太陰": "내면의 깊이와 섬세함으로",
    "貪狼": "호기심과 도전 정신으로",
    "巨門": "분석력과 통찰력으로",
    "天相": "조정과 신뢰로",
    "天梁": "보호와 지혜로",
    "七殺": "독립과 돌파로",
    "破軍": "변화와 혁신으로",
}

BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
IDX = {b: i for i, b in enumerate(BRANCHES)}

INAUSPICIOUS_TENDENCY = {
    "화성": "열정적이고 추진력이 강한",
    "영성": "감수성이 풍부하고 직관적인",
    "지공": "자유롭고 유연한 사고를 하는",
    "지겁": "현실적이고 실용적인 판단을 하는",
}

AUSPICIOUS = ["좌보", "우필", "문창", "문곡"]
INAUSPICIOUS = ["화성", "영성", "지공", "지겁"]


def _has_final_consonant(word: str) -> bool:
    """한글 받침 유무 판정 (이/가, 은/는 등)."""
    if not word:
        return False
    last = word[-1]
    if '가' <= last <= '힣':
        code = ord(last) - 0xAC00
        return code % 28 != 0
    return False


def _particle(word: str, particle: str = "이") -> str:
    """받침 유무에 따라 이/가 또는 은/는 선택."""
    if particle == "이":
        return word + ("이" if _has_final_consonant(word) else "가")
    if particle == "은":
        return word + ("은" if _has_final_consonant(word) else "는")
    return word + particle


def _get_opposite_branch(branch: str) -> str:
    if branch not in IDX:
        return ""
    return BRANCHES[(IDX[branch] + 6) % 12]


def _get_sam_bang_sa_jeong_branches(ming_b: str) -> list[str]:
    """명궁 삼방사정: 명궁(0), 대조(6), 관록(+4), 재백(+8)."""
    if ming_b not in IDX:
        return []
    i = IDX[ming_b]
    return [
        BRANCHES[i],
        BRANCHES[(i + 6) % 12],
        BRANCHES[(i + 4) % 12],
        BRANCHES[(i + 8) % 12],
    ]


def generate_ziwei_note(
    stars: dict,
    ming_gong: dict,
    sihua: dict,
    wuxing_ju: dict = None,
    aux_stars: dict = None,
    ziwei_info: dict = None,
) -> str:
    """정통 안성법 해석 (Z5-2 최종, 化忌 일관성 보강).

    - 14정성 전부 SIHUA_STAR_FLAVOR 커버
    - 化忌 누락 별은 "XX의 기운에서" 기본형
    """
    parts: list[str] = []

    # 1. 명궁 + 오행국 + 주성 (공궁 처리 포함)
    try:
        branch = (ming_gong or {}).get("branch", "")
        ju_name = (wuxing_ju or {}).get("ju_name", "") if wuxing_ju else ""
        ming_idx = str((ming_gong or {}).get("index", ""))
        main_star = ""
        is_empty_palace = False
        placement_known = False

        if ming_idx and stars and isinstance(stars.get(ming_idx), list):
            ming_stars = stars[ming_idx]
            placement_known = True
            is_empty_palace = not ming_stars
            if ming_stars:
                main_star = ming_stars[0]

        if branch:
            line = f"명궁 {branch}"
            if ju_name:
                line += f"·{ju_name}"
            if main_star:
                line += f", 주성 {main_star}"
            elif is_empty_palace:
                opp_idx = str((IDX.get(branch, 0) + 6) % 12)
                opp_star = ""
                if opp_idx and stars and opp_idx in stars:
                    opp_stars = stars[opp_idx]
                    if opp_stars:
                        opp_star = opp_stars[0]
                if opp_star:
                    line += f" (공궁, 대조궁 {opp_star} 기운 참고)"
                else:
                    line += " (공궁)"
            if not placement_known:
                line += " — 명궁 별 배치 미확인으로 주성·대조궁 해석을 생략합니다."
            else:
                line += " 경향이 있습니다."
            parts.append(line)
    except (KeyError, TypeError, AttributeError):
        pass

    # 2. 주요 4길성 (보좌하는 기운) — 명궁 삼방사정 내 (최대 2개)
    try:
        if aux_stars and ming_gong:
            ming_b = (ming_gong or {}).get("branch", "")
            target_branches = _get_sam_bang_sa_jeong_branches(ming_b)
            found = []
            for star in AUSPICIOUS:
                star_b = aux_stars.get(star)
                if star_b in target_branches:
                    found.append(star)
                if len(found) >= 2:
                    break
            for star in found:
                parts.append(f"{_particle(star)} 명궁 삼방사정에 보좌하는 기운으로 작용합니다.")
    except (KeyError, TypeError, AttributeError):
        pass

    # 3. 주요 4살성 (기질/성향) — 명궁 삼방사정 내 (최대 2개)
    try:
        if aux_stars and ming_gong:
            ming_b = (ming_gong or {}).get("branch", "")
            target_branches = _get_sam_bang_sa_jeong_branches(ming_b)
            found = []
            for star in INAUSPICIOUS:
                star_b = aux_stars.get(star)
                if star_b in target_branches:
                    found.append(star)
                if len(found) >= 2:
                    break
            for star in found:
                tendency = INAUSPICIOUS_TENDENCY.get(star, "특징적인")
                parts.append(f"{_particle(star)} 삼방사정에 있어 {tendency} 경향이 있습니다.")
    except (KeyError, TypeError, AttributeError):
        pass

    # 4. 사화 (별 차별화 + 14정성 커버 + 化忌 일관성)
    for hua in ("祿", "權", "科", "忌"):
        try:
            hua_data = (sihua or {}).get(hua)
            if hua_data and hua_data.get("star"):
                star = hua_data["star"]
                base = SIHUA_BASE.get(hua, "흐름이 참고됩니다")
                flavor = SIHUA_STAR_FLAVOR.get(star, "")
                if flavor:
                    if hua == "忌":
                        action = flavor.replace("으로", "에서").replace("로", "에서")
                        text = f"化{hua}({star}): {action} {base}이 참고됩니다."
                    else:
                        text = f"化{hua}({star}): {flavor} {base}이 참고됩니다."
                else:
                    # 키워드 없는 별 (예: 일부 化忌) 은 기본형으로 일관
                    if hua == "忌":
                        text = f"化{hua}({star}): {star}의 기운에서 {base}이 참고됩니다."
                    else:
                        text = f"化{hua}({star}): {base}이 참고됩니다."
                parts.append(text)
        except (KeyError, TypeError, AttributeError):
            pass

    if not parts:
        return ""

    return "🔮 자미두수: " + "\n".join(parts)
