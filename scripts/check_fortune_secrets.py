#!/usr/bin/env python3
"""Report forbidden paths and credential shapes in staged Git blobs without values."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import PurePosixPath
import re
import subprocess
import sys


@dataclass(frozen=True)
class Blob:
    path: str
    oid: str
    stage: int = 0


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    key: str = ""
    matched: str = field(default="", repr=False, compare=False)
    status: str = "block"

    @property
    def identity(self) -> str:
        source = "\0".join((self.path, self.rule, self.key, self.matched))
        return hashlib.sha256(source.encode("utf-8", "surrogateescape")).hexdigest()


SPECIFIC_RULES = (
    ("telegram-token", re.compile(r"(?<!\d)\d{8,12}:[A-Za-z0-9_-]{30,}"), (":",)),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), ("akia", "asia")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), ("xox",)),
    ("api-token", re.compile(r"\b(?:sk-ant-|sk-)[A-Za-z0-9_-]{20,}\b"), ("sk-",)),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"), ("bearer",)),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), ("-----begin",)),
)

GENERIC_ASSIGNMENT = re.compile(
    r"(?:\bexport\s+)?[\"']?\b(?P<key>[A-Za-z_][A-Za-z0-9_]*)[\"']?\s*[:=]\s*",
    re.IGNORECASE,
)
SYNTHETIC_MARKER = "secret-scan: allow-synthetic"
PLACEHOLDER_PARTS = (
    "placeholder",
    "replace-me",
    "replace_me",
    "change-me",
    "change_me",
    "changeme",
    "your-",
    "your_",
    "example",
    "sample",
    "dummy",
    "redacted",
    "masked",
    "not-a-real",
    "not_a_real",
    "test-secret",
    "test_secret",
)
ALLOWED_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}


def run_git(args: list[str], *, input_bytes: bytes | None = None, allow_failure: bool = False) -> bytes:
    result = subprocess.run(
        ["git", *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode and not allow_failure:
        raise RuntimeError("git operation failed; stderr suppressed to avoid data disclosure")
    return result.stdout


def index_blobs() -> list[Blob]:
    output = run_git(["ls-files", "-s", "-z"])
    blobs = []
    for record in output.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        _mode, oid, stage = header.split()
        blobs.append(Blob(os.fsdecode(raw_path), oid.decode("ascii"), int(stage)))
    return blobs


def tree_blobs(ref: str, wanted_paths: set[str]) -> list[Blob]:
    if not wanted_paths or not run_git(["rev-parse", "--verify", ref], allow_failure=True):
        return []
    output = run_git(["ls-tree", "-r", "-z", ref])
    blobs = []
    for record in output.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        path = os.fsdecode(raw_path)
        if path not in wanted_paths:
            continue
        _mode, object_type, oid = header.split()
        if object_type == b"blob":
            blobs.append(Blob(path, oid.decode("ascii")))
    return blobs


def read_blobs(blobs: list[Blob]) -> dict[str, bytes]:
    object_ids = sorted({blob.oid for blob in blobs})
    if not object_ids:
        return {}
    output = run_git(["cat-file", "--batch"], input_bytes=("\n".join(object_ids) + "\n").encode("ascii"))
    contents = {}
    position = 0
    for expected_oid in object_ids:
        end = output.find(b"\n", position)
        if end < 0:
            raise RuntimeError("truncated git cat-file header")
        header = output[position:end].split()
        position = end + 1
        if len(header) != 3 or header[0].decode("ascii") != expected_oid or header[1] != b"blob":
            raise RuntimeError("unexpected git cat-file response")
        size = int(header[2])
        end = position + size
        if end >= len(output) or output[end:end + 1] != b"\n":
            raise RuntimeError("truncated git cat-file blob")
        contents[expected_oid] = output[position:end]
        position = end + 1
    if position != len(output):
        raise RuntimeError("unexpected trailing git cat-file data")
    return contents


def forbidden_path(path: str) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name
    if name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_EXAMPLES):
        return "environment-file"
    if re.fullmatch(r"homes/[^/]+/auth\.json(?:\..+)?", path):
        return "auth-store"
    if re.search(r"\.bak(?:$|[._])", name):
        return "backup-file"
    if path in {"store/fortune_oracle_store.json", "store/daily_fortune_dedupe.json"}:
        return "runtime-store"
    parts = pure.parts
    if len(parts) >= 3 and parts[0] == "homes":
        if parts[2] in {"sessions", "logs", "checkpoints", "pastes"}:
            return "runtime-state"
        if len(parts) >= 4 and parts[2] == "cron" and parts[3] in {"output", "jobs.json"}:
            return "runtime-state"
    return None


def known_reference_status(path: str) -> str | None:
    pure = PurePosixPath(path)
    parts = pure.parts
    if "node_modules" in parts and (pure.suffix in {".js", ".cjs", ".mjs", ".css", ".map"}):
        return "suppressed-generated"
    if (
        len(parts) >= 4
        and parts[0] == "homes"
        and parts[2] == "skills"
        and pure.suffix.lower() in {".md", ".markdown", ".rst", ".txt"}
    ):
        return "suppressed-document"
    return None


def normalize_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        value = value[1:-1]
    return value.strip()


def assignment_value(line: str, start: int) -> tuple[str, int, int]:
    if start >= len(line):
        return "", start, start
    quote = line[start]
    if quote in "\"'`":
        position = start + 1
        while position < len(line):
            if line[position] == "\\":
                position += 2
                continue
            if line[position] == quote:
                return line[start:position + 1], start, position + 1
            position += 1
        return line[start:], start, len(line)
    position = start
    while position < len(line) and line[position] not in " \t\r\n,;#":
        position += 1
    return line[start:position], start, position


def is_placeholder(value: str) -> bool:
    normalized = normalize_value(value)
    lowered = normalized.lower()
    if not normalized or set(normalized) <= {"*"}:
        return True
    if lowered in {"null", "none", "nil", "false", "replaceme", "changeme"}:
        return True
    if normalized.startswith(("<", "${", "$", "%")):
        return True
    if any(part in lowered for part in PLACEHOLDER_PARTS):
        return True
    if ("(" in normalized and ")" in normalized) or normalized.startswith(("os.environ", "process.env")):
        return True
    return False


def is_synthetic(line: str, previous_line: str, value: str) -> bool:
    return (
        SYNTHETIC_MARKER in line
        or SYNTHETIC_MARKER in previous_line
        or "synthetic" in normalize_value(value).lower()
    )


def scan_blob(blob: Blob, data: bytes) -> tuple[list[Finding], int]:
    findings = []
    path_rule = forbidden_path(blob.path)
    if path_rule:
        findings.append(Finding(blob.path, 0, path_rule))
    text = data.decode("utf-8", "replace")
    lines = text.splitlines()
    placeholders = 0
    for line_number, line in enumerate(lines, 1):
        previous_line = lines[line_number - 2] if line_number > 1 else ""
        specific_spans = []
        lowered_line = line.lower()
        for rule, pattern, triggers in SPECIFIC_RULES:
            if not any(trigger in lowered_line for trigger in triggers):
                continue
            for match in pattern.finditer(line):
                value = match.group(0)
                specific_spans.append(match.span())
                if is_placeholder(value):
                    placeholders += 1
                else:
                    status = "allowed-synthetic" if is_synthetic(line, previous_line, value) else "block"
                    findings.append(Finding(blob.path, line_number, rule, matched=value, status=status))
        generic_triggers = ("token", "password", "passwd", "secret", "api_key", "access_key", "private_key")
        generic_matches = GENERIC_ASSIGNMENT.finditer(line) if any(trigger in lowered_line for trigger in generic_triggers) else ()
        for match in generic_matches:
            key = match.group("key")
            lowered_key = key.lower()
            sensitive_suffixes = (
                "_token", "_password", "_passwd", "_secret", "_secret_key",
                "_api_key", "_access_key", "_private_key",
            )
            if lowered_key not in {
                "token", "password", "passwd", "secret", "secret_key",
                "api_key", "access_key", "private_key",
            } and not lowered_key.endswith(sensitive_suffixes):
                continue
            raw_value, start, end = assignment_value(line, match.end())
            value = normalize_value(raw_value)
            if any(start < specific_end and end > specific_start for specific_start, specific_end in specific_spans):
                continue
            if is_placeholder(value):
                placeholders += 1
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", value):
                continue
            if (
                not raw_value.startswith(("\"", "'", "`"))
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
                and (value.lower() == lowered_key or value.lower().endswith("_" + lowered_key))
            ):
                continue
            if len(value) < 16:
                continue
            status = "allowed-synthetic" if is_synthetic(line, previous_line, value) else "block"
            findings.append(Finding(
                blob.path,
                line_number,
                "credential-assignment",
                key=key,
                matched=value,
                status=status,
            ))
    return findings, placeholders


@dataclass
class ScanResult:
    findings: list[Finding]
    placeholders: int = 0
    scanned_blobs: int = 0
    scanned_bytes: int = 0
    skipped_binary_blobs: int = 0
    skipped_binary_bytes: int = 0


def scan_blobs(blobs: list[Blob], contents: dict[str, bytes]) -> ScanResult:
    result = ScanResult([])
    for blob in blobs:
        data = contents.get(blob.oid)
        if data is None:
            continue
        result.scanned_blobs += 1
        if b"\0" in data:
            result.skipped_binary_blobs += 1
            result.skipped_binary_bytes += len(data)
            path_rule = forbidden_path(blob.path)
            if path_rule:
                result.findings.append(Finding(blob.path, 0, path_rule))
            continue
        result.scanned_bytes += len(data)
        found, placeholder_count = scan_blob(blob, data)
        result.findings.extend(found)
        result.placeholders += placeholder_count
    return result


def scan(use_baseline: bool) -> ScanResult:
    blobs = index_blobs()
    result = scan_blobs(blobs, read_blobs(blobs))
    if not use_baseline:
        return result
    blocked = [finding for finding in result.findings if finding.status == "block"]
    baseline_paths = {finding.path for finding in blocked}
    baseline_blobs = tree_blobs("HEAD", baseline_paths)
    baseline = scan_blobs(baseline_blobs, read_blobs(baseline_blobs))
    known_identities = {finding.identity for finding in baseline.findings}
    for finding in blocked:
        if finding.identity in known_identities:
            reference_status = known_reference_status(finding.path)
            finding.status = reference_status or "known"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="block all findings, including known generated and reference examples",
    )
    args = parser.parse_args()
    try:
        result = scan(not args.no_baseline)
    except (OSError, RuntimeError, ValueError):
        print("ERROR: scan failed; Git errors and blob values were suppressed", file=sys.stderr)
        return 2
    visible = [
        finding for finding in result.findings
        if not finding.status.startswith("suppressed-")
    ]
    for finding in sorted(visible, key=lambda item: (item.path, item.line, item.rule, item.key)):
        key = f" key={finding.key}" if finding.key else ""
        print(f"{finding.path}:{finding.line}: {finding.status} {finding.rule}{key}")
    counts = {
        "blocking": sum(finding.status == "block" for finding in result.findings),
        "known": sum(finding.status == "known" for finding in result.findings),
        "suppressed_generated": sum(
            finding.status == "suppressed-generated" for finding in result.findings
        ),
        "suppressed_document": sum(
            finding.status == "suppressed-document" for finding in result.findings
        ),
        "allowed_synthetic": sum(finding.status == "allowed-synthetic" for finding in result.findings),
        "placeholders": result.placeholders,
    }
    print(
        f"SUMMARY scanned_blobs={result.scanned_blobs} scanned_bytes={result.scanned_bytes} "
        f"skipped_binary_blobs={result.skipped_binary_blobs} "
        f"skipped_binary_bytes={result.skipped_binary_bytes} "
        + " ".join(f"{key}={value}" for key, value in counts.items())
    )
    return int(bool(counts["blocking"]))


if __name__ == "__main__":
    raise SystemExit(main())
