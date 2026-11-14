#!/usr/bin/env python3
"""Fortune Oracle — Western Astrology Interpreter (Phase 38C).

Western chart의 raw 데이터를 compact Korean interpretation으로 변환.
sanitize guard 포함: raw repr/traceback/raw dict dump 방지.

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .western_schema import (
    WesternChart,
    WesternPlanet,
    WesternAspect,
    KOREAN_PLANET_MAP,
    KOREAN_SIGN_MAP,
    KOREAN_ASPECT_MAP,
    WESTERN_DISCLAIMER,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# sanitize guard
# ---------------------------------------------------------------------------

_RAW_FORBIDDEN = [
    "WesternChart(",
    "WesternPlanet(",
    "WesternAspect(",
    "dataclass",
    "default_factory",
    "ok=True",
    "ok=False",
    "warnings=[",
]

def _is_raw_dump(text: str) -> bool:
    """raw repr/raw dict dump 감지."""
    if not text:
        return False
    if any(p in text for p in _RAW_FORBIDDEN):
        return True
    stripped = text.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or \
       (stripped.startswith("[") and stripped.endswith("]")):
        return True
    return False

def _sanitize(text: str) -> str:
    """raw dump 감지 시 안전한 대체 텍스트 반환."""
    if _is_raw_dump(text):
        return "해석 정보를 처리하는 중입니다. 잠시 후 다시 시도해 주세요."
    return text

# ---------------------------------------------------------------------------
# 해석 템플릿
# ---------------------------------------------------------------------------

# 태양별자리 핵심 키워드 (간략)
SUN_KEYWORDS = {
    "Aries": "행동력과 개척 정신이 강합니다.",
    "Taurus": "안정성과 인내심이 강합니다.",
    "Gemini": "교감과 학습에 대한 욕구가 강합니다.",
    "Cancer": "감수성과 관계에 대한 관심이 깊습니다.",
    "Leo": "자아 표현과 리더십에 대한 욕구가 강합니다.",
    "Virgo": "정확성과 분석력이 강합니다.",
    "Libra": "조화감과 대인 관계에 대한 관심이 깊습니다.",
    "Scorpio": "강한 집중력과 전환에 대한 욕구가 강합니다.",
    "Sagittarius": "탐구와 자유에 대한 욕구가 강합니다.",
    "Capricorn": "인내와 책임감이 강합니다.",
    "Aquarius": "독특함과 집단 의식에 대한 관심이 깊습니다.",
    "Pisces": "공감과 상상력이 강합니다.",
}

# 달별자리 핵심 키워드
MOON_KEYWORDS = {
    "Aries": "감정이 직접적이고 즉각적입니다.",
    "Taurus": "감정이 안정적이고 편안함을 추구합니다.",
    "Gemini": "감정이 다양하고 변화가 빠릅니다.",
    "Cancer": "감정이 깊고 보호 본능이 강합니다.",
    "Leo": "감정이 밝고 인정 욕구가 강합니다.",
    "Virgo": "감정이 섬세하고 분석적입니다.",
    "Libra": "감정이 조화를 추구합니다.",
    "Scorpio": "감정이 강렬하고 내면적입니다.",
    "Sagittarius": "감정이 낙관적이고 자유로운 편입니다.",
    "Capricorn": "감정이 절제되고 현실적입니다.",
    "Aquarius": "감정이 객관적이고 독립적입니다.",
    "Pisces": "감정이 풍부하고 공감 능력이 높습니다.",
}

# aspect 해석 키워드
ASPECT_INTERP = {
    "conjunction": "통합과 집중",
    "opposition": "대립과 균형 탐색",
    "trine": "자연스러운 흐름과 재능",
    "square": "갈등과 성장의 계기",
    "sextile": "기회와 협력",
}

# ---------------------------------------------------------------------------
# 주 해석 함수
# ---------------------------------------------------------------------------

def interpret_western_chart(chart: WesternChart, max_aspects: int = 5) -> str:
    """Western chart를 compact Korean 해석으로 변환."""
    if not chart.ok:
        blockers_text = " | ".join(chart.blockers) if chart.blockers else "계산 불가"
        return (
            f"⚠️ 서양 점성술: {blockers_text}\n\n"
            f"이 결과는 자기성찰과 선택지 점검용 참고이며 확정적 판단이 아닙니다."
        )

    lines: List[str] = []

    # 1. 제목
    lines.append("🌟 서양 점성술 출생 차트")
    lines.append("")

    # 2. 행성 위치
    lines.append("행성 위치")
    for p in chart.planets:
        lines.append(f"  {p.format_kr()}")
    lines.append("")

    # 3. Ascendant / Midheaven
    if chart.ascendant:
        lines.append(f"↑ Ascendant: {chart.ascendant.format_kr()}")
    if chart.midheaven:
        lines.append(f"↑ Midheaven: {chart.midheaven.format_kr()}")
    if chart.ascendant or chart.midheaven:
        lines.append("")

    # 4. 태양 핵심
    sun = chart.planet_dict().get("Sun")
    if sun:
        kr_sign = KOREAN_SIGN_MAP.get(sun.sign, sun.sign)
        keyword = SUN_KEYWORDS.get(sun.sign, "")
        lines.append(f"☀️ 태양 {kr_sign}: {keyword}")
        lines.append("")

    # 5. 달 핵심
    moon = chart.planet_dict().get("Moon")
    if moon:
        kr_sign = KOREAN_SIGN_MAP.get(moon.sign, moon.sign)
        keyword = MOON_KEYWORDS.get(moon.sign, "")
        lines.append(f"🌙 달 {kr_sign}: {keyword}")
        lines.append("")

    # 6. 주요 aspect (최대 max_aspects)
    if chart.aspects:
        lines.append("주요 Aspect")
        for a in chart.aspects[:max_aspects]:
            interp = ASPECT_INTERP.get(a.aspect_type, "")
            lines.append(f"  {a.korean_description} — {interp}")
        lines.append("")

    # 7. 경고
    if chart.warnings:
        lines.append("참고")
        for w in chart.warnings:
            lines.append(f"  ℹ️ {w}")
        lines.append("")

    # 8. 한계
    lines.append("한계")
    lines.append("  이 해석은 birth chart의 기본 구조를 바탕으로 한 간략한 참고입니다.")
    lines.append("  개별 행성의 세부 상호작용과 house 위치를 종합한 심층 분석은 아닙니다.")
    lines.append("")

    # 9. disclaimer
    lines.append(WESTERN_DISCLAIMER)

    result = "\n".join(lines)
    return _sanitize(result)

def format_planets_only(planets: List[WesternPlanet]) -> str:
    """행성 위치만 compact 포맷으로 반환 (planets-only mode)."""
    lines = ["행성 위치 (위치가 없어 Ascendant/house 제외)"]
    for p in planets:
        lines.append(f"  {p.format_kr()}")
    lines.append("")
    lines.append(WESTERN_DISCLAIMER)
    return _sanitize("\n".join(lines))
