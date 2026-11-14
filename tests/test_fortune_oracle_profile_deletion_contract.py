"""Deletion covers owned locations/consent while retaining other users and dedupe."""

# Numeric user/chat identities in this module are synthetic fixtures.
import importlib.util

import pytest
from _fo_paths import repo_plugin_path
from hermes_ext.fortune_oracle.daily_delivery import recipient_ref
from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
from hermes_ext.fortune_oracle.store import FortuneStore


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    monkeypatch.setenv("FORTUNE_ORACLE_STORE", str(tmp_path / "store.json"))
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:333333333333")
    monkeypatch.delenv("FORTUNE_ORACLE_PROFILE", raising=False)
    spec = importlib.util.spec_from_file_location("fo_delete_contract", repo_plugin_path("__init__.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("with_profile", [True, False])
def test_confirmed_deletion_removes_owned_data_and_preserves_other_account(plugin, with_profile):
    store = plugin._store()
    if with_profile:
        store.save_profile("telegram", "333333333333", {"birth_date": "2000-01-01", "display_name": "가상가"})
    store.save_profile("telegram", "444444444444", {"birth_date": "2001-01-01", "display_name": "가상나"})
    for uid in ("333333333333", "444444444444"):
        store.set_daily_push("telegram", uid, "08:00", target=uid)
        with store.transaction() as data:
            for key in (f"telegram:{uid}", build_location_profile_key("telegram", uid)):
                data[f"location_settings:{key}"] = {"label": "가상 위치", "timezone": "Asia/Seoul"}
    ledger = {recipient_ref("telegram:333333333333"): {"date": "2026-10-13", "state": "sent"}}
    with store.transaction() as data:
        data["daily_delivery"] = ledger
    before = store._load()
    before_bytes = store.path.read_bytes()
    assert "확인" in plugin._handle_delete_profile("")
    assert store.path.read_bytes() == before_bytes

    reply = plugin._handle_delete_profile("확인")
    after = store._load()
    assert "위치" in reply and "매일 운세" in reply
    assert "개인정보가 모두" not in reply
    assert "telegram:333333333333" not in after["profiles"]
    assert "telegram:333333333333" not in after["daily_push"]
    for key in ("telegram:333333333333", build_location_profile_key("telegram", "333333333333")):
        assert f"location_settings:{key}" not in after
    assert after["profiles"]["telegram:444444444444"] == before["profiles"]["telegram:444444444444"]
    assert after["daily_push"]["telegram:444444444444"] == before["daily_push"]["telegram:444444444444"]
    for key in ("telegram:444444444444", build_location_profile_key("telegram", "444444444444")):
        assert after[f"location_settings:{key}"] == before[f"location_settings:{key}"]
    assert after["daily_delivery"] == ledger
    plugin._handle_delete_profile("확인")
    assert store._load() == after


def test_store_deletion_covers_normalized_raw_and_hashed_location_keys(tmp_path):
    store = FortuneStore(tmp_path / "store.json")
    with store.transaction() as data:
        for key in ("telegram:333333333333", build_location_profile_key("telegram", "333333333333")):
            data[f"location_settings:{key}"] = {"label": "가상 위치"}
    store.delete_profile(" Telegram ", " 333333333333 ")
    assert not any(key.startswith("location_settings:") for key in store._load())
