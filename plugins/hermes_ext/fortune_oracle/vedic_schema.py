#!/usr/bin/env python3
"""Fortune Oracle — Vedic Astrology Schema (Phase 38D).

Vedic birth chart dataclass 기반 결과 모델.
sidereal zodiac, Lahiri ayanamsa 기준.

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

VEDIC_DISCLAIMER: str = (
    "이 베딕 점성술 판은 자기성찰과 선택지 점검용 참고이며, "
    "확정적 판단이 아닙니다. 의학, 투자, 법률 결정을 지시하지 않습니다."
)

# sidereal 별자리 (Vedic rasi)
SIDEREAL_SIGNS: List[str] = [
    "Mesha", "Vrishabha", "Mithuna", "Karka",
    "Simha", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makara", "Kumbha", "Meena",
]

# 한국어 라시 매핑
KOREAN_RASHI_MAP: Dict[str, str] = {
    "Mesha": "메샤(양)", "Vrishabha": "브리샤바(황소)",
    "Mithuna": "미투나(쌍둥이)", "Karka": "카르카(게)",
    "Simha": "심하(사자)", "Kanya": "칸야(처녀)",
    "Tula": "툴라(천칭)", "Vrishchika": "브리슈치카(전갈)",
    "Dhanu": "다누(궁수)", "Makara": "마카라(염소)",
    "Kumbha": "쿰바(물병)", "Meena": "미나(물고기)",
}

# graha 목록
GRAHA_NAMES: List[str] = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter",
    "Venus", "Saturn",
]

# 한국어 graha 매핑
KOREAN_GRAHA_MAP: Dict[str, str] = {
    "Sun": "수리야(태양)", "Moon": "찬드라(달)",
    "Mars": "망갈(화성)", "Mercury": "부다(수성)",
    "Jupiter": "브리하스파티(목성)", "Venus": "슈크라(금성)",
    "Saturn": "샤니(토성)", "Rahu": "라후", "Ketu": "케투",
}

# 27 Nakshatra (각 13°20′)
NAKSHATRA_WIDTH = 360.0 / 27  # = 13.333...

NAKSHATRA_NAMES: List[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini",
    "Mrigashira", "Ardra", "Punarvasu", "Pushya",
    "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# 한국어 나크샤트라 매핑
KOREAN_NAKSHATRA_MAP: Dict[str, str] = {
    "Ashwini": "아슈이니", "Bharani": "바라니",
    "Krittika": "크리티카", "Rohini": "로히니",
    "Mrigashira": "미라시라", "Ardra": "아르드라",
    "Punarvasu": "푸나르바수", "Pushya": "푸샤",
    "Ashlesha": "아슈레샤", "Magha": "마하",
    "Purva Phalguni": "푸르바 팔구니", "Uttara Phalguni": "우타라 팔구니",
    "Hasta": "하스타", "Chitra": "치트라",
    "Swati": "스와티", "Vishakha": "비샤카",
    "Anuradha": "아누라드하", "Jyeshtha": "제슈타",
    "Mula": "무라", "Purva Ashadha": "푸르바 아샤다",
    "Uttara Ashadha": "우타라 아샤다", "Shravana": "슈라바나",
    "Dhanishta": "다니슈타", "Shatabhisha": "샤타비샤",
    "Purva Bhadrapada": "푸르바 바드라파다",
    "Uttara Bhadrapada": "우타라 바드라파다",
    "Revati": "레바티",
}

# Vimshottari dasha periods (years)
VIMSHOTTARI_PERIODS: Dict[str, float] = {
    "Ketu": 7.0,
    "Venus": 20.0,
    "Sun": 6.0,
    "Moon": 10.0,
    "Mars": 7.0,
    "Rahu": 18.0,
    "Jupiter": 16.0,
    "Saturn": 19.0,
    "Mercury": 17.0,
}

# dasha 순서
VIMSHOTTARI_ORDER: List[str] = [
    "Ketu", "Venus", "Sun", "Moon", "Mars",
    "Rahu", "Jupiter", "Saturn", "Mercury",
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VedicGraha:
    """베딕 graha 데이터."""
    name: str = ""              # Sun, Moon, Mars, ...
    rashi: str = ""             # Mesha, Vrishabha, ...
    degree: float = 0.0         # 0.0 ~ 30.0

    @property
    def korean_name(self) -> str:
        return KOREAN_GRAHA_MAP.get(self.name, self.name)

    @property
    def korean_rashi(self) -> str:
        return KOREAN_RASHI_MAP.get(self.rashi, self.rashi)

    def format_kr(self) -> str:
        """한국어 포맷."""
        return f"{self.korean_name} {self.korean_rashi} {self.degree:.1f}°"

@dataclass
class VedicNakshatra:
    """베딕 nakshatra 데이터."""
    name: str = ""              # Ashwini, Bharani, ...
    pada: int = 0               # 1-4
    degree_in_nakshatra: float = 0.0

    @property
    def korean_name(self) -> str:
        return KOREAN_NAKSHATRA_MAP.get(self.name, self.name)

    def format_kr(self) -> str:
        return f"{self.korean_name} pada {self.pada}"

@dataclass
class VimshottariDasha:
    """Vimshottari dasha 현재 주기."""
    mahadasha: str = ""         # 현재 주요 dasha
    antardasha: str = ""        # 현재 하위 dasha
    remaining_years: float = 0.0
    end_year: Optional[int] = None

    def format_kr(self) -> str:
        md = KOREAN_GRAHA_MAP.get(self.mahadasha, self.mahadasha)
        ad = KOREAN_GRAHA_MAP.get(self.antardasha, self.antardasha)
        end = f" (종료 {self.end_year}년)" if self.end_year else ""
        return f"{md}/{ad} 대운 (남은 {self.remaining_years:.1f}년){end}"

@dataclass
class VedicChart:
    """베딕 점성술 차트 데이터."""
    ok: bool = False
    status: str = ""            # runnable | partial | blocked
    input_summary: str = ""
    zodiac_mode: str = "sidereal"
    ayanamsa: str = "Lahiri"
    grahas: List[VedicGraha] = field(default_factory=list)
    rahu: Optional[VedicGraha] = None
    ketu: Optional[VedicGraha] = None
    moon_nakshatra: Optional[VedicNakshatra] = None
    moon_pada: int = 0
    current_vimshottari_dasha: Optional[VimshottariDasha] = None
    lagna: Optional[str] = None
    lagna_degree: Optional[float] = None
    navamsa_lagna: Optional[str] = None
    backend: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    disclaimer: str = VEDIC_DISCLAIMER

    def graha_dict(self) -> Dict[str, VedicGraha]:
        """name → graha dict."""
        return {g.name: g for g in self.grahas}

    @classmethod
    def error(cls, status: str, input_summary: str, blockers: List[str]) -> "VedicChart":
        return cls(
            ok=False,
            status=status,
            input_summary=input_summary,
            blockers=blockers,
        )
