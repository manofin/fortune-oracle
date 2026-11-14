#!/usr/bin/env python3
"""Fortune Oracle public facade.

The implementation is split into platform-neutral core/session/store/privacy and
thin platform adapters. This module preserves the previous import surface used
by existing LINE tests and scripts while avoiding LINE/Telegram code copying.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional, Set

from .core import (
    FORTUNE_PROMPT_POLICY,
    render_daily_fortune as _render_today,
    render_fortune as _render_fortune,
    render_tomorrow_fortune,
    render_weekly_fortune,
    get_daily_candle_score,
    render_kline_card,
)
from .privacy import GROUP_CHAT_TYPES, is_group_chat, profile_for_display, redact_for_disk, redact_sensitive
from .session import AnalysisSession, StageResult
from .store import FortuneStore, make_key
from .kline import (
    FortuneCandle,
    build_daily_candle,
    build_monthly_kline,
    build_yearly_kline,
    summarize_kline,
    render_life_kline,
    render_month_kline,
    kline_card_phase1_fallback,
)
from .platforms.line import (
    LINE_COMMANDS,
    chunk_line_text,
    env_requirements,
    is_line_source_allowed,
    is_private_dm,
    may_register_profile,
    parse_env_list,
    prepare_voice_fortune,
    prepare_kline_text as prepare_line_kline_text,
    to_line_plain_text,
)
from .platforms.telegram import (
    CANONICAL_COMMANDS as TELEGRAM_CANONICAL_COMMANDS,
    bot_command_names as telegram_bot_command_names,
    parse_command as parse_telegram_command,
    prepare_voice_fortune as prepare_telegram_voice_fortune,
    prepare_divination,
    prepare_reading,
    to_telegram_text,
    validate_canonical_bot_commands,
)

COMMANDS = LINE_COMMANDS

CORE_RUNTIME_FILES = {
    Path("run_agent.py"),
    Path("gateway/run.py"),
    Path("gateway/config.py"),
    Path("gateway/platforms/__init__.py"),
    Path("hermes_cli/config.py"),
}


def render_daily_fortune(day: str = "today", *, profile: Optional[dict] = None) -> str:
    """Backward-compatible renderer returning LINE-safe plain text."""
    return to_line_plain_text(_render_fortune(day, profile=profile))


def render_daily_fortune_core(*, profile: Optional[dict] = None) -> str:
    return _render_today(profile=profile)


def help_text(language="ko") -> str:
    from .localization import language_code
    if language_code(language) == "en":
        return "\n".join(["Fortune Oracle commands",
            "/today, /tomorrow, /week — calculated readings in your current time zone",
            "Scores and advice are heuristic interpretations. Unavailable results start with 'Not a calculated result'.",
            "/tarot question — three cards; replay: question | 0 8r 21",
            "/iching question — three coins per line; replay: question | 7 8 7 8 7 8 (bottom first)",
            "/compatibility YYYY-MM-DD [HH:MM] [IANA_ZONE] | YYYY-MM-DD [HH:MM] [IANA_ZONE] — compare two profiles",
            "/voice_fortune — daily narration; or /voice_fortune tarot question",
            "/month_kline, /life_kline, /kline_card — calculated K-line readings",
            "/deep_fortune, /oracle_short — combined birth-chart facts and calculation limitations",
            "/qimen question — a separate question-time chart; not a birth chart",
            "Set language=en and reading_timezone to an IANA zone such as America/Los_Angeles.",
            "CLI: add --lang en; use --profile for your birth profile JSON."])
    return to_line_plain_text("\n".join(["Hermes Fortune Oracle 명령어", *COMMANDS,
        "일일·내일·7일 풀이의 점수·조언은 경험적 해석입니다. 비계산 응답은 '계산 결과가 아님'으로 표시합니다.",
        "/tarot 질문 — 3장 펼치기 (재현: 질문 | 0 8r 21)",
        "/iching 질문 — 3동전법 (재현: 질문 | 7 8 7 8 7 8, 아래부터)",
        "/compatibility YYYY-MM-DD [HH:MM] [IANA_ZONE] | YYYY-MM-DD [HH:MM] [IANA_ZONE] — 두 사람 비교",
        "/voice_fortune — 개인화 일일 운세 음성 (또는 /voice_fortune tarot 질문)"]))


def collect_daily_push_targets(store: FortuneStore, *, platform: Optional[str] = None):
    return store.collect_daily_push_targets(platform=platform)


def changed_core_runtime_files(repo: Path | str = ".") -> Set[Path]:
    """Return changed files that are part of core runtime registration.

    This helper is read-only and is used by tests to ensure fortune-oracle work
    does not modify Hermes core runtime or gateway adapter registration.
    """
    root = Path(repo)
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return set()
    changed: Set[Path] = set()
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path = Path(path_text)
        if path in CORE_RUNTIME_FILES:
            changed.add(path)
    return changed


def main() -> None:
    """Public local CLI, shared by the package and legacy module entry points."""
    import argparse

    parser = argparse.ArgumentParser(description="Hermes fortune oracle helper")
    parser.add_argument("command", choices=["today", "tomorrow", "week", "help", "env", "telegram-commands", "tarot", "iching", "compatibility", "voice_fortune", "month_kline", "life_kline", "year_kline", "kline_card", "deep_fortune", "oracle_short", "qimen"])
    parser.add_argument("reading_input", nargs="*", help="질문과 선택적 | 재현 값")
    parser.add_argument("--json", action="store_true", help="추첨 결과와 근거를 JSON으로 출력")
    parser.add_argument("--voice", action="store_true", help="계산된 풀이를 기존 Hermes TTS로 읽기")
    parser.add_argument("--profile", type=Path, help="내 프로필 JSON 파일 (자동 조회·저장 없음)")
    parser.add_argument("--partner-profile", type=Path, help="궁합 상대 프로필 JSON 파일")
    parser.add_argument("--lang", choices=["ko", "en"], help="풀이 언어 / Reading language")
    parser.add_argument("--reading-timezone", help="현재 거주지 IANA 시간대 (예: America/Los_Angeles)")
    args = parser.parse_args()
    if args.voice and args.command not in {"today", "tomorrow", "week", "tarot", "iching", "compatibility", "voice_fortune", "month_kline", "life_kline", "year_kline", "deep_fortune", "oracle_short", "qimen"}:
        parser.error("--voice는 풀이 명령과 함께 사용합니다.")
    partner_profile = None
    if args.partner_profile:
        if args.command not in {"compatibility", "voice_fortune"}:
            parser.error("--partner-profile은 궁합 명령에만 사용합니다.")
        try:
            partner_profile = json.loads(args.partner_profile.read_text())
            if not isinstance(partner_profile, dict):
                raise ValueError
        except (OSError, ValueError):
            parser.error("상대 프로필 JSON 파일을 읽을 수 없습니다.")
    profile = None
    if args.profile:
        try:
            profile = json.loads(args.profile.read_text())
            if not isinstance(profile, dict):
                raise ValueError
        except (OSError, ValueError):
            parser.error("프로필 JSON 파일을 읽을 수 없습니다.")
    if args.lang is not None or args.reading_timezone is not None:
        profile = dict(profile or {})
        if args.lang is not None:
            profile["language"] = args.lang
        if args.reading_timezone is not None:
            profile["reading_timezone"] = args.reading_timezone
    if args.command in {"today", "tomorrow", "week"} and (args.lang or args.reading_timezone or args.json or args.voice or (profile and profile.get("language"))):
        if args.reading_input:
            parser.error("일일 풀이에는 추가 텍스트를 입력하지 않습니다.")
        from .daily_reading import prepare_daily_reading
        result = prepare_daily_reading(profile, day=args.command)
        if args.voice:
            from .speech import synthesize_reading
            result = synthesize_reading(result)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
              result.get("media_response") or result.get("text") or result.get("text_fallback", ""))
        raise SystemExit(0 if result["ok"] else 1)
    if args.command in {"tarot", "iching", "compatibility", "voice_fortune", "month_kline", "life_kline", "year_kline", "kline_card", "deep_fortune", "oracle_short", "qimen"}:
        result = prepare_reading("/" + args.command + " " + " ".join(args.reading_input), profile=profile, partner_profile=partner_profile)
        if args.voice and args.command != "voice_fortune":
            from .speech import synthesize_reading
            result = synthesize_reading(result)
        output = result.get("media_response") or result.get("text") or result.get("text_fallback", "")
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else output)
        raise SystemExit(0 if result["ok"] else 1)
    elif args.reading_input:
        parser.error("추가 입력은 tarot·iching·compatibility에서만 사용합니다.")
    elif args.command == "today":
        print(render_daily_fortune("today", profile=profile))
    elif args.command == "tomorrow":
        print(render_daily_fortune("tomorrow", profile=profile))
    elif args.command == "week":
        print(render_daily_fortune("week", profile=profile))
    elif args.command == "help":
        print(help_text((profile or {}).get("language")))
    elif args.command == "env":
        print(json.dumps(env_requirements(), ensure_ascii=False, indent=2))
    elif args.command == "telegram-commands":
        print(json.dumps(telegram_bot_command_names(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
