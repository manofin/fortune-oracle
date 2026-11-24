"""Synthetic recovery regressions; never use operator stores or credentials."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web.app import create_app
from fortune_web import snapshots
from fortune_web.snapshots import backup, restore_aggregates
from fortune_web.storage import WebStore


@pytest.fixture
def state(tmp_path):
    store = WebStore(tmp_path / "live.sqlite3")
    token = store.create(600)
    profile = {"display_name": "synthetic_snapshot_person", "birth_date": "1990-04-16"}
    store.save(token, profile)
    store.record_event(token, "2026-01-02", "visit", "entry")
    return store, token, profile


def read(path, sql):
    with sqlite3.connect(path) as db:
        return db.execute(sql).fetchall()


def test_full_backup_is_consistent_private_and_does_not_modify_source(state, tmp_path):
    store, token, profile = state
    before = store.path.read_bytes()
    snapshot = tmp_path / "snapshot.sqlite3"
    assert backup(store.path, snapshot)["contains_private_session_data"] is True
    assert store.path.read_bytes() == before
    assert WebStore(snapshot).find(token)["profile"] == profile
    assert read(snapshot, "PRAGMA integrity_check") == [("ok",)]
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".fortune-snapshot-*"))


def test_wal_commits_are_included_in_standalone_snapshot(state, tmp_path):
    store, token, _ = state
    with sqlite3.connect(store.path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE web_sessions SET profile=?", (json.dumps({"display_name": "WAL synthetic person"}),))
        writer.commit()
        assert Path(str(store.path) + "-wal").stat().st_size > 0
        snapshot = tmp_path / "standalone.sqlite3"
        backup(store.path, snapshot)
        assert read(snapshot, "PRAGMA journal_mode") == [("delete",)]
        assert WebStore(snapshot).find(token)["profile"]["display_name"] == "WAL synthetic person"
        assert not Path(str(snapshot) + "-wal").exists()


def test_aggregate_recovery_does_not_revive_deleted_cookie_even_with_new_secret(state, tmp_path):
    store, token, profile = state
    snapshot, restored = tmp_path / "old.sqlite3", tmp_path / "recovered.sqlite3"
    backup(store.path, snapshot)
    store.delete(token)
    result = restore_aggregates(snapshot, restored)
    assert result == {"ok": True, "operation": "restore-aggregates", "aggregate_rows": 1,
                      "sessions_restored": 0, "profiles_restored": 0, "receipts_restored": 0}
    assert read(restored, "SELECT * FROM web_sessions") == []
    assert read(restored, "SELECT * FROM metric_receipts") == []
    assert read(restored, "SELECT * FROM metric_counts") == [("2026-01-02", "visit", "entry", 1)]
    # Personal strings are never copied into restored pages/freelists.
    assert profile["display_name"].encode() not in restored.read_bytes()
    app = create_app({"TESTING": True, "SECRET_KEY": "placeholder" * 4,
                      "WEB_STORE": str(restored), "COOKIE_SECURE": False, "START_CLEANUP": False})
    client = app.test_client()
    client.set_cookie("fortune_session", token)
    response = client.get("/api/session")
    assert response.status_code == 200 and response.json["profile"] is None
    assert profile["display_name"] not in response.get_data(as_text=True)
    assert client.get_cookie("fortune_session").value != token
    assert WebStore(snapshot).find(token)["profile"] == profile


@pytest.mark.parametrize("operation", [backup, restore_aggregates])
def test_existing_target_and_source_cannot_be_overwritten(operation, state, tmp_path):
    store, _, _ = state
    before = store.path.read_bytes()
    with pytest.raises(FileExistsError):
        operation(store.path, store.path)
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"synthetic existing file")
    with pytest.raises(FileExistsError):
        operation(store.path, destination)
    assert store.path.read_bytes() == before
    assert destination.read_bytes() == b"synthetic existing file"


@pytest.mark.parametrize("kind", ["source-link", "target-link", "parent-link", "public-source", "public-source-parent", "public-parent", "git-source", "git-target"])
def test_unsafe_locations_are_rejected_before_publication(kind, state, tmp_path, monkeypatch):
    store, _, _ = state
    source, destination = store.path, tmp_path / "output.sqlite3"
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    if kind == "source-link":
        source = tmp_path / "link.sqlite3"
        source.symlink_to(store.path)
    elif kind == "target-link":
        destination.symlink_to(tmp_path / "absent.sqlite3")
    elif kind == "parent-link":
        link = tmp_path / "link"
        link.symlink_to(private, target_is_directory=True)
        destination = link / "new.sqlite3"
    elif kind == "public-source":
        store.path.chmod(0o644)
    elif kind == "public-source-parent":
        tmp_path.chmod(0o777)
    elif kind == "public-parent":
        private.chmod(0o755)
        destination = private / "new.sqlite3"
    elif kind == "git-source":
        monkeypatch.setattr(snapshots, "SOURCE_ROOT", tmp_path)
    else:
        monkeypatch.setattr(snapshots, "SOURCE_ROOT", private)
        destination = private / "new.sqlite3"
    with pytest.raises(ValueError):
        backup(source, destination)
    assert not list(tmp_path.glob(".fortune-snapshot-*"))


@pytest.mark.parametrize("mutation", ["corrupt", "foreign-key", "extra-table", "trigger", "columns"])
def test_invalid_snapshot_never_leaves_partial_destination(mutation, state, tmp_path):
    store, _, _ = state
    if mutation == "corrupt":
        store.path.write_bytes(b"not a database")
    else:
        with sqlite3.connect(store.path) as db:
            if mutation == "foreign-key":
                db.execute("DELETE FROM web_sessions")
            elif mutation == "extra-table":
                db.execute("CREATE TABLE surprise(value)")
            elif mutation == "trigger":
                db.execute("CREATE TRIGGER surprise AFTER DELETE ON metric_counts BEGIN SELECT 1; END")
            else:
                db.execute("ALTER TABLE metric_counts ADD COLUMN surprise TEXT")
    for operation in (backup, restore_aggregates):
        destination = tmp_path / (operation.__name__ + ".sqlite3")
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            operation(store.path, destination)
        assert not destination.exists()
        assert not list(tmp_path.glob(".fortune-snapshot-*"))


@pytest.mark.parametrize("row", [("private arbitrary text", "visit", "entry", 1), ("2026-01-02", "arbitrary", "entry", 1),
                                  ("2026-01-02", "visit", "arbitrary", 1), ("2026-01-02", "visit", "entry", -1)])
def test_restore_accepts_only_fixed_anonymous_aggregate_labels(row, state, tmp_path):
    store, _, _ = state
    with store.connect() as db:
        db.execute("DELETE FROM metric_counts")
        db.execute("INSERT INTO metric_counts VALUES (?, ?, ?, ?)", row)
    destination = tmp_path / "restored.sqlite3"
    with pytest.raises(ValueError):
        restore_aggregates(store.path, destination)
    assert not destination.exists()


def test_busy_source_has_bounded_backup_and_no_published_partial_file(state, tmp_path):
    store, _, _ = state
    destination = tmp_path / "timeout.sqlite3"
    with sqlite3.connect(store.path) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            backup(store.path, destination, timeout=0.15)
        assert time.monotonic() - start < 1.5
    assert not destination.exists()
    assert not list(tmp_path.glob(".fortune-snapshot-*"))


def test_cli_errors_never_echo_private_path_or_sqlite_detail(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/fortune_web_snapshot.py"
    marker = "synthetic_private_filename"
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run([sys.executable, str(path), "backup", "--source", str(tmp_path / marker),
                             "--destination", str(tmp_path / "new.sqlite3")], capture_output=True, text=True, env=environment)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"] == "snapshot_failed"
    assert marker not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("operation", [backup, restore_aggregates])
def test_absent_destination_with_old_sidecars_is_not_a_fresh_target(operation, suffix, state, tmp_path):
    store, _, _ = state
    destination = tmp_path / "new.sqlite3"
    sidecar = Path(str(destination) + suffix)
    sidecar.write_bytes(b"synthetic stale bookkeeping")
    with pytest.raises(FileExistsError):
        operation(store.path, destination)
    assert not destination.exists()
    assert sidecar.read_bytes() == b"synthetic stale bookkeeping"


def test_weakened_schema_with_same_column_names_is_rejected(state, tmp_path):
    store, _, _ = state
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE metric_receipts")
        db.execute("CREATE TABLE metric_receipts(session_id TEXT, day TEXT, event TEXT, view TEXT)")
    for operation in (backup, restore_aggregates):
        destination = tmp_path / (operation.__name__ + ".sqlite3")
        with pytest.raises(ValueError, match="Unsupported database"):
            operation(store.path, destination)
        assert not destination.exists()


@pytest.mark.parametrize("operation", [backup, restore_aggregates])
def test_directory_fsync_failure_rolls_back_our_new_destination(operation, state, tmp_path, monkeypatch):
    store, _, _ = state
    destination = tmp_path / "failed.sqlite3"
    calls = []
    original = os.fsync
    def failing_directory_fsync(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError("synthetic directory sync failure")
        return original(fd)
    monkeypatch.setattr(snapshots.os, "fsync", failing_directory_fsync)
    with pytest.raises(OSError, match="synthetic directory sync failure"):
        operation(store.path, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".fortune-snapshot-*"))


def test_cleanup_failure_after_publication_is_reported_as_uncertain(state, tmp_path, monkeypatch):
    store, _, _ = state
    destination = tmp_path / "published.sqlite3"
    original = os.rmdir
    def fail_staging_cleanup(path, *args, **kwargs):
        if ".fortune-snapshot-" in str(path):
            raise OSError("synthetic cleanup failure")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(snapshots.os, "rmdir", fail_staging_cleanup)
        with pytest.raises(snapshots.PublicationUncertainError):
            backup(store.path, destination)
    assert read(destination, "PRAGMA integrity_check") == [("ok",)]
    assert destination.stat().st_mode & 0o777 == 0o600
