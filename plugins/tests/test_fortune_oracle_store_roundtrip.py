"""Persistence failures, mixed schemas and deterministic generated invariants.

Every file is a synthetic tmp_path fixture; no operational profile is read.
"""

from copy import deepcopy
import json
from pathlib import Path
import random

import pytest

from hermes_ext.fortune_oracle.store import FortuneStore


@pytest.fixture
def mixed_store(tmp_path):
    source = Path(__file__).parent / "fixtures" / "fortune_store_mixed_versions.json"
    path = tmp_path / "store.json"
    path.write_bytes(source.read_bytes())
    return FortuneStore(path)


def test_mixed_keys_prefer_current_line_key_and_isolate_telegram(mixed_store):
    assert mixed_store.get_profile("line", "shared")["birth_date"] == "1988-03-02"
    assert mixed_store.get_profile("telegram", "shared")["birth_date"] == "1992-06-12"
    assert mixed_store.get_profile("line", "legacy-only")["display_name"] == "구형 사용자"
    assert mixed_store.get_profile("telegram", "legacy-only") is None
    # Equal display names never identify or merge the owners.
    assert mixed_store.get_profile("line", "shared")["display_name"] == mixed_store.get_profile("telegram", "shared")["display_name"]


@pytest.mark.parametrize("platform", ["line", "telegram"])
def test_delete_one_owner_keeps_other_owner_profile_and_subscription(mixed_store, platform):
    before = json.loads(mixed_store.path.read_text())
    mixed_store.delete_profile(platform, "shared")
    after = json.loads(mixed_store.path.read_text())
    other = "telegram" if platform == "line" else "line"
    assert after["profiles"][other + ":shared"] == before["profiles"][other + ":shared"]
    assert mixed_store.get_profile(platform, "shared") is None
    if platform == "line":
        assert "shared" not in after["profiles"]
        assert after["daily_push"]["telegram:shared"] == before["daily_push"]["telegram:shared"]
    else:
        assert after["profiles"]["shared"] == before["profiles"]["shared"]
        assert "telegram:shared" not in after["daily_push"]
    assert after["future_metadata"] == before["future_metadata"]


def test_mixed_daily_target_fields_are_inferred_without_enabling_opted_out_users(mixed_store):
    assert mixed_store.collect_daily_push_targets(platform="line") == [
        {"platform": "line", "user_id": "legacy-only", "time": "00:00", "target": "legacy-chat"}
    ]
    assert mixed_store.collect_daily_push_targets(platform="telegram") == [
        {"platform": "telegram", "user_id": "shared", "time": "23:59", "target": "-1000001"}
    ]


@pytest.mark.parametrize("raw", [b'{', b'{"profiles":', b'\xff'])
def test_corrupt_store_never_overwrites_existing_bytes(tmp_path, raw):
    path = tmp_path / "store.json"
    path.write_bytes(raw)
    store = FortuneStore(path)
    with pytest.raises(ValueError):
        store.save_profile("telegram", "new", {"display_name": "fixture"})
    assert path.read_bytes() == raw
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("initial", [None, b''])
def test_empty_store_read_does_not_create_or_rewrite_file(tmp_path, initial):
    path = tmp_path / "store.json"
    if initial is not None:
        path.write_bytes(initial)
    store = FortuneStore(path)
    assert store.get_profile("telegram", "missing") is None
    assert store.collect_daily_push_targets() == []
    assert path.exists() == (initial is not None)
    if initial is not None:
        assert path.read_bytes() == initial


@pytest.mark.parametrize("time_hhmm", ["", "24:00", "23:60", "-1:00", "7:00", "00:00:00", " 07:00"])
def test_bad_push_time_is_rejected_without_any_store_change(mixed_store, time_hhmm):
    before = mixed_store.path.read_bytes()
    with pytest.raises(ValueError):
        mixed_store.set_daily_push("telegram", "shared", time_hhmm, target="fixture-chat")
    assert mixed_store.path.read_bytes() == before


@pytest.mark.parametrize("time_hhmm", ["00:00", "23:59"])
def test_push_time_boundaries_survive_reload(mixed_store, time_hhmm):
    mixed_store.set_daily_push("telegram", "boundary", time_hhmm, target="fixture-chat")
    reloaded = FortuneStore(mixed_store.path)
    assert reloaded.get_daily_push("telegram", "boundary")["time"] == time_hhmm


def test_failed_atomic_replace_preserves_previous_readable_store(mixed_store, monkeypatch):
    before = mixed_store.path.read_bytes()
    original_replace = Path.replace

    def fail_commit(path, target):
        if path == mixed_store.path.with_suffix(".json.tmp"):
            raise OSError("synthetic full filesystem")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_commit)
    with pytest.raises(OSError, match="synthetic"):
        mixed_store.save_profile("telegram", "new", {"display_name": "fixture"})
    assert mixed_store.path.read_bytes() == before
    assert FortuneStore(mixed_store.path).get_profile("telegram", "new") is None


def test_unserializable_input_preserves_original_store_and_caller(mixed_store):
    before = mixed_store.path.read_bytes()
    profile = {"display_name": "fixture", "invalid": {1, 2}}
    original = deepcopy(profile)
    with pytest.raises(TypeError):
        mixed_store.save_profile("telegram", "new", profile)
    assert mixed_store.path.read_bytes() == before
    assert profile == original


def test_generated_unicode_profile_roundtrips_preserve_all_owners_and_unknown_fields(mixed_store):
    # Fixed seed gives reproducible generated invariants without a new dependency.
    rng = random.Random(20261013)
    alphabet = list('한글甲子🙂"\\\n\t') + ["e\u0301", "\x00"]
    expected = json.loads(mixed_store.path.read_text())
    profiles = []
    for index in range(32):
        profile = {"display_name": "".join(rng.choices(alphabet, k=index)),
                   "extra": {"nested": [None, False, index, "\r\n"]}}
        profiles.append(deepcopy(profile))
        mixed_store.save_profile("telegram", f"generated-{index}", profile)
        expected["profiles"][f"telegram:generated-{index}"] = deepcopy(profile)
        # Stored objects must not remain aliased to mutable caller-owned data.
        profile["extra"]["nested"].append("caller-only")
    assert json.loads(mixed_store.path.read_text()) == expected
    reopened = FortuneStore(mixed_store.path)
    for index, profile in enumerate(profiles):
        assert reopened.get_profile("telegram", f"generated-{index}") == profile
