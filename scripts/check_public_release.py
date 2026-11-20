#!/usr/bin/env python3
"""Check a standalone public snapshot, including ignored and untracked files.

Usage: python3 scripts/check_public_release.py --root /path/to/public-snapshot
       python3 scripts/check_public_release.py --staged [--root /path/to/repo]
       python3 scripts/check_public_release.py --pre-push [--root /path/to/repo]
       python3 scripts/check_public_release.py --history TIP_OID [--exclude BASE_OID]

No HEAD baseline or broad document/test exemption is used. Git is optional before
initialization; when present it must be an independent repository with at most
one root commit and no inherited refs, reflogs, alternates, or unreachable objects.
The --staged mode checks all stage-0 index files for later development commits;
it does not inspect ignored local files or verify past Git history.
The --pre-push mode reads Git's pre-push records from stdin and checks every
introduced commit, including files removed before the tip. --history accepts
only complete object IDs and provides the same history inspection for CI.
This is a release guard, not proof that arbitrary prose contains no private data.
Ignoring a path does not remove previously tracked files or historical objects.
Only rule names, relative paths, line numbers, and counts are printed.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from threading import Timer
from time import monotonic

from check_fortune_secrets import (
    GENERIC_ASSIGNMENT,
    SPECIFIC_RULES,
    assignment_value,
    normalize_value,
)


MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PUSH_INPUT_BYTES = 128 * 1024
MAX_PUSH_REFS = 256
MAX_HISTORY_COMMITS = 4096
MAX_HISTORY_ENTRIES = 2_000_000
MAX_HISTORY_BYTES = 512 * 1024 * 1024
MAX_HISTORY_SECONDS = 120
MAX_TREE_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_TAG_DEPTH = 16
ENV_TEMPLATE_SUFFIXES = (".env.example", ".env.sample", ".env.template")
PRIVATE_ROOTS = {
    "homes", "store", "var", "instance", "runs", "recovery", "upstream-rescue",
    ".codex", ".claude", ".paseo", ".codex-attachments", ".ssh", ".aws", ".gnupg",
}
RUNTIME_DIRS = {"sessions", "logs", "checkpoints", "pastes", "profile-backups", "instance", "var"}
BUILD_DIRS = {"node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
GENERATED_SECRET = re.compile(r"secrets\.token_(?:hex|urlsafe|bytes)\(\d+\)")
SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:token|password|passwd|secret|secret_key|api_key|access_key|private_key)$",
    re.IGNORECASE,
)
EXTRA_RULES = (
    ("google-api-key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), ("aiza",)),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), ("glpat-",)),
    ("credential-url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{8,}@", re.I), ("://",)),
)
CONTENT_RULES = SPECIFIC_RULES + EXTRA_RULES
GENERIC_TRIGGERS = ("token", "password", "passwd", "secret", "api_key", "access_key", "private_key")
PLACEHOLDERS = {
    "", "placeholder", "replace-me", "replace_me", "replaceme", "change-me",
    "change_me", "changeme", "redacted", "masked", "null", "none", "nil", "false",
}
SYNTHETIC_MARKER = "public-release: allow-synthetic"


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str


def forbidden_path(path: str, *, directory: bool = False) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name
    parts = pure.parts
    if parts[0] in PRIVATE_ROOTS:
        return "private-runtime-tree"
    if name == ".git":
        return "nested-git-metadata"
    if directory and (name in BUILD_DIRS or name.startswith(".venv")):
        return "generated-dependency-tree"
    if directory and name in RUNTIME_DIRS:
        return "runtime-state"
    if "cron" in parts and name in {"output", "jobs.json"}:
        return "cron-runtime"
    if name == "crontab" or name.endswith(".crontab"):
        return "cron-runtime"
    env_file = name == ".env" or name.endswith(".env") or ".env." in name
    if env_file and not name.endswith(ENV_TEMPLATE_SUFFIXES):
        return "environment-file"
    if any(name == base or (name.startswith(base + ".") and name != base + ".example")
           for base in {"auth.json", "credentials.json", "token.json", "tokens.json"}):
        return "auth-store"
    if re.search(r"\.(?:bak|backup|old|orig)(?:$|[._-])", name, re.I) or name.endswith("~"):
        return "backup-file"
    if re.search(r"\.(?:db|sqlite|sqlite3)(?:$|[.-])", name, re.I):
        return "runtime-database"
    if re.search(r"\.log(?:$|[._-])", name, re.I) or name.endswith((".jsonl", ".ndjson")):
        return "runtime-log"
    if name in {"id_rsa", "id_ed25519"} or pure.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return "private-key-file"
    if pure.suffix.lower() in {".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".zst"}:
        return "uninspected-archive"
    if pure.suffix.lower() in {".json", ".yaml", ".yml", ".toml"} and re.search(
        r"profiles?.*(?:backup|bak)", name, re.I,
    ):
        return "profile-backup"
    return None


def placeholder(value: str) -> bool:
    value = normalize_value(value)
    lowered = value.lower()
    return (
        lowered in PLACEHOLDERS
        or bool(value and set(value) <= {"*"})
        or bool(re.fullmatch(r"<[^<>\r\n]+>|\$\{[A-Za-z_][A-Za-z0-9_]*\}", value))
        or bool(re.fullmatch(r"(?:your|set|insert)[_-][A-Za-z_-]+", lowered))
    )


def allowed_synthetic(path: str, line: str, previous_line: str, value: str) -> bool:
    # An inline marker alone cannot whitelist a credential. Only these exact,
    # deterministic shapes in Python unit tests may use it.
    pure = PurePosixPath(path)
    if pure.parts[0] != "tests" or pure.suffix != ".py":
        return False
    if SYNTHETIC_MARKER not in line and SYNTHETIC_MARKER not in previous_line:
        return False
    return bool(re.fullmatch(r"123456789:([A-F])\1{34}", value))


def scan_content(path: str, data: bytes) -> list[Finding]:
    findings: set[Finding] = set()
    lines = data.decode("utf-8", "replace").splitlines()
    suffix = PurePosixPath(path).suffix
    source_file = suffix in SOURCE_SUFFIXES
    markdown = suffix in {".md", ".markdown"}
    fenced = False
    for number, line in enumerate(lines, 1):
        if markdown and line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        previous = lines[number - 2] if number > 1 else ""
        spans: list[tuple[int, int]] = []
        lowered = line.lower()
        for rule, pattern, triggers in CONTENT_RULES:
            if not any(trigger in lowered for trigger in triggers):
                continue
            for match in pattern.finditer(line):
                spans.append(match.span())
                if not allowed_synthetic(path, line, previous, match.group()):
                    findings.add(Finding(path, number, rule))
        generic_matches = GENERIC_ASSIGNMENT.finditer(line) if any(trigger in lowered for trigger in GENERIC_TRIGGERS) else ()
        for match in generic_matches:
            if not SENSITIVE_KEY.search(match.group("key")):
                continue
            raw, start, end = assignment_value(line, match.end())
            if any(start < stop and end > begin for begin, stop in spans):
                continue
            value = normalize_value(raw)
            if placeholder(value):
                continue
            quoted_literal = bool(re.match(r"(?i)(?:[rubf]{0,2})[\"'`]", raw))
            if (source_file or fenced or suffix == ".sh") and not quoted_literal and GENERATED_SECRET.fullmatch(value):
                continue
            if suffix == ".sh" and (raw.startswith(("$", "`", '"$'))):
                continue
            if source_file and not quoted_literal:
                # Variable references and calls are source expressions. Provider
                # shaped credentials above are always scanned, quoted or not.
                continue
            if value.startswith(("os.environ", "os.getenv", "process.env")):
                continue
            if allowed_synthetic(path, line, previous, value):
                continue
            findings.add(Finding(path, number, "credential-assignment"))
    if PurePosixPath(path).suffix == ".py":
        try:
            tree = ast.parse(data.decode("utf-8", "replace"))
        except (SyntaxError, ValueError):
            tree = None  # Provider shapes and ordinary assignments still scan.
        if tree is not None:
            for node in ast.walk(tree):
                targets = node.targets if isinstance(node, ast.Assign) else (
                    [node.target] if isinstance(node, ast.AnnAssign) else []
                )
                for target in targets:
                    key = target.id if isinstance(target, ast.Name) else (
                        target.attr if isinstance(target, ast.Attribute) else ""
                    )
                    if not SENSITIVE_KEY.search(key):
                        continue
                    value_node = node.value
                    if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, (str, bytes)):
                        continue
                    value = value_node.value
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", "replace")
                    if placeholder(value):
                        continue
                    number = value_node.lineno
                    if not allowed_synthetic(path, lines[number - 1], lines[number - 2] if number > 1 else "", value):
                        findings.add(Finding(path, number, "credential-assignment"))
    return sorted(findings)


def git(
    root: Path, *args: str, allow_failure: bool = False,
    index_file: str | None = None, data: bytes | None = None,
    max_output: int | None = None,
) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
    )
    if index_file is not None:
        env["GIT_INDEX_FILE"] = index_file
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args]
    if max_output is not None:
        if data is not None:
            raise ValueError("bounded Git output does not accept stdin")
        # Bound tree output before buffering it in memory. The timer also
        # prevents a blocked read from hanging a developer's push indefinitely.
        with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            timer = Timer(30, process.kill)
            timer.daemon = True
            timer.start()
            try:
                assert process.stdout is not None
                output = process.stdout.read(max_output + 1)
                if len(output) > max_output:
                    process.kill()
                    raise RuntimeError("Git inspection output limit exceeded")
                if process.wait() and not allow_failure:
                    raise RuntimeError("Git metadata could not be checked")
                return output
            finally:
                timer.cancel()
    result = subprocess.run(
        command,
        input=data, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=30,
    )
    if result.returncode and not allow_failure:
        raise RuntimeError("Git metadata could not be checked")
    return result.stdout


def check_git(root: Path) -> list[Finding]:
    metadata = root / ".git"
    if not metadata.exists() and not metadata.is_symlink():
        return []
    def blocked(rule: str) -> list[Finding]:
        return [Finding(".git", 0, rule)]
    if metadata.is_symlink() or not metadata.is_dir():
        return blocked("git-linked-or-external-metadata")
    for current, directories, files in os.walk(metadata, followlinks=False):
        if any((Path(current) / name).is_symlink() for name in directories + files):
            return blocked("git-linked-or-external-metadata")
        if "objects" in Path(current).relative_to(metadata).parts and any(
            (Path(current) / name).stat().st_nlink > 1 for name in files
        ):
            return blocked("git-shared-object-storage")
    if any((metadata / path).exists() for path in (
        "commondir", "shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates",
    )):
        return blocked("git-shared-or-incomplete-history")
    try:
        top = os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()
        common = os.fsdecode(git(root, "rev-parse", "--git-common-dir")).strip()
        common_path = Path(common) if Path(common).is_absolute() else root / common
        if Path(top).resolve() != root or common_path.resolve() != metadata.resolve():
            return blocked("git-linked-or-external-metadata")
        if git(root, "rev-parse", "--is-shallow-repository").strip() != b"false":
            return blocked("git-shared-or-incomplete-history")
        if git(root, "config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$", allow_failure=True):
            return blocked("git-shared-or-incomplete-history")
        refs = git(root, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
        symbolic = git(root, "symbolic-ref", "-q", "HEAD", allow_failure=True).strip()
        if not symbolic.startswith(b"refs/heads/") or len(refs) > 1:
            return blocked("git-inherited-refs")
        commits = git(root, "rev-list", "--all", "--parents").splitlines()
        if refs and refs[0].split()[0] != symbolic:
            return blocked("git-inherited-refs")
        if len(commits) > 1 or any(len(commit.split()) != 1 for commit in commits):
            return blocked("git-inherited-history")
        head = commits[0].split()[0] if commits else b""
        if refs and (not head or refs[0].split()[1] != head):
            return blocked("git-inherited-refs")
        reflog = set(git(root, "reflog", "show", "--all", "--format=%H").splitlines())
        if reflog - {head}:
            return blocked("git-inherited-reflog")
        index_entries = git(root, "ls-files", "-v", "-z").split(b"\0")
        if any(entry and not entry.startswith(b"H ") for entry in index_entries):
            return blocked("git-hidden-index-entries")
        staged_entries = git(root, "ls-files", "-s", "-z").split(b"\0")
        if any(entry and entry.split(b" ", 1)[0] not in {b"100644", b"100755"} for entry in staged_entries):
            return blocked("git-non-file-index-entries")
        if git(root, "diff-files", "--name-only", "--no-ext-diff", "--"):
            return blocked("git-worktree-index-mismatch")
        if head and git(root, "diff-index", "--cached", "--name-only", "--no-ext-diff", "HEAD", "--"):
            return blocked("git-head-index-mismatch")
        # Includes index objects as roots, so a staged first commit is permitted.
        fsck = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), "fsck", "--full", "--no-reflogs", "--unreachable"],
            env={**{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
                 "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if fsck.returncode or fsck.stdout.strip():
            return blocked("git-inherited-or-invalid-objects")
    except (OSError, RuntimeError, ValueError, IndexError):
        return blocked("git-inspection-failed")
    return []


def scan(root: Path) -> tuple[list[Finding], int]:
    findings = check_git(root)
    scanned = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            findings.append(Finding(directory.relative_to(root).as_posix(), 0, "unreadable-path"))
            continue
        for entry in entries:
            relative = entry.relative_to(root).as_posix()
            if relative == ".git":
                continue
            try:
                mode = entry.lstat().st_mode
                if stat.S_ISLNK(mode):
                    findings.append(Finding(relative, 0, "symlink-not-allowed"))
                    continue
                directory_entry = stat.S_ISDIR(mode)
                rule = forbidden_path(relative, directory=directory_entry)
                if rule:
                    findings.append(Finding(relative, 0, rule))
                    continue
                if directory_entry:
                    pending.append(entry)
                    continue
                if not stat.S_ISREG(mode):
                    findings.append(Finding(relative, 0, "special-file-not-allowed"))
                    continue
                with entry.open("rb") as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    findings.append(Finding(relative, 0, "file-too-large-to-inspect"))
                    continue
                scanned += 1
                findings.extend(scan_content(relative, data))
            except OSError:
                findings.append(Finding(relative, 0, "unreadable-path"))
    return sorted(set(findings)), scanned


def scan_index(root: Path) -> tuple[list[Finding], int]:
    """Inspect stage-0 blobs, with no baseline or fresh-history requirement."""
    # Git may give a pre-commit hook a temporary index for a partial commit.
    # Respect that index only in this mode, while still ignoring Git-dir and
    # object-store environment overrides.
    requested_index = os.environ.get("GIT_INDEX_FILE")
    index_file = str(Path(requested_index).resolve()) if requested_index else None
    top = os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()
    if Path(top).resolve() != root:
        return [Finding(".git", 0, "git-index-root-mismatch")], 0
    findings = []
    scanned = 0
    for record in git(root, "ls-files", "-s", "-z", index_file=index_file).split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, _oid, stage = header.split()
        path = os.fsdecode(raw_path)
        if stage != b"0":
            findings.append(Finding(path, 0, "git-unmerged-index-entry"))
            continue
        if mode not in {b"100644", b"100755"}:
            findings.append(Finding(path, 0, "git-non-file-index-entry"))
            continue
        parts = PurePosixPath(path).parts
        rule = next((
            result for count in range(1, len(parts))
            if (result := forbidden_path(PurePosixPath(*parts[:count]).as_posix(), directory=True))
        ), None) or forbidden_path(path)
        if rule:
            findings.append(Finding(path, 0, rule))
            continue
        data = git(root, "show", "--no-ext-diff", "--no-textconv", ":0:" + path, index_file=index_file)
        if len(data) > MAX_FILE_BYTES:
            findings.append(Finding(path, 0, "file-too-large-to-inspect"))
            continue
        scanned += 1
        findings.extend(scan_content(path, data))
    return sorted(set(findings)), scanned


def history_repository(root: Path) -> int:
    """Require complete local objects without snapshot-only history limits."""
    metadata = root / ".git"
    if metadata.is_symlink() or not metadata.is_dir():
        raise RuntimeError("history inspection requires independent Git metadata")
    for relative in ("shallow", "commondir", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        path = metadata / relative
        if path.exists() or path.is_symlink():
            raise RuntimeError("shared or incomplete Git history")
    objects = metadata / "objects"
    if objects.is_symlink() or not objects.is_dir():
        raise RuntimeError("external or missing object storage")
    for current, directories, files in os.walk(objects, followlinks=False):
        if Path(current).is_symlink() or any((Path(current) / name).is_symlink() for name in directories + files):
            raise RuntimeError("external object storage")
    top = os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()
    common = os.fsdecode(git(root, "rev-parse", "--git-common-dir")).strip()
    common_path = Path(common) if Path(common).is_absolute() else root / common
    if Path(top).resolve() != root or common_path.resolve() != metadata.resolve():
        raise RuntimeError("history root mismatch")
    if git(root, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise RuntimeError("incomplete Git history")
    if git(root, "config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$", allow_failure=True):
        raise RuntimeError("partial Git history")
    object_format = git(root, "rev-parse", "--show-object-format").strip()
    if object_format not in {b"sha1", b"sha256"}:
        raise RuntimeError("unsupported object format")
    return 40 if object_format == b"sha1" else 64


def object_id(value: str, length: int, *, allow_zero: bool = False) -> str:
    if not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value):
        raise ValueError("complete object ID required")
    if not allow_zero and value == "0" * length:
        raise ValueError("zero object ID is not a target")
    return value


@dataclass(frozen=True)
class PushUpdate:
    local_ref: str
    local_oid: str
    remote_ref: str
    remote_oid: str


def push_updates(root: Path, data: bytes, oid_length: int) -> list[PushUpdate]:
    """Parse the pre-push protocol; refs are labels, never revision expressions."""
    if len(data) > MAX_PUSH_INPUT_BYTES or b"\r" in data or b"\0" in data:
        raise ValueError("invalid pre-push input")
    records = data.splitlines()
    if len(records) > MAX_PUSH_REFS:
        raise ValueError("too many push refs")
    updates = []
    seen = set()
    zero = "0" * oid_length
    for record in records:
        fields = record.split(b" ")
        if len(fields) != 4 or any(not field for field in fields):
            raise ValueError("invalid pre-push record")
        local_ref, local_oid, remote_ref, remote_oid = map(os.fsdecode, fields)
        object_id(local_oid, oid_length, allow_zero=True)
        object_id(remote_oid, oid_length, allow_zero=True)
        if remote_ref in seen or not remote_ref.startswith(("refs/heads/", "refs/tags/")):
            raise ValueError("duplicate or unsupported push ref")
        git(root, "check-ref-format", remote_ref)
        seen.add(remote_ref)
        if local_oid == zero:
            if local_ref != "(delete)" or remote_oid == zero:
                raise ValueError("invalid delete record")
        elif local_ref.startswith(("refs/heads/", "refs/tags/")):
            git(root, "check-ref-format", local_ref)
        elif local_ref != "HEAD":
            object_id(local_ref, oid_length)
        updates.append(PushUpdate(local_ref, local_oid, remote_ref, remote_oid))
    return updates


class HistoryScan:
    def __init__(self, root: Path, oid_length: int):
        self.root = root
        self.oid_length = oid_length
        self.findings: set[Finding] = set()
        self.inspected: set[tuple[str, str]] = set()
        self.object_info: dict[str, tuple[str, int]] = {}
        self.total_bytes = 0
        self.entries = 0
        self.scanned = 0
        self.started = monotonic()

    def check_time(self) -> None:
        if monotonic() - self.started > MAX_HISTORY_SECONDS:
            raise RuntimeError("history inspection time limit exceeded")

    def info(self, oid: str) -> tuple[str, int]:
        self.check_time()
        if oid not in self.object_info:
            record = git(self.root, "cat-file", "--batch-check", data=(oid + "\n").encode("ascii")).split()
            if len(record) != 3 or record[0].decode("ascii") != oid:
                raise RuntimeError("missing or invalid history object")
            kind, size = record[1].decode("ascii"), int(record[2])
            if size < 0 or kind not in {"blob", "tree", "commit", "tag"}:
                raise RuntimeError("invalid history object")
            self.object_info[oid] = kind, size
        return self.object_info[oid]

    def read(self, oid: str, kind: str, path: str) -> bytes | None:
        actual_kind, size = self.info(oid)
        if actual_kind != kind:
            raise RuntimeError("history object type mismatch")
        if size > MAX_FILE_BYTES:
            self.findings.add(Finding(path, 0, "file-too-large-to-inspect"))
            return None
        self.total_bytes += size
        if self.total_bytes > MAX_HISTORY_BYTES:
            raise RuntimeError("history byte limit exceeded")
        data = git(self.root, "cat-file", kind, oid)
        if len(data) != size:
            raise RuntimeError("history object size mismatch")
        return data

    def metadata(self, kind: str, data: bytes) -> None:
        header, _separator, message = data.partition(b"\n\n")
        self.findings.update(scan_content(f".git/{kind}-metadata", header))
        self.findings.update(scan_content(f".git/{kind}-message", message))

    def peel(self, oid: str, *, tags: bool, inspect_tags: bool) -> str:
        for _ in range(MAX_TAG_DEPTH + 1):
            kind, _size = self.info(oid)
            if kind == "commit":
                return oid
            if kind != "tag" or not tags:
                raise RuntimeError("only commit targets and commit tags are supported")
            # Even an existing tag needs its target read locally. Tag messages
            # are inspected only for outgoing targets, not baseline exclusions.
            data = self.read(oid, "tag", ".git/tag-message")
            if data is None:
                raise RuntimeError("tag too large to inspect")
            if inspect_tags and (".git/tag-message", oid) not in self.inspected:
                self.inspected.add((".git/tag-message", oid))
                self.metadata("tag", data)
            header = data.partition(b"\n\n")[0].splitlines()
            if len(header) < 3 or not header[0].startswith(b"object ") or not header[1].startswith(b"type ") or not header[2].startswith(b"tag "):
                raise RuntimeError("malformed tag target")
            oid = object_id(header[0][7:].decode("ascii"), self.oid_length)
            if header[1][5:].decode("ascii") != self.info(oid)[0] or not header[2][4:]:
                raise RuntimeError("tag target type mismatch")
        raise RuntimeError("tag nesting limit exceeded")

    def commits(self, tips: list[str], excludes: list[str]) -> None:
        if not tips:
            return
        # Inputs have already been resolved as exact, typed IDs. A separate
        # --not section ensures none can become a Git option or revision range.
        records = git(
            self.root, "rev-list", f"--max-count={MAX_HISTORY_COMMITS + 1}",
            *sorted(set(tips)), "--not", *sorted(set(excludes)), "--",
            max_output=(MAX_HISTORY_COMMITS + 1) * (self.oid_length + 1),
        ).splitlines()
        if len(records) > MAX_HISTORY_COMMITS:
            raise RuntimeError("history commit limit exceeded")
        for record in records:
            oid = object_id(record.decode("ascii"), self.oid_length)
            data = self.read(oid, "commit", ".git/commit-message")
            if data is not None:
                self.metadata("commit", data)
            tree = git(
                self.root, "ls-tree", "-r", "-t", "-z", "--full-tree", oid,
                max_output=MAX_TREE_OUTPUT_BYTES,
            )
            for entry in tree.split(b"\0"):
                if not entry:
                    continue
                self.check_time()
                self.entries += 1
                if self.entries > MAX_HISTORY_ENTRIES:
                    raise RuntimeError("history tree entry limit exceeded")
                header, raw_path = entry.split(b"\t", 1)
                mode, kind, raw_oid = header.split()
                path = os.fsdecode(raw_path)
                blob_oid = object_id(raw_oid.decode("ascii"), self.oid_length)
                directory = mode == b"040000" and kind == b"tree"
                # Modes must be checked before content deduplication: an older
                # symlink can reuse a newer regular file's exact blob and path.
                if not directory and (mode not in {b"100644", b"100755"} or kind != b"blob"):
                    self.findings.add(Finding(path, 0, "git-non-file-history-entry"))
                    continue
                pure = PurePosixPath(path)
                if pure.is_absolute() or pure.as_posix() != path or ".." in pure.parts:
                    raise RuntimeError("invalid history path")
                parts = pure.parts
                rule = next((
                    result for count in range(1, len(parts))
                    if (result := forbidden_path(PurePosixPath(*parts[:count]).as_posix(), directory=True))
                ), None) or forbidden_path(path, directory=directory)
                if rule:
                    self.findings.add(Finding(path, 0, rule))
                    continue
                if directory:
                    continue
                identity = path, blob_oid
                if identity in self.inspected:
                    continue
                self.inspected.add(identity)
                blob = self.read(blob_oid, "blob", path)
                if blob is not None:
                    self.scanned += 1
                    self.findings.update(scan_content(path, blob))


def scan_history(
    root: Path, tip: str, excludes: list[str],
) -> tuple[list[Finding], int]:
    oid_length = history_repository(root)
    if len(excludes) > MAX_PUSH_REFS:
        raise ValueError("too many history exclusions")
    inspector = HistoryScan(root, oid_length)
    target = inspector.peel(object_id(tip, oid_length), tags=True, inspect_tags=True)
    bases = [inspector.peel(object_id(oid, oid_length), tags=True, inspect_tags=False) for oid in excludes]
    inspector.commits([target], bases)
    return sorted(inspector.findings), inspector.scanned


def scan_push(root: Path, data: bytes) -> tuple[list[Finding], int]:
    oid_length = history_repository(root)
    updates = push_updates(root, data, oid_length)
    inspector = HistoryScan(root, oid_length)
    tips, bases = [], []
    zero = "0" * oid_length
    for update in updates:
        if update.local_oid == zero:
            # Deleting a remote ref publishes no local objects. In particular,
            # an unfetched remote ref can safely be deleted without networking.
            continue
        tags = update.remote_ref.startswith("refs/tags/")
        tips.append(inspector.peel(update.local_oid, tags=tags, inspect_tags=True))
        if update.remote_oid != zero:
            bases.append(inspector.peel(update.remote_oid, tags=tags, inspect_tags=False))
    inspector.commits(tips, bases)
    return sorted(inspector.findings), inspector.scanned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="snapshot directory, or repository root with --staged")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--staged", action="store_true",
        help="check index files for normal commits; does not verify past history or ignored local files",
    )
    mode.add_argument("--pre-push", action="store_true", help="inspect introduced history using Git pre-push records from stdin")
    mode.add_argument("--history", metavar="TIP_OID", help="inspect complete reachable history of an exact commit/tag object ID")
    parser.add_argument("--exclude", metavar="BASE_OID", action="append", default=[], help="exclude history already reachable from this exact object ID; requires --history")
    args = parser.parse_args()
    if args.exclude and not args.history:
        parser.error("--exclude requires --history")
    try:
        root = args.root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("not a directory")
        if args.pre_push:
            findings, scanned = scan_push(root, sys.stdin.buffer.read(MAX_PUSH_INPUT_BYTES + 1))
        elif args.history:
            findings, scanned = scan_history(root, args.history, args.exclude)
        else:
            findings, scanned = scan_index(root) if args.staged else scan(root)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        print("ERROR public-release-inspection-failed", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"BLOCK rule={finding.rule} path={json.dumps(finding.path, ensure_ascii=True)} line={finding.line}")
    print(f"SUMMARY scanned_files={scanned} blocking={len(findings)}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
