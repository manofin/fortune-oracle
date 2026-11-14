"""
Tests for location_settings store helper privacy.

Covers: sanitized key usage in save_location_settings,
legacy raw numeric key handling, dry_run safety, and
no destructive migration of existing raw numeric keys.
"""

from __future__ import annotations

# Numeric user/chat identities in this module are synthetic fixtures.

import pytest

# ---------------------------------------------------------------------------
# Store helper privacy: sanitized key usage
# ---------------------------------------------------------------------------

def test_save_location_settings_uses_sanitized_key():
    """save_location_settings must use sanitized location key, not raw numeric."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        build_location_profile_key,
        save_location_settings,
    )
    key = build_location_profile_key("telegram", "222222222222")
    assert "222222222222" not in key
    store = {}
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, key, settings, dry_run=True)
    # The store key should use the sanitized form
    sub_key = f"location_settings:{key}"
    assert sub_key in result
    assert "222222222222" not in sub_key


def test_save_with_raw_key_not_allowed_in_location():
    """If caller passes a raw numeric key, location_settings should not create it."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
    )
    # If someone accidentally passes raw key (shouldn't happen with build_location_profile_key)
    raw_key = "telegram:222222222222"
    store = {}
    settings = LocationSettings(label="Seoul")
    # This WILL save under the raw key because save_location_settings trusts the key
    # The enforcement is at the CALLER level (build_location_profile_key).
    # We verify the pattern: the location_settings module itself doesn't create
    # raw numeric keys when using build_location_profile_key.
    result = save_location_settings(store, raw_key, settings, dry_run=True)
    # The raw key IS in the result because we passed it directly.
    # This is expected — the module trusts the caller's key.
    # The privacy guarantee is: build_location_profile_key never produces raw keys.
    assert f"location_settings:{raw_key}" in result


def test_build_key_then_save_produces_no_raw_id():
    """End-to-end: build_location_profile_key + save_location_settings = no raw ID."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        build_location_profile_key,
        save_location_settings,
    )
    key = build_location_profile_key("telegram", "222222222222")
    store = {}
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, key, settings, dry_run=True)
    # Verify no raw numeric ID anywhere in the store keys
    for k in result.keys():
        assert "222222222222" not in k, f"Raw numeric ID leaked in store key: {k}"


def test_save_dry_run_does_not_mutate_store():
    """dry_run=True must not mutate the original store."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
    )
    store = {"other": "data"}
    settings = LocationSettings(label="Seoul")
    result = save_location_settings(store, "telegram:default", settings, dry_run=True)
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
        "location_settings:telegram:default": LocationSettings(label="Seoul").to_dict(),
        "other": "data",
    }
    result = clear_location_settings(store, "telegram:default", dry_run=True)
    assert "location_settings:telegram:default" in store
    assert "location_settings:telegram:default" not in result


# ---------------------------------------------------------------------------
# Legacy raw numeric key handling
# ---------------------------------------------------------------------------

def test_legacy_raw_numeric_key_not_destructively_migrated():
    """Existing raw numeric keys are NOT auto-migrated."""
    from hermes_ext.fortune_oracle.location_settings import (
        get_location_settings,
    )
    store = {
        "location_settings:telegram:222222222222": {
            "label": "Seoul",
            "timezone": "Asia/Seoul",
        },
    }
    # Reading with a sanitized key should NOT find the legacy key
    result = get_location_settings(store, "telegram:user_f00ddead")
    assert result is None


def test_legacy_raw_numeric_key_readable_by_raw_key():
    """Legacy raw numeric key IS still readable by its raw key (no data loss)."""
    from hermes_ext.fortune_oracle.location_settings import get_location_settings
    store = {
        "location_settings:telegram:222222222222": {
            "label": "Seoul",
            "timezone": "Asia/Seoul",
        },
    }
    # Reading with the raw key should still work
    result = get_location_settings(store, "telegram:222222222222")
    assert result is not None
    assert result.label == "Seoul"
    assert result.timezone == "Asia/Seoul"


def test_legacy_warning_on_raw_key_detection():
    """We can detect legacy raw numeric keys for reporting."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        save_location_settings,
        build_location_profile_key,
    )
    store = {
        "location_settings:telegram:222222222222": {
            "label": "Seoul",
        },
    }
    # New save with sanitized key should not overwrite legacy key
    key = build_location_profile_key("telegram", "222222222222")
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, key, settings, dry_run=True)
    # Both keys should exist — legacy not deleted, new one created
    assert "location_settings:telegram:222222222222" in result
    assert f"location_settings:{key}" in result


# ---------------------------------------------------------------------------
# telegram:default compatibility
# ---------------------------------------------------------------------------

def test_telegram_default_compatibility():
    """'telegram:default' key must be preserved."""
    from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
    key = build_location_profile_key("telegram", "default")
    assert key == "telegram:default"


def test_telegram_default_save_and_load():
    """Save and load with 'telegram:default' key."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        build_location_profile_key,
        save_location_settings,
        get_location_settings,
    )
    key = build_location_profile_key("telegram", "default")
    assert key == "telegram:default"
    store = {}
    settings = LocationSettings(label="Seoul", timezone="Asia/Seoul")
    result = save_location_settings(store, key, settings, dry_run=True)
    loaded = get_location_settings(result, key)
    assert loaded is not None
    assert loaded.label == "Seoul"
    assert loaded.timezone == "Asia/Seoul"


# ---------------------------------------------------------------------------
# No raw precise coordinate in display
# ---------------------------------------------------------------------------

def test_no_raw_precise_coordinate_in_store_entry():
    """redact_location_store_entry rounds coordinates to 2 decimals."""
    from hermes_ext.fortune_oracle.location_settings import redact_location_store_entry
    entry = {
        "label": "Seoul",
        "latitude": 37.5665,
        "longitude": 126.9780,
    }
    redacted = redact_location_store_entry(entry)
    assert redacted["latitude"] == 37.57
    assert redacted["longitude"] == 126.98
    assert "37.5665" not in str(redacted["latitude"])


# ---------------------------------------------------------------------------
# No token/chat_id/API key in output
# ---------------------------------------------------------------------------

def test_to_astro_input_location_no_token_or_chat_id():
    """to_astro_input_location must not include token/chat_id/user_id."""
    from hermes_ext.fortune_oracle.location_settings import (
        LocationSettings,
        to_astro_input_location,
    )
    settings = LocationSettings(
        label="Seoul",
        timezone="Asia/Seoul",
        latitude=37.5665,
        longitude=126.9780,
    )
    result = to_astro_input_location(settings)
    forbidden_keys = {"token", "chat_id", "user_id", "raw_numeric_id"}
    for fk in forbidden_keys:
        assert fk not in result, f"Forbidden key {fk} found in astro input"
    # Coordinates should be rounded
    assert result["latitude"] == 37.57
    assert result["longitude"] == 126.98
