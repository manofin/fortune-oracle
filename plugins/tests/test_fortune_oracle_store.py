"""Test FortuneStore daily_push opt-in/opt-out logic (Gate 2A)."""

import sys
import tempfile
from pathlib import Path

import pytest

_plugins_dir = str(Path(__file__).resolve().parents[1])
if _plugins_dir not in sys.path:
    sys.path.insert(0, _plugins_dir)

from hermes_ext.fortune_oracle.store import FortuneStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "fortune_oracle_store.json"
        yield FortuneStore(store_path)


class TestDailyPush:
    def test_set_daily_push_basic(self, temp_store):
        temp_store.set_daily_push("telegram", "user123", "07:00", target="telegram")
        entry = temp_store.get_daily_push("telegram", "user123")
        assert entry is not None
        assert entry["opt_in"] is True
        assert entry["time"] == "07:00"
        assert entry["platform"] == "telegram"

    def test_set_daily_push_invalid_time(self, temp_store):
        with pytest.raises(ValueError):
            temp_store.set_daily_push("telegram", "user123", "25:00", target="telegram")
        with pytest.raises(ValueError):
            temp_store.set_daily_push("telegram", "user123", "07:60", target="telegram")

    def test_disable_daily_push(self, temp_store):
        temp_store.set_daily_push("telegram", "user123", "07:00", target="telegram")
        temp_store.disable_daily_push("telegram", "user123")
        entry = temp_store.get_daily_push("telegram", "user123")
        assert entry is None

    def test_collect_daily_push_targets(self, temp_store):
        temp_store.set_daily_push("telegram", "userA", "07:00", target="telegram")
        temp_store.set_daily_push("telegram", "userB", "08:00", target="telegram")
        temp_store.disable_daily_push("telegram", "userB")  # opt-out

        targets = temp_store.collect_daily_push_targets(platform="telegram")
        assert len(targets) == 1
        assert targets[0]["user_id"] == "userA"
        assert targets[0]["time"] == "07:00"

    def test_daily_push_entries(self, temp_store):
        temp_store.set_daily_push("telegram", "user123", "07:00", target="telegram")
        entries = temp_store.daily_push_entries()
        assert "telegram:user123" in entries
        assert entries["telegram:user123"]["opt_in"] is True

    def test_multiple_platforms(self, temp_store):
        temp_store.set_daily_push("telegram", "u1", "07:00", target="telegram")
        temp_store.set_daily_push("line", "u2", "08:00", target="line")

        tg_targets = temp_store.collect_daily_push_targets(platform="telegram")
        line_targets = temp_store.collect_daily_push_targets(platform="line")

        assert len(tg_targets) == 1
        assert len(line_targets) == 1

    def test_default_off_behavior(self, temp_store):
        # No opt-in yet
        targets = temp_store.collect_daily_push_targets(platform="telegram")
        assert len(targets) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])