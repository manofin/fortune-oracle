#!/usr/bin/env python3
"""Run explicitly selected Fortune tests without the operator's store or identity.

Example: .venv/bin/python scripts/run_fortune_tests.py tests/test_fortune_oracle_web.py
This runner does not discover installed Hermes plugins or run tests/agent.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--junitxml")
    parser.add_argument("-k", default="")
    args = parser.parse_args()
    paths = []
    for value in args.paths:
        path = (REPO / value).resolve()
        if (path.parent not in (REPO / "tests", REPO / "plugins/tests")
                or not path.is_file()
                or not (path.name.startswith("test_fortune_oracle")
                        or path.name == "test_daily_fortune_engine.py")):
            parser.error(f"Select an individual Fortune test file: {value}")
        paths.append(str(path))

    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="fortune-tests-") as temporary:
        root = Path(temporary)
        # Set these before importing pytest, test modules, or the plugin.
        for key in list(os.environ):
            if (key.startswith(("FORTUNE_", "HERMES_SESSION_", "OPENAI_"))
                    or any(word in key for word in ("TOKEN", "API_KEY", "SECRET"))):
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
        attempts = []

        def deny_network(*_args, **_kwargs):
            attempts.append("network")
            raise AssertionError("Fortune tests forbid real network connections")

        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network
        # TTS may launch an external process; socket patches alone are insufficient.
        from hermes_ext.fortune_oracle import speech
        speech._runtime_tts = lambda: None
        import hermes_ext.fortune_oracle as library
        assert Path(library.__file__).resolve().is_relative_to(REPO / "plugins")
        import pytest
        pytest_args = ["-q", "--tb=short", "-p", "no:cacheprovider", "--import-mode=importlib", *paths]
        if args.collect_only:
            pytest_args.append("--collect-only")
        if args.junitxml:
            pytest_args.append(f"--junitxml={args.junitxml}")
        if args.k:
            pytest_args.extend(["-k", args.k])
        result = pytest.main(pytest_args)
        # Even a handler that catches the transport exception cannot hide a call.
        if attempts:
            print(f"Blocked external connection attempts: {len(attempts)}", file=sys.stderr)
            return 1
        return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
