"""Fortune Oracle — Dayun exactness audit helpers (Phase 25)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .dayun import calculate_dayun_skeleton
from .profile_schema import normalize_gender

DAYUN_EXACTNESS_POLICY: Dict[str, Any] = {
    "timezone": "Asia/Seoul",
    "start_age_precision": "approx",
    "uses_external_solar_term_network": False,
    "true_solar_time_supported": False,
    "longitude_correction_supported": False,
    "supported_basis": "local lunar-javascript/source plus deterministic skeleton",
    "known_limitations": [
        "start_age is approximate because exact solar-term timestamp delta is not computed in Python layer",
        "true solar time and longitude correction are documented limitations",
        "unsupported or missing gender fails open with direction=unknown",
        "current cycle detection is deterministic only when birth_year/current_age is supplied by caller",
    ],
}


def audit_dayun_exactness(
    eight_char: Dict[str, str],
    *,
    gender: Optional[str] = None,
    birth_year: Optional[int] = None,
    current_age: Optional[int] = None,
) -> Dict[str, Any]:
    normalized_gender = normalize_gender(gender or "")
    result = calculate_dayun_skeleton(eight_char, gender=normalized_gender, birth_year=birth_year)
    current = result.current_cycle(current_age) if current_age is not None else None
    return {
        "ok": bool(result.ok),
        "direction": result.direction,
        "direction_reason": result.direction_reason,
        "start_age": result.start_age,
        "start_age_precision": result.start_age_precision,
        "timezone": DAYUN_EXACTNESS_POLICY["timezone"],
        "true_solar_time_supported": False,
        "longitude_correction_supported": False,
        "current_cycle": getattr(current, "pillar", None),
        "limitations": list(DAYUN_EXACTNESS_POLICY["known_limitations"]),
        "warnings": list(result.warnings),
    }


def dayun_limitations_text() -> str:
    items = "\n".join(f"- {item}" for item in DAYUN_EXACTNESS_POLICY["known_limitations"])
    return (
        "Dayun exactness policy\n"
        "- timezone: Asia/Seoul\n"
        "- start_age_precision: approx\n"
        "- true solar time: unsupported\n"
        "- longitude correction: unsupported\n"
        f"{items}"
    )
