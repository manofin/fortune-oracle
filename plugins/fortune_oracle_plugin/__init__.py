"""Fortune Oracle Hermes plugin entry point.

Connects the ``hermes_ext.fortune_oracle`` library to Hermes slash commands.
Handlers keep the gateway's ``fn(args) -> str`` signature: registration is
one-shot (no multi-turn state), and the caller is identified only through the
session variables the gateway binds before dispatching a plugin command. Outside
the gateway the target must be named explicitly (FORTUNE_ORACLE_USER or
FORTUNE_ORACLE_PROFILE); a stored profile is never picked automatically.

Optional plugin layout (web setup: docs/PUBLIC_SETUP.md)::

    ~/.hermes/plugins/fortune-oracle/
        __init__.py, plugin.yaml   this file and its manifest
        lib/hermes_ext/...         library copy (runtime independent of the dev checkout)
        vendor/                    plugin-only Python dependencies
        ephemeris/de440s.bsp       verified JPL kernel

From the repository checkout the library is found next to this directory.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent


def _bootstrap_paths() -> None:
    """Make the library and plugin-only dependencies importable."""
    candidates = [_PLUGIN_DIR / "vendor", _PLUGIN_DIR / "lib", _PLUGIN_DIR.parent]
    for path in candidates:
        if path.name == "vendor" and not path.is_dir():
            continue
        if path.name != "vendor" and not (path / "hermes_ext" / "fortune_oracle").is_dir():
            continue
        if str(path) not in sys.path:
            sys.path.append(str(path))
    kernel = _PLUGIN_DIR / "ephemeris" / "de440s.bsp"
    if kernel.is_file():
        os.environ.setdefault("FORTUNE_EPHEMERIS_PATH", str(kernel))


_bootstrap_paths()

from hermes_ext.fortune_oracle import bazi_bridge as _bazi_bridge  # noqa: E402
from hermes_ext.fortune_oracle import core as _core  # noqa: E402
from hermes_ext.fortune_oracle import deep_review as _deep_review  # noqa: E402
from hermes_ext.fortune_oracle import kline as _kline  # noqa: E402
from hermes_ext.fortune_oracle.store import FortuneStore  # noqa: E402


def _default_store_path() -> Path:
    override = os.environ.get("FORTUNE_ORACLE_STORE")
    if override:
        return Path(override)
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    return Path(home) / "fortune_oracle" / "store.json"


_STORE_PATH = _default_store_path()

DISCLAIMER = "이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다."
_DEEP_DISCLAIMER = "이 결과는 오락과 자기성찰용 참고입니다. 의학, 투자, 법률 결정을 지시하지 않습니다."
_REGISTER_EXAMPLE = "/register_birth 1990년 5월 17일 오후 12시 30분, 홍길동, 남성"

_REGISTER_GUIDE = (
    "사주 등록은 한 번에 입력해 주세요.\n"
    f"예: {_REGISTER_EXAMPLE}\n"
    "한국어 별칭: /사주등록 (형식 동일)\n"
    "\n"
    "이 봇은 multi-turn 대화형 등록을 지원하지 않습니다. 이어지는 메시지로 나누어 보내면 등록되지 않습니다.\n"
    "날짜·시각·이름·성별을 한 줄에 함께 보내 주세요. 출생 시각을 모르면 생략할 수 있습니다.\n"
    "등록 정보를 지우려면 /delete_profile 확인 을 보내세요."
)

_NO_PROFILE_TEXT = (
    "등록된 사주 정보가 없습니다.\n"
    "\n"
    f"{_REGISTER_GUIDE}\n"
    "\n"
    f"{DISCLAIMER}"
)

_HELP_TEXT = "\n".join([
    "Fortune Oracle",
    "",
    "[일일 운세]",
    "/today_fortune (/오늘운세) · /tomorrow_fortune (/내일운세) · /week_fortune (/이번주운세)",
    "등록 정보로 해당 날짜를 계산합니다. 점수·조언은 경험적 해석이며, 계산하지 못한 응답은 '계산 결과가 아님'으로 표시합니다.",
    "",
    "[K선]",
    "/month_kline (/월간운세) — 이번 달 일별 흐름",
    "/life_kline (/인생K선) — 올해 12개월 흐름",
    "/kline_card — 월간 K선 이미지, /kline_card year — 연간 이미지",
    "",
    "[사주 프로필]",
    f"/register_birth (/사주등록) — 한 번에 입력: {_REGISTER_EXAMPLE}",
    "/show_profile (/사주확인) · /profile_status · /delete_profile (/사주삭제)",
    "/bazi_trace (/팔자강약) — 오행 강약 근거 (경험적 참고)",
    "",
    "[풀이]",
    "/tarot 질문 · /iching 질문 · /compatibility 상대 YYYY-MM-DD [HH:MM] [IANA_ZONE]",
    "/oracle · /fortune_full (/종합운세) · /astro · /western",
    "/vedic — 베딕 출생 풀이 (전용 천체력 환경 필요)",
    "/qimen 질문 — KST 질문 시각 판; 지정 시각: /qimen YYYY-MM-DD HH:MM 질문",
    "/ziwei_deep — 자미두수 심층 서사 (기본 비활성); 계산 요약은 /oracle",
    "/deep_fortune (/심층운세) — 심층 풀이, full·qna·ask 질문 지원 (운영자 활성화 시 외부 모델 사용)",
    "/voice_fortune — 오늘 운세 음성 낭독, /voice_fortune tarot 질문 처럼 다른 풀이도 가능",
    "",
    "[알림·위치]",
    "/daily_on [HH:MM] · /daily_off — 다음 날부터 KST 아침(06:00–11:59) 운세 수신·해제",
    "/set_location 도시 | IANA_ZONE [| 위도 | 경도] · /clear_location",
    "",
    "등록은 multi-turn 대화가 아니라 한 줄 입력으로만 받습니다.",
    "출생시각을 생략하면 미상으로 저장하며 시주와 대운은 계산하지 않습니다.",
    DISCLAIMER,
])


# ---------------------------------------------------------------------------
# Identity and store
# ---------------------------------------------------------------------------

def _store() -> FortuneStore:
    return FortuneStore(_STORE_PATH)


def _harden_store_file() -> None:
    try:
        _STORE_PATH.parent.chmod(0o700)
        if _STORE_PATH.exists():
            _STORE_PATH.chmod(0o600)
    except OSError:
        logger.debug("fortune-oracle: could not tighten store permissions", exc_info=True)


def _session_identity() -> Optional[Tuple[str, str]]:
    """(platform, user_id) bound by the gateway for this command, or None outside the gateway."""
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return None
    platform = (get_session_env("HERMES_SESSION_PLATFORM") or "").strip().lower()
    user_id = (get_session_env("HERMES_SESSION_USER_ID") or "").strip()
    if not platform or not user_id:
        return None
    from hermes_ext.fortune_oracle.profile_key import sanitize_user_id
    return platform.replace(":", "_"), sanitize_user_id(user_id)


def _explicit_identity() -> Optional[Tuple[str, str]]:
    """``FORTUNE_ORACLE_USER=platform:user_id`` names the target user outside the gateway."""
    raw = (os.environ.get("FORTUNE_ORACLE_USER") or "").strip()
    platform, sep, user_id = raw.partition(":")
    if not sep or not platform.strip() or not user_id.strip():
        return None
    from hermes_ext.fortune_oracle.profile_key import sanitize_user_id
    return platform.strip().lower(), sanitize_user_id(user_id.strip())


def _owner_key() -> Optional[Tuple[str, str]]:
    """Store owner: the gateway user, else an explicitly named user. Never guessed."""
    return _session_identity() or _explicit_identity()


def _profile_file() -> Optional[Dict[str, Any]]:
    """``FORTUNE_ORACLE_PROFILE=<json path>`` supplies a profile directly (read-only)."""
    path = (os.environ.get("FORTUNE_ORACLE_PROFILE") or "").strip()
    if not path:
        return None
    import json
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("fortune-oracle: FORTUNE_ORACLE_PROFILE is not a readable JSON file")
        return None
    return dict(data) if isinstance(data, dict) and data.get("birth_date") else None


def _resolve_profile() -> Optional[Dict[str, Any]]:
    """The requesting user's profile, or None.

    Order: gateway session user, FORTUNE_ORACLE_PROFILE, FORTUNE_ORACLE_USER. Without one of
    these the target user is unknown and nothing is calculated; no stored profile is picked.
    """
    identity = _session_identity()
    if identity is None:
        from_file = _profile_file()
        if from_file is not None:
            return from_file
        identity = _explicit_identity()
    if identity is None:
        return None
    profile = _store().get_profile(*identity)
    return dict(profile) if profile and profile.get("birth_date") else None


_IDENTITY_REQUIRED = (
    "요청한 사용자를 확인할 수 없어 처리하지 않았습니다.\n"
    "Telegram 등 Hermes 대화에서 사용하거나, 로컬에서는 FORTUNE_ORACLE_USER=telegram:<user_id> 또는 "
    "FORTUNE_ORACLE_PROFILE=<프로필 JSON 경로>를 지정해 주세요."
)


def _no_profile_text() -> str:
    if _owner_key() is None and _profile_file() is None:
        return f"{_IDENTITY_REQUIRED}\n\n{_NO_PROFILE_TEXT}"
    return _NO_PROFILE_TEXT


def _safe(fn: Callable[[], str], fallback: str) -> str:
    try:
        text = fn()
    except Exception:
        logger.warning("fortune-oracle: handler failed", exc_info=True)
        return fallback
    return text if isinstance(text, str) and text.strip() else fallback


def _reading_text(result: Dict[str, Any]) -> str:
    return str(result.get("text") or result.get("text_fallback") or "")


# ---------------------------------------------------------------------------
# Bazi summaries
# ---------------------------------------------------------------------------

_STEM_ELEMENT = {"甲": "목", "乙": "목", "丙": "화", "丁": "화", "戊": "토",
                 "己": "토", "庚": "금", "辛": "금", "壬": "수", "癸": "수"}
_ELEMENT_TRAIT = {
    "목": "성장과 확장을 향하는 기질",
    "화": "표현과 열정이 앞서는 기질",
    "토": "안정과 신뢰를 중시하는 기질",
    "금": "원칙과 결단을 중시하는 기질",
    "수": "유연함과 깊은 사고를 지닌 기질",
}
_PILLAR_LABELS = (("year", "年"), ("month", "月"), ("day", "日"), ("time", "時"))


def _calc_bazi(profile: Optional[Dict[str, Any]]):
    if not profile or not profile.get("birth_date"):
        return None
    try:
        result = _bazi_bridge.calculate_bazi_from_profile(profile)
    except Exception:
        logger.info("fortune-oracle: bazi calculation unavailable", exc_info=True)
        return None
    if getattr(result, "ok", False) is not True or not isinstance(getattr(result, "eight_char", None), dict):
        return None
    return result


def _day_master(eight_char: Dict[str, str]) -> Tuple[str, str]:
    stem = (eight_char.get("day") or "")[:1]
    return stem, _STEM_ELEMENT.get(stem, "")


def _bazi_lines(result) -> List[str]:
    eight_char = result.eight_char
    pillars = " · ".join(f"{label} {eight_char.get(key, '')}" for key, label in _PILLAR_LABELS
                         if eight_char.get(key))
    lines = [f"팔자: {pillars}"]
    stem, element = _day_master(eight_char)
    if stem:
        trait = _ELEMENT_TRAIT.get(element, "")
        lines.append(f"기본 기질: 일간 {stem}({element}) — {trait}" if trait else f"기본 기질: 일간 {stem}")
    elements = getattr(result, "elements", None)
    if isinstance(elements, dict) and elements:
        # The bridge keys counts as "목(木)"; absent elements have no key.
        counts = {str(k)[:1]: v for k, v in elements.items()}
        lines.append("오행 분포: " + " · ".join(f"{k} {counts.get(k, 0)}" for k in ("목", "화", "토", "금", "수")))
    return lines


def _bazi_section(profile: Dict[str, Any]) -> str:
    result = _calc_bazi(profile)
    if result is None:
        return ""
    return "\n".join(["🔮 팔자 기질 참고", *_bazi_lines(result), DISCLAIMER])


# ---------------------------------------------------------------------------
# Profile handlers
# ---------------------------------------------------------------------------

def _normalize_profile(parsed: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    from hermes_ext.fortune_oracle.oracle_input import normalize_gender
    profile: Dict[str, Any] = {}
    for key in ("language", "life_context"):
        if previous and key in previous:
            profile[key] = previous[key]
    profile.update({
        "display_name": parsed.get("display_name") or "",
        "name_hanja": parsed.get("name_hanja") or "",
        "birth_date": parsed["birth_date"],
        "birth_time": parsed.get("birth_time") or "",
        "timezone": parsed.get("timezone") or "Asia/Seoul",
        "birth_place": parsed.get("birth_place") or "",
        "gender": normalize_gender(str(parsed.get("gender") or "")),
        "birth_year": int(parsed["birth_date"][:4]),
    })
    return profile


def _handle_register_birth(args):
    text = (args or "").strip()
    if not text:
        return _REGISTER_GUIDE
    from hermes_ext.fortune_oracle.birth_parser import parse_birth_input
    parsed = parse_birth_input(text)
    if not parsed.get("ok"):
        reason = parsed.get("error") or "날짜를 인식하지 못했습니다."
        return f"⚠️ 입력을 인식하지 못했습니다: {reason}\n\n{_REGISTER_GUIDE}"
    owner = _owner_key()
    if owner is None:
        return _IDENTITY_REQUIRED
    store = _store()
    platform, user_id = owner
    profile = _normalize_profile(parsed, store.get_profile(platform, user_id))
    store.save_profile(platform, user_id, profile)
    _harden_store_file()
    name = profile["display_name"]
    lines = [f"✅ {name}님의 사주 정보를 등록했습니다." if name else "✅ 사주 정보를 등록했습니다."]
    result = _calc_bazi(profile)
    if result is not None:
        lines += ["", *_bazi_lines(result)]
    else:
        lines += ["", "팔자 요약은 다음 /show_profile 에서 다시 계산합니다."]
    if parsed.get("warnings"):
        lines += ["", "참고: " + " / ".join(str(w) for w in parsed["warnings"][:2])]
    lines += ["", "확인: /show_profile · 삭제: /delete_profile 확인", DISCLAIMER]
    return "\n".join(lines)


def _handle_show_profile(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    name = profile.get("display_name") or "등록 사용자"
    lines = [f"{name}님의 사주 정보"]
    result = _calc_bazi(profile)
    if result is not None:
        lines += _bazi_lines(result)
        from hermes_ext.fortune_oracle.bazi_element_strength import build_show_profile_strength_note
        note = build_show_profile_strength_note(result.eight_char, max_lines=2)
        if note:
            lines += ["", note]
    else:
        lines.append("팔자 요약을 지금은 계산하지 못했습니다. 잠시 후 다시 확인해 주세요.")
    location = _location_summary(profile)
    if location:
        lines += ["", location]
    lines += ["", "변경: /register_birth 재등록 · 삭제: /delete_profile 확인", DISCLAIMER]
    return "\n".join(lines)


def _handle_profile_status(args):
    from hermes_ext.fortune_oracle.profile_management import format_profile_status, get_profile_status
    return format_profile_status(get_profile_status(_resolve_profile()))


def _handle_delete_profile(args):
    from hermes_ext.fortune_oracle.profile_management import format_delete_confirm
    if (args or "").strip() not in {"확인", "confirm", "yes"}:
        return ("등록된 사주 정보를 삭제하려면 /delete_profile 확인 을 보내 주세요.\n"
                "삭제하면 생년월일·출생 시각·이름·저장된 위치와 매일 운세 설정이 함께 지워지며 되돌릴 수 없습니다.")
    owner = _owner_key()
    if owner is None:
        return _IDENTITY_REQUIRED
    store = _store()
    platform, user_id = owner
    previous = store.get_profile(platform, user_id)
    store.delete_profile(platform, user_id)
    _harden_store_file()
    if not previous:
        return "삭제할 사주 정보가 없습니다. 저장된 위치와 매일 운세 수신 설정은 삭제했습니다."
    return format_delete_confirm(previous.get("display_name"))


# ---------------------------------------------------------------------------
# Daily readings and K-line
# ---------------------------------------------------------------------------

def _prepare(command: str, args: str = "", **kwargs) -> Dict[str, Any]:
    from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading
    text = f"/{command} {args}".strip()
    return prepare_reading(text, profile=_resolve_profile(), **kwargs)


def _with_register_hint(text: str, profile: Optional[Dict[str, Any]]) -> str:
    if profile:
        return text
    return f"{text}\n\n사주를 등록하면 개인화된 풀이를 받을 수 있습니다. 예: {_REGISTER_EXAMPLE}"


def _daily(command: str) -> str:
    profile = _resolve_profile()
    text = _reading_text(_prepare(command))
    if not text.strip():
        return "계산 결과가 아님\n운세를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."
    return _with_register_hint(text, profile)


def _handle_today_fortune(args):
    return _safe(lambda: _daily("today_fortune"), "계산 결과가 아님\n오늘 운세를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_tomorrow_fortune(args):
    return _safe(lambda: _daily("tomorrow_fortune"), "계산 결과가 아님\n내일 운세를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_week_fortune(args):
    return _safe(lambda: _daily("week_fortune"), "계산 결과가 아님\n이번 주 운세를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_month_kline(args):
    profile = _resolve_profile()
    return _safe(lambda: _with_register_hint(_kline.render_month_kline(profile=profile), profile),
                 "월간 K선을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_year_kline(args):
    return _safe(lambda: _with_register_hint(_reading_text(_prepare("year_kline", args)), _resolve_profile()),
                 "연간 K선을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_life_kline(args):
    profile = _resolve_profile()
    base = _safe(lambda: _kline.render_life_kline(profile=profile), "인생 K선을 준비하지 못했습니다.")
    if not profile:
        return (f"{base}\n\n사주를 등록하면 팔자 기질 참고 섹션이 함께 표시됩니다.\n"
                f"예: {_REGISTER_EXAMPLE}")
    section = _bazi_section(profile)
    return f"{base}\n\n{section}" if section else base


def _handle_kline_card(args):
    period = "year" if (args or "").strip().lower() in {"year", "연간", "올해"} else "month"
    profile = _resolve_profile()
    try:
        return _core.render_kline_card(profile=profile, period=period)
    except Exception:
        logger.warning("fortune-oracle: kline card failed", exc_info=True)
        return _with_register_hint(
            "K선 이미지를 만들지 못해 텍스트로 대신합니다. /month_kline 으로 월간 K선을 확인할 수 있습니다.",
            profile)


# ---------------------------------------------------------------------------
# Divination, compatibility, voice
# ---------------------------------------------------------------------------

def _handle_tarot(args):
    return _safe(lambda: _reading_text(_prepare("tarot", args)), "타로 카드를 펼치지 못했습니다. 다시 시도해 주세요.")


def _handle_iching(args):
    return _safe(lambda: _reading_text(_prepare("iching", args)), "주역 괘를 얻지 못했습니다. 다시 시도해 주세요.")


def _handle_compatibility(args):
    return _safe(lambda: _reading_text(_prepare("compatibility", args)),
                 "궁합을 계산하지 못했습니다. 입력 형식을 확인해 주세요.")


def _handle_voice_fortune(args):
    def run() -> str:
        result = _prepare("voice_fortune", args)
        if result.get("ok") and result.get("media_response"):
            return f"{result['media_response']}\n{result.get('text', '')}".strip()
        text = _reading_text(result) or "음성으로 읽을 풀이를 준비하지 못했습니다."
        return f"음성 합성을 사용할 수 없어 텍스트로 보내드립니다.\n\n{text}"
    return _safe(run, "음성 운세를 준비하지 못했습니다. 텍스트 명령 /today_fortune 을 이용해 주세요.")


# ---------------------------------------------------------------------------
# Daily push and location
# ---------------------------------------------------------------------------

def _handle_daily_on(args):
    time_hhmm = (args or "").strip() or "08:00"
    if not re.fullmatch(r"(0[6-9]|1[01]):[0-5]\d", time_hhmm):
        return "KST 아침 06:00–11:59 중 HH:MM 형식으로 입력해 주세요. 예: /daily_on 08:00"
    owner = _owner_key()
    if owner is None:
        return _IDENTITY_REQUIRED
    platform, user_id = owner
    target = ""
    try:
        from gateway.session_context import get_session_env
        target = get_session_env("HERMES_SESSION_CHAT_ID") or ""
    except Exception:
        target = ""
    if platform != "telegram" or not user_id.isdecimal() or (target and target != user_id):
        return "개인정보 보호를 위해 봇과의 Telegram 개인 대화에서 /daily_on 을 보내 주세요."
    _store().set_daily_push(platform, user_id, time_hhmm, target=user_id)
    _harden_store_file()
    return (f"다음 날부터 매일 KST {time_hhmm} 운세 수신에 동의했습니다.\n"
            "하루 최대 1회, 등록된 출생정보가 있을 때 보내드립니다. 해제: /daily_off\n"
            "발송 서비스 점검 중에는 도착하지 않을 수 있습니다.")


def _handle_daily_off(args):
    owner = _owner_key()
    if owner is None:
        return _IDENTITY_REQUIRED
    platform, user_id = owner
    _store().disable_daily_push(platform, user_id)
    return "매일 운세 수신을 해제했습니다."


def _location_key() -> Optional[str]:
    from hermes_ext.fortune_oracle.location_settings import build_location_profile_key
    owner = _owner_key()
    return build_location_profile_key(*owner) if owner else None


def _location_scope() -> Tuple[Optional[Dict[str, Any]], str, str]:
    """(store, platform, user_id) for saved-location lookups; no store when the user is unknown."""
    owner = _owner_key()
    if owner is None:
        return None, "telegram", "default"
    return _store()._load(), owner[0], owner[1]


def _location_summary(profile: Optional[Dict[str, Any]]) -> str:
    try:
        from hermes_ext.fortune_oracle.location_bridge import location_status_for_show_profile
        from hermes_ext.fortune_oracle.location_settings import build_astro_location_context
        key = _location_key()
        if key is None:
            return ""
        ctx = build_astro_location_context(store=_store()._load(), profile_key=key, profile=profile,
                                           has_birth_time=bool((profile or {}).get("birth_time")))
        return location_status_for_show_profile(ctx)
    except Exception:
        return ""


def _handle_set_location(args):
    from hermes_ext.fortune_oracle.location_settings import (
        parse_location_command, redact_location_for_display, save_location_settings,
    )
    text = (args or "").strip()
    if not text:
        return ("출생 위치를 한 줄로 입력해 주세요.\n"
                "예: /set_location Seoul, Korea | Asia/Seoul\n"
                "좌표까지: /set_location Seoul, Korea | Asia/Seoul | 37.5665 | 126.9780")
    try:
        settings = parse_location_command(text)
    except ValueError as exc:
        return f"위치를 인식하지 못했습니다: {exc}"
    key = _location_key()
    if key is None:
        return _IDENTITY_REQUIRED
    store = _store()
    with store.transaction() as data:
        save_location_settings(data, key, settings, dry_run=False)
    _harden_store_file()
    return f"위치를 저장했습니다: {redact_location_for_display(settings)}\n해제: /clear_location"


def _handle_clear_location(args):
    from hermes_ext.fortune_oracle.location_settings import clear_location_settings
    key = _location_key()
    if key is None:
        return _IDENTITY_REQUIRED
    store = _store()
    with store.transaction() as data:
        clear_location_settings(data, key, dry_run=False)
    return "저장된 위치를 지웠습니다. 사주 프로필은 그대로 유지됩니다."


# ---------------------------------------------------------------------------
# Multi-system readings
# ---------------------------------------------------------------------------

def _oracle_cards(profile: Dict[str, Any], *, include_qimen: bool = False, question: str = ""):
    from hermes_ext.fortune_oracle.oracle_input import from_profile
    from hermes_ext.fortune_oracle.oracle_method_adapters import adapt_all
    store, platform, user_id = _location_scope()
    return adapt_all(from_profile(profile), include_qimen=include_qimen, question=question,
                     store=store, platform=platform, user_id=user_id, profile=profile)


def _handle_oracle(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    from hermes_ext.fortune_oracle.oracle_renderer import render_final_reading
    return _safe(lambda: render_final_reading(_oracle_cards(profile), detailed=False),
                 "종합 풀이를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_fortune_full(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    from hermes_ext.fortune_oracle.oracle_renderer import render_final_reading
    return _safe(lambda: render_final_reading(_oracle_cards(profile), detailed=True),
                 "상세 종합 풀이를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_oracle_short(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    return _safe(lambda: _reading_text(_prepare("oracle_short")),
                 "짧은 풀이를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _astro_input(profile: Dict[str, Any]):
    from hermes_ext.fortune_oracle.astro_input import AstroBirthInput
    from hermes_ext.fortune_oracle.location_bridge import (
        apply_location_to_astro_input, build_location_context_for_command,
    )
    store, platform, user_id = _location_scope()
    loc_ctx = build_location_context_for_command(store=store, platform=platform, user_id=user_id,
                                                 profile=profile, has_birth_time=bool(profile.get("birth_time")))
    birth_time = profile.get("birth_time") or ""
    astro_inp = AstroBirthInput(
        name=profile.get("display_name", ""),
        gender=profile.get("gender", "unknown"),
        birth_datetime=f"{profile['birth_date']}T{birth_time}" if birth_time else profile["birth_date"],
        timezone=loc_ctx.timezone or profile.get("timezone") or "Asia/Seoul",
        latitude=loc_ctx.latitude,
        longitude=loc_ctx.longitude,
        birthplace_text=loc_ctx.label or profile.get("birth_place", ""),
    )
    apply_location_to_astro_input(astro_inp, loc_ctx)
    return astro_inp, loc_ctx


def _handle_astro(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    from hermes_ext.fortune_oracle.oracle_renderer import render_astro_summary
    store, platform, user_id = _location_scope()
    return _safe(lambda: render_astro_summary(
        birth_date=profile["birth_date"], birth_time=profile.get("birth_time") or "",
        timezone=profile.get("timezone") or "Asia/Seoul", profile=profile,
        store=store, platform=platform, user_id=user_id),
        "점성술 요약을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_western(args):
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()

    def run() -> str:
        from hermes_ext.fortune_oracle.location_bridge import format_location_basis
        from hermes_ext.fortune_oracle.western_bridge import calculate_western_chart
        from hermes_ext.fortune_oracle.western_interpreter import interpret_western_chart
        astro_inp, loc_ctx = _astro_input(profile)
        return f"{format_location_basis(loc_ctx)}\n\n{interpret_western_chart(calculate_western_chart(astro_inp))}"
    return _safe(run, "서양 점성술 차트를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_vedic(args):
    profile = _resolve_profile()
    if not profile:
        return "계산 결과가 아님\n" + _no_profile_text()

    def run() -> str:
        from hermes_ext.fortune_oracle.location_bridge import format_location_basis
        from hermes_ext.fortune_oracle.vedic_bridge import calculate_vedic_chart
        from hermes_ext.fortune_oracle.vedic_interpreter import interpret_vedic_chart
        astro_inp, loc_ctx = _astro_input(profile)
        return interpret_vedic_chart(calculate_vedic_chart(astro_inp),
                                     location_basis=format_location_basis(loc_ctx))
    return _safe(run, "계산 결과가 아님\n베딕 출생 풀이를 준비하지 못했습니다. 출생정보와 계산 환경을 확인해 주세요.")


def _handle_qimen(args):
    from hermes_ext.fortune_oracle import qimen_interpreter
    text = (args or "").strip()
    dated = re.match(r"^\d{4}-\d{2}-\d{2}(?=\s|T|$)", text)
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})(?:\s+(.*))?", text)

    def run() -> str:
        if match:
            return qimen_interpreter.format_qimen_at(match.group(1), match.group(2) or "")
        if dated:
            # An explicit date requires an explicit time; never substitute noon or now.
            return qimen_interpreter.format_qimen_at("")
        return qimen_interpreter.format_qimen_now(text)
    return _safe(run, "계산 결과가 아님\n기문둔갑 판을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_ziwei_deep(args):
    if not _deep_enabled():
        return ("자미두수 심층 서사는 외부 언어 모델을 사용하므로 현재 비활성화되어 있습니다.\n"
                "계산된 자미두수 요약은 /oracle 에서 확인할 수 있습니다.")
    profile = _resolve_profile()
    if not profile:
        return _no_profile_text()
    from hermes_ext.fortune_oracle.platforms.telegram import prepare_ziwei_deep
    return _safe(lambda: _reading_text(prepare_ziwei_deep(profile=profile)),
                 "자미두수 심층 서사를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _handle_bazi_trace(args):
    profile = _resolve_profile()
    result = _calc_bazi(profile)
    if result is None:
        return ("등록된 사주 정보가 없어 오행(목·화·토·금·수) 강약 근거를 계산하지 않았습니다.\n"
                f"{_REGISTER_EXAMPLE} 처럼 한 번에 등록하면 일간과 오행 분포 근거를 보여드립니다.\n"
                "오행 강약은 경험적 참고이며 확정적 판단이 아닙니다. 자기성찰용으로만 읽어 주세요.")
    from hermes_ext.fortune_oracle.bazi_element_strength import build_show_profile_strength_note
    from hermes_ext.fortune_oracle.bazi_trace import build_bazi_trace, build_trace_summary
    from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
    eight_char = result.eight_char
    try:
        yongshen = calculate_yongshen(eight_char)
    except Exception:
        yongshen = None
    lines = ["팔자 강약 근거", *_bazi_lines(result)]
    for block in (build_show_profile_strength_note(eight_char, max_lines=3),
                  build_trace_summary(build_bazi_trace(eight_char, yongshen_result=yongshen), max_lines=6)):
        if block:
            lines += ["", block]
    lines += ["", "오행 강약은 경험적 참고이며 확정적 판단이 아닙니다. 자기성찰용으로만 읽어 주세요."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deep fortune (/deep_fortune): opt-in provider, deterministic otherwise
# ---------------------------------------------------------------------------

_DEEP_DISABLED_NOTICE = (
    "심층 운세는 현재 비활성화되어 있습니다.\n"
    "provider를 호출하지 않고 계산된 팔자 요약만으로 기본 풀이를 보여드립니다.\n"
    "활성화하려면 운영자가 FORTUNE_DEEP_ANALYSIS=1과 local provider 설정을 적용해야 합니다."
)
_DEEP_FAILURE_NOTICE = "현재 심층 분석 provider 응답이 안정적이지 않아 기본 해석으로 전환했습니다."
_TAHEO_TITLE = "태허의 운명분석 Question & Answer"
_RAW_REPR = re.compile(r"[A-Za-z_]+\(.*=|ok=|warnings=\[|default_factory|dataclass|^\s*[\[{]")


def _deep_enabled() -> bool:
    from hermes_ext.fortune_oracle.deep_provider_health import deep_provider_default_off
    return not deep_provider_default_off()


def _default_provider_factory():
    from hermes_ext.fortune_oracle.deep_provider_health import deep_provider_env_snapshot
    from hermes_ext.fortune_oracle.deep_qopus_provider import make_qopus_provider
    snap = deep_provider_env_snapshot()
    return make_qopus_provider(base_url=snap["base_url"], model=snap["model"], timeout=snap["timeout_sec"])


def _deep_style_from_args(args) -> str:
    first = (args or "").strip().split(maxsplit=1)
    return "taheo_qna" if first and first[0].lower() in {"full", "qna", "전체", "문답"} else "short"


def _append_preview_section(lines: List[str], title: str, body) -> None:
    text = str(body or "").strip()
    if text:
        lines.append(f"[{title}] {text}")


def _clean_context_value(value, replacement: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return replacement if _RAW_REPR.search(text) else text


def _build_taheo_fallback(context: Dict[str, Any], profile: Dict[str, Any], reason: str) -> str:
    sections = [
        ("명식 산출 검토", _clean_context_value(context.get("eight_char"), "명식 원문 대신 계산 요약만 참고합니다.")),
        ("해석의 핵심 구조", _clean_context_value(context.get("elements"), "오행 분포는 요약 수치로만 참고합니다.")),
        ("관계 흐름과 재배치 압력", _clean_context_value(
            context.get("relation_summary"), "관계 흐름은 특정 사건보다 내적 기준과 선택의 재배치로 일반화해 읽습니다.")),
        ("대운 흐름", _clean_context_value(
            context.get("dayun_summary"), "대운 흐름은 확정 예언이 아니라 장기 리듬을 보는 참고 지표입니다.")),
        ("용신 참고", _clean_context_value(
            context.get("yongshen_summary"), "용신 참고는 절대 판정이 아니라 균형을 보는 보조 정보입니다. 이 판단은 rule-based 참고입니다.")),
    ]
    life = str(context.get("life_context_summary") or "").strip()
    reality = (f"사용자가 직접 알려준 현실 맥락을 함께 읽습니다: {life}" if life else
               "사용자가 알려준 현실 맥락이 없어 특정 직업이나 사건을 단정하지 않고, "
               "현재의 직업적 전환감이나 역할 변화 정도로 일반화해 읽습니다.")
    blocks = [_TAHEO_TITLE,
              "태허의 운명분석으로서 계산된 명식 요약만으로 흐름을 정리합니다. 선택권은 언제나 사용자에게 있습니다."]
    for title, body in sections:
        if body:
            blocks.append(f"[{title}]\n{body}")
    blocks.append(f"[현실 연결]\n{reality}")
    if any(body for _, body in sections):
        blocks.append("[최종 조언]\n지금은 오래 쌓아온 역할과 새로 펼치고 싶은 방향을 함께 점검해 보는 때로 읽습니다.")
    blocks.append(_DEEP_DISCLAIMER)
    return "\n\n".join(blocks)


def _build_short_preview(context: Dict[str, Any], dayun) -> str:
    lines = ["심층 운세 미리보기"]
    eight_char = str(context.get("eight_char") or "")
    day_stem = ""
    match = re.search(r"일주:(\S)", eight_char)
    if match:
        day_stem = match.group(1)
    element = _STEM_ELEMENT.get(day_stem, "")
    if day_stem:
        _append_preview_section(lines, "기본 기질", f"일간 {day_stem}({element}) — {_ELEMENT_TRAIT.get(element, '')}".rstrip(" —"))
    _append_preview_section(lines, "오행 흐름", context.get("elements"))
    _append_preview_section(lines, "관계 흐름", context.get("relation_summary"))
    _append_preview_section(lines, "용신 참고", context.get("yongshen_summary"))
    if getattr(dayun, "direction", "unknown") not in (None, "", "unknown"):
        _append_preview_section(lines, "대운 흐름", context.get("dayun_summary"))
    _append_preview_section(lines, "K선 흐름", context.get("kline_summary"))
    lines.append(_DEEP_DISCLAIMER)
    return "\n".join(lines)


def _kline_summary(profile: Dict[str, Any]) -> str:
    try:
        candles = _kline.build_yearly_kline(profile)
        return _kline.summarize_kline(candles, unit="개월") if candles else ""
    except Exception:
        return ""


def _build_deep_fortune_material(profile: Dict[str, Any], *, reason: str = "disabled",
                                 style: str = "short") -> Tuple[Dict[str, Any], str]:
    """Privacy-safe provider context and the deterministic fallback text."""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
    bazi = _calc_bazi(profile)
    eight_char = bazi.eight_char if bazi is not None else None
    # The legacy skeleton substitutes age seven without a solar-term calculation.
    # Do not send that estimate to a model as personal calculation evidence.
    # The K-line summary below already carries the existing calculated cycle.
    relation = dayun = yongshen = None
    if eight_char:
        for name, call in (
            ("relation", lambda: detect_relations(eight_char)),
            ("yongshen", lambda: calculate_yongshen(eight_char)),
        ):
            try:
                value = call()
            except Exception:
                value = None
            if name == "relation":
                relation = value
            else:
                yongshen = value
    context = _deep_review.build_deep_review_context(profile, bazi, None, relation, dayun, yongshen)
    context["kline_summary"] = _kline_summary(profile) if bazi is not None else ""
    context["style"] = style
    if style == "taheo_qna":
        return context, _build_taheo_fallback(context, profile, reason)
    return context, _build_short_preview(context, dayun)


def _format_provider_result(result: Dict[str, Any], style: str, source: str) -> str:
    if style == "taheo_qna":
        blocks = [str(result.get("title") or _TAHEO_TITLE)]
        for section in result.get("sections", []):
            body = "\n".join(str(section.get(k) or "").strip() for k in ("body", "emphasis") if section.get(k))
            blocks.append(f"[{str(section.get('heading') or '').strip()}]\n{body}".strip())
        if result.get("final_advice"):
            blocks.append(f"[최종 조언]\n{str(result['final_advice']).strip()}")
    else:
        blocks = ["심층 운세"]
        for section in result.get("sections", []):
            text = "\n".join(str(section.get(k) or "").strip() for k in ("title", "summary") if section.get(k))
            if section.get("reflection_question"):
                text += f"\n질문: {str(section['reflection_question']).strip()}"
            blocks.append(text)
        if result.get("reflection_question"):
            blocks.append(f"자기성찰 질문\n{str(result['reflection_question']).strip()}")
    blocks += [f"source: {source}", _DEEP_DISCLAIMER]
    notice = "계산 결과가 아님 — 계산된 요약을 바탕으로 외부 모델이 작성한 해석입니다. 성향과 조언은 경험적 참고입니다."
    return notice + "\n\n" + "\n\n".join(b for b in blocks if b)


def _split_telegram_long_text(text: str, limit: int = 3200) -> str:
    if len(text) <= limit:
        return text
    parts: List[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        while len(paragraph) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > limit:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    total = len(parts)
    return "\n\n".join(f"[{i}부/{total}]\n{part}" for i, part in enumerate(parts, 1))


def _make_provider(provider_factory):
    try:
        return (provider_factory or _default_provider_factory)()
    except Exception:
        logger.warning("fortune-oracle: deep provider unavailable")
        return None


def _deep_ask(args: str, profile: Optional[Dict[str, Any]], provider_factory) -> str:
    from hermes_ext.fortune_oracle.deep_provider_health import build_provider_source
    from hermes_ext.fortune_oracle.deep_question_router import (
        ASK_USAGE, analyze_oracle_question, extract_question, format_oracle_answer,
    )
    question = extract_question(args)
    if not question:
        return ASK_USAGE
    if not profile:
        return _no_profile_text()
    enabled = _deep_enabled()
    context, _ = _build_deep_fortune_material(profile, reason="disabled" if not enabled else "provider_failure")
    provider = _make_provider(provider_factory) if enabled else None
    result = analyze_oracle_question(question, context, provider=provider, enabled=provider is not None)
    if result.get("source") == "deep_provider":
        result["source"] = build_provider_source()
    text = format_oracle_answer(result, include_disabled_notice=not enabled)
    if enabled and result.get("source") == "template":
        text = f"{_DEEP_FAILURE_NOTICE}\n\n{text}"
    return _split_telegram_long_text(text)


def _handle_deep_fortune(args, provider_factory=None):
    """Deep fortune. Calls the provider only when FORTUNE_DEEP_ANALYSIS=1 and a profile exists."""
    from hermes_ext.fortune_oracle.deep_question_router import is_ask_request
    args = (args or "").strip()
    profile = _resolve_profile()
    try:
        if is_ask_request(args):
            return _deep_ask(args, profile, provider_factory)
        if not profile:
            return _no_profile_text()
        style = _deep_style_from_args(args)
        enabled = _deep_enabled()
        context, fallback = _build_deep_fortune_material(
            profile, reason="disabled" if not enabled else "provider_failure", style=style)
        if not enabled:
            return _split_telegram_long_text(f"{_DEEP_DISABLED_NOTICE}\n\n{fallback}")
        provider = _make_provider(provider_factory)
        result = _deep_review.analyze_deep_review(context, provider=provider, enabled=provider is not None)
        if result.get("source") != "deep_provider":
            return _split_telegram_long_text(f"{_DEEP_FAILURE_NOTICE}\n\n{fallback}")
        from hermes_ext.fortune_oracle.deep_provider_health import build_provider_source
        return _split_telegram_long_text(_format_provider_result(result, style, build_provider_source()))
    except Exception:
        logger.warning("fortune-oracle: deep fortune failed")
        return "심층 운세를 지금은 준비하지 못했습니다. /show_profile 로 기본 팔자 요약을 확인해 주세요."


def _handle_help(args):
    return _HELP_TEXT


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# (command, handler, description). Gateway matches /today_fortune to today-fortune.
_COMMANDS: List[Tuple[str, Callable[..., str], str]] = [
    ("fortune-help",     _handle_help,              "Fortune Oracle 명령 안내"),
    ("도움말",            _handle_help,              "Fortune Oracle 명령 안내"),
    ("today-fortune",    _handle_today_fortune,     "오늘 운세"),
    ("오늘운세",          _handle_today_fortune,     "오늘 운세"),
    ("tomorrow-fortune", _handle_tomorrow_fortune,  "내일 운세"),
    ("내일운세",          _handle_tomorrow_fortune,  "내일 운세"),
    ("week-fortune",     _handle_week_fortune,      "이번 주 운세"),
    ("이번주운세",        _handle_week_fortune,      "이번 주 운세"),
    ("month-kline",      _handle_month_kline,       "월간 K선"),
    ("월간운세",          _handle_month_kline,       "월간 K선"),
    ("life-kline",       _handle_life_kline,        "올해 12개월 인생 K선"),
    ("인생k선",           _handle_life_kline,        "올해 12개월 인생 K선"),
    ("year-kline",       _handle_year_kline,        "연간 K선"),
    ("kline-card",       _handle_kline_card,        "K선 이미지 카드 (year 지원)"),
    ("register-birth",   _handle_register_birth,    "사주 등록 (한 줄 입력)"),
    ("사주등록",          _handle_register_birth,    "사주 등록 (한 줄 입력)"),
    ("show-profile",     _handle_show_profile,      "등록된 사주 확인"),
    ("사주확인",          _handle_show_profile,      "등록된 사주 확인"),
    ("profile-status",   _handle_profile_status,    "프로필 등록 상태"),
    ("delete-profile",   _handle_delete_profile,    "사주 정보 삭제"),
    ("사주삭제",          _handle_delete_profile,    "사주 정보 삭제"),
    ("bazi-trace",       _handle_bazi_trace,        "팔자 오행 강약 근거"),
    ("팔자강약",          _handle_bazi_trace,        "팔자 오행 강약 근거"),
    ("tarot",            _handle_tarot,             "타로 3장"),
    ("타로",              _handle_tarot,             "타로 3장"),
    ("iching",           _handle_iching,            "주역 점"),
    ("주역",              _handle_iching,            "주역 점"),
    ("compatibility",    _handle_compatibility,     "두 사람 궁합"),
    ("궁합",              _handle_compatibility,     "두 사람 궁합"),
    ("voice-fortune",    _handle_voice_fortune,     "운세 음성 낭독"),
    ("운세음성",          _handle_voice_fortune,     "운세 음성 낭독"),
    ("daily-on",         _handle_daily_on,          "매일 운세 수신 켜기"),
    ("daily-off",        _handle_daily_off,         "매일 운세 수신 끄기"),
    ("set-location",     _handle_set_location,      "출생 위치 설정"),
    ("clear-location",   _handle_clear_location,    "출생 위치 삭제"),
    ("oracle",           _handle_oracle,            "다체계 종합 풀이"),
    ("fortune-full",     _handle_fortune_full,      "상세 종합 풀이"),
    ("종합운세",          _handle_fortune_full,      "상세 종합 풀이"),
    ("oracle-short",     _handle_oracle_short,      "짧은 풀이"),
    ("짧은운세",          _handle_oracle_short,      "짧은 풀이"),
    ("astro",            _handle_astro,             "점성술 요약"),
    ("western",          _handle_western,           "서양 점성술"),
    ("vedic",            _handle_vedic,             "베딕 출생 풀이 (전용 천체력 환경 필요)"),
    ("qimen",            _handle_qimen,             "기문둔갑 질문 시각 판"),
    ("기문",              _handle_qimen,             "기문둔갑 질문 시각 판"),
    ("ziwei-deep",       _handle_ziwei_deep,        "자미두수 심층 서사 (운영자 활성화 시)"),
    ("deep-fortune",     _handle_deep_fortune,      "심층 운세 (full·qna·ask)"),
    ("심층운세",          _handle_deep_fortune,      "심층 운세 (full·qna·ask)"),
]


def register(ctx) -> None:
    for name, handler, description in _COMMANDS:
        try:
            ctx.register_command(name, handler=handler, description=description)
        except Exception:
            logger.warning("fortune-oracle: could not register /%s", name, exc_info=True)
    from hermes_ext.fortune_oracle.public_telegram import enabled, make_factory
    if enabled():
        native_register = getattr(ctx, "register_telegram_handler", None)
        if callable(native_register):
            native_register(make_factory({name: handler for name, handler, _ in _COMMANDS}))
        else:
            logger.warning("fortune-oracle: public Telegram ingress requires native handler support")
