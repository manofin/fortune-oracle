"""Tests for Fortune Oracle Phase 19: profile_management UX helpers.

Validates:
- get_profile_status with None and real profile
- format_profile_status masks sensitive info
- format_delete_confirm returns str
- get_help_additions returns list
- /profile_status registered in CANONICAL_COMMANDS
- /register_birth re-registration guidance present
- Regression: /delete_profile, /register_birth, /show_profile not removed
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from plugins.hermes_ext.fortune_oracle.profile_management import (
    format_delete_confirm,
    format_profile_status,
    get_help_additions,
    get_profile_status,
)
from plugins.hermes_ext.fortune_oracle.platforms.telegram import (
    CANONICAL_COMMANDS,
    COMMAND_ALIASES,
)


# ---------------------------------------------------------------------------
# get_profile_status
# ---------------------------------------------------------------------------

def test_get_profile_status_none_registered_false():
    status = get_profile_status(None)
    assert status["registered"] is False


def test_get_profile_status_none_birth_info_false():
    status = get_profile_status(None)
    assert status["birth_info_present"] is False


def test_get_profile_status_none_gender_false():
    status = get_profile_status(None)
    assert status["gender_present"] is False


def test_get_profile_status_none_birth_place_false():
    status = get_profile_status(None)
    assert status["birth_place_present"] is False


def test_get_profile_status_none_default_timezone():
    status = get_profile_status(None)
    assert status["timezone"] == "Asia/Seoul"


def test_get_profile_status_with_profile_registered_true():
    profile = {
        "display_name": "홍길동",
        "birth_date": "1990-01-01",
        "birth_time": "13:00",
        "gender": "male",
        "birth_place": "서울",
        "name_hanja": "洪吉童",
        "timezone": "Asia/Seoul",
    }
    status = get_profile_status(profile)
    assert status["registered"] is True


def test_get_profile_status_birth_info_present():
    profile = {"birth_date": "1990-01-01"}
    status = get_profile_status(profile)
    assert status["birth_info_present"] is True


def test_get_profile_status_birth_date_masked():
    profile = {"birth_date": "1990-01-01"}
    status = get_profile_status(profile)
    assert status["birth_date"] == "***"
    assert "1990" not in status["birth_date"]


def test_get_profile_status_birth_time_masked():
    profile = {"birth_date": "1990-01-01", "birth_time": "13:00"}
    status = get_profile_status(profile)
    assert status["birth_time"] == "***"
    assert "13" not in status["birth_time"]


def test_get_profile_status_name_hanja_masked():
    profile = {"name_hanja": "洪吉童"}
    status = get_profile_status(profile)
    assert status["name_hanja"] == "***"
    assert "洪" not in status["name_hanja"]


def test_get_profile_status_display_name_preserved():
    profile = {"display_name": "길동"}
    status = get_profile_status(profile)
    assert status["display_name"] == "길동"


def test_get_profile_status_timezone_preserved():
    profile = {"timezone": "America/New_York"}
    status = get_profile_status(profile)
    assert status["timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# format_profile_status — sensitive data must NOT appear in output
# ---------------------------------------------------------------------------

def _full_profile():
    return {
        "display_name": "홍길동",
        "birth_date": "1990-01-01",
        "birth_time": "13:00",
        "gender": "male",
        "birth_place": "서울",
        "name_hanja": "洪吉童",
        "timezone": "Asia/Seoul",
    }


def test_format_profile_status_no_raw_birth_date():
    status = get_profile_status(_full_profile())
    text = format_profile_status(status)
    assert "1990" not in text
    assert "01-01" not in text


def test_format_profile_status_no_raw_birth_time():
    status = get_profile_status(_full_profile())
    text = format_profile_status(status)
    # raw time value "13:00" must not appear
    assert "13:00" not in text


def test_format_profile_status_no_raw_name_hanja():
    status = get_profile_status(_full_profile())
    text = format_profile_status(status)
    assert "洪吉童" not in text


def test_format_profile_status_contains_masked_marker():
    status = get_profile_status(_full_profile())
    text = format_profile_status(status)
    assert "***" in text


def test_format_profile_status_not_registered_includes_register_birth():
    status = get_profile_status(None)
    text = format_profile_status(status)
    assert "/register_birth" in text


def test_format_profile_status_registered_includes_reregister_hint():
    status = get_profile_status(_full_profile())
    text = format_profile_status(status)
    assert "/register_birth" in text


def test_format_profile_status_returns_str():
    status = get_profile_status(None)
    assert isinstance(format_profile_status(status), str)


# ---------------------------------------------------------------------------
# format_delete_confirm
# ---------------------------------------------------------------------------

def test_format_delete_confirm_returns_str():
    assert isinstance(format_delete_confirm("홍길동"), str)


def test_format_delete_confirm_with_name():
    msg = format_delete_confirm("홍길동")
    assert "홍길동" in msg


def test_format_delete_confirm_without_name():
    msg = format_delete_confirm(None)
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_format_delete_confirm_no_birth_info():
    msg = format_delete_confirm("홍길동")
    # no raw birth data should be present
    assert "1990" not in msg
    assert "birth_date" not in msg


# ---------------------------------------------------------------------------
# get_help_additions
# ---------------------------------------------------------------------------

def test_get_help_additions_returns_list():
    assert isinstance(get_help_additions(), list)


def test_get_help_additions_contains_profile_status():
    additions = get_help_additions()
    joined = " ".join(additions)
    assert "profile_status" in joined


# ---------------------------------------------------------------------------
# Telegram command registry — /profile_status added
# ---------------------------------------------------------------------------

def test_profile_status_in_canonical_commands():
    assert "profile_status" in CANONICAL_COMMANDS


def test_profile_status_in_aliases():
    assert "profile_status" in COMMAND_ALIASES


# ---------------------------------------------------------------------------
# Regression: existing commands still present
# ---------------------------------------------------------------------------

def test_delete_profile_still_in_canonical():
    assert "delete_profile" in CANONICAL_COMMANDS


def test_register_birth_still_in_canonical():
    assert "register_birth" in CANONICAL_COMMANDS


def test_show_profile_still_in_canonical():
    assert "show_profile" in CANONICAL_COMMANDS


def test_delete_profile_still_in_aliases():
    assert "delete_profile" in COMMAND_ALIASES


def test_register_birth_still_in_aliases():
    assert "register_birth" in COMMAND_ALIASES


def test_show_profile_still_in_aliases():
    assert "show_profile" in COMMAND_ALIASES
