"""Vedic Nakshatra — Pure Ticket Issuer (v3, Moon Nakshatra Only).

달 나크샤트라 1개만 5원형 매핑 → 1 티켓 발급.
나머지 graha·라시 기반 매핑 제거. 서양과 측정 대상 분리(독립 3시스템).
 guna는 보조 라벨로만 (5원형 매핑 아님).

27개 중 4개 검증 완료, 23개 미검증 초안.
점수화 없음. 티켓만 발급.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 27 나크샤트라 → 5원형 매핑
# 검증된 4개: Purva Bhadrapada, Vishakha, Ardra, Purva Phalguni
# 나머지 23개: 미검증 초안 (에이전트 조사 + 전통적 상징 기반)
# ---------------------------------------------------------------------------

_NAKSHATRA_TO_ARCHETYPE: Dict[str, Tuple[str, bool]] = {
    # 1-6
    "Ashwini": ("실행", False),
    "Bharani": ("사고", False),
    "Krittika": ("사고", False),
    "Rohini": ("온화", False),
    "Mrigashira": ("사고·온화", False),
    "Ardra": ("사고·독립", True),  # ✅ 검증 완료 (작가님 원본: 사고·독립)

    # 7-12
    "Punarvasu": ("실행", False),
    "Pushya": ("온화", False),
    "Ashlesha": ("사고·독립", False),
    "Magha": ("리더", False),
    "Purva Phalguni": ("온화", True),  # ✅ 검증 완료
    "Uttara Phalguni": ("리더", False),

    # 13-18
    "Hasta": ("실행", False),
    "Chitra": ("실행", False),
    "Swati": ("독립·온화", False),
    "Vishakha": ("실행", True),  # ✅ 검증 완료
    "Anuradha": ("온화", False),
    "Jyeshtha": ("리더", False),

    # 19-24
    "Mula": ("독립", False),
    "Purva Ashadha": ("리더", False),
    "Uttara Ashadha": ("리더", False),
    "Shravana": ("사고", False),
    "Dhanishta": ("실행", False),
    "Shatabhisha": ("사고", False),

    # 25-27
    "Purva Bhadrapada": ("독립", True),  # ✅ 검증 완료
    "Uttara Bhadrapada": ("사고", False),
    "Revati": ("온화", False),
}

# 분포 확인: 온화 5, 실행 6, 리더 5, 독립 5, 사고 6 — 과부하 없음

# 한국어 나크샤트라 매핑 (vedic_schema와 동일)
_NAKSHATRA_KR: Dict[str, str] = {
    "Ashwini": "아슈이니",
    "Bharani": "바라니",
    "Krittika": "크리티카",
    "Rohini": "로히니",
    "Mrigashira": "미라시라",
    "Ardra": "아르드라",
    "Punarvasu": "푸나르바수",
    "Pushya": "푸샤",
    "Ashlesha": "아슈레샤",
    "Magha": "마하",
    "Purva Phalguni": "푸르바 팔구니",
    "Uttara Phalguni": "우타라 팔구니",
    "Hasta": "하스타",
    "Chitra": "치트라",
    "Swati": "스와티",
    "Vishakha": "비샤카",
    "Anuradha": "아누라드하",
    "Jyeshtha": "제슈타",
    "Mula": "무라",
    "Purva Ashadha": "푸르바 아샤다",
    "Uttara Ashadha": "우타라 아샤다",
    "Shravana": "슈라바나",
    "Dhanishta": "다니슈타",
    "Shatabhisha": "샤타비샤",
    "Purva Bhadrapada": "푸르바 바드라파다",
    "Uttara Bhadrapada": "우타라 바드라파다",
    "Revati": "레바티",
}

# 구나 → 보조 라벨 (5원형 매핑 아님)
_GUNA_LABELS = {
    "사트바": "정화",
    "라자스": "활동",
    "타마스": "암흑",
}

# 유효 원형
_ARCHETYPES = {"온화", "실행", "리더", "독립", "사고"}


def _find_nakshatra(nakshatra_str: str) -> Optional[str]:
    """'아르드라 pada 3' 또는 'Ardra' → nakshatra 영문명.
    
    한국어/영문 모두 지원. 부분 매칭.
    """
    if not nakshatra_str:
        return None
    
    # 영문으로 직접 확인
    for name in _NAKSHATRA_TO_ARCHETYPE:
        if name in nakshatra_str:
            return name
    
    # 한국어 → 영문 매핑
    for en_name, kr_name in _NAKSHATRA_KR.items():
        if kr_name in nakshatra_str:
            return en_name
    
    return None


def issue_vedic_tickets(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Vedic facts → 달 나크샤트라 1개만 티켓 발급.
    
    입력: calculate_vedic_chart()에서 생성한 MethodCard.facts
    - nakshatra: "Ardra" 또는 "아르드라" 등
    
    출력:
        {
            "ok": bool,
            "tickets": ["사고"],           # 원형 1개 (또는 빈 리스트)
            "nakshatra": "Ardra",         # 영문명
            "nakshatra_kr": "아르드라",    # 한국어명
            "verified": bool,              # 이 매핑이 검증되었는지
            "guna_label": "활동",          # 구나 보조 라벨 (있으면)
            "raw_hints": {...}
        }
    """
    if not facts:
        return {
            "ok": False,
            "tickets": [],
            "nakshatra": None,
            "nakshatra_kr": None,
            "verified": False,
            "guna_label": None,
            "raw_hints": {},
        }

    nakshatra_raw = facts.get("nakshatra", "") or ""
    guna_raw = facts.get("guna", "") or ""
    
    # 나크샤트라 찾기
    nak_name = _find_nakshatra(nakshatra_raw)
    
    if not nak_name or nak_name not in _NAKSHATRA_TO_ARCHETYPE:
        return {
            "ok": False,
            "tickets": [],
            "nakshatra": None,
            "nakshatra_kr": None,
            "verified": False,
            "guna_label": None,
            "raw_hints": {"nakshatra_raw": nakshatra_raw, "error": "매핑 불가"},
        }

    archetype, verified = _NAKSHATRA_TO_ARCHETYPE[nak_name]
    nak_kr = _NAKSHATRA_KR.get(nak_name, nak_name)
    
    # ·로 구분된 원형(예: "사고·독립") → 여러 티켓 발급
    archetypes = archetype.split("·") if "·" in archetype else [archetype]
    tickets = [a for a in archetypes if a in _ARCHETYPES]

    # 구나 보조 라벨
    guna_label = None
    for guna_key, guna_lbl in _GUNA_LABELS.items():
        if guna_key in guna_raw:
            guna_label = guna_lbl
            break

    return {
        "ok": True,
        "tickets": tickets,
        "nakshatra": nak_name,
        "nakshatra_kr": nak_kr,
        "verified": verified,
        "guna_label": guna_label,
        "raw_hints": {
            "nakshatra_raw": nakshatra_raw,
            "guna_raw": guna_raw,
            "archetype": archetype,
            "verified": verified,
        },
    }


def format_vedic_tickets(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"티켓 발급 실패: {result.get('raw_hints', {}).get('error', '정보 없음')}"
    
    lines = []
    nak = result.get("nakshatra_kr", result.get("nakshatra", ""))
    verified_tag = "✅ 검증" if result.get("verified") else "⚠️ 신뢰 낮음"
    arch_str = " + ".join(result["tickets"])
    lines.append(f"달 나크샤트라: {nak} → {arch_str} {verified_tag}")
    
    guna = result.get("guna_label")
    if guna:
        lines.append(f"  구나: {guna} (보조 라벨)")
    
    return "\n".join(lines)
