from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_public_release.py"
IGNORE = Path(__file__).resolve().parents[1] / ".gitignore"


def git(root: Path, *args: str, data: bytes | None = None, index_file: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="Synthetic Test", GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Synthetic Test", GIT_COMMITTER_EMAIL="test@example.invalid",
    )
    if index_file is not None:
        environment["GIT_INDEX_FILE"] = str(index_file)
    return subprocess.run(
        ["git", "-C", str(root), *args], input=data, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )


def initialize(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "commit.gpgsign", "false")


def commit(root: Path) -> None:
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "synthetic fixture")


def scan(root: Path, *, staged: bool = False, index_file: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    if index_file is not None:
        environment["GIT_INDEX_FILE"] = str(index_file)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *(["--staged"] if staged else [])],
        cwd=root, env=environment, capture_output=True, text=True, check=False,
    )


def write(root: Path, relative: str, data: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def token() -> str:
    return "123456789:" + "B" * 35


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    write(tmp_path, "README.md", "Public source fixture\n")
    return tmp_path


@pytest.mark.parametrize("state", ["no-git", "unborn", "staged", "one-root-commit"])
def test_accepts_independent_initial_snapshot(snapshot: Path, state: str) -> None:
    if state != "no-git":
        initialize(snapshot)
    if state == "staged":
        git(snapshot, "add", ".")
    if state == "one-root-commit":
        commit(snapshot)
    result = scan(snapshot)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "blocking=0" in result.stdout


@pytest.mark.parametrize(
    "relative",
    [
            ".env", "web/.env.local", "runtime.env", "service.env", "runtime.env.production",
            "auth.json", "web/auth.json.backup",
        "credentials.json", "profile.json.bak_case", "profile.json.backup",
        "homes/dev/config.yaml", "store/profiles.json", "logs/worker.txt",
        "web/instance/session.json", "sessions/session.md", "state.db",
        "web/state.sqlite3-wal", "cron/jobs.json", "cron/output/result.txt",
        "worker.log.1", "events.jsonl", "crontab", "id_ed25519", "state.db.gz",
        "credentials.json.save", "profiles_backup.json", "session-export.zip",
    ],
)
def test_runtime_and_secret_paths_are_blocked_even_with_safe_content(snapshot: Path, relative: str) -> None:
    write(snapshot, relative, "placeholder\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "BLOCK rule=" in result.stdout


def test_blank_and_explicit_placeholder_env_templates_are_allowed(snapshot: Path) -> None:
    key = "TELEGRAM_BOT_" + "TOKEN"
    for relative, value in [
        (".env.example", ""), ("web/.env.sample", "<set-by-human>"),
        ("templates/.env.template", "${DEPLOYMENT_TOKEN}"),
        ("runtime.env.example", ""), ("service.env.sample", ""), ("service.env.template", ""),
    ]:
        write(snapshot, relative, f"{key}={value}\n")
    assert scan(snapshot).returncode == 0


def test_named_environment_template_still_has_its_content_scanned(snapshot: Path) -> None:
    write(snapshot, "runtime.env.example", token())
    result = scan(snapshot)
    assert result.returncode == 1
    assert 'rule=telegram-token path="runtime.env.example" line=1' in result.stdout


def test_ignored_untracked_and_committed_tokens_all_block_without_values_or_hashes(snapshot: Path) -> None:
    initialize(snapshot)
    secret = token()
    write(snapshot, ".gitignore", "settings.txt\n")
    write(snapshot, "settings.txt", secret)
    ignored = scan(snapshot)
    assert ignored.returncode == 1
    git(snapshot, "add", "-f", "settings.txt")
    commit(snapshot)
    committed = scan(snapshot)
    assert committed.returncode == 1  # HEAD is deliberately never a baseline.
    for result in [ignored, committed]:
        output = result.stdout + result.stderr
        assert 'rule=telegram-token path="settings.txt" line=1' in output
        assert secret not in output
        assert hashlib.sha256(secret.encode()).hexdigest() not in output


def test_old_synthetic_marker_and_placeholder_substrings_cannot_hide_tokens(snapshot: Path) -> None:
    fixture_value = "ghp_" + "example" + "Z" * 25
    write(snapshot, "settings.txt", fixture_value + " # secret-scan: allow-synthetic\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "rule=github-token" in result.stdout
    assert fixture_value not in result.stdout + result.stderr


def test_synthetic_exception_is_exact_and_only_for_marked_python_tests(snapshot: Path) -> None:
    secret = token()
    marker = "# public-release: allow-synthetic"
    write(snapshot, "tests/test_fixture.py", secret + " " + marker)
    assert scan(snapshot).returncode == 0
    write(snapshot, "settings.txt", secret + " " + marker)
    assert scan(snapshot).returncode == 1
    (snapshot / "settings.txt").unlink()
    write(snapshot, "tests/test_fixture.py", secret.replace("B", "Z", 1) + " " + marker)
    assert scan(snapshot).returncode == 1


def test_credential_assignments_and_embedded_binary_credentials_are_scanned(snapshot: Path) -> None:
    key = "API_" + "KEY"
    fixture_value = "opaqueCredentialValue192837"
    write(snapshot, "config.yaml", f'{key}: "{fixture_value}"\n')
    write(snapshot, "image.bin", b"\0\xff" + token().encode() + b"\0")
    result = scan(snapshot)
    assert result.returncode == 1
    assert 'rule=credential-assignment path="config.yaml" line=1' in result.stdout
    assert 'rule=telegram-token path="image.bin" line=1' in result.stdout
    assert fixture_value not in result.stdout + result.stderr


def test_annotated_and_multiline_python_literals_are_scanned(snapshot: Path) -> None:
    key = "WEB_SESSION_" + "SECRET"
    fixture_value = "opaqueCredentialValue192837"
    write(snapshot, "config.py", f'{key}: str = (\n    "{fixture_value}"\n)\n')
    result = scan(snapshot)
    assert result.returncode == 1
    assert 'rule=credential-assignment path="config.py" line=2' in result.stdout
    assert fixture_value not in result.stdout + result.stderr


def test_documented_generator_expression_does_not_allow_static_codeblock_credentials(snapshot: Path) -> None:
    key = "SESSION_" + "SECRET"
    write(snapshot, "SETUP.md", "```bash\n" + key + "=secrets.token_hex(32)\n```\n")
    assert scan(snapshot).returncode == 0
    write(snapshot, "SETUP.md", "```bash\n" + key + "=opaqueCredentialValue192837\n```\n")
    assert scan(snapshot).returncode == 1


def test_shell_unquoted_literal_is_scanned_while_runtime_expansion_is_allowed(snapshot: Path) -> None:
    key = "API_" + "KEY"
    write(snapshot, "start.sh", key + '=opaqueCredentialValue192837\n')
    assert scan(snapshot).returncode == 1
    write(snapshot, "start.sh", key + '="$DEPLOYMENT_KEY"\n')
    assert scan(snapshot).returncode == 0


def test_external_symlink_and_nested_repository_are_blocked(snapshot: Path, tmp_path: Path) -> None:
    (snapshot / "link").symlink_to("/etc/passwd")
    write(snapshot, "nested/.git/HEAD", "ref: refs/heads/main\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "symlink-not-allowed" in result.stdout
    assert "nested-git-metadata" in result.stdout


@pytest.mark.parametrize("metadata", ["shallow", "commondir", "objects/info/alternates", "objects/info/http-alternates", "info/grafts"])
def test_shared_or_incomplete_git_metadata_is_blocked(snapshot: Path, metadata: str) -> None:
    initialize(snapshot)
    write(snapshot, ".git/" + metadata, "synthetic metadata\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-shared-or-incomplete-history" in result.stdout
    assert "synthetic metadata" not in result.stdout + result.stderr


def test_linked_worktree_git_file_is_blocked(snapshot: Path) -> None:
    write(snapshot, ".git", "gitdir: /nonpublic/example\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-linked-or-external-metadata" in result.stdout
    assert "/nonpublic/example" not in result.stdout + result.stderr


def test_history_additional_refs_and_reflog_are_blocked(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    git(snapshot, "tag", "old-release")
    assert "git-inherited-refs" in scan(snapshot).stdout
    git(snapshot, "tag", "-d", "old-release")
    write(snapshot, "README.md", "second synthetic revision\n")
    commit(snapshot)
    assert "git-inherited-history" in scan(snapshot).stdout
    git(snapshot, "checkout", "--orphan", "clean")
    commit(snapshot)
    git(snapshot, "branch", "-D", "main")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-inherited-reflog" in result.stdout


def test_unreachable_old_objects_cannot_be_hidden_by_erasing_refs_and_reflogs(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    git(snapshot, "hash-object", "-w", "--stdin", data=b"synthetic old object\n")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-inherited-or-invalid-objects" in result.stdout
    assert "synthetic old object" not in result.stdout + result.stderr


@pytest.mark.parametrize("state", ["staged-differs", "committed-file-deleted", "head-differs", "assume-unchanged", "skip-worktree"])
def test_hidden_index_and_head_content_cannot_pass_a_worktree_scan(snapshot: Path, state: str) -> None:
    initialize(snapshot)
    write(snapshot, "settings.txt", token())
    if state != "staged-differs":
        commit(snapshot)
    else:
        git(snapshot, "add", ".")
    if state == "committed-file-deleted":
        (snapshot / "settings.txt").unlink()
    else:
        write(snapshot, "settings.txt", "placeholder\n")
    if state == "head-differs":
        git(snapshot, "add", ".")
    if state in {"assume-unchanged", "skip-worktree"}:
        git(snapshot, "update-index", "--" + state, "settings.txt")
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-" in result.stdout
    assert token() not in result.stdout + result.stderr


def test_staged_mode_allows_ignored_local_environment_and_later_commits(snapshot: Path) -> None:
    initialize(snapshot)
    write(snapshot, ".gitignore", ".env\n")
    commit(snapshot)
    write(snapshot, ".env", token())
    write(snapshot, "README.md", "second synthetic revision\n")
    git(snapshot, "add", "README.md")
    assert scan(snapshot, staged=True).returncode == 0
    commit(snapshot)
    write(snapshot, "README.md", "third synthetic revision\n")
    git(snapshot, "add", "README.md")
    assert scan(snapshot, staged=True).returncode == 0
    assert scan(snapshot).returncode == 1


@pytest.mark.parametrize("relative", [".env", "web/.env.local", "logs/output.txt", "homes/dev/config.yaml"])
def test_staged_mode_blocks_forced_runtime_paths(snapshot: Path, relative: str) -> None:
    initialize(snapshot)
    write(snapshot, relative, "placeholder\n")
    git(snapshot, "add", "-f", relative)
    result = scan(snapshot, staged=True)
    assert result.returncode == 1
    assert f'path="{relative}"' in result.stdout


def test_staged_mode_reads_index_even_when_worktree_hides_secret(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    write(snapshot, "config.txt", token())
    git(snapshot, "add", "config.txt")
    write(snapshot, "config.txt", "placeholder\n")
    result = scan(snapshot, staged=True)
    assert result.returncode == 1
    assert 'rule=telegram-token path="config.txt" line=1' in result.stdout
    assert token() not in result.stdout + result.stderr


@pytest.mark.parametrize("entry_type", ["symlink", "submodule", "unmerged"])
def test_staged_mode_rejects_nonfile_and_unmerged_index_entries(snapshot: Path, entry_type: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    if entry_type == "symlink":
        (snapshot / "link").symlink_to("README.md")
        git(snapshot, "add", "link")
    elif entry_type == "submodule":
        oid = git(snapshot, "rev-parse", "HEAD").stdout.decode().strip()
        git(snapshot, "update-index", "--add", "--cacheinfo", "160000," + oid + ",nested")
    else:
        oid = git(snapshot, "hash-object", "-w", "--stdin", data=b"synthetic conflict\n").stdout.strip()
        git(snapshot, "update-index", "--index-info", data=b"100644 " + oid + b" 1\tconflicted.txt\n")
    result = scan(snapshot, staged=True)
    assert result.returncode == 1
    assert ("git-unmerged-index-entry" if entry_type == "unmerged" else "git-non-file-index-entry") in result.stdout


def test_staged_mode_never_uses_head_as_secret_baseline(snapshot: Path) -> None:
    initialize(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    result = scan(snapshot, staged=True)
    assert result.returncode == 1
    assert "telegram-token" in result.stdout


def test_staged_mode_checks_the_temporary_index_used_for_partial_commits(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    alternate = snapshot / ".git" / "synthetic-index"
    git(snapshot, "read-tree", "HEAD", index_file=alternate)
    write(snapshot, "config.txt", token())
    git(snapshot, "add", "config.txt", index_file=alternate)
    write(snapshot, "config.txt", "placeholder\n")
    assert scan(snapshot, staged=True).returncode == 0
    result = scan(snapshot, staged=True, index_file=alternate)
    assert result.returncode == 1
    assert "telegram-token" in result.stdout
    assert token() not in result.stdout + result.stderr


def test_snapshot_rejects_shared_hardlinked_git_objects(snapshot: Path, tmp_path: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    object_path = next((snapshot / ".git" / "objects").glob("[0-9a-f][0-9a-f]/*"))
    os.link(object_path, snapshot.parent / (snapshot.name + "-shared-object"))
    result = scan(snapshot)
    assert result.returncode == 1
    assert "git-shared-object-storage" in result.stdout


def test_ignore_blocks_new_runtime_paths_but_keeps_env_templates(snapshot: Path) -> None:
    initialize(snapshot)
    write(snapshot, ".gitignore", IGNORE.read_bytes())
    for relative in [".env", "web/.env.production", "auth.json", "nested/profile.json.bak", "web/state.db-wal", "sessions/example.md"]:
        write(snapshot, relative, "placeholder\n")
        assert git(snapshot, "check-ignore", "--", relative).returncode == 0
    for relative in [".env.example", "web/.env.sample", "nested/.env.template"]:
        write(snapshot, relative, "")
        result = subprocess.run(["git", "-C", str(snapshot), "check-ignore", "--", relative], capture_output=True, check=False)
        assert result.returncode == 1
