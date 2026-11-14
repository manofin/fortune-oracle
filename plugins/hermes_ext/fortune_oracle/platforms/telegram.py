#!/usr/bin/env python3
"""Telegram adapter helpers for Fortune Oracle."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

CANONICAL_COMMANDS = {
    "tarot",
    "iching",
    "compatibility",
    "today_fortune",
    "tomorrow_fortune",
    "week_fortune",
    "register_birth",
    "show_profile",
    "delete_profile",
    "profile_status",
    "voice_fortune",
    "daily_on",
    "daily_off",
    "life_kline",
    "year_kline",
    "month_kline",
    "kline_card",
    "deep_fortune",
    "help",
    "qimen",
    "bazi_trace",
    "oracle_short",  # Phase 39: short deterministic fortune
    "ziwei_deep",  # ZD-5: /ziwei_deep 자허 심층 서사 + 자허 비평 에이전트 (critique+rewrite)
}

COMMAND_ALIASES = {
    "today": "today_fortune",
    "tomorrow": "tomorrow_fortune",
    "week": "week_fortune",
    "tarot": "tarot",
    "타로": "tarot",
    "iching": "iching",
    "주역": "iching",
    "compatibility": "compatibility",
    "궁합": "compatibility",
    "today_fortune": "today_fortune",
    "오늘운세": "today_fortune",
    "tomorrow_fortune": "tomorrow_fortune",
    "내일운세": "tomorrow_fortune",
    "week_fortune": "week_fortune",
    "이번주운세": "week_fortune",
    "register_birth": "register_birth",
    "사주등록": "register_birth",
    "show_profile": "show_profile",
    "사주확인": "show_profile",
    "delete_profile": "delete_profile",
    "사주삭제": "delete_profile",
    "profile_status": "profile_status",
    "프로필상태": "profile_status",
    "voice_fortune": "voice_fortune",
    "운세음성": "voice_fortune",
    "daily_on": "daily_on",
    "매일운세켜기": "daily_on",
    "daily_off": "daily_off",
    "매일운세끄기": "daily_off",
    # K-line commands
    "life_kline": "life_kline",
    "인생K선": "life_kline",
    "year_kline": "year_kline",
    "올해운세": "year_kline",
    "month_kline": "month_kline",
    "월간운세": "month_kline",
    "운세차트": "month_kline",
    "kline_card": "kline_card",
    "deep_fortune": "deep_fortune",
    "심층운세": "deep_fortune",
    "qimen": "qimen",
    "기문": "qimen",
    "oracle_short": "oracle_short",
    "짧은운세": "oracle_short",
    "ziwei_deep": "ziwei_deep",
    "자미두수": "ziwei_deep",
    "심층자미": "ziwei_deep",
    "ziwei-deep": "ziwei_deep",
    "help": "help",
    "도움말": "help",
}

_BOT_COMMAND_RE = re.compile(r"^[a-z0-9_]+$")


def bot_command_names() -> list[str]:
    """Canonical commands safe for Telegram BotCommand registration."""
    return sorted(CANONICAL_COMMANDS)


def validate_canonical_bot_commands() -> bool:
    return all(_BOT_COMMAND_RE.fullmatch(command) for command in CANONICAL_COMMANDS)


def parse_command(text: str) -> Optional[Dict[str, str]]:
    """Parse canonical Telegram commands and Korean convenience aliases.

    The returned canonical value is always a bot-safe English command name.
    Korean commands are user input aliases only; they are not for BotCommand
    registration.
    """
    stripped = text.strip()
    if not stripped:
        return None
    parts = stripped.split(maxsplit=1)
    first, rest = parts[0], parts[1] if len(parts) == 2 else ""
    token = first[1:] if first.startswith("/") else first
    if "@" in token:
        token = token.split("@", 1)[0]
    canonical = COMMAND_ALIASES.get(token)
    if not canonical:
        return None
    return {"command": canonical, "args": rest.strip(), "raw": stripped}


def to_telegram_text(text: str) -> str:
    """Telegram can preserve simple Markdown text from core/session renderers."""
    return text.strip()


def split_plain_text(text: str, limit: int = 3500) -> list[str]:
    """Preserve every character while reserving room below Telegram's limit."""
    pieces = []
    while len(text) > limit:
        boundary = text.rfind("\n", 0, limit)
        boundary = boundary + 1 if boundary >= limit // 2 else limit
        pieces.append(text[:boundary])
        text = text[boundary:]
    if text:
        pieces.append(text)
    return pieces


def prepare_divination(text: str, *, rng=None) -> Dict[str, Any]:
    """Resolve /tarot or /iching input through a real draw and interpretation.

    Optional replay syntax: question | 0 8r 21 (tarot, r means reversed),
    question | 7 8 7 8 7 8 (I Ching, bottom to top).
    Returns plain text: send without Telegram Markdown parse mode.
    """
    from ..divination import build_tarot_reading, build_iching_reading, ReadingInputError
    parsed = parse_command(text)
    if not parsed or parsed["command"] not in {"tarot", "iching"}:
        return {"ok": False, "error": "unsupported_command", "text": "타로 또는 주역 명령을 입력해 주세요."}
    command = parsed["command"]
    question, separator, replay = parsed["args"].partition("|")
    try:
        if command == "tarot":
            draws = None
            if separator:
                tokens = replay.replace(",", " ").split()
                if len(tokens) != 3 or any(not re.fullmatch(r"\d{1,2}[rR]?", t) for t in tokens):
                    raise ReadingInputError("카드 3장을 지정해 주세요. 예: /tarot 질문 | 0 8r 21")
                draws = [(int(t.rstrip("rR")), t[-1:] in {"r", "R"}) for t in tokens]
            return build_tarot_reading(question.strip(), draws=draws, rng=rng)
        lines = None
        if separator:
            tokens = replay.replace(",", " ").split()
            if len(tokens) != 6 or any(t not in {"6", "7", "8", "9"} for t in tokens):
                raise ReadingInputError("아래부터 효값 6개를 입력해 주세요. 예: /iching 질문 | 7 8 7 8 7 8")
            lines = [int(t) for t in tokens]
        return build_iching_reading(question.strip(), lines=lines, rng=rng)
    except ReadingInputError as error:
        return {"ok": False, "error": "invalid_input", "text": str(error)}
    except Exception:
        return {"ok": False, "error": "draw_unavailable", "text": "추첨을 완료하지 못했습니다. 다시 시도해 주세요."}


def prepare_reading(text: str, *, profile=None, partner_profile=None, rng=None, tts=None, output_root=None,
                    language=None, reading_timezone=None, now=None) -> Dict[str, Any]:
    """Local dispatcher for the three P1 readings. Does not look up other users.

    /compatibility date [time] [IANA zone] | date [time] [IANA zone] supplies both profiles explicitly.
    With the caller's own `profile`, a single date [time] [IANA zone] supplies the partner.
    All responses are plain text; no Telegram Markdown parse mode is needed.
    """
    from ..compatibility import build_compatibility, _valid_profile
    parsed = parse_command(text)
    from ..localization import language_code
    from ..reading_localization import localize_reading
    try:
        code = language_code(language if language is not None else (profile or {}).get("language"))
    except ValueError:
        return {"ok": False, "computed": False, "error": "unsupported_language",
                "text": "계산 결과가 아님 / Not a calculated result\nUnsupported language; use ko or en."}
    if partner_profile is not None and (not parsed or parsed["command"] not in {"compatibility", "voice_fortune"}):
        return localize_reading({"ok": False, "error": "invalid_input", "text":
                "상대 프로필은 궁합 명령에만 사용합니다."}, code)
    if parsed and parsed["command"] == "help":
        from ..oracle import help_text
        return {"ok": True, "kind": "help", "language": code, "text": help_text(code)}
    if parsed and parsed["command"] in {"deep_fortune", "oracle_short", "qimen"}:
        from ..combined_reading import prepare_combined_reading
        if parsed["command"] != "qimen" and parsed["args"]:
            return {"ok": False, "error": "invalid_input", "language": code,
                    "text": "Use your supplied birth profile; this command takes no additional text."
                    if code == "en" else "전달된 출생 프로필을 사용합니다. 추가 텍스트는 입력하지 않습니다."}
        result = prepare_combined_reading(profile, language=code, detailed=parsed["command"] == "deep_fortune",
                                         question=parsed["args"] if parsed["command"] == "qimen" else None)
        result["messages"] = split_plain_text(result["text"])
        return result
    if parsed and parsed["command"] in {"month_kline", "life_kline", "year_kline", "kline_card"}:
        from ..daily_reading import prepare_kline_reading
        return prepare_kline_reading(profile, command=parsed["command"], args=parsed["args"], language=code,
                                     reading_timezone=reading_timezone, now=now)
    if parsed and parsed["command"] in {"today_fortune", "tomorrow_fortune", "week_fortune"}:
        from ..daily_reading import prepare_daily_reading
        day = {"today_fortune": "today", "tomorrow_fortune": "tomorrow", "week_fortune": "week"}[parsed["command"]]
        return prepare_daily_reading(profile, day=day, language=language,
                                     reading_timezone=reading_timezone, now=now)
    if parsed and parsed["command"] == "voice_fortune":
        from ..speech import prepare_daily_voice, synthesize_reading
        if not parsed["args"]:
            if partner_profile is not None:
                return localize_reading({"ok": False, "error": "invalid_input", "text": "궁합 명령을 지정해 주세요."}, code)
            if language is not None or reading_timezone is not None or now is not None or (profile and profile.get("language")):
                from ..daily_reading import prepare_daily_reading
                reading = prepare_daily_reading(profile, language=language, reading_timezone=reading_timezone, now=now)
                return synthesize_reading(reading, tts=tts, output_root=output_root)
            return prepare_daily_voice(profile, tts=tts, output_root=output_root)
        nested = parse_command(parsed["args"])
        if not nested or nested["command"] not in {"tarot", "iching", "compatibility", "today_fortune", "tomorrow_fortune", "week_fortune", "month_kline", "life_kline", "year_kline", "deep_fortune", "oracle_short", "qimen"}:
            return localize_reading({"ok": False, "error": "invalid_input", "text_fallback":
                    "/voice_fortune 또는 /voice_fortune tarot 질문처럼 입력해 주세요."}, code)
        reading = prepare_reading(parsed["args"], profile=profile, partner_profile=partner_profile, rng=rng, language=language,
                                  reading_timezone=reading_timezone, now=now)
        return synthesize_reading(reading, tts=tts, output_root=output_root)
    if parsed and parsed["command"] in {"tarot", "iching"}:
        return localize_reading(prepare_divination(text, rng=rng), code)
    if not parsed or parsed["command"] != "compatibility":
        return localize_reading({"ok": False, "error": "unsupported_command", "text": "타로·주역·궁합 명령을 입력해 주세요."}, code)
    def supplied_profile(value):
        parts = value.split()
        if len(parts) not in {1, 2, 3}:
            raise ValueError
        candidate = {"birth_date": parts[0]}
        remaining = parts[1:]
        if remaining and ":" in remaining[0]:
            candidate["birth_time"] = remaining.pop(0)
        if remaining:
            if len(remaining) != 1:
                raise ValueError
            candidate["timezone"] = remaining[0]
        if not _valid_profile(candidate):
            raise ValueError
        return candidate
    try:
        first, separator, second = parsed["args"].partition("|")
        if partner_profile is not None:
            if parsed["args"] or profile is None:
                raise ValueError
            a, b = profile, partner_profile
        elif separator:
            a, b = supplied_profile(first), supplied_profile(second)
        elif profile is not None:
            a, b = profile, supplied_profile(first)
        else:
            raise ValueError
        return localize_reading(build_compatibility(a, b), code)
    except ValueError:
        return localize_reading({"ok": False, "error": "invalid_input", "text":
                "출생정보 두 개를 입력해 주세요. 예: /compatibility 1990-05-15 07:30 | 1988-03-02 22:10\n"
                "내 프로필이 전달된 경우 상대의 YYYY-MM-DD [HH:MM] [IANA_ZONE]만 입력할 수 있습니다."}, code)


def prepare_kline_card(
    *,
    profile: Optional[Dict[str, Any]] = None,
    period: str = "month",
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    """Telegram용 /kline_card 응답 준비.

    Returns:
        {
            "ok": True,
            "media_response": "MEDIA:/tmp/fortune_kline_XXX.png\n<caption>",
            "png_path": "/tmp/fortune_kline_XXX.png",
            "caption": "<caption>",
        }
        또는 실패 시:
        {
            "ok": False,
            "text_fallback": "<텍스트 fallback>",
            "error": "<이유>",
        }

    민감 출생정보(birth_date, birth_time, birth_place, name_hanja)는
    caption, 파일명 어디에도 포함하지 않는다.
    """
    from ..core import render_kline_card

    result = render_kline_card(profile=profile, period=period, year=year, month=month)

    if result.startswith("MEDIA:"):
        lines = result.split("\n", 2)
        # MEDIA:/path 추출
        media_line = lines[0]                        # "MEDIA:/tmp/..."
        png_path = media_line[len("MEDIA:"):].strip()
        caption = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        return {
            "ok": True,
            "media_response": result,
            "png_path": png_path,
            "caption": caption,
        }
    else:
        return {
            "ok": False,
            "text_fallback": to_telegram_text(result),
            "error": "renderer_unavailable",
        }


def prepare_voice_fortune(
    *,
    text: str,
    tts_available: bool,
    audio_file: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Telegram voice policy: send voice only when TTS succeeded, else fallback text."""
    if not tts_available or not audio_file:
        return {"ok": False, "text_fallback": to_telegram_text(text), "error": "TTS unavailable"}
    from ..speech import inspect_audio
    audio = inspect_audio(audio_file)
    if audio is None:
        return {"ok": False, "text_fallback": to_telegram_text(text), "error": "TTS audio unavailable"}
    delivery = "voice" if audio["voice_compatible"] else "audio" if audio["format"] == "mp3" else "document"
    return {"ok": True, "text": to_telegram_text(text), "audio_file": audio["path"],
            "duration_ms": audio["duration_ms"], "delivery": delivery}


def prepare_oracle_short(
    *,
    profile: Optional[Dict[str, Any]] = None,
    full_reading: str = "",
) -> Dict[str, Any]:
    """Phase 39 — /oracle_short, /짧은운세
    deep provider 호출 없이 deterministic 2~3문장 요약 반환.
    loading phrase와 fallback phrase bank 사용.
    raw traceback/error leak 완전 차단.
    """
    from ..oracle_short_renderer import (
        render_oracle_short,
        get_loading_phrase,
        get_fallback_phrase,
    )
    import random

    if not profile or not profile.get("birth_date"):
        return {
            "ok": True,
            "text": "등록된 사주 정보가 없습니다.\n/register_birth 명령으로 먼저 등록해주세요.",
        }

    if random.random() < 0.15:  # UX polish - loading phrase
        return {
            "ok": True,
            "text": get_loading_phrase(),
        }

    if full_reading:
        short_text = render_oracle_short(full_reading=full_reading, profile=profile)
    else:
        short_text = get_fallback_phrase()

    return {
        "ok": True,
        "text": to_telegram_text(short_text),
    }


def prepare_ziwei_deep(
    *,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """1-pass stable path (use_critic=False default). Critic/rewrite code preserved behind flag for future experiments.

    생산 경로: calculate_ziwei_chart → generate_deep_narrative_with_critique
      - 첫 초안 안전 생성 (safety_check + retry)
      - 자허 비평 에이전트: 삭제·정정·유지 후보 만 출력 (재작성 금지)
      - 자허 본체 재작성: 비평 후보를 받아 밀도 ↑, 풍부함·정통성·목소리·안전 보호
    1회 기본 패스 (비용 N배이므로 /ziwei_deep 프리미엄 전용).
    fail-open: 모든 예외에서 안전 메시지 반환, 다른 기능 영향 없음.
    Telegram 4096자 제한 대응: 초과 시 truncate + 노트.
    선응답: "🔮 자허(紫虛)가 명반을 읽고 있어요... (약 3분 정도 걸려요)"
    """
    from ..deep_transport import deep_enabled
    if not deep_enabled():
        return {"ok": False, "text": "자미두수 심층 서사는 현재 비활성화되어 있습니다. 계산 요약은 /oracle 에서 확인해 주세요."}
    if not profile or not profile.get("birth_date"):
        return {
            "ok": False,
            "text": "등록된 사주 정보가 없습니다.\n\n/register_birth 명령으로 먼저 등록해주세요.",
        }

    try:
        from ..ziwei_bridge import calculate_ziwei_chart
        from ..ziwei_deep_llm import generate_deep_narrative_with_critique

        birth_date = profile.get("birth_date", "")
        birth_time = profile.get("birth_time") or ""
        if not birth_time:
            return {"ok": False, "text": "계산 결과가 아님\n출생시각이 없어 자미두수 심층 풀이를 준비하지 않았습니다."}
        gender = profile.get("gender")

        # production path: returns facts with birth_sihua + current (daxian) sihua, brightness, etc.
        chart_facts = calculate_ziwei_chart(
            birth_date, birth_time, gender=gender,
            calendar=profile.get("calendar", "solar"),
            is_leap_month=profile.get("is_leap_month", False),
        )

        if not chart_facts or chart_facts.get("ok") is False:
            return {
                "ok": False,
                "text": "자미두수 차트 계산에 실패했습니다. 잠시 후 다시 시도해주세요.",
            }

        # All enrichment (ming_gong, sihua conversion, daxian + daxian_sihua) 
        # is now done inside calculate_ziwei_chart for consistency across /oracle, adapters, deep etc.
        name = profile.get("display_name", profile.get("name", "사용자"))

        gen = generate_deep_narrative_with_critique(
            chart_facts=chart_facts,
            name=name,
            temperature=0.7,
            max_retries=1,
            use_critic=False,  # ZD-5 critic disabled by default; stable 1-pass only
        )

        if gen.get("ok") and gen.get("text"):
            text = gen["text"]
            # Telegram limit handling (4096 chars). Truncate with note for safety; full split can be done at send time.
            if len(text) > 4000:
                text = text[:3900] + "\n\n... (메시지 길이 제한으로 일부 생략. /ziwei_deep 재호출 또는 자허 참고)"
            return {
                "ok": True,
                "text": to_telegram_text("출처: 외부 모델 · local_openai_compatible:local-writer\n\n" + text),
            }
        else:
            safe_msg = "지금 자허가 명반을 읽기 어려워요. 잠시 후 다시 시도해주세요."
            return {
                "ok": False,
                "text": safe_msg,
            }
    except Exception:
        return {
            "ok": False,
            "text": "지금 자허가 명반을 읽기 어려워요. 잠시 후 다시 시도해주세요.",
        }
