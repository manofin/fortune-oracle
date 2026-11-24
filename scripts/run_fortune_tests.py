#!/usr/bin/env python3
"""Run Fortune tests without the operator's store, identity, network or TTS.

Use --profile core for the offline contributor baseline, --profile astronomy
for explicitly provisioned astronomy regressions, or --profile guard for source
scanner tests. Individual Fortune files can still be selected without a profile;
that mode runs every assertion in those files, including optional calculations.
This runner never discovers installed Hermes plugins or tests/agent.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "plugins/hermes_ext/fortune_oracle/scripts"
GUARD_FILES = (
    "tests/test_public_release_guard.py",
    "tests/test_fortune_oracle_secret_scan.py",
)

# Exact tests requiring Skyfield/DE440s and/or pyswisseph, rather than excluding
# whole modules containing useful offline failure, privacy and geometry checks.
# Collection fails if an entry is renamed or removed: update this inventory
# deliberately when changing the optional calculation contract.
ASTRONOMY_TESTS = frozenset({
    "plugins/tests/test_fortune_oracle_birth_clock.py::test_solar_term_table_cross_checked_against_jpl_longitude",
    "plugins/tests/test_fortune_oracle_combined_english.py::test_actual_english_four_method_calculation_and_provenance",
    "plugins/tests/test_fortune_oracle_combined_english.py::test_cli_combined_english_has_real_evidence",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_nasa_horizons_independent_reference_two_epochs_five_bodies",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_input_time_zones_same_instant_and_dst_are_correct",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_no_legacy_formula_is_called",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_missing_location_is_partial_and_no_birth_time_is_blocked",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_retrograde_and_provenance_reach_renderer_without_raw_birth_time",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_horizon_angles_are_on_ecliptic_and_correct_half_of_horizon",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_house_systems_use_computed_ascendant",
    "plugins/tests/test_fortune_oracle_ephemeris.py::test_chart_calculation_never_downloads",
    "plugins/tests/test_fortune_oracle_ephemeris_regression.py::TestBug01SpeedField::test_speed_field_not_daily_motion",
    "plugins/tests/test_fortune_oracle_ephemeris_regression.py::TestBug01SpeedField::test_daily_motion_must_be_sampled",
    "plugins/tests/test_fortune_oracle_ephemeris_regression.py::TestBug03HouseSystemComparison::test_asc_mc_not_dependent_on_house_system",
    "plugins/tests/test_fortune_oracle_ephemeris_regression.py::TestBug03HouseSystemComparison::test_house_cusps_differ_by_system",
    "plugins/tests/test_fortune_oracle_routing_evidence.py::test_astrology_calculation_sources_survive_adapter_and_renderer",
})
EXPECTED_CORE_SKIPS = frozenset({
    # An operator's external Hermes checkout is intentionally never imported.
    "tests/test_fortune_oracle_plugin_integration.py::test_gateway_files_not_modified",
})


def profile_paths(profile):
    if profile == "guard":
        return list(GUARD_FILES)
    if profile == "astronomy":
        return sorted({nodeid.split("::", 1)[0] for nodeid in ASTRONOMY_TESTS})
    return sorted(
        path.relative_to(REPO).as_posix()
        for folder in (REPO / "tests", REPO / "plugins/tests")
        for path in folder.glob("test_*.py")
        if (path.name.startswith("test_fortune_oracle")
            or path.name == "test_daily_fortune_engine.py")
        and path.relative_to(REPO).as_posix() not in GUARD_FILES
    )


def prepare_environment(root):
    # Do this before importing pytest, test modules or the plugin. In particular,
    # PYTEST_ADDOPTS/PYTEST_PLUGINS could otherwise defeat plugin isolation.
    for key in list(os.environ):
        if (key.startswith(("FORTUNE_", "HERMES_SESSION_", "OPENAI_"))
                or any(word in key for word in ("TOKEN", "API_KEY", "SECRET"))
                or key in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "NODE_OPTIONS", "NODE_PATH"}):
            os.environ.pop(key)
    os.environ.update({
        "HERMES_HOME": str(root / "hermes"),
        "FORTUNE_ORACLE_STORE": str(root / "store.json"),
        "FORTUNE_DEEP_ANALYSIS": "0",
        "MPLCONFIGDIR": str(root / "mpl"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": os.pathsep.join((str(REPO / "plugins"), str(REPO / "tests"))),
    })
    tempfile.tempdir = str(root)
    sys.path[:0] = [str(REPO / "plugins"), str(REPO / "tests")]


def check_profile_requirements(profile, ephemeris_path=None):
    modules = {"pytest": "pytest"}
    if profile == "core":
        modules.update({"Flask": "flask", "matplotlib": "matplotlib", "Pillow": "PIL"})
    missing = []
    for package, module in modules.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        raise ValueError(
            "Missing test dependencies: " + ", ".join(missing)
            + ". Install with: python -m pip install -r web/requirements-test.txt"
        )
    if profile == "guard":
        return
    if not shutil.which("node"):
        raise ValueError("Node.js 22 is required. Then run: npm ci --prefix "
                         "plugins/hermes_ext/fortune_oracle/scripts")
    # Check the locked versions and require both bridges, including their
    # transitive imports. Merely finding node_modules would permit false skips.
    try:
        locked = json.loads((BRIDGE / "package-lock.json").read_text())["packages"]
        script = """const fs = require('fs');
const names = ['iztro', 'lunar-javascript'];
const versions = Object.fromEntries(names.map(name => {
  require(name);
  return [name, JSON.parse(fs.readFileSync('node_modules/' + name + '/package.json')).version];
}));
process.stdout.write(JSON.stringify(versions));"""
        result = subprocess.run(["node", "-e", script], cwd=BRIDGE,
                                capture_output=True, text=True, timeout=15)
        versions = json.loads(result.stdout) if result.returncode == 0 else {}
        if any(versions.get(name) != locked[f"node_modules/{name}"]["version"]
               for name in ("iztro", "lunar-javascript")):
            raise ValueError("Node bridge dependencies are missing or differ from package-lock.json")
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        raise ValueError("Node bridge dependencies are unavailable or differ from package-lock.json. "
                         "Run: npm ci --prefix plugins/hermes_ext/fortune_oracle/scripts") from error
    if profile == "core":
        missing_media = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
        if missing_media:
            raise ValueError("Missing audio test tools: " + ", ".join(missing_media)
                             + ". Install ffmpeg (includes ffprobe); see docs/PUBLIC_SETUP.md")
    if profile == "astronomy":
        for module in ("skyfield", "swisseph"):
            try:
                importlib.import_module(module)
            except ImportError:
                raise ValueError("Astronomy profile requires Skyfield and pyswisseph. Install "
                                 "web/requirements-astronomy-test.txt in a separate Python 3.11 venv; "
                                 "see docs/PUBLIC_SETUP.md") from None
        from hermes_ext.fortune_oracle import ephemeris
        if ephemeris_path is not None:
            os.environ["FORTUNE_EPHEMERIS_PATH"] = str(ephemeris_path)
        try:
            ephemeris.resources()
        except ephemeris.EphemerisUnavailable as error:
            raise ValueError("Astronomy profile requires the hash-verified local JPL DE440s kernel. "
                             "Provision it explicitly before running tests, then use --ephemeris PATH; "
                             "see docs/PUBLIC_SETUP.md") from error


def profile_plugin(pytest, profile):
    class Selection:
        def __init__(self):
            self.unexpected_skips = []

        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(self, config, items):
            if profile == "guard":
                return
            collected = {item.nodeid for item in items}
            missing = ASTRONOMY_TESTS - collected
            if missing:
                raise pytest.UsageError("Astronomy test inventory is stale; update exact node IDs: "
                                        + ", ".join(sorted(missing)))
            selected, deselected = [], []
            for item in items:
                optional = item.nodeid in ASTRONOMY_TESTS
                (selected if optional == (profile == "astronomy") else deselected).append(item)
            items[:] = selected
            config.hook.pytest_deselected(items=deselected)
            reporter = config.pluginmanager.get_plugin("terminalreporter")
            if reporter:
                reporter.write_line(f"Fortune profile {profile}: {len(selected)} selected; "
                                    f"{len(deselected)} explicitly outside this profile")

        def pytest_runtest_logreport(self, report):
            if report.skipped and not (profile == "core" and report.nodeid in EXPECTED_CORE_SKIPS):
                self.unexpected_skips.append(report.nodeid)

        def pytest_collectreport(self, report):
            if report.skipped:
                self.unexpected_skips.append(report.nodeid)

    return Selection()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--profile", choices=("core", "astronomy", "guard"))
    parser.add_argument("--ephemeris", type=Path,
                        help="Explicit local DE440s kernel (astronomy profile only; never downloaded)")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--junitxml")
    parser.add_argument("-k", default="")
    args = parser.parse_args()
    if bool(args.profile) == bool(args.paths):
        parser.error("Select either --profile core|astronomy|guard or individual Fortune test files")
    if args.ephemeris is not None and args.profile != "astronomy":
        parser.error("--ephemeris requires --profile astronomy")
    ephemeris_path = args.ephemeris.resolve() if args.ephemeris else None
    paths = []
    for value in profile_paths(args.profile) if args.profile else args.paths:
        path = (REPO / value).resolve()
        if (path.parent not in (REPO / "tests", REPO / "plugins/tests")
                or not path.is_file()
                or not (path.name.startswith("test_fortune_oracle")
                        or path.name == "test_daily_fortune_engine.py"
                        or (args.profile == "guard" and value in GUARD_FILES))):
            parser.error(f"Select an individual Fortune test file: {value}")
        paths.append(str(path))
    if not paths:
        parser.error("No Fortune test files found in this checkout")

    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="fortune-tests-") as temporary:
        prepare_environment(Path(temporary))
        attempts = []

        def deny_network(*_args, **_kwargs):
            attempts.append("network")
            raise AssertionError("Fortune tests forbid real network connections")

        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network
        # TTS may launch an external process; sockets alone are insufficient.
        from hermes_ext.fortune_oracle import speech
        speech._runtime_tts = lambda: None
        import hermes_ext.fortune_oracle as library
        assert Path(library.__file__).resolve().is_relative_to(REPO / "plugins")
        if args.profile:
            try:
                check_profile_requirements(args.profile, ephemeris_path)
            except ValueError as error:
                parser.error(str(error))
        try:
            import pytest
        except ImportError:
            parser.error("pytest is unavailable. Install web/requirements-test.txt")
        selection = profile_plugin(pytest, args.profile) if args.profile else None
        pytest_args = ["-q", "-rs", "--tb=short", "-p", "no:cacheprovider",
                       "--import-mode=importlib", "--rootdir", str(REPO),
                       "--confcutdir", str(REPO), "-c", os.devnull, *paths]
        if args.collect_only:
            pytest_args.append("--collect-only")
        if args.junitxml:
            pytest_args.append(f"--junitxml={args.junitxml}")
        if args.k:
            pytest_args.extend(["-k", args.k])
        result = pytest.main(pytest_args, plugins=[selection] if selection else [])
        # A handler catching the transport exception cannot hide a real call.
        if attempts:
            print(f"Blocked external connection attempts: {len(attempts)}", file=sys.stderr)
            return 1
        if selection and selection.unexpected_skips:
            print("Unexpected skips in profile: " + ", ".join(sorted(set(selection.unexpected_skips))),
                  file=sys.stderr)
            return 1
        return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
