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


def scan(
    root: Path, *, staged: bool = False, index_file: Path | None = None,
    history: str | None = None, excludes: tuple[str, ...] = (),
    push_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    if index_file is not None:
        environment["GIT_INDEX_FILE"] = str(index_file)
    mode = ["--staged"] if staged else []
    if history is not None:
        mode = ["--history", history, *[part for oid in excludes for part in ("--exclude", oid)]]
    elif push_input is not None:
        mode = ["--pre-push"]
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *mode],
        input=push_input, cwd=root, env=environment, capture_output=True, text=True, check=False,
    )


def write(root: Path, relative: str, data: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def token() -> str:
    return "123456789:" + "B" * 35


def oid(root: Path, revision: str = "HEAD") -> str:
    return git(root, "rev-parse", "--verify", revision).stdout.decode().strip()


def push_record(
    target: str, base: str | None = None, *,
    remote_ref: str = "refs/heads/main", local_ref: str = "refs/heads/main",
) -> str:
    return f"{local_ref} {target} {remote_ref} {base or '0' * len(target)}\n"


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


@pytest.mark.parametrize("new_ref", [False, True])
def test_history_catches_secret_removed_before_pushed_tip(snapshot: Path, new_ref: bool) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    (snapshot / "settings.txt").unlink()
    commit(snapshot)
    assert scan(snapshot, staged=True).returncode == 0
    target = oid(snapshot)
    results = [
        scan(snapshot, history=target, excludes=() if new_ref else (base,)),
        scan(snapshot, push_input=push_record(target, None if new_ref else base)),
    ]
    for result in results:
        assert result.returncode == 1, result.stdout + result.stderr
        assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout
        assert token() not in result.stdout + result.stderr
        assert hashlib.sha256(token().encode()).hexdigest() not in result.stdout + result.stderr
        assert target not in result.stdout + result.stderr


def test_push_reads_committed_objects_independently_of_index_and_worktree(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    write(snapshot, "settings.txt", "placeholder\n")
    git(snapshot, "add", "settings.txt")
    assert scan(snapshot, staged=True).returncode == 0
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout


def test_clean_push_ignores_unpushed_index_worktree_and_unrelated_branch(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    git(snapshot, "checkout", "-q", "-b", "unpublished")
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    git(snapshot, "checkout", "-q", "main")
    write(snapshot, "README.md", "second clean revision\n")
    commit(snapshot)
    target = oid(snapshot)
    write(snapshot, "settings.txt", token())
    git(snapshot, "add", "settings.txt")
    write(snapshot, ".env", token())
    assert scan(snapshot, staged=True).returncode == 1
    for result in [scan(snapshot, history=target), scan(snapshot, push_input=push_record(target, base))]:
        assert result.returncode == 0, result.stdout + result.stderr


def test_existing_ref_exclusion_does_not_reinspect_removed_remote_content(snapshot: Path) -> None:
    initialize(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    base = oid(snapshot)
    (snapshot / "settings.txt").unlink()
    commit(snapshot)
    target = oid(snapshot)
    assert scan(snapshot, history=target).returncode == 1
    assert scan(snapshot, history=target, excludes=(base,)).returncode == 0
    assert scan(snapshot, push_input=push_record(target, base)).returncode == 0
    assert scan(snapshot, push_input=push_record(target)).returncode == 1


def test_push_checks_every_outgoing_ref(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "README.md", "clean main revision\n")
    commit(snapshot)
    clean = oid(snapshot)
    git(snapshot, "checkout", "-q", "-b", "feature", base)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    secret_commit = oid(snapshot)
    result = scan(snapshot, push_input=(
        push_record(clean, base)
        + push_record(secret_commit, remote_ref="refs/heads/feature", local_ref="refs/heads/feature")
    ))
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout


def test_empty_push_and_deleting_an_unfetched_remote_ref_publish_no_objects(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    for data in ["", push_record("0" * 40, "1" * 40, local_ref="(delete)")]:
        result = scan(snapshot, push_input=data)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "scanned_files=0 blocking=0" in result.stdout


def test_clean_multiple_ref_push_includes_new_branch_tag_and_deletion(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "README.md", "second clean revision\n")
    commit(snapshot)
    target = oid(snapshot)
    git(snapshot, "tag", "-a", "release", "-m", "Synthetic public release")
    result = scan(snapshot, push_input=(
        push_record(target, base)
        + push_record(target, remote_ref="refs/heads/new-feature", local_ref="HEAD")
        + push_record(oid(snapshot, "refs/tags/release"), remote_ref="refs/tags/release", local_ref="refs/tags/release")
        + push_record("0" * 40, "1" * 40, remote_ref="refs/heads/removed", local_ref="(delete)")
    ))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("tag_kind", ["lightweight", "annotated", "nested"])
def test_commit_tags_cannot_hide_intermediate_secret(snapshot: Path, tag_kind: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    (snapshot / "settings.txt").unlink()
    commit(snapshot)
    if tag_kind == "lightweight":
        git(snapshot, "tag", "release")
    else:
        git(snapshot, "tag", "-a", "release", "-m", "Synthetic release")
        if tag_kind == "nested":
            git(snapshot, "tag", "-a", "outer", "-m", "Synthetic outer tag", "release")
    ref = "refs/tags/outer" if tag_kind == "nested" else "refs/tags/release"
    target = oid(snapshot, ref)
    for result in [scan(snapshot, history=target), scan(snapshot, push_input=push_record(target, remote_ref=ref, local_ref=ref))]:
        assert result.returncode == 1
        assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout


@pytest.mark.parametrize("kind", ["commit", "tag"])
def test_history_checks_commit_and_annotated_tag_messages(snapshot: Path, kind: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    if kind == "commit":
        git(snapshot, "commit", "-q", "--allow-empty", "-m", token())
        record = push_record(oid(snapshot), base)
    else:
        git(snapshot, "tag", "-a", "release", "-m", token())
        record = push_record(oid(snapshot, "refs/tags/release"), remote_ref="refs/tags/release", local_ref="refs/tags/release")
    result = scan(snapshot, push_input=record)
    assert result.returncode == 1
    assert f'rule=telegram-token path=".git/{kind}-message" line=1' in result.stdout
    assert token() not in result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["commit", "tag"])
def test_history_checks_credentials_in_commit_and_tag_headers(snapshot: Path, kind: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    if kind == "commit":
        data = (
            f"tree {oid(snapshot, 'HEAD^{tree}')}\nparent {oid(snapshot)}\n"
            f"author {token()} <test@example.invalid> 1000000000 +0000\n"
            "committer Synthetic Test <test@example.invalid> 1000000000 +0000\n\n"
            "Synthetic metadata fixture\n"
        )
        target = git(snapshot, "hash-object", "-t", "commit", "-w", "--stdin", data=data.encode()).stdout.decode().strip()
        rule = "telegram-token"
    else:
        tag_name = "ghp_" + "B" * 32
        git(snapshot, "tag", "-a", tag_name, "-m", "Synthetic metadata fixture")
        target = oid(snapshot, "refs/tags/" + tag_name)
        rule = "github-token"
    result = scan(snapshot, history=target)
    assert result.returncode == 1
    assert f'rule={rule} path=".git/{kind}-metadata" line=3' in result.stdout
    assert token() not in result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["blob", "tree"])
def test_history_rejects_noncommit_tag_targets(snapshot: Path, kind: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot, "HEAD:README.md" if kind == "blob" else "HEAD^{tree}")
    git(snapshot, "tag", "-a", "release", "-m", "Synthetic tag", target)
    target = oid(snapshot, "refs/tags/release")
    result = scan(snapshot, push_input=push_record(target, remote_ref="refs/tags/release", local_ref="refs/tags/release"))
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"
    assert target not in result.stdout + result.stderr


@pytest.mark.parametrize("missing", ["target", "base", "blob", "parent", "tree"])
def test_push_fails_closed_on_missing_objects(snapshot: Path, missing: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "README.md", "second clean revision\n")
    commit(snapshot)
    target = oid(snapshot)
    if missing == "target":
        target = "1" * 40
    elif missing == "base":
        base = "1" * 40
    else:
        missing_oid = {"blob": oid(snapshot, "HEAD:README.md"), "parent": base, "tree": oid(snapshot, "HEAD^{tree}")}[missing]
        (snapshot / ".git" / "objects" / missing_oid[:2] / missing_oid[2:]).unlink()
    result = scan(snapshot, push_input=push_record(target, base))
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"
    assert target not in result.stdout + result.stderr


@pytest.mark.parametrize("mutation", [
    "short-id", "upper-id", "revision-expression", "local-ref-expression", "extra-field", "blank-record",
    "duplicate-ref", "unsupported-ref", "invalid-ref", "bad-delete", "delete-missing-ref", "crlf", "nul",
])
def test_push_fails_closed_on_malformed_protocol(snapshot: Path, mutation: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot)
    record = push_record(target)
    if mutation == "short-id":
        record = push_record(target[:8])
    elif mutation == "upper-id":
        record = push_record(target.upper())
    elif mutation == "revision-expression":
        record = push_record("HEAD~1")
    elif mutation == "local-ref-expression":
        record = push_record(target, local_ref="main~1")
    elif mutation == "extra-field":
        record = record.rstrip() + " extra\n"
    elif mutation == "blank-record":
        record += "\n"
    elif mutation == "duplicate-ref":
        record *= 2
    elif mutation == "unsupported-ref":
        record = push_record(target, remote_ref="refs/notes/synthetic")
    elif mutation == "invalid-ref":
        record = push_record(target, remote_ref="refs/heads/../synthetic")
    elif mutation == "bad-delete":
        record = push_record("0" * 40, target)
    elif mutation == "delete-missing-ref":
        record = push_record("0" * 40, local_ref="(delete)")
    elif mutation == "crlf":
        record = record.replace("\n", "\r\n")
    elif mutation == "nul":
        record = record.replace("refs/heads/main", "refs/heads/ma\0in")
    result = scan(snapshot, push_input=record)
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"


@pytest.mark.parametrize("limit", ["bytes", "refs"])
def test_push_protocol_work_limits_fail_closed(snapshot: Path, limit: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot)
    if limit == "bytes":
        data = "A" * (128 * 1024 + 1)
    else:
        data = "".join(push_record(target, remote_ref=f"refs/heads/synthetic-{number}") for number in range(257))
    result = scan(snapshot, push_input=data)
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"


@pytest.mark.parametrize("target", ["HEAD", "HEAD~1", "main", "--all", "0" * 40, "1" * 8])
def test_history_cli_requires_complete_nonzero_object_ids(snapshot: Path, target: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    result = scan(snapshot, history=target)
    assert result.returncode == 2


def test_push_ignores_object_replacements_that_hide_secret(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    target = oid(snapshot)
    git(snapshot, "checkout", "-q", "-b", "replacement", base)
    write(snapshot, "README.md", "clean replacement revision\n")
    commit(snapshot)
    replacement = oid(snapshot)
    git(snapshot, "replace", target, replacement)
    result = scan(snapshot, push_input=push_record(target, base))
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout


@pytest.mark.parametrize("metadata", ["shallow", "objects/info/alternates", "objects/info/http-alternates", "info/grafts"])
def test_history_rejects_incomplete_or_external_object_storage(snapshot: Path, metadata: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot)
    write(snapshot, ".git/" + metadata, "synthetic metadata\n")
    result = scan(snapshot, push_input=push_record(target))
    assert result.returncode == 2
    assert "synthetic metadata" not in result.stdout + result.stderr


def test_history_rejects_partial_clones_without_lazy_fetch(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    git(snapshot, "config", "remote.synthetic.promisor", "true")
    result = scan(snapshot, push_input=push_record(oid(snapshot)))
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"


def test_history_rejects_symlinked_object_storage(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot)
    objects = snapshot / ".git" / "objects"
    elsewhere = snapshot / "synthetic-objects"
    objects.rename(elsewhere)
    objects.symlink_to(elsewhere, target_is_directory=True)
    result = scan(snapshot, push_input=push_record(target))
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"


def test_history_rejects_mistyped_tag_object(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    data = f"object {oid(snapshot)}\ntype blob\ntag synthetic\n\nSynthetic mistyped tag\n"
    target = git(snapshot, "hash-object", "-t", "tag", "--literally", "-w", "--stdin", data=data.encode()).stdout.decode().strip()
    result = scan(snapshot, history=target)
    assert result.returncode == 2
    assert result.stderr.strip() == "ERROR public-release-inspection-failed"


def test_history_deduplication_preserves_path_specific_synthetic_policy(snapshot: Path) -> None:
    initialize(snapshot)
    data = token() + " # public-release: allow-synthetic\n"
    write(snapshot, "tests/test_fixture.py", data)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "settings.txt", data)
    commit(snapshot)
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout
    assert 'path="tests/test_fixture.py"' not in result.stdout


def test_history_checks_paths_even_when_the_blob_was_previously_clean(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    git(snapshot, "mv", "README.md", "auth.json")
    commit(snapshot)
    git(snapshot, "mv", "auth.json", "README.md")
    commit(snapshot)
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=auth-store path="auth.json" line=0' in result.stdout


@pytest.mark.parametrize("kind", ["symlink", "submodule"])
def test_history_rejects_nonfile_entries_even_if_removed_at_tip(snapshot: Path, kind: str) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    if kind == "symlink":
        (snapshot / "nested").symlink_to("README.md")
        commit(snapshot)
    else:
        git(snapshot, "update-index", "--add", "--cacheinfo", "160000," + base + ",nested")
        git(snapshot, "commit", "-q", "-m", "Synthetic submodule fixture")
    git(snapshot, "rm", "--cached", "nested")
    if kind == "symlink":
        (snapshot / "nested").unlink()
    git(snapshot, "commit", "-q", "-m", "Remove synthetic nonfile")
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=git-non-file-history-entry path="nested" line=0' in result.stdout


def test_history_deduplication_cannot_hide_an_older_symlink_with_same_blob(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    (snapshot / "nested").symlink_to("README.md")
    commit(snapshot)
    (snapshot / "nested").unlink()
    write(snapshot, "nested", "README.md")
    commit(snapshot)
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=git-non-file-history-entry path="nested" line=0' in result.stdout


def test_history_checks_forbidden_empty_tree_entries(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    empty_tree = git(snapshot, "mktree", data=b"").stdout.strip()
    tree = git(snapshot, "mktree", data=b"040000 tree " + empty_tree + b"\tstore\n").stdout.strip()
    target = git(snapshot, "commit-tree", tree.decode(), "-p", base, data=b"Synthetic empty tree fixture\n").stdout.decode().strip()
    result = scan(snapshot, push_input=push_record(target, base))
    assert result.returncode == 1
    assert 'rule=private-runtime-tree path="store" line=0' in result.stdout


def test_push_checks_intermediate_commits_from_merged_branch(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    git(snapshot, "checkout", "-q", "-b", "feature")
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    (snapshot / "settings.txt").unlink()
    commit(snapshot)
    git(snapshot, "checkout", "-q", "main")
    write(snapshot, "README.md", "clean main revision\n")
    commit(snapshot)
    git(snapshot, "merge", "-q", "--no-ff", "-m", "Merge synthetic feature", "feature")
    result = scan(snapshot, push_input=push_record(oid(snapshot), base))
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout


def test_pre_push_hook_executes_history_guard_without_consuming_protocol(snapshot: Path) -> None:
    initialize(snapshot)
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "settings.txt", token())
    commit(snapshot)
    (snapshot / "settings.txt").unlink()
    commit(snapshot)
    write(snapshot, "scripts/check_public_release.py", SCRIPT.read_bytes())
    write(snapshot, "scripts/check_fortune_secrets.py", (SCRIPT.parent / "check_fortune_secrets.py").read_bytes())
    hook = SCRIPT.parent.parent / ".githooks" / "pre-push"
    result = subprocess.run(
        [str(hook), "synthetic-remote", "https://example.invalid/no-network"],
        input=push_record(oid(snapshot), base), cwd=snapshot,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert 'rule=telegram-token path="settings.txt" line=1' in result.stdout
    assert token() not in result.stdout + result.stderr


def test_history_supports_sha256_git_objects(snapshot: Path) -> None:
    try:
        git(snapshot, "init", "-q", "-b", "main", "--object-format=sha256")
    except subprocess.CalledProcessError:
        pytest.skip("Git does not support SHA-256 repositories")
    git(snapshot, "config", "commit.gpgsign", "false")
    commit(snapshot)
    base = oid(snapshot)
    write(snapshot, "README.md", "clean SHA-256 revision\n")
    commit(snapshot)
    target = oid(snapshot)
    assert len(target) == 64
    result = scan(snapshot, push_input=push_record(target, base))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("limit", ["MAX_HISTORY_COMMITS", "MAX_HISTORY_ENTRIES", "MAX_HISTORY_BYTES", "MAX_HISTORY_SECONDS", "MAX_TREE_OUTPUT_BYTES"])
def test_history_limits_fail_closed(snapshot: Path, monkeypatch: pytest.MonkeyPatch, limit: str) -> None:
    import importlib

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    guard = importlib.import_module("check_public_release")
    initialize(snapshot)
    commit(snapshot)
    target = oid(snapshot)
    monkeypatch.setattr(guard, limit, 0)
    with pytest.raises(RuntimeError):
        guard.scan_history(snapshot, target, [])


def test_history_oversized_blob_blocks_without_printing_payload(snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    guard = importlib.import_module("check_public_release")
    initialize(snapshot)
    write(snapshot, "oversized.txt", "synthetic oversized body\n" * 100)
    commit(snapshot)
    monkeypatch.setattr(guard, "MAX_FILE_BYTES", 1000)
    findings, _ = guard.scan_history(snapshot, oid(snapshot), [])
    assert guard.Finding("oversized.txt", 0, "file-too-large-to-inspect") in findings
