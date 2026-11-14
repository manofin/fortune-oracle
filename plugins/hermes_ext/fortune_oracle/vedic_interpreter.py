#!/usr/bin/env python3
"""Fortune Oracle — Vedic Astrology Interpreter (Phase 38D).

Vedic chart의 raw 데이터를 compact Korean interpretation으로 변환.
sanitize guard 포함.

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
from typing import List

from .vedic_schema import (
    VedicChart,
    VEDIC_DISCLAIMER,
    KOREAN_RASHI_MAP,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# sanitize guard
# ---------------------------------------------------------------------------

_RAW_FORBIDDEN = [
    "VedicChart(",
    "VedicGraha(",
    "VedicNakshatra(",
    "VimshottariDasha(",
    "dataclass",
    "default_factory",
    "ok=True",
    "ok=False",
]

def _is_raw_dump(text: str) -> bool:
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
    if _is_raw_dump(text):
        return "계산 결과가 아님\n해석 정보를 표시하지 못했습니다. 잠시 후 다시 시도해 주세요."
    return text

# ---------------------------------------------------------------------------
# 해석
# ---------------------------------------------------------------------------

# 라시별 graha 해석 키워드 (간략)
RASHI_GRAHA_KEYWORDS = {
    "Mesha": "행동력과 개척 에너지",
    "Vrishabha": "안정성과 물질적 기반",
    "Mithuna": "교감과 정보 교환",
    "Karka": "감수성과 보호 본능",
    "Simha": "자아 표현과 리더십",
    "Kanya": "분석력과 섬세한 관심",
    "Tula": "조화와 관계의 균형",
    "Vrishchika": "강한 집중과 전환",
    "Dhanu": "탐구와 확장의 에너지",
    "Makara": "인내와 구조적 접근",
    "Kumbha": "독특함과 혁신",
    "Meena": "공감과 영적 탐구",
}

# nakshatra 핵심 키워드 (간략)
NAKSHATRA_KEYWORDS = {
    "Ashwini": "빠른 시작과 치유",
    "Bharani": "변화와 포용",
    "Krittika": "정제와 단련",
    "Rohini": "성장과 물질적 풍요",
    "Mrigashira": "탐구와 발견",
    "Ardra": "변혁과 정화",
    "Punarvasu": "재생과 복귀",
    "Pushya": "보호와 양육",
    "Ashlesha": "깊은 연결과 영향",
    "Magha": "전통과 권위",
    "Purva Phalguni": "창의와 낭만",
    "Uttara Phalguni": "책임과 성숙",
    "Hasta": "기술과 표현",
    "Chitra": "미와 장식",
    "Swati": "독립과 자유",
    "Vishakha": "집중과 성취",
    "Anuradha": "협력과 성취",
    "Jyeshtha": "권위와 보호",
    "Mula": "근본과 재탄생",
    "Purva Ashadha": "불굴의 의지",
    "Uttara Ashadha": "승리와 인내",
    "Shravana": "청취와 학습",
    "Dhanishta": "명성과 리듬",
    "Shatabhisha": "치유와 은밀",
    "Purva Bhadrapada": "변혁과 신비",
    "Uttara Bhadrapada": "지혜와 완성",
    "Revati": "마무리와 자비",
}

def interpret_vedic_chart(chart: VedicChart, *, location_basis: str = "") -> str:
    """Vedic chart를 compact Korean 해석으로 변환."""
    if not chart.ok:
        return (
            "계산 결과가 아님\n⚠️ 베딕 출생 차트를 산출하지 못했습니다.\n"
            "출생일·출생시각·시간대를 확인하고 다시 시도해 주세요.\n\n"
            f"{VEDIC_DISCLAIMER}"
        )

    computed = chart.backend == "swisseph-moshier" and bool(chart.provenance)
    lines: List[str] = ["계산된 출생 차트 — Swiss Ephemeris / Moshier 해석적 천체력, Lahiri 항성황도."
                        if computed else "출처 미확인 참고 자료 — 통합 계산 결과로 사용하지 않습니다."]
    lines.append("행성 위치와 나크샤트라는 계산값이며 성향 문구는 전통적 해석입니다."
                 if computed else "이 자료의 계산 출처는 확인되지 않았습니다.")
    if location_basis:
        lines += ["", location_basis]
    lines.append("")

    # 1. 제목
    lines.append("🕉️ 베딕 점성술 출생 풀이")
    lines.append(f"  Ayanamsa: {chart.ayanamsa} | Zodiac: {chart.zodiac_mode}")
    lines.append("")

    # 2. Graha 위치
    lines.append("Graha 위치" + (" (계산값)" if computed else " (출처 미확인)"))
    for g in chart.grahas:
        lines.append(f"  {g.format_kr()}")
    lines.append("")

    # 3. Rahu/Ketu
    if chart.rahu:
        lines.append(f"  🐉 Rahu: {chart.rahu.format_kr()}")
    if chart.ketu:
        lines.append(f"  🐉 Ketu: {chart.ketu.format_kr()}")
    lines.append("")

    # 4. 달 나크샤트라
    if chart.moon_nakshatra:
        nak = chart.moon_nakshatra
        keyword = NAKSHATRA_KEYWORDS.get(nak.name, "")
        lines.append(f"🌙 달 나크샤트라: {nak.format_kr()}")
        if keyword:
            lines.append(f"  해석: {keyword}")
        lines.append("")

    # 4.5 Lagna + D9 Navamsa (Gate 1B)
    if chart.lagna:
        kr_lagna = KOREAN_RASHI_MAP.get(chart.lagna, chart.lagna)
        lines.append(f"⬆️ Lagna (상승점): {kr_lagna} {chart.lagna_degree:.1f}° (D1)")
        if chart.navamsa_lagna:
            kr_nav = KOREAN_RASHI_MAP.get(chart.navamsa_lagna, chart.navamsa_lagna)
            lines.append(f"   D9 Navamsa Lagna: {kr_nav}")
        lines.append("")

    # 5. 주요 graha 해석
    moon = chart.graha_dict().get("Moon")
    sun = chart.graha_dict().get("Sun")
    if moon:
        kr_rashi = moon.korean_rashi
        keyword = RASHI_GRAHA_KEYWORDS.get(moon.rashi, "")
        lines.append(f"해석: 찬드라(달) {kr_rashi} — {keyword}")
    if sun:
        kr_rashi = sun.korean_rashi
        keyword = RASHI_GRAHA_KEYWORDS.get(sun.rashi, "")
        lines.append(f"해석: 수리야(태양) {kr_rashi} — {keyword}")
    lines.append("")

    # 6. Vimshottari dasha
    if chart.current_vimshottari_dasha:
        dasha = chart.current_vimshottari_dasha
        lines.append(f"🔄 현재 대운 (참고용 근사): {dasha.format_kr()}")
        lines.append("")

    # 7. 경고
    if chart.warnings:
        lines.append("참고")
        for w in chart.warnings:
            lines.append(f"  ℹ️ {w}")
        lines.append("")

    # 8. 한계
    lines.append("한계")
    lines.append("  이 해석은 D1 라시 차트의 기본 구조를 바탕으로 한 간략한 참고입니다.")
    if chart.lagna and chart.navamsa_lagna:
        lines.append("  D9 상승점만 계산했으며 D9 전체 행성 차트와 상세 해석은 제공하지 않습니다.")
    else:
        lines.append("  D9 Navamsa Lagna는 산출하지 않아 표시하지 않았습니다.")
    lines.append("")

    # 9. disclaimer
    lines.append(VEDIC_DISCLAIMER)

    result = "\n".join(lines)
    return _sanitize(result)
