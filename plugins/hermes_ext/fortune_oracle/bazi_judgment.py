"""Fortune Oracle — Bazi Judgment Engine v1 (사주 원형 판정기).

사주 팔자로부터 5원형(리더/독립/사고/온화/실행) % 분포를 결정론적으로 산출.

논리:
1. 일간 강약 거친 판정 (신강/신약/중화):
   득령 여부 + 통근 + 돕는 것(비겁·인성) vs 빼는 것(재·관·식상)
2. 십신 점수화 (득령 큰 가중, 통근/투출 보조)
3. 일간 강약 보정 (신약 시 재성/관성 → "압도" 성격, 신강 시 "다루는" 성격)
4. 5원형 합산 → % 분포 + 우세 뚜렷함(50%+)

5원형 매핑:
- 리더: 정관(正官) + 칠살(七殺/偏官)
- 독립: 비겁(비견+겁재)
- 사고: 상관(傷官)
- 온화: 정인(正印) + 식신(食神) + 편인(偏印)
- 실행: 정재(正財) + 편재(偏財)

※ 격국은 수렴 핵 제외(고유 문법 층).

금지:
- 확정 예언/진단 금지
- raw birth_date 노출 금지
- 외부 네트워크/AI 호출 없음
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .bazi_reference import (
    BRANCH_ELEMENT,
    EARTHLY_BRANCHES,
    ELEMENT_CONTROLS,
    ELEMENT_GENERATES,
    ELEMENT_TO_STEMS,
    HEAVENLY_STEMS,
    SHICHEN_ORDER,
    TEN_GODS_TABLE,
    _stem_element,
    _stem_polarity,
    get_hidden_stems,
    get_ten_god,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

# 득령 가중: 일지가 일간과 같은 오행이면 득령
# 득령이면 해당 오행의 점수 배수
DE_LING_WEIGHT = 1.5  # 득령일 때 해당 오행 세력 가중 (1.8→1.5: 식신 폭증 완화)

# 통근 가중: 일간과 같은 오행의 천간이 다른 곳에 있으면 통근
TONG_GEN_WEIGHT = 1.3  # 통근일 때 비겁 세력 가중

# 투출 가중: 지지에 같은 오행의 지장간이 있으면 투출
TOU_CHU_WEIGHT = 1.15  # 투출일 때 해당 십신 세력 가중

# 5원형 매핑 (십신 → 원형)
SHISHEN_TO_ARCHETYPE: Dict[str, str] = {
    # 리더형: 권력, 책임, 원칙, 도전
    "정관": "리더",
    "편관": "리더",
    # 독립형: 자립, 경쟁, 사교
    "비견": "독립",
    "겁재": "독립",
    # 사고형: 혁신, 예술, 독창성
    "상관": "사고",
    # 온화형: 학문, 창의, 공감
    "정인": "온화",
    "편인": "온화",
    "식신": "온화",
    # 실행형: 재물, 성실, 기회
    "정재": "실행",
    "편재": "실행",
}

# 원형 이름/설명
ARCHETYPE_INFO: Dict[str, Dict[str, str]] = {
    "리더": {
        "hanja": "リーダー型",
        "desc": "책임감과 원칙으로 주변을 이끄는 기질",
        "shishen": "정관·칠살",
    },
    "독립": {
        "hanja": "獨立型",
        "desc": "자립심과 추진력으로 스스로 길을 여는 기질",
        "shishen": "비겁",
    },
    "사고": {
        "hanja": "思考型",
        "desc": "혁신과 독창성으로 기존 틀을 넘어선다",
        "shishen": "상관",
    },
    "온화": {
        "hanja": "溫和型",
        "desc": "배움과 공감으로 깊이 있게 연결하는 기질",
        "shishen": "정인·편인·식신",
    },
    "실행": {
        "hanja": "実行型",
        "desc": "꾸준한 노력과 기회 감각으로 구체화하는 기질",
        "shishen": "정재·편재",
    },
}

# ---------------------------------------------------------------------------
# 1. 일간 강약 판정
# ---------------------------------------------------------------------------

def _count_element_in_pillars(
    eight_char: Dict[str, str],
    element: str,
    count_hidden: bool = True,
) -> Dict[str, Any]:
    """주(柱)에서 특정 오행의 세력을 세어 반환.

    Returns:
        {
            "stems": int,          # 천간에서 나온 횟수
            "branches": int,       # 지지에서 나온 횟수
            "hidden": int,         # 지장간에서 나온 횟수
            "total_raw": int,      # 합계(가중 미적용)
            "de_ling": bool,       # 일지가 이 오행이면 True
        }
    """
    stem_count = 0
    branch_count = 0
    hidden_count = 0
    de_ling = False

    for pillar_name, gz in eight_char.items():
        if not gz or len(gz) < 2:
            continue
        stem = gz[0]
        branch = gz[1]

        # 천간
        if _stem_element(stem) == element:
            stem_count += 1

        # 지지 주 기운
        if BRANCH_ELEMENT.get(branch) == element:
            branch_count += 1
            if pillar_name == "day":
                de_ling = True

        # 지장간 (투출)
        if count_hidden:
            for hs in get_hidden_stems(branch):
                if _stem_element(hs) == element:
                    hidden_count += 1

    return {
        "stems": stem_count,
        "branches": branch_count,
        "hidden": hidden_count,
        "total_raw": stem_count + branch_count + hidden_count,
        "de_ling": de_ling,
    }

def judge_day_strength(
    day_master: str,
    eight_char: Dict[str, str],
) -> Dict[str, Any]:
    """일간 강약 판정.

    논리:
    1. 일간 오행을 도는 것(비겁 + 인성) vs 빼는 것(재 + 관 + 식상) 세력 비교
    2. 득령(일지가 일간과 같은 오행)이면 가중
    3. 통근(다른 천간에 같은 오행)이면 가중

    Returns:
        {
            "strength": "신강" | "신약" | "중화",
            "help_score": float,    # 돕는 세력(가중 후)
            "drain_score": float,   # 빼는 세력(가중 후)
            "de_ling": bool,        # 득령 여부
            "tong_gen": bool,       # 통근 여부
            "element": str,         # 일간 오행
        }
    """
    dm_element = _stem_element(day_master)
    if dm_element == "?":
        return {
            "strength": "중화",
            "help_score": 0.0,
            "drain_score": 0.0,
            "de_ling": False,
            "tong_gen": False,
            "element": dm_element,
        }

    # 일간 오행 세력 (득령 + 통근 체크)
    dm_count = _count_element_in_pillars(eight_char, dm_element)
    de_ling = dm_count["de_ling"]
    tong_gen = dm_count["stems"] > 1  # 일간 외에도 같은 오행 천간이 있으면 통근

    help_score = 0.0
    drain_score = 0.0

    # 일간 오행의 세력 (비겁)
    base = dm_count["stems"] + dm_count["branches"] * 0.5 + dm_count["hidden"] * 0.3
    if de_ling:
        base *= DE_LING_WEIGHT
    if tong_gen:
        base *= TONG_GEN_WEIGHT
    help_score += base

    # 인성 (일간을 생하는 오행)
    resource_element = None
    for elem, generated in ELEMENT_GENERATES.items():
        if generated == dm_element:
            resource_element = elem
            break

    if resource_element:
        res_count = _count_element_in_pillars(eight_char, resource_element)
        res_base = res_count["stems"] + res_count["branches"] * 0.5 + res_count["hidden"] * 0.3
        help_score += res_base

    # 빼는 것: 재성 + 관성 + 식상
    # 재성: 일간이 극하는 오행
    wealth_element = ELEMENT_CONTROLS.get(dm_element)
    if wealth_element:
        we_count = _count_element_in_pillars(eight_char, wealth_element)
        drain_score += we_count["stems"] + we_count["branches"] * 0.5 + we_count["hidden"] * 0.3

    # 관성: 일간을 극하는 오행
    for elem, controlled in ELEMENT_CONTROLS.items():
        if controlled == dm_element:
            power_element = elem
            pw_count = _count_element_in_pillars(eight_char, power_element)
            drain_score += pw_count["stems"] + pw_count["branches"] * 0.5 + pw_count["hidden"] * 0.3
            break

    # 식상: 일간이 생하는 오행
    output_element = ELEMENT_GENERATES.get(dm_element)
    if output_element:
        out_count = _count_element_in_pillars(eight_char, output_element)
        drain_score += out_count["stems"] + out_count["branches"] * 0.5 + out_count["hidden"] * 0.3

    # 강약 판단
    ratio = help_score / (drain_score + 0.001)
    if ratio >= 1.3:
        strength = "신강"
    elif ratio <= 0.7:
        strength = "신약"
    else:
        strength = "중화"

    return {
        "strength": strength,
        "help_score": round(help_score, 2),
        "drain_score": round(drain_score, 2),
        "de_ling": de_ling,
        "tong_gen": tong_gen,
        "element": dm_element,
        "ratio": round(ratio, 2),
    }

# ---------------------------------------------------------------------------
# 2. 십신 점수화 (5원형)
# ---------------------------------------------------------------------------

def compute_shishen_scores(
    day_master: str,
    eight_char: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    """8개의 십신에 대해 점수화.

    각 십신:
    - count: 주에서 나온 횟수(천간)
    - branch_count: 지지 본기에서 나온 횟수 (층1, 필수)
    - hidden_count: 지장간 암장에서 나온 횟수 (층2, 보조)
    - tou_chu: 투출 여부(지장간에 같은 오행 존재)
    - de_ling: 해당 오행의 득령 여부
    - score: 가중 점수

    Returns:
        {십신명: {"count": int, "branch_count": int, "hidden_count": int, "tou_chu": bool, "de_ling": bool, "score": float}}
    """
    # 8개의 십신 매핑 (관계 유형, 극성) → 십신명
    shishen_map = {
        "비견": ("self", True),
        "겁재": ("self", False),
        "식신": ("output", True),
        "상관": ("output", False),
        "편재": ("wealth_indirect", True),
        "정재": ("wealth_direct", False),
        "편관": ("power_indirect", True),
        "정관": ("power_direct", False),
        "편인": ("resource_indirect", True),
        "정인": ("resource_direct", False),
    }

    dm_element = _stem_element(day_master)
    dm_pol = _stem_polarity(day_master)

    result = {}

    # ---- 천간 매핑 (기존) ----
    for pillar_name, gz in eight_char.items():
        if not gz or len(gz) < 2:
            continue
        stem = gz[0]
        if stem == day_master:
            continue  # 일간 자체는 십신 아님

        tg = get_ten_god(day_master, stem)
        if not tg:
            continue

        shishen_name = tg["name"]
        if shishen_name not in result:
            # 이 십신의 오행 확인
            shishen_element = _stem_element(stem)
            result[shishen_name] = {
                "count": 0,
                "branch_count": 0,
                "hidden_count": 0,
                "tou_chu": False,
                "de_ling": False,
                "score": 0.0,
                "element": shishen_element,
            }

        result[shishen_name]["count"] += 1

    # ---- 층1: 지지 본기 오행 → 십신 매핑 ----
    # 각 지지의 본기 오행(BRANCH_ELEMENT)을 십신으로 매핑.
    # 未=토 → 甲木에게 재성(편재) 등.
    for pillar_name, gz in eight_char.items():
        if not gz or len(gz) < 2:
            continue
        branch = gz[1]
        branch_elem = BRANCH_ELEMENT.get(branch)
        if not branch_elem:
            continue

        # 본기 오행 → 천간 찾기 (같은 오행의 천간에서 극성 일치 우선)
        matched_stem = None
        for s in HEAVENLY_STEMS:
            if _stem_element(s) == branch_elem:
                if _stem_polarity(s) == dm_pol:
                    matched_stem = s  # 극성 일치 우선
                    break
        if not matched_stem:
            # 극성 일치 안 하면 첫 번째로 찾은 것 사용
            for s in HEAVENLY_STEMS:
                if _stem_element(s) == branch_elem:
                    matched_stem = s
                    break

        if not matched_stem:
            continue

        tg = get_ten_god(day_master, matched_stem)
        if not tg:
            continue

        shishen_name = tg["name"]
        if shishen_name not in result:
            result[shishen_name] = {
                "count": 0,
                "branch_count": 0,
                "hidden_count": 0,
                "tou_chu": False,
                "de_ling": False,
                "score": 0.0,
                "element": branch_elem,
            }

        result[shishen_name]["branch_count"] += 1

    # ---- 층2: 지장간 암장 (기존) ----
    for pillar_name, gz in eight_char.items():
        if not gz or len(gz) < 2:
            continue
        branch = gz[1]
        for hs in get_hidden_stems(branch):
            tg = get_ten_god(day_master, hs)
            if not tg:
                continue
            shishen_name = tg["name"]
            if shishen_name in result:
                result[shishen_name]["hidden_count"] += 1
                if not result[shishen_name]["tou_chu"]:
                    result[shishen_name]["tou_chu"] = True

    # ---- 득령 체크 (기존) ----
    day_branch = eight_char.get("day", "")[1] if eight_char.get("day") and len(eight_char["day"]) >= 2 else ""
    day_branch_element = BRANCH_ELEMENT.get(day_branch, "")
    for shishen_name, info in result.items():
        if info["element"] == day_branch_element:
            info["de_ling"] = True

    # ---- 점수 계산 ----
    for shishen_name, info in result.items():
        score = info["count"] * 1.0          # 천간 기본
        score += info["branch_count"] * 0.7  # 지지 본기 (천간과 약간 낮은 가중)
        score += info["hidden_count"] * 0.3  # 지장간 암장 (보조)
        if info["tou_chu"]:
            score *= TOU_CHU_WEIGHT  # 투출 가중
        if info["de_ling"]:
            score *= DE_LING_WEIGHT  # 득령 가중
        info["score"] = round(score, 2)

    return result

# ---------------------------------------------------------------------------
# 3. 5원형 합산
# ---------------------------------------------------------------------------

def compute_archetype_distribution(
    day_master: str,
    eight_char: Dict[str, str],
    strength_info: Dict[str, Any],
) -> Dict[str, Any]:
    """우세 원형 + 강약 라벨을 반환 (C-1 우세-범주 모드).

    논리:
    1. 십신 점수 → 5원형으로 매핑
    2. arch_scores 정렬 → 점수 차이 기반 우세 분류 (단일/복합/다면적)
    3. 강약 라벨 + 재관(실행/리더) 우세 조건으로 "(압도/다루는)" 부착

    분류 임계값(초기값, 검증에서 조정):
    - _STRONG_GAP=1.2  : 1위-2위 차가 이상 → 단일 우세
    - _MULTI_GAP=0.6   : 이상 → 복합 우세
    - 미만            → 다면적
    """
    shishen_scores = compute_shishen_scores(day_master, eight_char)
    strength = strength_info["strength"]

    # 5원형 합산 (참고용)
    arch_scores: Dict[str, float] = {
        "리더": 0.0,
        "독립": 0.0,
        "사고": 0.0,
        "온화": 0.0,
        "실행": 0.0,
    }

    for shishen_name, info in shishen_scores.items():
        archetype = SHISHEN_TO_ARCHETYPE.get(shishen_name)
        if archetype:
            arch_scores[archetype] += info["score"]

    # 두드러진 십신 상위 1~2개 (거친 서술)
    sorted_shishen = sorted(shishen_scores.items(), key=lambda x: -x[1]["score"])
    positive_scores = [(name, s) for name, s in sorted_shishen if s["score"] > 0]
    if positive_scores:
        top_shishen = [name for name, _ in positive_scores[:2]]
    else:
        top_shishen = [sorted_shishen[0][0]] if sorted_shishen else []

    strength_label = f"{strength} (역학(극/통관) 미반영)"

    return {
        "top_shishen": top_shishen,
        "strength_label": strength_label,
        "strength": strength,
        "arch_scores_raw": {k: round(v, 2) for k, v in arch_scores.items()},
        "shishen_scores": shishen_scores,
        "strength_adjustment": "",
    }

# ---------------------------------------------------------------------------
# 4. 메인 함수
# ---------------------------------------------------------------------------

def analyze_bazi_archetype(
    eight_char: Dict[str, str],
    day_master: str,
) -> Dict[str, Any]:
    """사주 팔자로부터 5원형 분석을 반환.

    Args:
        eight_char: {"year": "丙寅", "month": "癸巳", "day": "戊寅", "time": "己未"}
        day_master: 일간 천간 (예: "戊")

    Returns:
        {
            "ok": bool,
            "day_master": str,
            "day_element": str,
            "strength": "신강" | "신약" | "중화",
            "strength_detail": dict,
            "distribution": {원형: %},
            "dominant": str | None,
            "archetypes": [원형명, ...],
            "strength_adjustment": str,
            "shishen_scores": dict,
        }
    """
    if not eight_char or not day_master:
        return {"ok": False, "error": "eight_char 또는 day_master가 비어 있습니다."}

    try:
        strength_info = judge_day_strength(day_master, eight_char)
        archetype = compute_archetype_distribution(day_master, eight_char, strength_info)

        return {
            "ok": True,
            "day_master": day_master,
            "day_element": strength_info["element"],
            "strength": strength_info["strength"],
            "strength_detail": strength_info,
            "top_shishen": archetype["top_shishen"],
            "strength_label": archetype["strength_label"],
            "strength_adjustment": "",
            "shishen_scores": archetype["shishen_scores"],
            "arch_scores_raw": archetype["arch_scores_raw"],
        }
    except Exception as e:
        logger.warning("bazi_judgment error: %s", e)
        return {"ok": False, "error": str(e)}


def issue_bazi_archetype_tickets(top_shishen: list[str]) -> dict[str, Any]:
    """bazi top_shishen → 거친 5원형 티켓 (점수화 없음).

    Args:
        top_shishen: compute_archetype_distribution 산출 상위 십신 1~2개.

    Returns:
        {"ok": bool, "tickets": [...], "labels": {...}, "raw_hints": {"top_shishen": [...]}}
    """
    if not top_shishen:
        return {"ok": True, "tickets": [], "labels": {}, "raw_hints": {"top_shishen": []}}
    tickets: list[str] = []
    labels: dict[str, list[str]] = {}
    for name in top_shishen:
        arch = SHISHEN_TO_ARCHETYPE.get(name)
        if not arch:
            continue
        if arch not in tickets:
            tickets.append(arch)
            labels.setdefault(arch, []).append("십신")
    return {
        "ok": True,
        "tickets": tickets,
        "labels": labels,
        "raw_hints": {"top_shishen": list(top_shishen)},
    }
