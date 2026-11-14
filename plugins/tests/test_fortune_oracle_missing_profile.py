"""A known user without a profile receives guidance without writing the store."""

import importlib.util
from pathlib import Path


def test_show_profile_known_user_with_empty_store_returns_guidance(tmp_path, monkeypatch):
    store_path = tmp_path / "store.json"
    store_path.write_text('{"profiles": {}, "daily_push": {}}', encoding="utf-8")
    original = store_path.read_bytes()
    monkeypatch.setenv("FORTUNE_ORACLE_STORE", str(store_path))
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:repro-no-profile")
    monkeypatch.delenv("FORTUNE_ORACLE_PROFILE", raising=False)
    path = Path(__file__).resolve().parents[1] / "fortune_oracle_plugin" / "__init__.py"
    spec = importlib.util.spec_from_file_location("fortune_oracle_missing_profile", path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setattr(plugin, "_session_identity", lambda: None)

    result = plugin._handle_show_profile("")

    assert result == plugin._NO_PROFILE_TEXT
    assert "/register_birth" in result
    assert plugin._IDENTITY_REQUIRED not in result
    assert store_path.read_bytes() == original
