"""Natal Vedic chart using Swiss Ephemeris/Moshier with explicit Lahiri mode.

No built-in chart fallback, automatic download or external model call. A missing
backend produces a blocked result. Legacy year-only dasha and Julian-day helpers
remain importable for compatibility but are NOT used by the live natal pipeline.
The natal chart intentionally omits current dasha until period-aware calculation
and independent validation are implemented.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

from .astro_input import AstroBirthInput
from .astro_method_card import AstroMethodCard, ERR_CALCULATION_FAILED, STATUS_BLOCKED, STATUS_PARTIAL, STATUS_RUNNABLE
from .vedic_schema import (VedicChart, VedicGraha, VedicNakshatra, VimshottariDasha,
    SIDEREAL_SIGNS, NAKSHATRA_NAMES, VIMSHOTTARI_PERIODS, VIMSHOTTARI_ORDER, GRAHA_NAMES)
from . import vedic_ephemeris

NAKSHATRA_WIDTH = 360.0 / 27

def _julian_day(year: int, month: int, day: float) -> float:
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100)
    B = 2 - A + math.floor(A / 4)
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day + B - 1524.5
    )


def _calculate_nakshatra(moon_sidereal_lon: float) -> VedicNakshatra:
    """달의 sidereal 경도에서 nakshatra와 pada 계산.

    deterministic table: 27 nakshatra × 13°20′
    """
    # sidereal 경도를 0-360 범위로
    lon = moon_sidereal_lon % 360.0

    # nakshatra 인덱스
    idx = int(lon / NAKSHATRA_WIDTH) % 27

    # nakshatra 내 도수
    degree_in = lon - idx * NAKSHATRA_WIDTH

    # pada (4등분)
    pada = int(degree_in / (NAKSHATRA_WIDTH / 4)) + 1
    pada = min(pada, 4)  # 안전

    return VedicNakshatra(
        name=NAKSHATRA_NAMES[idx],
        pada=pada,
        degree_in_nakshatra=round(degree_in, 2),
    )


def _calculate_vimshottari_dasha(
    moon_sidereal_lon: float,
    birth_year: int,
    current_year: int,
) -> Optional[VimshottariDasha]:
    """Vimshottari dasha 현재 주기 계산 (수정됨: remaining <= period 보장).

    balance = remaining at birth of birth nakshatra dasha.
    elapsed = current_year - birth_year
    """
    lon = moon_sidereal_lon % 360.0
    nak_idx = int(lon / NAKSHATRA_WIDTH) % 27
    nak_name = NAKSHATRA_NAMES[nak_idx]
    nak_to_graha = {
        "Ashwini": "Ketu", "Bharani": "Venus", "Krittika": "Sun",
        "Rohini": "Moon", "Mrigashira": "Mars", "Ardra": "Rahu",
        "Punarvasu": "Jupiter", "Pushya": "Saturn", "Ashlesha": "Mercury",
        "Magha": "Ketu", "Purva Phalguni": "Venus", "Uttara Phalguni": "Sun",
        "Hasta": "Moon", "Chitra": "Mars", "Swati": "Rahu",
        "Vishakha": "Jupiter", "Anuradha": "Saturn", "Jyeshtha": "Mercury",
        "Mula": "Ketu", "Purva Ashadha": "Venus", "Uttara Ashadha": "Sun",
        "Shravana": "Moon", "Dhanishta": "Mars", "Shatabhisha": "Rahu",
        "Purva Bhadrapada": "Jupiter", "Uttara Bhadrapada": "Saturn",
        "Revati": "Mercury",
    }
    lagna_graha = nak_to_graha.get(nak_name)
    if lagna_graha is None:
        return None
    degree_in_nak = lon - nak_idx * NAKSHATRA_WIDTH
    fraction = degree_in_nak / NAKSHATRA_WIDTH
    lagna_period = VIMSHOTTARI_PERIODS.get(lagna_graha, 0)
    balance = (1.0 - fraction) * lagna_period
    elapsed = current_year - birth_year
    if elapsed < 0 or elapsed > 150:
        return None
    order = VIMSHOTTARI_ORDER
    lagna_idx = order.index(lagna_graha)
    left = elapsed
    idx = lagna_idx
    if left <= balance:
        maha = lagna_graha
        rem = balance - left
    else:
        left -= balance
        idx = (lagna_idx + 1) % len(order)
        while left >= VIMSHOTTARI_PERIODS[order[idx]]:
            left -= VIMSHOTTARI_PERIODS[order[idx]]
            idx = (idx + 1) % len(order)
        maha = order[idx]
        rem = VIMSHOTTARI_PERIODS[maha] - left
    end_year = current_year + int(rem)
    # simple antardasha approx (next in cycle, scaled proportion)
    anta_idx = (idx + 1) % len(order)
    anta_name = order[anta_idx]
    return VimshottariDasha(
        mahadasha=maha,
        antardasha=anta_name,
        remaining_years=round(rem, 1),
        end_year=end_year,
    )


def _longitude_to_rashi_degree(lon: float) -> tuple:
    """sidereal 경도를 라시 + 도수로 변환."""
    sign_idx = int(lon) // 30
    degree = lon - sign_idx * 30
    rashi = SIDEREAL_SIGNS[sign_idx % 12]
    return rashi, degree


def _calculate_navamsa_lagna(lagna_sign: str, lagna_degree: float) -> str:
    """간단한 D9 Navamsa Lagna 계산 (Lagna longitude * 9 mod 360)."""
    if lagna_sign not in SIDEREAL_SIGNS:
        return lagna_sign
    sign_idx = SIDEREAL_SIGNS.index(lagna_sign)
    full_lon = sign_idx * 30.0 + lagna_degree
    navamsa_lon = (full_lon * 9.0) % 360.0
    nav_idx = int(navamsa_lon // 30)
    return SIDEREAL_SIGNS[nav_idx]


def bridge_available() -> bool:
    return backend_info()["status"] == "computed"


def backend_info() -> Dict[str, str]:
    return vedic_ephemeris.backend_info()


def calculate_vedic_chart(birth_input: AstroBirthInput) -> VedicChart:
    """Calculate natal facts, never manufacture an unknown time or a dasha."""
    try:
        if birth_input.validate():
            raise ValueError("Invalid birth input")
        rows, ascendant, provenance = vedic_ephemeris.natal_positions(birth_input)
        by_name = {row["name"]: row["longitude"] for row in rows}
        def graha(name):
            sign, degree = _longitude_to_rashi_degree(by_name[name])
            return VedicGraha(name=name, rashi=sign, degree=degree)
        nakshatra = _calculate_nakshatra(by_name["Moon"])
        lagna = lagna_degree = navamsa = None
        warnings = list(birth_input.precision_notes)
        if ascendant is not None:
            lagna, lagna_degree = _longitude_to_rashi_degree(ascendant)
            navamsa = _calculate_navamsa_lagna(lagna, lagna_degree)
        else:
            warnings.append("출생지 좌표가 없거나 극지 지평선이어서 상승점·D9 상승점은 계산하지 않았습니다.")
        warnings.append("출생 성향용 계산입니다. 현재 다샤·트랜짓과 D9 전체 차트는 포함하지 않습니다.")
        return VedicChart(
            ok=True, status=STATUS_RUNNABLE if ascendant is not None else STATUS_PARTIAL,
            input_summary="", zodiac_mode="sidereal", ayanamsa="Lahiri",
            grahas=[graha(name) for name in GRAHA_NAMES], rahu=graha("Rahu"), ketu=graha("Ketu"),
            moon_nakshatra=nakshatra, moon_pada=nakshatra.pada,
            current_vimshottari_dasha=None, lagna=lagna, lagna_degree=lagna_degree,
            navamsa_lagna=navamsa, backend=vedic_ephemeris.BACKEND,
            provenance=provenance, warnings=warnings,
        )
    except vedic_ephemeris.VedicEphemerisUnavailable:
        return VedicChart.error(STATUS_BLOCKED, "", ["DEPENDENCY_MISSING: 검증된 베딕 천체력 환경을 사용할 수 없습니다."])
    except Exception:
        return VedicChart.error(STATUS_BLOCKED, "", ["CALCULATION_FAILED: 출생시각·시간대·위치·천체력 범위를 확인해 주세요."])


def calculate_vedic_method_card(birth_input: AstroBirthInput) -> AstroMethodCard:
    chart = calculate_vedic_chart(birth_input)
    if not chart.ok:
        return AstroMethodCard.blocked(method="vedic", error_code=ERR_CALCULATION_FAILED,
                                      message="; ".join(chart.blockers), blockers=chart.blockers)
    facts = {
        "grahas": [g.format_kr() for g in chart.grahas],
        "graha_positions": [{"name": g.name, "rashi": g.rashi, "degree": g.degree}
                            for g in chart.grahas + [chart.rahu, chart.ketu] if g],
        "nakshatra": chart.moon_nakshatra.format_kr(),
        "nakshatra_details": {"name": chart.moon_nakshatra.name, "pada": chart.moon_nakshatra.pada},
        "provenance": dict(chart.provenance),
    }
    for name in ("rahu", "ketu"):
        graha = getattr(chart, name)
        if graha:
            facts[name] = graha.format_kr()
    if chart.lagna is not None:
        facts.update(lagna=chart.lagna, lagna_degree=chart.lagna_degree,
                     navamsa_lagna=chart.navamsa_lagna)
    return AstroMethodCard(method="vedic", status=chart.status,
                           backend=chart.backend, calculation_mode="computed", facts=facts,
                           interpretation="", confidence=0.0, warnings=chart.warnings)
