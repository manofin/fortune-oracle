from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_fortune_secrets.py"


def synthetic_telegram(letter: str = "A") -> str:
    return "123456789:" + letter * 35


def git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(repo),
    }
    subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def stage(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", "-f", "--", relative)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Synthetic Test")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    git(tmp_path, "config", "commit.gpgsign", "false")
    stage(tmp_path, "README.md", "synthetic fixture\n")
    git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def scan(repo: Path, *, baseline: bool = True) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    if not baseline:
        command.append("--no-baseline")
    return subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)


def summary(result: subprocess.CompletedProcess[str]) -> dict[str, int]:
    line = next(line for line in result.stdout.splitlines() if line.startswith("SUMMARY "))
    return {key: int(value) for key, value in (item.split("=") for item in line.split()[1:])}


def test_placeholders_and_explicit_synthetic_token_are_distinguished(repo: Path) -> None:
    token = synthetic_telegram()
    stage(
        repo,
        "settings.txt",
        "TELEGRAM_BOT_TOKEN=<set-by-human>\n"
        "COPILOT_API_KEY=placeholder\n"
        f"DISCORD_BOT_TOKEN={token}  # secret-scan: allow-synthetic\n",
    )
    result = scan(repo, baseline=False)
    counts = summary(result)
    assert result.returncode == 0
    assert counts["blocking"] == 0
    assert counts["placeholders"] == 2
    assert counts["allowed_synthetic"] == 1
    assert token not in result.stdout + result.stderr


def test_real_shaped_staged_token_is_blocked_without_value_output(repo: Path) -> None:
    token = synthetic_telegram("B")
    stage(repo, "settings.txt", f"TELEGRAM_BOT_TOKEN={token}\n")
    result = scan(repo, baseline=False)
    counts = summary(result)
    assert result.returncode == 1
    assert counts["blocking"] == 1
    assert "settings.txt:1: block telegram-token" in result.stdout
    assert token not in result.stdout + result.stderr


def test_forbidden_paths_block_but_env_example_is_allowed(repo: Path) -> None:
    stage(repo, "homes/dev/.env", "TELEGRAM_BOT_TOKEN=placeholder\n")
    stage(repo, "store/profile.bak_case", "synthetic fixture\n")
    stage(repo, "homes/dev/.env.example", "TELEGRAM_BOT_TOKEN=<set-by-human>\n")
    result = scan(repo, baseline=False)
    counts = summary(result)
    assert result.returncode == 1
    assert counts["blocking"] == 2
    assert "homes/dev/.env:0: block environment-file" in result.stdout
    assert "store/profile.bak_case:0: block backup-file" in result.stdout
    assert "homes/dev/.env.example:0" not in result.stdout


def test_head_violations_are_known_but_changed_secret_is_blocked(repo: Path) -> None:
    old_token = synthetic_telegram("C")
    new_value = "copilotReplacement123"
    stage(repo, "homes/dev/.env", f"TELEGRAM_BOT_TOKEN={old_token}\n")
    git(repo, "commit", "-q", "-m", "known violation")
    known = scan(repo)
    assert known.returncode == 0
    assert summary(known)["known"] == 2
    assert summary(known)["blocking"] == 0
    stage(
        repo,
        "homes/dev/.env",
        f"TELEGRAM_BOT_TOKEN={old_token}\n"
        f"COPILOT_API_KEY={new_value}\n",
    )
    changed = scan(repo)
    counts = summary(changed)
    assert changed.returncode == 1
    assert counts["known"] == 2
    assert counts["blocking"] == 1
    assert old_token not in changed.stdout + changed.stderr
    assert new_value not in changed.stdout + changed.stderr


def test_index_blob_is_scanned_instead_of_worktree_content(repo: Path) -> None:
    token = synthetic_telegram("D")
    stage(repo, "settings.txt", "TELEGRAM_BOT_TOKEN=placeholder\n")
    git(repo, "commit", "-q", "-m", "safe placeholder")
    stage(repo, "settings.txt", f"TELEGRAM_BOT_TOKEN={token}\n")
    (repo / "settings.txt").write_text("TELEGRAM_BOT_TOKEN=placeholder\n", encoding="utf-8")
    staged = scan(repo)
    assert staged.returncode == 1
    assert summary(staged)["blocking"] == 1
    stage(repo, "settings.txt", "TELEGRAM_BOT_TOKEN=placeholder\n")
    (repo / "settings.txt").write_text(f"TELEGRAM_BOT_TOKEN={token}\n", encoding="utf-8")
    unstaged = scan(repo)
    assert unstaged.returncode == 0
    assert summary(unstaged)["blocking"] == 0
    assert token not in staged.stdout + staged.stderr + unstaged.stdout + unstaged.stderr


def test_private_key_block_does_not_print_key_material(repo: Path) -> None:
    marker = "U1lOVEhFVElDLUtFWS1NQVRFUklBTA"
    material = "-----BEGIN " + "PRIVATE KEY-----\n" + marker + "\n-----END PRIVATE KEY-----\n"
    stage(repo, "key.txt", material)
    result = scan(repo, baseline=False)
    assert result.returncode == 1
    assert summary(result)["blocking"] == 1
    assert "key.txt:1: block private-key" in result.stdout
    assert marker not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("relative", "suppressed_key"),
    [
        ("plugins/example/node_modules/iztro/dist/iztro.min.js", "suppressed_generated"),
        ("plugins/example/node_modules/iztro/dist/iztro.min.js.map", "suppressed_generated"),
        ("plugins/example/node_modules/lunar-typescript/dist/index.cjs", "suppressed_generated"),
        ("homes/dev/skills/reference/SKILL.md", "suppressed_document"),
    ],
)
def test_known_reference_example_does_not_hide_a_new_secret(
    repo: Path,
    relative: str,
    suppressed_key: str,
) -> None:
    old_token = synthetic_telegram("E")
    new_token = synthetic_telegram("F")
    stage(repo, relative, f"example={old_token}\n")
    git(repo, "commit", "-q", "-m", "known reference example")
    existing = scan(repo)
    existing_counts = summary(existing)
    assert existing.returncode == 0
    assert existing_counts["blocking"] == 0
    assert existing_counts["known"] == 0
    assert existing_counts[suppressed_key] == 1
    strict = scan(repo, baseline=False)
    assert strict.returncode == 1
    assert summary(strict)["blocking"] == 1
    stage(repo, relative, f"example={new_token}\n")
    changed = scan(repo)
    changed_counts = summary(changed)
    assert changed.returncode == 1
    assert changed_counts["blocking"] == 1
    assert changed_counts["known"] == 0
    assert changed_counts[suppressed_key] == 0
    assert old_token not in existing.stdout + existing.stderr
    assert new_token not in changed.stdout + changed.stderr
