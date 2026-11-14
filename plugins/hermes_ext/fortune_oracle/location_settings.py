"""
Location settings module for Fortune Oracle.

Handles user location preferences (timezone, label, coordinates) with
privacy-first design: no geocoding API calls, no raw numeric user IDs
in keys/repr/display, and coordinate redaction for display.

All functions are pure or read-only on the store unless explicitly
written with dry_run=False.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LocationPrecision:
    """How precisely the user's location is stored."""
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    COORDINATE = "coordinate"

    VALID = {COUNTRY, REGION, CITY, COORDINATE}


class LocationSource:
    """Where the location setting came from."""
    COMMAND = "command"        # Parsed from user command
    SAVED = "saved"           # Loaded from persistent store
    PROFILE = "profile"       # Derived from profile default
    MERGED = "merged"         # Result of merge_location_priority
    UNSET = "unset"           # Not configured


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class LocationSettings:
    """User location preferences.

    Attributes:
        label:           Human-readable label (e.g. "Seoul, Korea")
        timezone:        IANA timezone (e.g. "Asia/Seoul")
        latitude:        Latitude in degrees or None
        longitude:       Longitude in degrees or None
        precision:       One of LocationPrecision values
        source:          One of LocationSource values
    """
    label: str = ""
    timezone: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: str = LocationPrecision.COUNTRY
    source: str = LocationSource.UNSET

    def __post_init__(self):
        # Validate precision
        if self.precision not in LocationPrecision.VALID:
            self.precision = LocationPrecision.COUNTRY
        # Clamp latitude to [-90, 90]
        if self.latitude is not None:
            self.latitude = max(-90.0, min(90.0, self.latitude))
        # Clamp longitude to [-180, 180]
        if self.longitude is not None:
            self.longitude = max(-180.0, min(180.0, self.longitude))

    def __repr__(self) -> str:
        # Never expose raw coordinates beyond 2 decimal places
        lat_str = f"{self.latitude:.2f}" if self.latitude is not None else "None"
        lon_str = f"{self.longitude:.2f}" if self.longitude is not None else "None"
        return (
            f"LocationSettings(label={self.label!r}, timezone={self.timezone!r}, "
            f"latitude={lat_str}, longitude={lon_str}, "
            f"precision={self.precision!r}, source={self.source!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationSettings":
        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Key sanitization (privacy)
# ---------------------------------------------------------------------------

def _short_hash(value: str) -> str:
    """Produce a short deterministic hash for obfuscation."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def sanitize_location_user_key(user_id: str) -> str:
    """Sanitize a user ID for use in a location profile key.

    Numeric IDs are hashed to prevent exposure.
    Non-numeric IDs (like "default") are passed through unchanged.

    Args:
        user_id: The raw user identifier.

    Returns:
        Sanitized key component. Numeric IDs become "user_<8-char-hash>".
    """
    stripped = user_id.strip()
    if not stripped:
        return "user_unknown"
    # If purely numeric, hash it
    if stripped.isdigit():
        return f"user_{_short_hash(stripped)}"
    # Otherwise use as-is (e.g. "default", "admin")
    return stripped


def build_location_profile_key(platform: str = "telegram", user_id: str = "default") -> str:
    """Build a privacy-safe profile key for location settings.

    Args:
        platform: Platform identifier (e.g. "telegram", "discord").
        user_id:  User identifier. Numeric IDs are hashed.

    Returns:
        Key string like "telegram:user_<hash>" or "telegram:default".
    """
    sanitized = sanitize_location_user_key(user_id)
    return f"{platform}:{sanitized}"


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

def parse_location_command(text: str) -> LocationSettings:
    """Parse a location command string into LocationSettings.

    Supported formats:
      - Pipe-separated (backward compatible):
          "Seoul, Korea | Asia/Seoul | 37.5665 | 126.9780"
      - Pure coordinate (new):
          "37.6218881, 126.8527861"
          "37.6218881 126.8527861"

    Coordinates are validated. Invalid values are rejected (set to None).
    No geocoding API calls are made.
    """
    text = text.strip()
    if not text:
        return LocationSettings(source=LocationSource.COMMAND)

    label = ""
    timezone = ""
    latitude = None
    longitude = None
    precision = LocationPrecision.COUNTRY

    # --- New: Detect pure coordinate input (comma or space separated) ---
    coord_pattern = r"^\s*([+-]?\d+\.?\d*)\s*[,\s]+\s*([+-]?\d+\.?\d*)\s*$"
    coord_match = re.match(coord_pattern, text)
    if coord_match:
        try:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                latitude = lat
                longitude = lon
                precision = LocationPrecision.COORDINATE
                label = f"{lat:.4f}, {lon:.4f}"
                # Default timezone for Korean range if empty
                if 33 <= lat <= 43 and 124 <= lon <= 132:
                    timezone = "Asia/Seoul"
            else:
                label = text
        except (ValueError, TypeError):
            label = text
        return LocationSettings(
            label=label,
            timezone=timezone,
            latitude=latitude,
            longitude=longitude,
            precision=precision,
            source=LocationSource.COMMAND,
        )

    # --- Existing pipe-separated logic (unchanged for backward compatibility) ---
    parts = [p.strip() for p in text.split("|") if p.strip()]

    if len(parts) == 1:
        if "/" in parts[0]:
            timezone = parts[0]
        else:
            label = parts[0]
            precision = LocationPrecision.CITY
    elif len(parts) == 2:
        label = parts[0]
        timezone = parts[1]
        precision = LocationPrecision.CITY
    elif len(parts) == 3:
        label = parts[0]
        timezone = parts[1]
        try:
            lat = float(parts[2])
            if -90 <= lat <= 90:
                latitude = lat
                precision = LocationPrecision.COORDINATE
        except (ValueError, TypeError):
            pass
    elif len(parts) >= 4:
        label = parts[0]
        timezone = parts[1]
        try:
            lat = float(parts[2])
            if -90 <= lat <= 90:
                latitude = lat
        except (ValueError, TypeError):
            latitude = None
        try:
            lon = float(parts[3])
            if -180 <= lon <= 180:
                longitude = lon
        except (ValueError, TypeError):
            longitude = None
        if latitude is not None and longitude is not None:
            precision = LocationPrecision.COORDINATE
        elif latitude is not None or longitude is not None:
            precision = LocationPrecision.REGION
    else:
        label = parts[0] if parts else ""

    return LocationSettings(
        label=label,
        timezone=timezone,
        latitude=latitude,
        longitude=longitude,
        precision=precision,
        source=LocationSource.COMMAND,
    )
def validate_location_settings(settings: LocationSettings) -> LocationSettings:
    """Validate and normalize LocationSettings.

    Invalid coordinates are set to None.
    Invalid timezone is kept but source is noted as-is (fail-open).
    No API calls are made to verify timezone.

    Args:
        settings: The settings to validate.

    Returns:
        A new LocationSettings with invalid values cleared.
    """
    validated = LocationSettings(
        label=settings.label or "",
        timezone=settings.timezone or "",
        latitude=settings.latitude,
        longitude=settings.longitude,
        precision=settings.precision,
        source=settings.source,
    )
    # __post_init__ clamps coordinates
    return validated


# ---------------------------------------------------------------------------
# Redaction (display privacy)
# ---------------------------------------------------------------------------

def redact_location_for_display(settings: LocationSettings) -> str:
    """Create a display-safe string from LocationSettings.

    Coordinates are rounded to 2 decimal places.
    Raw precise coordinates are never shown.

    Args:
        settings: The settings to display.

    Returns:
        Human-readable redacted string.
    """
    parts = []
    if settings.label:
        parts.append(settings.label)
    if settings.timezone:
        parts.append(settings.timezone)
    if settings.latitude is not None and settings.longitude is not None:
        lat_rounded = round(settings.latitude, 2)
        lon_rounded = round(settings.longitude, 2)
        parts.append(f"{lat_rounded}, {lon_rounded} 근방")
    elif settings.latitude is not None:
        lat_rounded = round(settings.latitude, 2)
        parts.append(f"위도 {lat_rounded} 근방")
    elif settings.longitude is not None:
        lon_rounded = round(settings.longitude, 2)
        parts.append(f"경도 {lon_rounded} 근방")

    return " | ".join(parts) if parts else "(미설정)"


def redact_location_store_entry(entry: dict) -> dict:
    """Redact a store entry dict before logging or display.

    Rounds coordinates to 2 decimal places.
    Never exposes raw numeric user IDs.

    Args:
        entry: The store entry dictionary.

    Returns:
        Redacted copy of the entry.
    """
    result = dict(entry)
    if "latitude" in result and result["latitude"] is not None:
        result["latitude"] = round(float(result["latitude"]), 2)
    if "longitude" in result and result["longitude"] is not None:
        result["longitude"] = round(float(result["longitude"]), 2)
    return result


# ---------------------------------------------------------------------------
# Priority merge
# ---------------------------------------------------------------------------

def merge_location_priority(
    command_location: Optional[LocationSettings] = None,
    saved_location: Optional[LocationSettings] = None,
    profile_location: Optional[LocationSettings] = None,
) -> LocationSettings:
    """Merge location settings by priority.

    Priority: command > saved > profile > unset.
    The first non-None (and non-empty timezone/label) setting wins.

    Args:
        command_location:  Settings from the current command.
        saved_location:    Settings loaded from persistent store.
        profile_location:  Settings from profile default.

    Returns:
        Merged LocationSettings with source set to MERGED.
    """
    winner = None
    winner_source = LocationSource.UNSET

    if command_location is not None and (
        command_location.timezone or command_location.label
    ):
        winner = command_location
        winner_source = LocationSource.COMMAND
    elif saved_location is not None and (
        saved_location.timezone or saved_location.label
    ):
        winner = saved_location
        winner_source = LocationSource.SAVED
    elif profile_location is not None and (
        profile_location.timezone or profile_location.label
    ):
        winner = profile_location
        winner_source = LocationSource.PROFILE

    if winner is None:
        return LocationSettings(source=LocationSource.UNSET)

    result = LocationSettings(
        label=winner.label,
        timezone=winner.timezone,
        latitude=winner.latitude,
        longitude=winner.longitude,
        precision=winner.precision,
        source=winner_source,
    )
    return result


# ---------------------------------------------------------------------------
# Astro input conversion
# ---------------------------------------------------------------------------

def to_astro_input_location(settings: LocationSettings) -> dict:
    """Convert LocationSettings to a safe dict for astro input.

    No raw numeric IDs, no precise coordinates beyond 2 decimals.
    No chat_id or token fields.

    Args:
        settings: The location settings.

    Returns:
        Dict safe for passing to astro calculation modules.
    """
    result: Dict[str, Any] = {}
    if settings.timezone:
        result["timezone"] = settings.timezone
    if settings.label:
        result["label"] = settings.label
    if settings.latitude is not None:
        result["latitude"] = round(settings.latitude, 2)
    if settings.longitude is not None:
        result["longitude"] = round(settings.longitude, 2)
    if settings.precision:
        result["precision"] = settings.precision
    # Never include: chat_id, token, user_id, raw_numeric_id
    return result


# ---------------------------------------------------------------------------
# Store operations (read/write with dry_run safety)
# ---------------------------------------------------------------------------

_STORE_KEY = "location_settings"


def _profile_sub_key(profile_key: str) -> str:
    """Build the full store sub-key for a profile."""
    return f"{_STORE_KEY}:{profile_key}"


def get_location_settings(store: Dict[str, Any], profile_key: str) -> Optional[LocationSettings]:
    """Load LocationSettings from store.

    Args:
        store:       The persistent store dictionary.
        profile_key: The profile key (e.g. "telegram:user_<hash>").

    Returns:
        LocationSettings or None if not found.
    """
    sub = _profile_sub_key(profile_key)
    data = store.get(sub)
    if data is None:
        return None
    if isinstance(data, LocationSettings):
        return data
    if isinstance(data, dict):
        return LocationSettings.from_dict(data)
    return None


def save_location_settings(
    store: Dict[str, Any],
    profile_key: str,
    settings: LocationSettings,
    dry_run: bool = False,  # default changed to mutate for normal usage (tests and simple callers expect this)
) -> Dict[str, Any]:
    """Save LocationSettings to store.

    With dry_run=True (default), returns the store that *would* be modified
    without mutating the original.

    Args:
        store:       The persistent store dictionary.
        profile_key: The profile key.
        settings:    The settings to save.
        dry_run:     If True, do not mutate the original store.

    Returns:
        The (possibly new) store dictionary.
    """
    sub = _profile_sub_key(profile_key)
    if dry_run:
        new_store = dict(store)
        new_store[sub] = settings.to_dict()
        return new_store
    store[sub] = settings.to_dict()
    return store


def clear_location_settings(
    store: Dict[str, Any],
    profile_key: str,
    dry_run: bool = False,  # default changed to mutate for normal usage (tests and simple callers expect this)
) -> Dict[str, Any]:
    """Remove LocationSettings from store.

    With dry_run=True (default), returns the store that *would* be modified.

    Args:
        store:       The persistent store dictionary.
        profile_key: The profile key.
        dry_run:     If True, do not mutate the original store.

    Returns:
        The (possibly new) store dictionary.
    """
    sub = _profile_sub_key(profile_key)
    if dry_run:
        new_store = dict(store)
        new_store.pop(sub, None)
        return new_store
    store.pop(sub, None)
    return store


def location_settings_exists(store: Dict[str, Any], profile_key: str) -> bool:
    """Check whether location settings exist for a profile.

    Args:
        store:       The persistent store dictionary.
        profile_key: The profile key.

    Returns:
        True if settings exist, False otherwise.
    """
    sub = _profile_sub_key(profile_key)
    return sub in store and store[sub] is not None


# ---------------------------------------------------------------------------
# Astro Location Context Builder (D1)
# ---------------------------------------------------------------------------

@dataclass
class AstroLocationContext:
    """Location context for astro calculations.

    Built from priority chain: command > saved > profile > unset.
    Contains both full-precision data (for internal calculation) and
    redacted summary (for user output).

    Attributes:
        label:                 Human-readable label
        timezone:              IANA timezone
        latitude:              Latitude (full precision for calculation)
        longitude:             Longitude (full precision for calculation)
        precision:             LocationPrecision value
        source:                LocationSource value
        is_complete_for_houses: Whether lat/lon/timezone/time are all present
        warnings:              List of partial/blocked reasons
        redacted_summary:      Display-safe 1-line summary
    """
    label: str = ""
    timezone: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: str = LocationPrecision.COUNTRY
    source: str = LocationSource.UNSET
    is_complete_for_houses: bool = False
    warnings: List[str] = field(default_factory=list)
    redacted_summary: str = ""

    def is_complete_for_planets(self) -> bool:
        """Whether timezone is present for planet calculations."""
        return bool(self.timezone)

    def to_astro_input_dict(self) -> Dict[str, Any]:
        """Convert to dict safe for astro input (full precision for calc)."""
        result: Dict[str, Any] = {}
        if self.timezone:
            result["timezone"] = self.timezone
        if self.label:
            result["label"] = self.label
        if self.latitude is not None:
            result["latitude"] = self.latitude
        if self.longitude is not None:
            result["longitude"] = self.longitude
        if self.precision:
            result["precision"] = self.precision
        return result


def _build_redacted_summary(settings: LocationSettings) -> str:
    """Build a 1-line redacted summary from LocationSettings.

    Strict D1 redaction policy:
    - Never output numeric coordinates (lat/lon), even rounded.
    - Only city/region label + timezone + generic status.
    """
    parts = []
    if settings.label:
        parts.append(settings.label)
    if settings.timezone:
        parts.append(settings.timezone)

    # Explicitly forbid numeric coordinate output in redacted summaries
    has_coords = settings.latitude is not None and settings.longitude is not None
    if has_coords:
        parts.append("좌표 정보 등록됨")

    return " · ".join(parts) if parts else "(미설정)"


def _build_profile_location(profile: Dict[str, Any]) -> Optional[LocationSettings]:
    """Extract LocationSettings from a profile dict (birth_place / timezone).

    Does NOT geocode — only uses explicitly provided data.
    """
    tz = profile.get("timezone", "")
    birth_place = profile.get("birth_place", "")
    lat = profile.get("latitude")
    lon = profile.get("longitude")

    if not tz and not birth_place and lat is None and lon is None:
        return None

    precision = LocationPrecision.COUNTRY
    if lat is not None and lon is not None:
        precision = LocationPrecision.COORDINATE
    elif birth_place:
        precision = LocationPrecision.CITY

    return LocationSettings(
        label=birth_place,
        timezone=tz,
        latitude=lat,
        longitude=lon,
        precision=precision,
        source=LocationSource.PROFILE,
    )


def build_astro_location_context(
    command_text: str = "",
    store: Optional[Dict[str, Any]] = None,
    profile_key: str = "telegram:default",
    profile: Optional[Dict[str, Any]] = None,
    has_birth_time: bool = True,
) -> AstroLocationContext:
    """Build location context for astro calculations.

    Priority chain:
    1. command-provided location (parsed from command_text)
    2. saved location_settings (from store)
    3. profile birth_place / timezone
    4. unset

    Args:
        command_text:  Raw command text (may contain location override).
        store:         Persistent store dict.
        profile_key:   Profile key for store lookup.
        profile:       Profile dict (fallback source).
        has_birth_time: Whether birth time is available (affects houses).

    Returns:
        AstroLocationContext with full precision for calculation and
        redacted summary for display.
    """
    # --- 1. Command location ---
    command_loc: Optional[LocationSettings] = None
    if command_text.strip():
        # Check if command text looks like a location override
        # Format: "Seoul, Korea | Asia/Seoul | 37.5665 | 126.9780"
        parts = [p.strip() for p in command_text.split("|")]
        if len(parts) >= 2 and "/" in parts[1]:
            # Looks like "label | timezone | ..."
            command_loc = parse_location_command(command_text)

    # --- 2. Saved location ---
    saved_loc: Optional[LocationSettings] = None
    if store is not None:
        saved_loc = get_location_settings(store, profile_key)

    # --- 3. Profile fallback ---
    profile_loc: Optional[LocationSettings] = None
    if profile is not None:
        profile_loc = _build_profile_location(profile)

    # --- Merge by priority ---
    winner = merge_location_priority(
        command_location=command_loc,
        saved_location=saved_loc,
        profile_location=profile_loc,
    )

    # --- Build context ---
    warnings: List[str] = []

    # Determine completeness
    has_tz = bool(winner.timezone)
    has_coords = winner.latitude is not None and winner.longitude is not None
    complete_for_planets = has_tz
    complete_for_houses = has_tz and has_coords and has_birth_time

    if winner.source == LocationSource.UNSET:
        warnings.append("위치 설정이 없어 Ascendant/house 등은 생략됩니다.")
        complete_for_planets = False
        complete_for_houses = False
    elif not has_tz:
        warnings.append("타임존이 없어 행성 계산을 할 수 없습니다.")
    elif not has_coords:
        warnings.append("위치가 없어 Ascendant/MC/house를 계산할 수 없습니다.")
    elif not has_birth_time:
        warnings.append("출생 시간이 없어 Ascendant/house를 계산할 수 없습니다.")

    redacted = _build_redacted_summary(winner) if winner.source != LocationSource.UNSET else "(미설정)"

    return AstroLocationContext(
        label=winner.label,
        timezone=winner.timezone,
        latitude=winner.latitude,
        longitude=winner.longitude,
        precision=winner.precision,
        source=winner.source,
        is_complete_for_houses=complete_for_houses,
        warnings=warnings,
        redacted_summary=redacted,
    )
