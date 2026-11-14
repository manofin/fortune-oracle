import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from hermes_ext.fortune_oracle import oracle


def test_line_allowlist_fail_closed_for_unknown_source():
    source = {"type": "user", "userId": "U_not_allowed"}
    assert oracle.is_line_source_allowed(source, allowed_users=[], allowed_groups=[], allowed_rooms=[]) is False
    assert oracle.is_line_source_allowed(source, allowed_users=["U_allowed"], allowed_groups=[], allowed_rooms=[]) is False


def test_line_allowlist_accepts_dm_user_and_group_ids():
    assert oracle.is_line_source_allowed(
        {"type": "user", "userId": "U_allowed"},
        allowed_users=["U_allowed"],
        allowed_groups=[],
        allowed_rooms=[],
    ) is True
    assert oracle.is_line_source_allowed(
        {"type": "group", "groupId": "C_allowed"},
        allowed_users=[],
        allowed_groups=["C_allowed"],
        allowed_rooms=[],
    ) is True


def test_profile_redaction_removes_sensitive_birth_fields_and_token():
    payload = {
        "line_user_id": "Uabc",
        "birth_date": "1986-01-02",
        "birth_time": "03:04",
        "birth_place": "Seoul",
        "name_hanja": "洪吉童",
        "LINE_CHANNEL_ACCESS_TOKEN": secrets.token_hex(32),
        "safe": "kept",
    }
    redacted = oracle.redact_sensitive(payload)
    assert redacted["safe"] == "kept"
    assert redacted["birth_date"] == "[REDACTED]"
    assert redacted["birth_time"] == "[REDACTED]"
    assert redacted["birth_place"] == "[REDACTED]"
    assert redacted["name_hanja"] == "[REDACTED]"
    assert redacted["LINE_CHANNEL_ACCESS_TOKEN"] == "[REDACTED]"


def test_delete_profile_removes_profile_and_daily_push_opt_in(tmp_path):
    store = oracle.FortuneStore(tmp_path / "fortune.json")
    store.save_profile("U1", {"birth_date": "1990-01-01"})
    store.set_daily_push("U1", "08:30", target="U1")
    assert store.get_profile("U1") is not None
    assert store.get_daily_push("U1") is not None

    store.delete_profile("U1")

    assert store.get_profile("U1") is None
    assert store.get_daily_push("U1") is None


def test_daily_push_only_targets_opted_in_users(tmp_path):
    store = oracle.FortuneStore(tmp_path / "fortune.json")
    store.save_profile("U1", {"birth_date": "1990-01-01"})
    store.save_profile("U2", {"birth_date": "1991-01-01"})
    store.set_daily_push("U1", "07:00", target="U1")

    targets = oracle.collect_daily_push_targets(store)

    assert targets == [{"user_id": "U1", "time": "07:00", "target": "U1"}]


def test_long_response_chunking_respects_line_limits():
    chunks = oracle.chunk_line_text("가" * 12050, max_chars=5000, max_chunks=5)
    assert len(chunks) == 3
    assert all(len(chunk) <= 5000 for chunk in chunks)
    assert "…" not in chunks[-1]

    truncated = oracle.chunk_line_text("나" * 26000, max_chars=5000, max_chunks=5)
    assert len(truncated) == 5
    assert truncated[-1].endswith("…")
    assert all(len(chunk) <= 5000 for chunk in truncated)


def test_plain_text_formatting_strips_markdown_for_line():
    text = "# 제목\n**굵게**와 `코드`\n```\nblock\n```\n[링크](https://example.com)"
    plain = oracle.to_line_plain_text(text)
    assert "#" not in plain
    assert "**" not in plain
    assert "`" not in plain
    assert "링크 (https://example.com)" in plain


def test_voice_fortune_requires_public_url(tmp_path):
    result = oracle.prepare_voice_fortune(
        text="오늘은 가볍게 움직이세요.",
        public_url="",
        audio_file=tmp_path / "fortune.mp3",
    )
    assert result["ok"] is False
    assert result["text_fallback"] == "오늘은 가볍게 움직이세요."
    assert "LINE_PUBLIC_URL" in result["error"]


def test_today_fortune_is_short_plain_text():
    text = oracle.render_daily_fortune("today", profile={"display_name": "홍길동"})
    lines = [line for line in text.splitlines() if line.strip()]
    assert 5 <= len(lines) <= 8
    assert "태허" in text
    assert "오락" in text and "자기성찰" in text
    assert "**" not in text and "#" not in text and "```" not in text


def test_precise_analysis_stage_requires_explicit_continue():
    session = oracle.AnalysisSession()
    first = session.start("integrated")
    assert first.stage == 1
    assert first.text.endswith("다음 단계를 진행할까요?")

    blocked = session.next("아니오")
    assert blocked.stage == 1
    assert blocked.waiting_for_confirmation is True

    second = session.next("다음")
    assert second.stage == 2
    assert second.text.endswith("다음 단계를 진행할까요?")


def test_core_runtime_files_are_not_modified_for_fortune_oracle():
    forbidden = [
        Path("run_agent.py"),
        Path("gateway/run.py"),
        Path("gateway/config.py"),
        Path("gateway/platforms/__init__.py"),
        Path("hermes_cli/config.py"),
    ]
    changed = oracle.changed_core_runtime_files()
    assert not changed.intersection(forbidden)
