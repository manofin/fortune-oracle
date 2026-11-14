#!/usr/bin/env python3
"""Check a standalone public snapshot, including ignored and untracked files.

Usage: python3 scripts/check_public_release.py --root /path/to/public-snapshot
       python3 scripts/check_public_release.py --staged [--root /path/to/repo]

No HEAD baseline or broad document/test exemption is used. Git is optional before
initialization; when present it must be an independent repository with at most
one root commit and no inherited refs, reflogs, alternates, or unreachable objects.
The --staged mode checks all stage-0 index files for later development commits;
it does not inspect ignored local files or verify past Git history.
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

from check_fortune_secrets import (
    GENERIC_ASSIGNMENT,
    SPECIFIC_RULES,
    assignment_value,
    normalize_value,
)


MAX_FILE_BYTES = 32 * 1024 * 1024
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


def git(root: Path, *args: str, allow_failure: bool = False, index_file: str | None = None) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    if index_file is not None:
        env["GIT_INDEX_FILE"] = index_file
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="snapshot directory, or repository root with --staged")
    parser.add_argument(
        "--staged", action="store_true",
        help="check index files for normal commits; does not verify past history or ignored local files",
    )
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("not a directory")
        findings, scanned = scan_index(root) if args.staged else scan(root)
    except (OSError, RuntimeError, ValueError):
        print("ERROR public-release-inspection-failed", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"BLOCK rule={finding.rule} path={json.dumps(finding.path, ensure_ascii=True)} line={finding.line}")
    print(f"SUMMARY scanned_files={scanned} blocking={len(findings)}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
