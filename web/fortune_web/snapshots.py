"""Offline operator snapshots; restoring aggregates never revives browser access."""
from contextlib import closing, contextmanager
from datetime import date
import math
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time

from .metrics import CLIENT_EVENTS
from .storage import WebStore


COLUMNS = {
    "web_sessions": (("id", "TEXT", 0, None, 1), ("expires", "INTEGER", 1, None, 0), ("profile", "TEXT", 0, None, 0)),
    "metric_receipts": (("session_id", "TEXT", 1, None, 1), ("day", "TEXT", 1, None, 2),
                        ("event", "TEXT", 1, None, 3), ("view", "TEXT", 1, None, 4)),
    "metric_counts": (("day", "TEXT", 1, None, 1), ("event", "TEXT", 1, None, 2),
                      ("view", "TEXT", 1, None, 3), ("count", "INTEGER", 1, None, 0)),
}
EVENTS = {**CLIENT_EVENTS, "visit": {"entry"}, "profile_saved": {"entry"}}
SOURCE_ROOT = Path(__file__).resolve().parents[2]


class PublicationUncertainError(RuntimeError):
    """The new destination could not be safely removed after publication failed."""


def _path(value):
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("Parent traversal is not supported")
    path = path.absolute()
    if path.is_relative_to(SOURCE_ROOT) or ".git" in path.parts:
        raise ValueError("Database files must stay outside this source checkout")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Symbolic links are not supported")
    return path


def _deadline(timeout):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise ValueError("Timeout must be between zero and sixty seconds")
    end = time.monotonic() + timeout

    def check(*_):
        if time.monotonic() >= end:
            raise TimeoutError("Snapshot operation exceeded its time budget")

    return check, end


@contextmanager
def _source(path, end):
    path = _path(path)
    _private_directory(path.parent)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Source must be an owner-only regular file")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1)
    try:
        db.execute("PRAGMA query_only = ON")
        db.execute("PRAGMA trusted_schema = OFF")
        db.set_progress_handler(lambda: int(time.monotonic() >= end), 1000)
        yield db
    finally:
        db.close()


def _validate(db):
    objects = dict(db.execute("SELECT name, type FROM sqlite_master WHERE type != 'index'"))
    if objects != {name: "table" for name in COLUMNS}:
        raise ValueError("Unsupported database schema")
    for table, expected in COLUMNS.items():
        # Table names are constants, never database-provided SQL.
        if tuple(tuple(row)[1:] for row in db.execute(f"PRAGMA table_info({table})")) != expected:
            raise ValueError("Unsupported database columns")
        expected_keys = [(0, 0, "web_sessions", "session_id", "id", "NO ACTION", "CASCADE", "NONE")] if table == "metric_receipts" else []
        if [tuple(row) for row in db.execute(f"PRAGMA foreign_key_list({table})")] != expected_keys:
            raise ValueError("Unsupported database foreign keys")
    if tuple(db.execute("PRAGMA integrity_check(1)").fetchone()) != ("ok",):
        raise ValueError("Database integrity check failed")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Database foreign keys are inconsistent")


def _private_directory(path):
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Directory must exist and be owner-only")


def _unused_destination(destination):
    # A stale WAL/journal beside an absent main DB is not a fresh database path.
    if any(os.path.lexists(str(destination) + suffix) for suffix in ("", "-wal", "-shm", "-journal")):
        raise FileExistsError("Destination already exists")


@contextmanager
def _destination(value):
    destination = _path(value)
    parent = destination.parent
    _private_directory(parent)
    _unused_destination(destination)
    linked = False
    try:
        with tempfile.TemporaryDirectory(prefix=".fortune-snapshot-", dir=parent) as temporary:
            stage = Path(temporary) / "data.sqlite3"
            fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            yield stage
            # Publish only a completed file, atomically and without replacing any path.
            with stage.open("rb") as stream:
                os.fsync(stream.fileno())
            _unused_destination(destination)
            os.link(stage, destination, follow_symlinks=False)
            linked = True
            try:
                directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                try:
                    published = destination.stat(follow_symlinks=False)
                    staged = stage.stat()
                    if (published.st_dev, published.st_ino) != (staged.st_dev, staged.st_ino):
                        raise PublicationUncertainError("Published file was replaced")
                    destination.unlink()
                    linked = False
                except OSError:
                    raise PublicationUncertainError("Publication rollback failed") from None
                raise
    except OSError:
        if linked:
            # Even a staging-directory cleanup failure must not imply no output
            # exists. A private completed destination may already be durable.
            raise PublicationUncertainError("Output published but final cleanup failed") from None
        raise


def backup(source, destination, *, timeout=10):
    """Create a full private snapshot using SQLite's consistent online backup API."""
    check, end = _deadline(timeout)
    with _source(source, end) as src, _destination(destination) as stage:
        with closing(sqlite3.connect(stage)) as dst:
            src.backup(dst, pages=128, progress=check, sleep=0.02)
            dst.set_progress_handler(lambda: int(time.monotonic() >= end), 1000)
            _validate(dst)
            # A backup of a WAL database must be standalone before publication.
            dst.execute("PRAGMA journal_mode = DELETE")
            check()
    return {"ok": True, "operation": "backup", "contains_private_session_data": True}


def restore_aggregates(source, destination, *, timeout=10):
    """Create a new store with daily counts only; all users must register again.

    A full historical profile restore cannot honor subsequent deletions without
    a separate deletion ledger. Never copy old sessions, profiles, or receipts.
    """
    check, end = _deadline(timeout)
    count = 0
    with _source(source, end) as src, _destination(destination) as stage:
        src.execute("BEGIN")
        _validate(src)
        store = WebStore(stage)
        with store.connect() as dst:
            dst.set_progress_handler(lambda: int(time.monotonic() >= end), 1000)
            for day, event, view, total in src.execute("SELECT day, event, view, count FROM metric_counts"):
                check()
                if (not isinstance(day, str) or date.fromisoformat(day).isoformat() != day
                        or not isinstance(event, str) or not isinstance(view, str)
                        or view not in EVENTS.get(event, set()) or type(total) is not int or total < 0):
                    raise ValueError("Unsupported daily aggregate")
                dst.execute("INSERT INTO metric_counts VALUES (?, ?, ?, ?)", (day, event, view, total))
                count += 1
            _validate(dst)
            check()
    return {"ok": True, "operation": "restore-aggregates", "aggregate_rows": count,
            "sessions_restored": 0, "profiles_restored": 0, "receipts_restored": 0}
