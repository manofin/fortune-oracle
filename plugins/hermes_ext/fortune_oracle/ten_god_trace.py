#!/usr/bin/env python3
"""Fortune Oracle — Ten God Trace helpers (Phase 36).

Deterministic helpers that map each pillar's stem/branch to its
Ten God (십신) role relative to the day master. Does NOT replace
any calculation engine — purely an explainability layer.

Principles:
- Deterministic, fail-open
- No external network/AI calls
- No raw dataclass repr in user output
- No medical/investment/legal/career/parent determinative claims

This result is for self-reflection and option-checking reference only.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hermes_ext.fortune_oracle.bazi_trace import (
    HiddenStemSummary,
    HiddenStemTrace,
    TenGodSummary,
    TenGodTrace,
)

# ---------------------------------------------------------------------------
# 십신 매핑 테이블
# ---------------------------------------------------------------------------

# 오행 → 양/음 구분
_STEM_YIN_YANG: Dict[str, str] = {
    "甲": "양", "乙": "음",
    "丙": "양", "丁": "음",
    "戊": "양", "己": "음",
    "庚": "양", "辛": "음",
    "壬": "양", "癸": "음",
}

# 오행 매핑
_STEM_ELEMENT: Dict[str, str] = {
    "甲": "목", "乙": "목",
    "丙": "화", "丁": "화",
    "戊": "토", "己": "토",
    "庚": "금", "辛": "금",
    "壬": "수", "癸": "수",
}

# 십신 이름 테이블: (관계, 음양 동일 여부) → 십신
_TEN_GOD_TABLE: Dict[Tuple[str, bool], str] = {
    # same element, same yin-yang → 비견
    ("same", True): "비견",
    # same element, different yin-yang → 겁재
    ("same", False): "겁재",
    # element that day master produces (食傷)
    ("produces", True): "식신",
    ("produces", False): "상관",
    # element that day master controls (財)
    ("controls", True): "정재",
    ("controls", False): "편재",
    # element that produces day master (印)
    ("produced_by", True): "정인",
    ("produced_by", False): "편인",
    # element that controls day master (官殺)
    ("controls_me", True): "정관",
    ("controls_me", False): "편관",
}

# 오행 생극 관계 (상생/상극)
_SHENG: Dict[str, str] = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
_KE: Dict[str, str] = {"목": "토", "화": "금", "토": "수", "금": "목", "수": "화"}

# 지장간 매핑 (기존 bazi_relations/yongshen과 동일)
_HIDDEN_STEMS: Dict[str, list] = {
    "子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"],
    "卯": ["乙"], "辰": ["戊", "乙", "癸"], "巳": ["丙", "庚", "戊"],
    "午": ["丁", "己"], "未": ["己", "丁", "乙"], "申": ["庚", "壬", "戊"],
    "酉": ["辛"], "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"],
}

# 천간 합 (六合天干)
_TIANGAN_HE: Dict[str, str] = {
    "甲": "己", "乙": "庚", "丙": "辛",
    "丁": "壬", "戊": "癸",
    "己": "甲", "庚": "乙", "辛": "丙",
    "壬": "丁", "癸": "戊",
}


# ---------------------------------------------------------------------------
# 십신 계산
# ---------------------------------------------------------------------------

def _get_relationship(dm_element: str, target_element: str) -> Optional[str]:
    """일간 오행과 타 오행의 관계 반환."""
    if dm_element == target_element:
        return "same"
    if _SHENG.get(dm_element) == target_element:
        return "produces"
    if _KE.get(dm_element) == target_element:
        return "controls"
    if _SHENG.get(target_element) == dm_element:
        return "produced_by"
    if _KE.get(target_element) == dm_element:
        return "controls_me"
    return None


def get_ten_god(stem: str, day_master_stem: str) -> Optional[str]:
    """천간과 일간 간의 십신 관계 반환.

    Args:
        stem: 평가할 천간 (e.g. "甲")
        day_master_stem: 일간 천간 (e.g. "丙")

    Returns:
        십신 이름 또는 None
    """
    if not stem or not day_master_stem:
        return None

    dm_elem = _STEM_ELEMENT.get(day_master_stem, "")
    tgt_elem = _STEM_ELEMENT.get(stem, "")
    if not dm_elem or not tgt_elem:
        return None

    rel = _get_relationship(dm_elem, tgt_elem)
    if rel is None:
        return None

    same_yy = _STEM_YIN_YANG.get(stem, "") == _STEM_YIN_YANG.get(day_master_stem, "")
    return _TEN_GOD_TABLE.get((rel, same_yy), "")


# ---------------------------------------------------------------------------
# TenGodTrace 생성
# ---------------------------------------------------------------------------

def build_ten_god_trace(
    eight_char: Dict[str, str],
    day_master_stem: str,
) -> TenGodTrace:
    """팔자 각 기둥의 천간/지지에 대한 십신 trace 생성.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        day_master_stem: 일간 천간 (e.g. "丙")

    Returns:
        TenGodTrace
    """
    trace = TenGodTrace()
    if not eight_char or not day_master_stem:
        return trace

    pillar_labels = {
        "year": "년천간", "month": "월천간", "day": "일천간", "time": "시천간",
    }

    for pillar_key, label in pillar_labels.items():
        gz = eight_char.get(pillar_key, "")
        if not gz:
            continue

        # 천간 십신
        stem = gz[0] if len(gz) >= 1 else ""
        if stem and stem != day_master_stem:
            tg = get_ten_god(stem, day_master_stem)
            if tg:
                trace.items.append(f"{label} {stem} → {tg}")
        elif stem == day_master_stem:
            trace.items.append(f"{label} {stem} → 일간")

        # 지지의 주 기신(주 기간) 십신
        branch = gz[1] if len(gz) >= 2 else ""
        if branch:
            branch_label = label.replace("천간", "지지")
            # 지장간의 주 기신(첫 번째)만 사용
            hidden = _HIDDEN_STEMS.get(branch, [])
            if hidden:
                tg = get_ten_god(hidden[0], day_master_stem)
                if tg:
                    trace.items.append(f"{branch_label} {branch}({hidden[0]}) → {tg}")

    return trace


# ---------------------------------------------------------------------------
# HiddenStemTrace 생성
# ---------------------------------------------------------------------------

def build_hidden_stem_trace(
    eight_char: Dict[str, str],
    day_master_stem: str,
) -> HiddenStemTrace:
    """각 지지의 장간 기여도를 trace.

    Args:
        eight_char: 팔자 사주
        day_master_stem: 일간 천간

    Returns:
        HiddenStemTrace
    """
    trace = HiddenStemTrace()
    if not eight_char or not day_master_stem:
        return trace

    for pillar_key in ("year", "month", "day", "time"):
        gz = eight_char.get(pillar_key, "")
        branch = gz[1] if len(gz) >= 2 else ""
        if not branch:
            continue

        hidden = _HIDDEN_STEMS.get(branch, [])
        if not hidden:
            continue

        parts = []
        for hs in hidden:
            tg = get_ten_god(hs, day_master_stem)
            if tg:
                parts.append(f"{hs}({tg})")
            else:
                parts.append(hs)

        trace.items.append(f"{branch}: {'·'.join(parts)}")

    return trace


# ---------------------------------------------------------------------------
# TenGodSummary / HiddenStemSummary (BaziTrace용)
# ---------------------------------------------------------------------------

def build_ten_god_summary(
    eight_char: Dict[str, str],
    day_master_stem: str,
) -> TenGodSummary:
    """TenGodTrace → TenGodSummary (BaziTrace에 넣을 요약)."""
    tg = build_ten_god_trace(eight_char, day_master_stem)
    return TenGodSummary(summaries=tg.items)


def build_hidden_stem_summary(
    eight_char: Dict[str, str],
    day_master_stem: str,
) -> HiddenStemSummary:
    """HiddenStemTrace → HiddenStemSummary (BaziTrace에 넣을 요약)."""
    hs = build_hidden_stem_trace(eight_char, day_master_stem)
    # BaziTrace에 넣을 compact summary
    return HiddenStemSummary(summaries=[item.split(":")[0] + ":" + item.split(":")[1].replace("(", "").replace(")", "").replace("·", "") for item in hs.items])
