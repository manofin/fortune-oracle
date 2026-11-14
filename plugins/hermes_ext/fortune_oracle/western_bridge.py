#!/usr/bin/env python3
"""Fortune Oracle — Western Astrology Bridge (Phase 38C).

Western birth chart 계산.
현재 계산은 Skyfield + 로컬 JPL DE440s를 사용한다. 파일/의존성이 없으면 계산을 차단한다.
어떤 경우에도 fail-open이며 plugin 전체를 중단시키지 않는다.

금지:
- shell=True 사용 금지
- 외부 네트워크 호출 금지
- AI/LLM 호출 금지
- 파일 쓰기 금지

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .astro_input import AstroBirthInput
from .astro_method_card import (
    AstroMethodCard,
    ERR_DEPENDENCY_MISSING,
    ERR_CALCULATION_FAILED,
    ERR_INSUFFICIENT_BIRTH_DATA,
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_RUNNABLE,
)
from .western_schema import (
    WesternChart,
    WesternPlanet,
    WesternAspect,
    PLANET_NAMES,
    MAJOR_ASPECTS,
    TROPICAL_SIGNS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend 가용성
# ---------------------------------------------------------------------------

_SWISSEPH_AVAILABLE: Optional[bool] = None
_SWISSEPH_IMPORT_ERROR: str = ""

def _check_swisseph() -> bool:
    global _SWISSEPH_AVAILABLE, _SWISSEPH_IMPORT_ERROR
    if _SWISSEPH_AVAILABLE is not None:
        return _SWISSEPH_AVAILABLE
    try:
        import swisseph as swe  # noqa: F401
        _SWISSEPH_AVAILABLE = True
        return True
    except ImportError as e:
        _SWISSEPH_AVAILABLE = False
        _SWISSEPH_IMPORT_ERROR = str(e)
        return False

def bridge_available() -> bool:
    return backend_info()["status"] == "computed"


def backend_info() -> Dict[str, str]:
    from .ephemeris import backend_info as info
    return info()

# ---------------------------------------------------------------------------
# 내장 stub 알고리즘 (Meeus 기반 근사)
# ---------------------------------------------------------------------------

# Julian day 계산
def _julian_day(year: int, month: int, day: float) -> float:
    """Julian day 계산 (Meeus)."""
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

# 행성 경도 계산 (tropical, ecliptic longitude)
def _sun_longitude(jd: float) -> float:
    """태양 경도 (tropical, degrees)."""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    C = (1.914602 - 0.004817 * T) * math.sin(math.radians(M)) + \
        0.019993 * math.sin(math.radians(2 * M)) + \
        0.000289 * math.sin(math.radians(3 * M))
    return (L0 + C) % 360.0

def _moon_longitude(jd: float) -> float:
    """달 경도 (tropical, degrees)."""
    T = (jd - 2451545.0) / 36525.0
    Lp = 218.3165 + 481267.8813 * T
    D = 297.8502 + 445267.1115 * T
    M = 357.5291 + 35999.0503 * T
    Mp = 134.9634 + 477198.8676 * T
    omega = 125.0445 - 1934.1363 * T

    arg1 = 2*D - Mp
    arg2 = D
    arg3 = D - Mp
    arg4 = D + Mp
    arg5 = M

    L = (
        Lp
        + 6.289 * math.sin(math.radians(arg1))
        + 1.274 * math.sin(math.radians(arg2))
        + 0.658 * math.sin(math.radians(arg3))
        + 0.214 * math.sin(math.radians(arg4))
        - 0.186 * math.sin(math.radians(Mp))
        - 0.114 * math.sin(math.radians(arg5))
        + 0.059 * math.sin(math.radians(2*D - M))
        - 0.057 * math.sin(math.radians(2*D - Mp - M))
        + 0.053 * math.sin(math.radians(2*D - Mp + M))
    )
    return L % 360.0

# 내장 행성 테이블 (tropical, ecliptic longitude 계산)
# Meeus "Astronomical Algorithms" 기반 근사
def _planet_longitude(jd: float, planet: str) -> float:
    """행성 경도 계산 (tropical, degrees)."""
    T = (jd - 2451545.0) / 36525.0

    # Mercury
    if planet == "Mercury":
        L = 252.2509 + 149472.6747 * T
        M = 174.8439 + 149472.6747 * T
        C = 1.9146 * math.sin(math.radians(M)) + 0.02 * math.sin(math.radians(2*M))
        return (L + C) % 360.0

    # Venus
    if planet == "Venus":
        L = 181.9798 + 58517.8158 * T
        M = 50.0774 + 58517.8158 * T
        C = 1.274 * math.sin(math.radians(M)) + 0.09 * math.sin(math.radians(2*M))
        return (L + C) % 360.0

    # Mars
    if planet == "Mars":
        L = 355.433 + 19140.2993 * T
        M = 19.373 + 19140.2993 * T
        C = 2.26 * math.sin(math.radians(M)) + 0.1 * math.sin(math.radians(2*M))
        return (L + C) % 360.0

    # Jupiter
    if planet == "Jupiter":
        L = 34.3515 + 3034.9057 * T
        M = 20.020 + 3034.9057 * T
        C = 1.1 * math.sin(math.radians(M))
        return (L + C) % 360.0

    # Saturn
    if planet == "Saturn":
        L = 50.0774 + 1222.1138 * T
        M = 13.178 + 1222.1138 * T
        C = 0.8 * math.sin(math.radians(M))
        return (L + C) % 360.0

    # Uranus
    if planet == "Uranus":
        L = 314.055 + 428.467 * T
        M = 142.238 + 428.467 * T
        C = 0.5 * math.sin(math.radians(M))
        return (L + C) % 360.0

    # Neptune
    if planet == "Neptune":
        L = 304.348 + 21.105 * T
        M = 256.228 + 21.105 * T
        C = 0.3 * math.sin(math.radians(M))
        return (L + C) % 360.0

    # Pluto
    if planet == "Pluto":
        L = 238.929 + 14.524 * T
        M = 148.733 + 14.524 * T
        C = 0.3 * math.sin(math.radians(M))
        return (L + C) % 360.0

    return 0.0

def _is_retrograde(jd: float, planet: str) -> bool:
    """역행 여부 단순 추정 (±1일 비교)."""
    lon1 = _planet_longitude(jd - 1, planet)
    lon2 = _planet_longitude(jd + 1, planet)
    delta = (lon2 - lon1) % 360
    return delta > 180  # 역행이면 delta > 180

def _longitude_to_sign_degree(lon: float) -> tuple:
    """경도를 별자리 + 도수로 변환."""
    sign_idx = int(lon) // 30
    degree = lon - sign_idx * 30
    sign = TROPICAL_SIGNS[sign_idx % 12]
    return sign, round(degree, 2)

# Ascendant / Midheaven 계산 (단순화)
def _ascendant_longitude(jd: float, lat: float, lon: float, tz_offset_hours: float) -> float:
    """Ascendant 경도 계산 (근사)."""
    # sidereal time 계산
    T = (jd - 2451545.0) / 36525.0
    GMST = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T
    LMST = (GMST + lon) % 360

    obliquity = 23.4393 - 0.0130 * T
    epsilon = math.radians(obliquity)
    phi = math.radians(lat)
    theta = math.radians(LMST)

    # Asc = atan2(-sin(theta), cos(epsilon)*tan(phi) + sin(epsilon)*sin(theta))
    num = -math.sin(theta)
    den = math.cos(epsilon) * math.tan(phi) + math.sin(epsilon) * math.sin(theta)
    asc = math.degrees(math.atan2(num, den))

    # ecliptic longitude로 변환
    asc = (asc + 180) % 360
    return asc

def _midheaven_longitude(jd: float, lon: float) -> float:
    """Midheaven 경도 계산 (근사)."""
    T = (jd - 2451545.0) / 36525.0
    GMST = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T
    LMST = (GMST + lon) % 360

    obliquity = 23.4393 - 0.0130 * T
    epsilon = math.radians(obliquity)
    theta = math.radians(LMST)

    mc = math.degrees(math.atan2(math.sin(theta), math.cos(theta) * math.cos(epsilon)))
    mc = (mc + 180) % 360
    return mc

# Aspect 계산
def _detect_aspects(planets: List[WesternPlanet], orb_table: Optional[Dict[str, float]] = None) -> List[WesternAspect]:
    """주요 aspect 감지."""
    if orb_table is None:
        orb_table = {
            "conjunction": 8.0,
            "opposition": 8.0,
            "trine": 8.0,
            "square": 7.0,
            "sextile": 6.0,
        }

    aspects = []
    for i, p1 in enumerate(planets):
        for p2 in planets[i + 1:]:
            lon1 = TROPICAL_SIGNS.index(p1.sign) * 30 + p1.degree if p1.sign in TROPICAL_SIGNS else 0
            lon2 = TROPICAL_SIGNS.index(p2.sign) * 30 + p2.degree if p2.sign in TROPICAL_SIGNS else 0

            for aspect_name, info in MAJOR_ASPECTS.items():
                target = info["angle"]
                orb_limit = orb_table.get(aspect_name, info["orb_default"])
                separation = abs((lon1 - lon2 + 180) % 360 - 180)
                diff = abs(separation - target)
                if diff <= orb_limit:
                    aspects.append(WesternAspect(
                        planet1=p1.name,
                        planet2=p2.name,
                        aspect_type=aspect_name,
                        orb=round(diff, 1),
                    ))
    aspects.sort(key=lambda item: (item.orb, item.planet1, item.planet2))
    return aspects

# ---------------------------------------------------------------------------
# 주 계산 함수
# ---------------------------------------------------------------------------

def calculate_western_chart(
    birth_input: AstroBirthInput,
    orb_table: Optional[Dict[str, float]] = None,
) -> WesternChart:
    """Actual geocentric apparent positions; never substitute the legacy stub."""
    from .ephemeris import birth_utc, positions, horizon_angles, EphemerisUnavailable, KERNEL_SHA256, KERNEL_URL
    try:
        if birth_input.validate():
            raise ValueError("Invalid birth input")
        utc = birth_utc(birth_input)
        computed,t = positions(utc)
        planets = [WesternPlanet(name=p["name"],sign=TROPICAL_SIGNS[int(p["longitude"]//30)],
                                 degree=p["longitude"]%30,retrograde=p["retrograde"],
                                 longitude=p["longitude"],speed=p["speed"]) for p in computed]
        asc = mc = None
        houses,house_system = [],""
        warnings = list(birth_input.precision_notes)
        if birth_input.sufficient_for_houses:
            try:
                asc_lon,mc_lon = horizon_angles(t,birth_input.latitude,birth_input.longitude)
                asc = WesternPlanet(name="Ascendant",sign=TROPICAL_SIGNS[int(asc_lon//30)],
                                    degree=asc_lon%30,longitude=asc_lon)
                mc = WesternPlanet(name="Midheaven",sign=TROPICAL_SIGNS[int(mc_lon//30)],
                                   degree=mc_lon%30,longitude=mc_lon)
                requested = getattr(birth_input,'house_system_preference','Whole Sign')
                if requested not in {"Whole Sign","Equal House"}:
                    raise ValueError("Unsupported house system")
                house_system = requested
                opening = asc_lon if requested == "Equal House" else math.floor(asc_lon/30)*30
                houses = [(opening+i*30)%360 for i in range(12)]
            except ValueError:
                asc = mc = None
                warnings.append("요청한 하우스 체계 또는 극지 지평선 계산을 지원하지 않습니다. 행성 위치만 표시합니다.")
        else:
            warnings.append("위치가 없어 ASC/MC/하우스는 계산하지 않았습니다.")
        return WesternChart(ok=True,status=STATUS_RUNNABLE if houses else STATUS_PARTIAL,
            input_summary=birth_input.birth_datetime,planets=planets,ascendant=asc,midheaven=mc,
            houses=houses,house_system=house_system,aspects=_detect_aspects(planets,orb_table),
            warnings=warnings,backend="skyfield-jpl-de440s",
            provenance={"ephemeris":"DE440s","sha256":KERNEL_SHA256,"source":KERNEL_URL,
                        "frame":"apparent geocentric tropical ecliptic of date",
                        "targets":{p["name"]:p["target"] for p in computed},
                        "time_conversion":"IANA to UTC; ambiguous/nonexistent times rejected",
                        "retrograde":"centered 2-hour longitude difference",
                        "body_note":"Planetary system barycenters except Sun/Moon; Pluto is not its body center"})
    except EphemerisUnavailable:
        return WesternChart.error(STATUS_BLOCKED,"",["DEPENDENCY_MISSING: 로컬 JPL DE440s/Skyfield를 사용할 수 없습니다."])
    except Exception:
        return WesternChart.error(STATUS_BLOCKED,"",["CALCULATION_FAILED: 출생시각·시간대·천체력 범위를 확인해 주세요."])

def calculate_western_method_card(
    birth_input: AstroBirthInput,
    orb_table: Optional[Dict[str, float]] = None,
) -> AstroMethodCard:
    """Western chart를 MethodCard로 감싸 반환."""
    chart = calculate_western_chart(birth_input, orb_table)

    if not chart.ok:
        return AstroMethodCard.blocked(
            method="western",
            error_code=ERR_CALCULATION_FAILED,
            message="; ".join(chart.blockers),
            blockers=chart.blockers,
        )

    # facts 구성 (Dict[str, Any])
    facts: Dict[str, Any] = {
        "planets": [p.format_kr() for p in chart.planets],
    }
    facts["planet_positions"] = [{"name":p.name,"longitude":p.longitude,"speed":p.speed,
                                  "retrograde":p.retrograde} for p in chart.planets]
    facts["provenance"] = chart.provenance
    facts["angles"] = {name: value.longitude for name, value in
                       (("Ascendant", chart.ascendant), ("Midheaven", chart.midheaven)) if value}
    facts["house_cusps"] = list(chart.houses)
    facts["house_system"] = chart.house_system
    facts["aspect_details"] = [{"planet1": aspect.planet1, "planet2": aspect.planet2,
                                "type": aspect.aspect_type, "orb": aspect.orb} for aspect in chart.aspects]
    if chart.ascendant:
        facts["ascendant"] = chart.ascendant.format_kr()
    if chart.midheaven:
        facts["midheaven"] = chart.midheaven.format_kr()
    if chart.aspects:
        facts["aspects"] = [a.korean_description for a in chart.aspects[:5]]

    # interpretation은 interpreter에서 처리하므로 여기서는 빈 문자열
    return AstroMethodCard(
        method="western",
        status=chart.status,
        backend=chart.backend,
        calculation_mode="computed",
        facts=facts,
        interpretation="",
        confidence=0.9,
        warnings=chart.warnings + ["행성 위치는 천체력 계산값이며 점성 해석의 예측 정확도를 뜻하지 않습니다.",
                                  "외행성은 계의 질량중심 위치입니다 (명왕성 본체 중심 아님)."],
    )
