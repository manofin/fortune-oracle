#!/usr/bin/env python3
"""Fortune Oracle — Location Bridge (D1).

Connects saved location settings to Western/Vedic/Astro bridges.
Uses build_astro_location_context for priority chain:
  command > saved > profile > unset

No geocoding API calls. No raw numeric user IDs. No precise coordinates
in user output.

Prohibited:
- external geocoding/API calls
- raw numeric user_id in key/output
- destructive profile migration
- modifying gateway/platforms/config
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .location_settings import (
    AstroLocationContext,
    build_astro_location_context,
    build_location_profile_key,
    get_location_settings,
    LocationSource,
    redact_location_for_display,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bridge helpers
# ---------------------------------------------------------------------------


def apply_location_to_astro_input(
    astro_input: Any,
    loc_ctx: AstroLocationContext,
) -> Any:
    """Apply AstroLocationContext to an AstroBirthInput.

    Overwrites timezone/latitude/longitude from the location context
    if they are more complete than the current input.

    Args:
        astro_input: An AstroBirthInput instance.
        loc_ctx:    AstroLocationContext from build_astro_location_context.

    Returns:
        The modified AstroBirthInput (same object).
    """
    # Only override if the context has better data
    if loc_ctx.timezone and not astro_input.timezone:
        astro_input.timezone = loc_ctx.timezone
    if loc_ctx.latitude is not None and astro_input.latitude is None:
        astro_input.latitude = loc_ctx.latitude
    if loc_ctx.longitude is not None and astro_input.longitude is None:
        astro_input.longitude = loc_ctx.longitude

    # Add precision notes from the context
    if loc_ctx.warnings:
        astro_input.precision_notes.extend(loc_ctx.warnings[:3])

    return astro_input


def apply_location_to_unified_input(
    unified_input: Any,
    loc_ctx: AstroLocationContext,
) -> Any:
    """Apply AstroLocationContext to a UnifiedOracleInput.

    Args:
        unified_input: A UnifiedOracleInput instance.
        loc_ctx:       AstroLocationContext from build_astro_location_context.

    Returns:
        The modified UnifiedOracleInput (same object).
    """
    if loc_ctx.timezone and not unified_input.timezone:
        unified_input.timezone = loc_ctx.timezone
    if loc_ctx.latitude is not None and unified_input.latitude is None:
        unified_input.latitude = loc_ctx.latitude
    if loc_ctx.longitude is not None and unified_input.longitude is None:
        unified_input.longitude = loc_ctx.longitude

    if loc_ctx.warnings:
        unified_input.precision_notes.extend(loc_ctx.warnings[:3])

    return unified_input


def build_location_context_for_command(
    command_text: str = "",
    store: Optional[Dict[str, Any]] = None,
    platform: str = "telegram",
    user_id: str = "default",
    profile: Optional[Dict[str, Any]] = None,
    has_birth_time: bool = True,
) -> AstroLocationContext:
    """Build AstroLocationContext for a command execution.

    Uses build_location_profile_key for privacy-safe key generation.

    Args:
        command_text:  Raw command text (may contain location override).
        store:         Persistent store dict.
        platform:      Platform identifier.
        user_id:       User identifier (hashed if numeric).
        profile:       Profile dict (fallback source).
        has_birth_time: Whether birth time is available.

    Returns:
        AstroLocationContext.
    """
    profile_key = build_location_profile_key(platform, user_id)
    return build_astro_location_context(
        command_text=command_text,
        store=store,
        profile_key=profile_key,
        profile=profile,
        has_birth_time=has_birth_time,
    )


def format_location_basis(loc_ctx: AstroLocationContext) -> str:
    """Format location basis for user output (redacted).

    Strict redaction: never allow numeric coordinates in final output,
    even if redacted_summary was constructed with them.
    """
    if loc_ctx.source == LocationSource.UNSET:
        return "📍 위치 기준: 설정되지 않음"

    summary = loc_ctx.redacted_summary or ""

    # Final safety net: strip any remaining numeric coordinate patterns
    import re
    summary = re.sub(r'좌표\s*[\d.]+\s*,\s*[\d.]+', '좌표 정보', summary)
    summary = re.sub(r'위도\s*[\d.]+', '위도 정보', summary)
    summary = re.sub(r'경도\s*[\d.]+', '경도 정보', summary)

    if loc_ctx.is_complete_for_houses:
        return f"📍 위치 기준: {summary}"

    if loc_ctx.timezone:
        if loc_ctx.warnings:
            reason = loc_ctx.warnings[0] if loc_ctx.warnings else ""
            return f"📍 위치 기준: {summary} (좌표 없음 — {reason})"
        return f"📍 위치 기준: {summary} (좌표 없음)"

    return f"📍 위치 기준: {summary}"


def location_status_for_show_profile(
    loc_ctx: AstroLocationContext,
) -> str:
    """Format location summary for /show_profile (1-2 lines).

    Strict privacy: remove decimal coordinate numbers.
    """
    if loc_ctx.source == LocationSource.UNSET:
        return ""

    summary = loc_ctx.redacted_summary or ""

    # Remove patterns like "좌표 37.57, 126.98 근방" -> "좌표 정보 근방"
    if "좌표 " in summary and "," in summary:
        summary = summary.split("좌표 ")[0] + "좌표 정보" + (summary.split(" 근방")[-1] if " 근방" in summary else "")

    return (
        f"위치 설정\n"
        f"- Western/Vedic 기준: {summary}"
    )


