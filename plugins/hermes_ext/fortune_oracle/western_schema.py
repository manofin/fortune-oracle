#!/usr/bin/env python3
"""Fortune Oracle — Western Astrology Schema (Phase 38C).

Western birth chart dataclass 기반 결과 모델.
tropical zodiac 기준.

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

WESTERN_DISCLAIMER: str = (
    "이 서양 점성술 판은 자기성찰과 선택지 점검용 참고이며, "
    "확정적 판단이 아닙니다. 의학, 투자, 법률 결정을 지시하지 않습니다."
)

# 행성 목록 (표준 10행성)
PLANET_NAMES: List[str] = [
    "Sun", "Moon", "Mercury", "Venus", "Mars",
    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
]

# 주요 aspect 목록
MAJOR_ASPECTS: Dict[str, Dict[str, Any]] = {
    "conjunction":  {"angle": 0,   "orb_default": 8},
    "opposition":   {"angle": 180, "orb_default": 8},
    "trine":        {"angle": 120, "orb_default": 8},
    "square":       {"angle": 90,  "orb_default": 7},
    "sextile":      {"angle": 60,  "orb_default": 6},
}

# 별자리 순서 (tropical)
TROPICAL_SIGNS: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# 한국어 별자리 매핑
KOREAN_SIGN_MAP: Dict[str, str] = {
    "Aries": "양자리", "Taurus": "황소자리", "Gemini": "쌍둥이자리",
    "Cancer": "게자리", "Leo": "사자자리", "Virgo": "처녀자리",
    "Libra": "천칭자리", "Scorpio": "전갈자리",
    "Sagittarius": "궁수자리", "Capricorn": "염소자리",
    "Aquarius": "물병자리", "Pisces": "물고기자리",
}

# 한국어 행성 매핑
KOREAN_PLANET_MAP: Dict[str, str] = {
    "Sun": "태양", "Moon": "달", "Mercury": "수성",
    "Venus": "금성", "Mars": "화성", "Jupiter": "목성",
    "Saturn": "토성", "Uranus": "천왕성", "Neptune": "해왕성",
    "Pluto": "명왕성",
}

# 한국어 aspect 매핑
KOREAN_ASPECT_MAP: Dict[str, str] = {
    "conjunction": "합", "opposition": "대립", "trine": "삼합",
    "square": "직각", "sextile": "육합",
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WesternPlanet:
    """서양 점성술 행성 데이터."""
    name: str = ""              # Sun, Moon, Mercury, ...
    sign: str = ""              # Aries, Taurus, ...
    degree: float = 0.0         # 0.0 ~ 30.0
    retrograde: bool = False
    longitude: Optional[float] = None
    speed: Optional[float] = None  # degrees/day, apparent geocentric

    @property
    def korean_name(self) -> str:
        return KOREAN_PLANET_MAP.get(self.name, self.name)

    @property
    def korean_sign(self) -> str:
        return KOREAN_SIGN_MAP.get(self.sign, self.sign)

    def format_kr(self) -> str:
        """한국어 포맷: 행성 별자리 °'"""
        retro = " (R)" if self.retrograde else ""
        return f"{self.korean_name} {self.korean_sign} {self.degree:.1f}°{retro}"

@dataclass
class WesternAspect:
    """서양 점성술 aspect 데이터."""
    planet1: str = ""
    planet2: str = ""
    aspect_type: str = ""       # conjunction, opposition, trine, square, sextile
    orb: float = 0.0            # 실제 각도 차이

    @property
    def korean_description(self) -> str:
        p1 = KOREAN_PLANET_MAP.get(self.planet1, self.planet1)
        p2 = KOREAN_PLANET_MAP.get(self.planet2, self.planet2)
        a = KOREAN_ASPECT_MAP.get(self.aspect_type, self.aspect_type)
        return f"{p1}-{p2} {a} (orb {self.orb:.1f}°)"

@dataclass
class WesternChart:
    """서양 점성술 차트 데이터."""
    ok: bool = False
    status: str = ""            # runnable | partial | blocked
    input_summary: str = ""
    zodiac_mode: str = "tropical"
    house_system: str = ""      # Placidus | Whole Sign | "" (unavailable)
    planets: List[WesternPlanet] = field(default_factory=list)
    ascendant: Optional[WesternPlanet] = None
    midheaven: Optional[WesternPlanet] = None
    houses: List[float] = field(default_factory=list)  # cusps in degrees (int accepted via union)
    aspects: List[WesternAspect] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    disclaimer: str = WESTERN_DISCLAIMER
    backend: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def planet_dict(self) -> Dict[str, WesternPlanet]:
        """name → planet dict."""
        return {p.name: p for p in self.planets}

    @classmethod
    def error(cls, status: str, input_summary: str, blockers: List[str]) -> "WesternChart":
        return cls(
            ok=False,
            status=status,
            input_summary=input_summary,
            blockers=blockers,
        )
