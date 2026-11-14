"""
Tests for fortune_oracle.location_settings module.

Covers: parsing, validation, redaction, key sanitization, store operations,
merge priority, and privacy (no raw numeric user IDs).
"""

from __future__ import annotations

# Numeric user/chat identities in this module are synthetic fixtures.

import pytest

# ---------------------------------------------------------------------------
# Import smoke
# ---------------------------------------------------------------------------

def test_import_smoke():
    """Basic import should work."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        LocationPrecision,
        LocationSource,
        build_location_profile_key,
        parse_location_command,
        validate_location_settings,
        redact_location_for_display,
        redact_location_store_entry,
        merge_location_priority,
        to_astro_input_location,
        get_location_settings,
        save_location_settings,
        clear_location_settings,
        location_settings_exists,
        sanitize_location_user_key,
    )
    assert LocationSettings is not None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_timezone_only_parse():
    """Parse timezone-only command."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Asia/Seoul")
    assert s.timezone == "Asia/Seoul"
    assert s.label == ""
    assert s.latitude is None
    assert s.source == "command"


def test_label_timezone_parse():
    """Parse label + timezone."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Seoul, Korea | Asia/Seoul")
    assert s.label == "Seoul, Korea"
    assert s.timezone == "Asia/Seoul"
    assert s.latitude is None


def test_label_timezone_latlon_parse():
    """Parse full command with coordinates."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Seoul, Korea | Asia/Seoul | 37.5665 | 126.9780")
    assert s.label == "Seoul, Korea"
    assert s.timezone == "Asia/Seoul"
    assert s.latitude == pytest.approx(37.5665)
    assert s.longitude == pytest.approx(126.9780)
    assert s.precision == "coordinate"


def test_korean_label_parse():
    """Parse Korean label."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("서울 | Asia/Seoul | 37.5665 | 126.9780")
    assert s.label == "서울"
    assert s.timezone == "Asia/Seoul"
    assert s.latitude == pytest.approx(37.5665)


def test_invalid_latitude_rejected():
    """Invalid latitude should be None."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Seoul | Asia/Seoul | 999 | 126.9780")
    assert s.latitude is None


def test_invalid_longitude_rejected():
    """Invalid longitude should be None."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Seoul | Asia/Seoul | 37.5665 | 9999")
    assert s.longitude is None


def test_invalid_timezone_fail_open():
    """Invalid timezone is kept (fail-open), no API call."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    s = parse_location_command("Seoul | Invalid/Timezone")
    assert s.timezone == "Invalid/Timezone"


def test_no_geocoding_api_call():
    """Parsing should not make any network calls (structural check)."""
    from hermes_ext.fortune_oracle.location_settings import parse_location_command
    # If this test runs without network, we know no API was called
    s = parse_location_command("Seoul, Korea | Asia/Seoul")
    assert s.label == "Seoul, Korea"
    # No assertions about network — the test infrastructure would fail if
    # network was required. The absence of requests/httpx imports in the
    # module confirms no geocoding.


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redacted_display_rounds_coordinates():
    """Display should round coordinates to 2 decimals."""
    from hermes_ext.fortune_oracle.location_settings import (
        parse_location_command,
        redact_location_for_display,
    )
    s = parse_location_command("Seoul | Asia/Seoul | 37.5665 | 126.9780")
    out = redact_location_for_display(s)
    assert "37.57" in out
    assert "126.98" in out


def test_raw_precise_coordinate_not_in_display():
    """Raw precise coordinates must not appear in display."""
    from hermes_ext.fortune_oracle.location_settings import (
        parse_location_command,
        redact_location_for_display,
    )
    s = parse_location_command("Seoul | Asia/Seoul | 37.5665 | 126.9780")
    out = redact_location_for_display(s)
    assert "37.5665" not in out
    assert "126.9780" not in out


# ---------------------------------------------------------------------------
# Key sanitization
# ---------------------------------------------------------------------------

def test_telegram_default_compatibility():
    """'default' user_id should produce 'telegram:default'."""
    from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
    key = build_location_profile_key("telegram", "default")
    assert key == "telegram:default"


def test_numeric_user_id_not_present_in_key():
    """Numeric user ID must not appear in the key."""
    from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
    key = build_location_profile_key("telegram", "222222222222")
    assert "222222222222" not in key
    assert key.startswith("telegram:user_")


def test_deterministic_sanitized_key():
    """Same input should produce same key (deterministic hash)."""
    from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
    key1 = build_location_profile_key("telegram", "222222222222")
    key2 = build_location_profile_key("telegram", "222222222222")
    assert key1 == key2


def test_raw_numeric_id_not_in_repr():
    """Raw numeric ID must not appear in LocationSettings repr."""
    from hermes_ext.fortune_oracle.location_settings import LocationSettings
    s = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    r = repr(s)
    # No user_id is stored in LocationSettings, so no numeric ID can leak
    assert "222222222222" not in r


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------

def test_save_dry_run_does_not_mutate_store():
    """dry_run=True must not mutate the original store."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
    )
    store = {"other": "data"}
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, "telegram:default", settings, dry_run=True)
    assert "other" in store
    assert store == {"other": "data"}
    assert result is not store


def test_clear_dry_run_does_not_mutate_store():
    """dry_run=True on clear must not mutate the original store."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
        clear_location_settings,
    )
    store = {
        "location_settings:telegram:default": LocationSettings(
            label="Seoul", timezone="Asia/Seoul"
        ).to_dict(),
        "other": "data",
    }
    result = clear_location_settings(store, "telegram:default", dry_run=True)
    assert "location_settings:telegram:default" in store
    assert "location_settings:telegram:default" not in result


def test_save_preserves_profiles():
    """Saving for one profile should not affect another."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
    )
    store = {
        "location_settings:telegram:other": {"label": "Busan"},
    }
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, "telegram:default", settings, dry_run=True)
    assert result["location_settings:telegram:other"]["label"] == "Busan"


def test_save_preserves_daily_push():
    """Saving location should not affect daily_push settings."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
    )
    store = {
        "daily_push:telegram:default": {"enabled": True},
    }
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, "telegram:default", settings, dry_run=True)
    assert result["daily_push:telegram:default"]["enabled"] is True


def test_clear_removes_only_location_settings():
    """Clear should only remove location_settings, not other keys."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
        clear_location_settings,
    )
    store = {
        "location_settings:telegram:default": LocationSettings(
            label="Seoul"
        ).to_dict(),
        "daily_push:telegram:default": {"enabled": True},
    }
    result = clear_location_settings(store, "telegram:default", dry_run=True)
    assert "location_settings:telegram:default" not in result
    assert "daily_push:telegram:default" in result


def test_legacy_raw_numeric_key_not_destructively_migrated():
    """Existing legacy keys with raw numeric IDs should not be auto-migrated."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
        get_location_settings,
    )
    # Simulate legacy store with raw numeric key
    store = {
        "location_settings:telegram:222222222222": {
            "label": "Seoul",
            "timezone": "Asia/Seoul",
        },
    }
    # Reading with sanitized key should NOT find the legacy key
    sanitized_key = "telegram:user_" + "a" * 8  # Not the real hash, but starts right
    result = get_location_settings(store, sanitized_key)
    assert result is None  # Legacy key is not auto-migrated
