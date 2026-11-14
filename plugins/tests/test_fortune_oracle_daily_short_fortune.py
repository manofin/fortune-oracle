"""Deterministic legacy preview checks; actual sending uses daily_delivery."""
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_ext.fortune_oracle import daily_short_fortune as preview
from hermes_ext.fortune_oracle.daily_delivery import run_delivery
from hermes_ext.fortune_oracle.store import FortuneStore

NOW = datetime(2026, 10, 7, 7, tzinfo=preview.KST)
PROFILE = {"birth_date": "2000-01-01", "birth_time": "12:00"}


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(preview, "get_current_kst", lambda: NOW)
    monkeypatch.setattr(preview, "DEDUPE_LOG_PATH", tmp_path / "preview-ledger.json")
    result = FortuneStore(tmp_path / "store.json")
    result.set_daily_push("telegram", "101", "07:00", target="101", now=NOW - timedelta(days=1))
    return result


def test_preview_has_exact_profile_and_does_not_write(store):
    store.save_profile("telegram", "101", PROFILE)
    before = store.path.read_bytes()
    assert preview.get_recipients_with_profile_for_dry_run(store) == [{
        "user_id": "101", "time": "07:00", "target": "101", "platform": "telegram", "profile": PROFILE,
    }]
    assert store.path.read_bytes() == before
    assert not preview.DEDUPE_LOG_PATH.exists()


def test_profile_free_preview_is_not_permission_to_send(store):
    recipients = preview.get_recipients_with_profile_for_dry_run(store)
    assert len(recipients) == 1 and recipients[0]["profile"] is None
    report = run_delivery(store, now=NOW, send=True, sender=lambda *_: pytest.fail("no-profile delivery"))
    assert report["candidates"] == 1 and report["sent"] == 0
    assert [item["status"] for item in report["decisions"]] == ["no_profile"]


def test_fixed_clock_filters_later_time_and_opt_out(store):
    store.set_daily_push("telegram", "202", "08:00", target="202", now=NOW - timedelta(days=1))
    store.set_daily_push("telegram", "303", "07:00", target="303", now=NOW - timedelta(days=1))
    store.disable_daily_push("telegram", "303")
    recipients = preview.get_recipients_with_profile_for_dry_run(store)
    assert [item["user_id"] for item in recipients] == ["101"]


def test_legacy_preview_dedupe_is_date_bound_and_readonly(store, monkeypatch):
    preview.DEDUPE_LOG_PATH.write_text('{"2026-10-07:101": "sent"}')
    before = preview.DEDUPE_LOG_PATH.read_bytes()
    assert preview.get_recipients_with_profile_for_dry_run(store) == []
    monkeypatch.setattr(preview, "get_current_kst", lambda: NOW + timedelta(days=1))
    assert len(preview.get_recipients_with_profile_for_dry_run(store)) == 1
    assert preview.DEDUPE_LOG_PATH.read_bytes() == before
