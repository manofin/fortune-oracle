"""Contributor profiles preserve assertion failures and runner isolation."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_fortune_tests.py"
spec = importlib.util.spec_from_file_location("fortune_test_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def isolated_checkout(tmp_path):
    """A synthetic checkout proves guards without touching the working source."""
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "tests").mkdir()
    shutil.copyfile(SCRIPT, checkout / "scripts/run_fortune_tests.py")
    plugin = checkout / "plugins/hermes_ext/fortune_oracle"
    plugin.mkdir(parents=True)
    (plugin.parent / "__init__.py").write_text("")
    (plugin / "__init__.py").write_text("")
    (plugin / "speech.py").write_text("def _runtime_tts():\n    raise AssertionError('TTS must be disabled')\n")
    return checkout


def run(checkout, *args, env=None):
    return subprocess.run(
        [sys.executable, "-B", str(checkout / "scripts/run_fortune_tests.py"), *args],
        cwd=checkout, env=env, capture_output=True, text=True, timeout=30,
    )


def test_inventory_names_real_tests_and_leaves_offline_checks_in_core():
    assert len(runner.ASTRONOMY_TESTS) == 16
    for nodeid in runner.ASTRONOMY_TESTS:
        filename, *names = nodeid.split("::")
        body = ast.parse((REPO / filename).read_text()).body
        for name in names:
            node = next((node for node in body if getattr(node, "name", None) == name), None)
            assert node is not None, nodeid
            body = getattr(node, "body", [])
    assert not any("test_missing_corrupt_kernel_or_dependency" in nodeid
                   for nodeid in runner.ASTRONOMY_TESTS)
    assert not any("test_real_report_is_natal" in nodeid for nodeid in runner.ASTRONOMY_TESTS)


def test_profiles_discover_fortune_files_and_keep_source_guards_separate(tmp_path, monkeypatch):
    for filename in ("tests/test_fortune_oracle_new.py", "tests/test_fortune_oracle_secret_scan.py",
                     "tests/test_public_release_guard.py", "tests/test_unrelated.py",
                     "plugins/tests/test_daily_fortune_engine.py",
                     "tests/agent/test_fortune_oracle_private.py"):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(runner, "REPO", tmp_path)
    assert runner.profile_paths("core") == [
        "plugins/tests/test_daily_fortune_engine.py", "tests/test_fortune_oracle_new.py",
    ]
    assert runner.profile_paths("guard") == list(runner.GUARD_FILES)


def test_astronomy_collects_only_its_inventory_modules():
    assert runner.profile_paths("astronomy") == sorted({
        nodeid.split("::", 1)[0] for nodeid in runner.ASTRONOMY_TESTS
    })
    assert len(runner.profile_paths("astronomy")) == 5
    assert all(not path.startswith("tests/") for path in runner.profile_paths("astronomy"))


@pytest.mark.parametrize("profile,expected", [("core", "offline"), ("astronomy", "numeric")])
def test_profiles_partition_exact_nodes_and_report_deselection(monkeypatch, profile, expected):
    monkeypatch.setattr(runner, "ASTRONOMY_TESTS", frozenset({"numeric"}))
    removed = []
    config = SimpleNamespace(
        hook=SimpleNamespace(pytest_deselected=lambda items: removed.extend(items)),
        pluginmanager=SimpleNamespace(get_plugin=lambda _: None),
    )
    items = [SimpleNamespace(nodeid="offline"), SimpleNamespace(nodeid="numeric")]
    runner.profile_plugin(pytest, profile).pytest_collection_modifyitems(config, items)
    assert [item.nodeid for item in items] == [expected]
    assert {item.nodeid for item in items + removed} == {"offline", "numeric"}


def test_stale_optional_inventory_fails_collection_instead_of_silently_dropping_coverage(monkeypatch):
    monkeypatch.setattr(runner, "ASTRONOMY_TESTS", frozenset({"renamed_numeric_test"}))
    with pytest.raises(pytest.UsageError, match="inventory is stale"):
        runner.profile_plugin(pytest, "core").pytest_collection_modifyitems(None, [])


def test_runner_removes_inherited_credentials_pytest_options_and_node_injection(isolated_checkout, tmp_path):
    (isolated_checkout / "tests/test_fortune_oracle_probe.py").write_text('''
import json
import os
from pathlib import Path
from hermes_ext.fortune_oracle import speech

def test_probe():
    for name in ("FORTUNE_ORACLE_USER", "HERMES_SESSION_ID", "OPENAI_BASE_URL",
                 "SYNTHETIC_API_KEY", "SYNTHETIC_TOKEN", "SYNTHETIC_SECRET",
                 "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "NODE_OPTIONS", "NODE_PATH"):
        assert name not in os.environ
    assert os.environ["FORTUNE_DEEP_ANALYSIS"] == "0"
    assert os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert speech._runtime_tts() is None
    store = Path(os.environ["FORTUNE_ORACLE_STORE"])
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir()
    store.write_text("synthetic isolated test state")
    Path(os.environ["RUNNER_PROBE_REPORT"]).write_text(json.dumps([str(home), str(store)]))
''')
    original = tmp_path / "inherited-store.json"
    original.write_text("synthetic operator fixture")
    report = tmp_path / "report.json"
    inherited = {
        **os.environ, "HERMES_HOME": str(tmp_path / "operator-home"),
        "FORTUNE_ORACLE_STORE": str(original), "FORTUNE_ORACLE_USER": "synthetic-user",
        "HERMES_SESSION_ID": "synthetic-session", "OPENAI_BASE_URL": "https://example.invalid",
        "SYNTHETIC_API_KEY": "placeholder", "SYNTHETIC_TOKEN": "placeholder",
        "SYNTHETIC_SECRET": "placeholder", "PYTEST_ADDOPTS": "--invalid-inherited-option",
        "PYTEST_PLUGINS": "unavailable_inherited_plugin", "NODE_OPTIONS": "--invalid-option",
        "NODE_PATH": "/synthetic/inherited/module", "RUNNER_PROBE_REPORT": str(report),
    }
    result = run(isolated_checkout, "tests/test_fortune_oracle_probe.py", env=inherited)
    assert result.returncode == 0, result.stdout + result.stderr
    assert original.read_text() == "synthetic operator fixture"
    assert not (tmp_path / "operator-home").exists()
    assert all(not Path(path).exists() for path in json.loads(report.read_text()))


def test_caught_network_attempt_still_fails_the_runner(isolated_checkout):
    (isolated_checkout / "tests/test_fortune_oracle_probe.py").write_text('''
import socket

def test_caught_attempt():
    try:
        socket.create_connection(("example.invalid", 443))
    except AssertionError:
        pass
''')
    result = run(isolated_checkout, "tests/test_fortune_oracle_probe.py")
    assert result.returncode == 1
    assert "1 passed" in result.stdout
    assert "Blocked external connection attempts: 1" in result.stderr


def test_explicit_selection_preserves_calculation_assertion_failures(isolated_checkout):
    (isolated_checkout / "tests/test_fortune_oracle_numeric.py").write_text(
        "def test_real_calculation():\n    assert False, 'real computation unavailable'\n"
    )
    result = run(isolated_checkout, "tests/test_fortune_oracle_numeric.py")
    assert result.returncode == 1
    assert "1 failed" in result.stdout and "real computation unavailable" in result.stdout


def test_guard_profile_rejects_unexpected_skip(isolated_checkout):
    for filename in runner.GUARD_FILES:
        (isolated_checkout / filename).write_text(
            "import pytest\ndef test_guard():\n    pytest.skip('unexpected fixture skip')\n"
        )
    result = run(isolated_checkout, "--profile", "guard")
    assert result.returncode == 1
    assert "2 skipped" in result.stdout and "Unexpected skips in profile" in result.stderr


def test_guard_profile_rejects_module_level_import_skip(isolated_checkout):
    for filename in runner.GUARD_FILES:
        (isolated_checkout / filename).write_text(
            "import pytest\npytest.skip('unexpected collection skip', allow_module_level=True)\n"
        )
    result = run(isolated_checkout, "--profile", "guard")
    assert result.returncode == 1
    assert "2 skipped" in result.stdout and "Unexpected skips in profile" in result.stderr


def test_only_external_hermes_contract_may_skip_in_core():
    core = runner.profile_plugin(pytest, "core")
    known = next(iter(runner.EXPECTED_CORE_SKIPS))
    core.pytest_runtest_logreport(SimpleNamespace(skipped=True, nodeid=known))
    core.pytest_runtest_logreport(SimpleNamespace(skipped=True, nodeid="unexpected_numeric_skip"))
    assert core.unexpected_skips == ["unexpected_numeric_skip"]
    astronomy = runner.profile_plugin(pytest, "astronomy")
    astronomy.pytest_runtest_logreport(SimpleNamespace(skipped=True, nodeid=known))
    assert astronomy.unexpected_skips == [known]


def test_core_preflight_reports_missing_pinned_python_dependencies(monkeypatch):
    def missing(module):
        if module == "flask":
            raise ImportError("synthetic missing Flask")
    monkeypatch.setattr(runner, "importlib", SimpleNamespace(import_module=missing))
    with pytest.raises(ValueError, match="Missing test dependencies: Flask.*requirements-test.txt"):
        runner.check_profile_requirements("core")


def test_core_preflight_rejects_bridge_version_drift(monkeypatch):
    monkeypatch.setattr(runner, "importlib", SimpleNamespace(import_module=lambda _: None))
    monkeypatch.setattr(runner, "shutil", SimpleNamespace(which=lambda _: "/synthetic/node"))
    monkeypatch.setattr(runner, "subprocess", SimpleNamespace(
        run=lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"iztro":"0.0.0"}'),
        TimeoutExpired=subprocess.TimeoutExpired,
    ))
    with pytest.raises(ValueError, match="differ from package-lock.json.*npm ci"):
        runner.check_profile_requirements("core")


@pytest.mark.parametrize("args", [(), ("--profile", "core", "tests/test_fortune_oracle_probe.py"),
    ("--profile", "core", "--ephemeris", "synthetic.bsp")])
def test_ambiguous_profile_arguments_fail_before_import(isolated_checkout, args):
    result = run(isolated_checkout, *args)
    assert result.returncode == 2 and "error:" in result.stderr


def test_symlink_cannot_select_a_test_outside_checkout(isolated_checkout, tmp_path):
    outside = tmp_path / "test_fortune_oracle_outside.py"
    outside.write_text("raise AssertionError('must not import outside checkout')\n")
    (isolated_checkout / "tests/test_fortune_oracle_link.py").symlink_to(outside)
    result = run(isolated_checkout, "tests/test_fortune_oracle_link.py")
    assert result.returncode == 2 and "individual Fortune test file" in result.stderr
