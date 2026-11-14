"""Western Astrology — Pure Ticket Issuer (v2, Big Three only).

핵심 3개(태양·달·상승궁)만 매핑 → 1~3 티켓.
나머지 행성 제외 (변별력 확보, 자미두수 명궁과 동등 해상도).
aspect는 핵심 3개 간 보정으로만.
점수화 없음. 티켓만 발급.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# 12사인 → 5원형 매핑
_SIGN_TO_ARCHETYPE: Dict[str, str] = {
    "양자리": "리더",
    "황소자리": "실행",
    "쌍둥이자리": "사고",
    "게자리": "온화",
    "사자자리": "리더",
    "처녀자리": "실행",
    "천칭자리": "온화",
    "전갈자리": "독립",
    "궁수자리": "사고",
    "염소자리": "실행",
    "물병자리": "독립",
    "물고기자리": "온화",
}

# 핵심 3개 (Big Three) — 이 행성만 매핑
_CORE_PLANETS = {"태양", "달"}

# aspect 보정: 핵심 3개 간 관계만
_ASPECT_STRENGTHEN: Dict[str, str] = {
    "합": "강화",
    "삼합": "안정 발현",
}


def _parse_western_planet(s: str) -> Optional[Tuple[str, str, float]]:
    """Parse '태양 물병자리 3.6°' → (planet_kor, sign_kor, degree)."""
    s = s.strip()
    if not s:
        return None
    parts = s.split(' ')
    if len(parts) < 3:
        return None
    planet = parts[0]
    sign = parts[1]
    try:
        degree = float(parts[2].replace('°', ''))
    except ValueError:
        degree = 0.0
    return planet, sign, degree


def _parse_western_aspect(s: str) -> Optional[Tuple[str, str, str, float]]:
    """Parse '태양-수성 합 (orb 5.1°)' → (p1, p2, type, orb)."""
    s = s.strip()
    if not s:
        return None
    # p1-p2 type (orb X.X°)
    try:
        p1_rest, p2_orb = s.split('-', 1)
        p2, type_orb = p2_orb.strip().split(' ', 1)
        type_part, orb_part = type_orb.strip().split(' (orb ')
        aspect_type = type_part.strip()
        orb = float(orb_part.replace('°)', '').replace('°', ''))
        return p1_rest.strip(), p2.strip(), aspect_type, orb
    except Exception:
        return None


def issue_western_tickets(facts: Dict[str, Any]) -> Dict[str, Any]:
    """western facts → pure ticket structure.

    BIG THREE ONLY: 태양·달·상승궁만 매핑.
    나머지 행성은 aspect 보정 시 참조용으로만.

    Returns:
        {"ok": bool, "tickets": [str, ...], "labels": {원형: [라벨, ...]}, "raw_hints": {...}}
    """
    if not facts:
        return {"ok": False, "tickets": [], "labels": {}, "raw_hints": {}}

    tickets: List[str] = []
    labels: Dict[str, List[str]] = {}
    hints: Dict[str, Any] = {
        "core_planets": [],
        "ascendant": "",
        "aspects": [],
    }

    # 1. 핵심 3개: 태양, 달
    for p in facts.get("planets", []) or []:
        parsed = _parse_western_planet(p)
        if not parsed:
            continue
        planet, sign, degree = parsed
        # 핵심 3개만 매핑
        if planet not in _CORE_PLANETS:
            continue
        arch = _SIGN_TO_ARCHETYPE.get(sign)
        if arch:
            hints["core_planets"].append({"planet": planet, "sign": sign, "degree": degree})
            if arch not in tickets:
                tickets.append(arch)
                labels.setdefault(arch, []).append(planet)

    # 2. 핵심 3개: 상승궁 (Ascendant)
    asc = facts.get("ascendant", "") or ""
    hints["ascendant"] = asc
    if asc:
        # "Ascendant 전갈자리 17.4°"
        parts = asc.split(' ')
        sign = parts[1] if len(parts) > 1 else ""
        arch = _SIGN_TO_ARCHETYPE.get(sign)
        if arch:
            if arch not in tickets:
                tickets.append(arch)
                labels.setdefault(arch, []).append("상승궁")
            else:
                if "상승궁 강화" not in (labels.get(arch) or []):
                    labels.setdefault(arch, []).append("상승궁 강화")

    # 3. aspect 보정: 핵심 3개 간 관계만
    for a in facts.get("aspects", []) or []:
        parsed = _parse_western_aspect(a)
        if not parsed:
            continue
        p1, p2, aspect_type, orb = parsed
        hints["aspects"].append({"p1": p1, "p2": p2, "type": aspect_type, "orb": orb})

        # 핵심 3개 간 aspect만 보정
        if p1 not in _CORE_PLANETS and p2 not in _CORE_PLANETS:
            continue

        # 강화 라벨
        if aspect_type in _ASPECT_STRENGTHEN:
            # 핵심 행성 기준 원형 찾기
            target = p1 if p1 in _CORE_PLANETS else p2
            for cp in (facts.get("planets") or []):
                cp_parsed = _parse_western_planet(cp)
                if cp_parsed and cp_parsed[0] == target:
                    arch = _SIGN_TO_ARCHETYPE.get(cp_parsed[1])
                    if arch and arch in tickets:
                        label = _ASPECT_STRENGTHEN[aspect_type]
                        if label not in (labels.get(arch) or []):
                            labels.setdefault(arch, []).append(label)
                    break

    # 정리
    for k in list(labels.keys()):
        labels[k] = list(dict.fromkeys(labels[k]))

    return {
        "ok": True,
        "tickets": tickets,
        "labels": labels,
        "raw_hints": hints,
    }


def format_western_tickets(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return "티켓 발급 실패"
    lines = [f"티켓: {', '.join(result['tickets'])}"]
    labels = result.get("labels", {})
    for arch in result["tickets"]:
        lbl = labels.get(arch, [])
        lines.append(f"  {arch}: {', '.join(lbl) if lbl else '(라벨 없음)'}")
    return "\n".join(lines)
