"""Real process crash/restart probes, using only disposable synthetic stores.

Pipe barriers locate crash points; no database, backup, HTTP, or subprocess
result is mocked. Snapshot crash probes cover process loss, not power loss.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import selectors
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
sys.path.insert(0, str(ROOT / "web"))

from fortune_web.storage import WebStore


DAY = "2026-11-20"
PROFILE = {"birth_date": "1990-05-17", "birth_time": "12:30",
           "display_name": "synthetic-process-person", "timezone": "Asia/Seoul", "gender": "male"}


def _ready(**details):
    print(json.dumps({"ready": True, **details}), flush=True)
    # The parent either releases this barrier or kills this exact child PID.
    if sys.stdin.readline() != "continue\n":
        raise RuntimeError("Parent closed the crash barrier")


def _transaction_child(path, token, phase, operation):
    store = WebStore(path)
    connect = store.connect

    @contextmanager
    def at_commit():
        with connect() as db:
            yield db
            assert db.in_transaction
            if phase == "before":
                _ready(boundary="before-commit")
        if phase == "after":
            _ready(boundary="after-commit")

    store.connect = at_commit
    if operation == "event":
        assert store.record_event(token, DAY, "visit", "entry")
    elif operation == "sample":
        assert store.record_sample_event(token, DAY, "product_sample_viewed", "self_manual_v1") == "inserted"
    elif operation == "delete":
        store.delete(token)
    else:
        raise ValueError(operation)


def _snapshot_child(source, destination, phase, operation):
    from fortune_web import snapshots

    link = snapshots.os.link

    def at_publication(*args, **kwargs):
        if phase == "before":
            _ready(boundary="before-publication")
        result = link(*args, **kwargs)
        if phase == "after":
            _ready(boundary="after-publication")
        return result

    snapshots.os.link = at_publication
    getattr(snapshots, operation)(source, destination)


def _server_child(path):
    from fortune_web import create_app
    from werkzeug.serving import make_server

    configuration = json.loads(sys.stdin.readline())
    app = create_app({"WEB_STORE": path, "SECRET_KEY": configuration["secret"], "COOKIE_SECURE": False,
                      "START_CLEANUP": False, "NOW": datetime(2026, 11, 20, tzinfo=timezone.utc)})
    server = make_server("127.0.0.1", 0, app)
    print(json.dumps({"ready": True, "port": server.server_port}), flush=True)
    server.serve_forever()


def _message(process, timeout=10):
    deadline = time.monotonic() + timeout
    pending = bytearray()
    with selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ)
        while b"\n" not in pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not ready.select(remaining):
                raise AssertionError(f"Child {process.pid} did not reach its complete barrier")
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                raise AssertionError(f"Child {process.pid} closed stdout before its barrier (exit {process.poll()})")
            pending.extend(chunk)
            if len(pending) > 65536:
                raise AssertionError("Child barrier exceeded its size limit")
    result = json.loads(bytes(pending).split(b"\n", 1)[0])
    assert result["ready"] is True
    return result


@contextmanager
def _child(tmp_path, *arguments):
    process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), *map(str, arguments)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=_environment(tmp_path), cwd=ROOT)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def _environment(tmp_path):
    # Never inherit FORTUNE_*, HERMES_*, credentials, operator config paths,
    # proxy settings, Python import hooks, or Node startup configuration.
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
            "HERMES_HOME": str(tmp_path / "empty-hermes"),
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"}


def _kill(process):
    # Popen owns this PID and waits/reaps it; no name-based process selection.
    process.kill()
    process.wait(timeout=10)
    assert process.returncode == -signal.SIGKILL


def _rows(path, statement, parameters=()):
    with sqlite3.connect(path) as db:
        return db.execute(statement, parameters).fetchall()


def _healthy(path):
    assert _rows(path, "PRAGMA integrity_check") == [("ok",)]
    assert _rows(path, "PRAGMA foreign_key_check") == []


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX SIGKILL and SQLite crash recovery")
@pytest.mark.parametrize("journal_mode", ["DELETE", "WAL"])
@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("operation,event,view", [("event", "visit", "entry"),
                                                  ("sample", "product_sample_viewed", "self_manual_v1")])
def test_sigkill_metric_transaction_recovers_without_partial_count_or_duplicate(tmp_path, phase, operation, event, view, journal_mode):
    store = WebStore(tmp_path / "metrics.sqlite3")
    with store.connect() as db:
        assert db.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()[0] == journal_mode.lower()
    token = store.create(86400)
    assert store.save(token, PROFILE)
    with _child(tmp_path, "transaction", store.path, token, phase, operation) as process:
        assert _message(process)["boundary"] == f"{phase}-commit"
        _kill(process)

    _healthy(store.path)
    expected = int(phase == "after")
    assert _rows(store.path, "SELECT count(*) FROM metric_receipts") == [(expected,)]
    assert _rows(store.path, "SELECT coalesce(sum(count), 0) FROM metric_counts") == [(expected,)]
    assert store.find(token)["profile"] == PROFILE
    # Retrying after an uncertain acknowledgement must complete once in either
    # recovery state, and must not count a previously committed attempt again.
    if operation == "event":
        assert store.record_event(token, DAY, event, view) is (phase == "before")
        assert not store.record_event(token, DAY, event, view)
    else:
        assert store.record_sample_event(token, DAY, event, view) == ("inserted" if phase == "before" else "duplicate")
        assert store.record_sample_event(token, DAY, event, view) == "duplicate"
    assert _rows(store.path, "SELECT day, event, view, count FROM metric_counts") == [(DAY, event, view, 1)]
    assert _rows(store.path, "SELECT count(*) FROM metric_receipts") == [(1,)]
    _healthy(store.path)


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX SIGKILL")
@pytest.mark.parametrize("phase", ["before", "after"])
def test_sigkill_profile_deletion_keeps_session_receipt_cascade_atomic(tmp_path, phase):
    store = WebStore(tmp_path / "deletion.sqlite3")
    token = store.create(86400)
    assert store.save(token, PROFILE)
    assert store.record_event(token, DAY, "visit", "entry")
    with _child(tmp_path, "transaction", store.path, token, phase, "delete") as process:
        assert _message(process)["boundary"] == f"{phase}-commit"
        _kill(process)
    _healthy(store.path)
    remaining = int(phase == "before")
    assert _rows(store.path, "SELECT count(*) FROM web_sessions") == [(remaining,)]
    assert _rows(store.path, "SELECT count(*) FROM metric_receipts") == [(remaining,)]
    assert _rows(store.path, "SELECT count FROM metric_counts") == [(1,)]
    assert (store.find(token) is not None) is (phase == "before")
    store.delete(token)  # Safe retry after either commit boundary.
    assert store.find(token) is None
    assert _rows(store.path, "SELECT count(*) FROM metric_receipts") == [(0,)]
    assert PROFILE["display_name"].encode() not in store.path.read_bytes()


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX SIGKILL and private hardlink publication")
@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("operation", ["backup", "restore_aggregates"])
def test_sigkill_snapshot_never_publishes_an_incomplete_database(tmp_path, phase, operation):
    from fortune_web import snapshots

    tmp_path.chmod(0o700)
    store = WebStore(tmp_path / "live.sqlite3")
    token = store.create(86400)
    assert store.save(token, PROFILE)
    assert store.record_event(token, DAY, "visit", "entry")
    destination = tmp_path / "published.sqlite3"
    with _child(tmp_path, "snapshot", store.path, destination, phase, operation) as process:
        assert _message(process)["boundary"] == f"{phase}-publication"
        assert destination.exists() is (phase == "after")
        _kill(process)

    _healthy(store.path)
    # SIGKILL cannot run TemporaryDirectory cleanup. Any remaining staging
    # database must still be private and complete, never a public partial file.
    stages = list(tmp_path.glob(".fortune-snapshot-*"))
    assert len(stages) == 1
    assert stages[0].stat().st_mode & 0o777 == 0o700
    staged = stages[0] / "data.sqlite3"
    assert staged.stat().st_mode & 0o777 == 0o600
    _healthy(staged)
    if phase == "before":
        assert not destination.exists()
        getattr(snapshots, operation)(store.path, destination)
    else:
        before = destination.read_bytes()
        with pytest.raises(FileExistsError):
            getattr(snapshots, operation)(store.path, destination)
        assert destination.read_bytes() == before
    _healthy(destination)
    assert destination.stat().st_mode & 0o777 == 0o600
    assert _rows(destination, "SELECT day, event, view, count FROM metric_counts") == [(DAY, "visit", "entry", 1)]
    if operation == "backup":
        assert WebStore(destination).find(token)["profile"] == PROFILE
    else:
        assert _rows(destination, "SELECT * FROM web_sessions") == []
        assert _rows(destination, "SELECT * FROM metric_receipts") == []
        assert PROFILE["display_name"].encode() not in destination.read_bytes()


def _http_child(port, path, method):
    port = int(port)
    if not 1 <= port <= 65535 or path not in {
        "/api/session", "/api/profile", "/api/events", "/api/readings/today",
    } or method not in {"GET", "PUT", "POST", "DELETE"}:
        raise ValueError("Only fixed loopback probe endpoints are permitted")
    arguments = json.load(sys.stdin)
    token, csrf, payload = (arguments[key] for key in ("token", "csrf", "payload"))
    headers = {"Origin": f"http://127.0.0.1:{port}"}
    if token:
        headers["Cookie"] = f"fortune_session={token}"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
    class NoRedirects(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            raise ValueError("Probe redirects are forbidden")

    try:
        response = build_opener(NoRedirects()).open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        print(json.dumps({"status": response.status, "body": json.load(response),
                          "headers": {"Set-Cookie": response.headers.get("Set-Cookie", "")}}), flush=True)


def _http(tmp_path, port, path, method="GET", token=None, csrf=None, payload=None):
    # The official offline runner denies all parent-process network access. A
    # sanitized child makes this one bounded loopback request; the runner's
    # external-connection guard remains unchanged for the rest of the suite.
    result = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                             "http", str(port), path, method],
                            input=json.dumps({"token": token, "csrf": csrf, "payload": payload}),
                            capture_output=True, text=True, timeout=10, check=True,
                            env=_environment(tmp_path), cwd=ROOT)
    reply = json.loads(result.stdout)
    return reply["status"], reply["body"], reply["headers"]


def _cookie(headers):
    cookie = SimpleCookie()
    cookie.load(headers.get("Set-Cookie", ""))
    return cookie["fortune_session"].value if "fortune_session" in cookie else None


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX SIGKILL and loopback HTTP")
@pytest.mark.parametrize("session_state", ["live", "deleted", "expired"])
def test_http_process_restart_preserves_revocation_and_metric_deduplication(tmp_path, session_state):
    path = tmp_path / "http.sqlite3"
    http = partial(_http, tmp_path)
    secret = secrets.token_hex(32)
    with _child(tmp_path, "server", path) as first:
        first.stdin.write(json.dumps({"secret": secret}) + "\n")
        first.stdin.flush()
        port = _message(first)["port"]
        status, body, headers = http(port, "/api/session")
        assert status == 200
        token, csrf = _cookie(headers), body["csrf"]
        assert token
        assert http(port, "/api/profile", "PUT", token, csrf, PROFILE)[0] == 200
        for event in ("product_sample_viewed", "product_sample_interest"):
            assert http(port, "/api/events", "POST", token, csrf,
                         {"event": event, "view": "self_manual_v1"})[0] == 202
        if session_state == "deleted":
            assert http(port, "/api/profile", "DELETE", token, csrf)[0] == 200
        _kill(first)
    if session_state == "expired":
        with sqlite3.connect(path) as db:
            db.execute("UPDATE web_sessions SET expires = 0")

    before = _rows(path, "SELECT day, event, view, count FROM metric_counts ORDER BY event, view")
    assert len(before) == 4 and all(row[3] == 1 for row in before)
    with _child(tmp_path, "server", path) as second:
        second.stdin.write(json.dumps({"secret": secret}) + "\n")
        second.stdin.flush()
        port = _message(second)["port"]
        if session_state == "live":
            status, body, headers = http(port, "/api/session", token=token)
            assert status == 200 and body["profile"]["display_name"] == PROFILE["display_name"]
            assert body["csrf"] == csrf and _cookie(headers) is None
            for event in ("product_sample_viewed", "product_sample_interest"):
                assert http(port, "/api/events", "POST", token, csrf,
                             {"event": event, "view": "self_manual_v1"})[0] == 202
            assert _rows(path, "SELECT day, event, view, count FROM metric_counts ORDER BY event, view") == before
        else:
            assert http(port, "/api/readings/today", token=token)[0] == 401
            assert http(port, "/api/events", "POST", token, csrf,
                         {"event": "product_sample_interest", "view": "self_manual_v1"})[0] == 401
            assert _rows(path, "SELECT count(*) FROM metric_receipts") == [(0,)]
            assert _rows(path, "SELECT count(*) FROM web_sessions") == [(0,)]
            assert _rows(path, "SELECT day, event, view, count FROM metric_counts ORDER BY event, view") == before
            status, body, headers = http(port, "/api/session", token=token)
            assert status == 200 and body["profile"] is None
            assert _cookie(headers) not in (None, token)
            assert PROFILE["display_name"] not in json.dumps(body)
            # A new registration counts one new visit; rejected old-cookie
            # requests did not duplicate any prior aggregate.
            after = _rows(path, "SELECT event, count FROM metric_counts ORDER BY event")
            assert after == [("product_sample_interest", 1), ("product_sample_viewed", 1),
                             ("profile_saved", 1), ("visit", 2)]
            assert PROFILE["display_name"].encode() not in path.read_bytes()
    _healthy(path)


@pytest.mark.skipif(not shutil.which("node") or os.name != "posix", reason="Real Node and POSIX process reaping required")
def test_real_node_bridge_timeout_kills_and_reaps_the_child(tmp_path, monkeypatch):
    from hermes_ext.fortune_oracle import bazi_bridge

    pid_file = tmp_path / "slow-node.pid"
    script = tmp_path / "slow-node.mjs"
    script.write_text("import fs from 'node:fs';\n"
                      f"fs.writeFileSync({json.dumps(str(pid_file))}, String(process.pid));\n"
                      "setInterval(() => {}, 1000);\n", encoding="utf-8")
    monkeypatch.setattr(bazi_bridge, "_NODE_BIN", shutil.which("node"))
    monkeypatch.setattr(bazi_bridge, "_BRIDGE_SCRIPT", script)
    monkeypatch.setattr(bazi_bridge, "_SCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(bazi_bridge, "_TIMEOUT_SEC", 1)
    start = time.monotonic()
    result = bazi_bridge.calculate_bazi(bazi_bridge.BaziInput(birth_date="1990-05-17", birth_time="12:30"))
    elapsed = time.monotonic() - start
    assert result.ok is False and result.error_code == "TIMEOUT"
    assert elapsed < 5
    pid = int(pid_file.read_text())  # Proves an actual Node process started.
    assert not Path(f"/proc/{pid}").exists()
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)  # subprocess.run already reaped its child.


if __name__ == "__main__":
    command, *arguments = sys.argv[1:]
    {"transaction": _transaction_child, "snapshot": _snapshot_child,
     "server": _server_child, "http": _http_child}[command](*arguments)
