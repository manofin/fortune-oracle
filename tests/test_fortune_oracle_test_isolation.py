"""Regression checks for the runner that protects operator state."""

# Numeric user/chat identities in this module are synthetic fixtures.
import json
import os
from pathlib import Path
import subprocess
import sys

from _fo_paths import repo_path, repo_plugin_path


def test_plugin_and_library_come_from_the_same_checkout():
    from hermes_ext.fortune_oracle import store
    assert Path(repo_plugin_path("__init__.py")).is_file()
    assert Path(store.__file__).resolve().is_relative_to(Path(repo_path("plugins")))


def test_runner_preserves_inherited_store_and_identity(tmp_path):
    home = tmp_path / "operator-home"
    store = home / "fortune_oracle/store.json"
    store.parent.mkdir(parents=True)
    original = json.dumps({
        "profiles": {"telegram:333333333333": {"birth_date": "2000-01-01"}},
        "daily_push": {"telegram:333333333333": {"opt_in": True, "time": "08:00"}},
        "location_settings:telegram:333333333333": {"timezone": "UTC"},
    }).encode()
    store.write_bytes(original)
    env = dict(os.environ, HERMES_HOME=str(home), FORTUNE_ORACLE_STORE=str(store),
               FORTUNE_ORACLE_USER="telegram:333333333333", FORTUNE_DEEP_ANALYSIS="1")
    result = subprocess.run([
        sys.executable, repo_path("scripts/run_fortune_tests.py"),
        "tests/test_fortune_oracle.py",
        "-k", "test_line_allowlist_fail_closed_for_unknown_source",
    ], env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert store.read_bytes() == original
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "fortune_oracle/store.json"
    ]


def test_runner_refuses_unrelated_test_directories():
    result = subprocess.run([
        sys.executable, repo_path("scripts/run_fortune_tests.py"), "tests/agent",
    ], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "individual Fortune test file" in result.stderr
