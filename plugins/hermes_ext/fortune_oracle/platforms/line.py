#!/usr/bin/env python3
"""LINE adapter helpers for Fortune Oracle."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

LINE_COMMANDS = [
    "/사주등록",
    "/사주확인",
    "/사주삭제",
    "/오늘운세",
    "/내일운세",
    "/이번주운세",
    "/운세음성",
    "/사주정밀",
    "/통합분석",
    "/매일운세켜기 HH:MM",
    "/매일운세끄기",
    "/인생K선",
    "/올해운세",
    "/월간운세",
    "/운세차트",
    "/도움말",
]


def _as_set(values: Optional[Iterable[str]]) -> Set[str]:
    return {str(v).strip() for v in values or [] if str(v).strip()}


def parse_env_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def is_line_source_allowed(
    source: Mapping[str, Any],
    *,
    allowed_users: Optional[Iterable[str]] = None,
    allowed_groups: Optional[Iterable[str]] = None,
    allowed_rooms: Optional[Iterable[str]] = None,
    allow_all: bool = False,
) -> bool:
    if allow_all:
        return True
    users = _as_set(allowed_users)
    groups = _as_set(allowed_groups)
    rooms = _as_set(allowed_rooms)
    source_type = str(source.get("type", ""))
    if source_type == "user":
        return str(source.get("userId", "")) in users
    if source_type == "group":
        return str(source.get("groupId", "")) in groups
    if source_type == "room":
        return str(source.get("roomId", "")) in rooms
    return False


def is_private_dm(source: Mapping[str, Any]) -> bool:
    return str(source.get("type", "")) == "user" and bool(source.get("userId"))


def may_register_profile(
    source: Mapping[str, Any],
    *,
    allowed_users: Optional[Iterable[str]] = None,
    allowed_groups: Optional[Iterable[str]] = None,
    allowed_rooms: Optional[Iterable[str]] = None,
    allow_all: bool = False,
) -> bool:
    return is_line_source_allowed(
        source,
        allowed_users=allowed_users,
        allowed_groups=allowed_groups,
        allowed_rooms=allowed_rooms,
        allow_all=allow_all,
    )


def to_line_plain_text(text: str) -> str:
    """Strip markdown unsupported by LINE while preserving readable content."""
    text = _LINK_RE.sub(r"\1 (\2)", text)
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("`", ""), text)
    replacements = ["**", "__", "`", "###", "##", "#", "* ", "> ", "*"]
    for marker in replacements:
        text = text.replace(marker, "")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def chunk_line_text(text: str, *, max_chars: int = 5000, max_chunks: int = 5) -> List[str]:
    plain = to_line_plain_text(text)
    if not plain:
        return [""]
    chunks = [plain[i : i + max_chars] for i in range(0, len(plain), max_chars)]
    if len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
        chunks[-1] = chunks[-1][: max_chars - 1] + "…"
    return chunks


def prepare_voice_fortune(*, text: str, public_url: str, audio_file: Path | str) -> Dict[str, Any]:
    """Prepare a LINE voice fortune response. LINE media requires public HTTPS."""
    plain = to_line_plain_text(text)
    if not public_url:
        return {"ok": False, "error": "LINE_PUBLIC_URL is required for LINE audio send", "text_fallback": plain}
    from urllib.parse import urlsplit
    try:
        url = urlsplit(str(public_url))
        valid_url = url.scheme == "https" and bool(url.hostname) and not (url.query or url.fragment or url.username or url.password)
    except ValueError:
        valid_url = False
    if not valid_url:
        return {"ok": False, "error": "LINE_PUBLIC_URL must be public HTTPS", "text_fallback": plain}
    audio_path = Path(audio_file)
    from ..speech import inspect_audio
    from uuid import uuid4
    audio = inspect_audio(audio_path)
    if audio is None or audio["format"] != "mp3":
        return {"ok": False, "error": "Verified MP3 audio is required", "text_fallback": plain}
    # Generated jobs share the basename narration.mp3. A basename URL can point
    # two users at the same asset; publish each verified file under an opaque key.
    media_key = uuid4().hex + '.mp3'
    media_url = f"{public_url.rstrip('/')}/line/media/fortune-oracle/{media_key}"
    return {"ok": True, "text": plain, "audio_file": audio["path"], "media_url": media_url,
            "media_key":media_key,
            "duration_ms": audio["duration_ms"],
            "message": {"type": "audio", "originalContentUrl": media_url, "duration": audio["duration_ms"]}}


def prepare_kline_text(text: str, *, public_url: Optional[str] = None) -> Dict[str, Any]:
    """LINE K선 출력 준비. LINE은 plain text 유지; image/card는 LINE_PUBLIC_URL 없으면 fail-closed text fallback."""
    plain = to_line_plain_text(text)
    if not public_url or not str(public_url).startswith("https://"):
        return {"ok": True, "text": plain, "image_fallback": True,
                "note": "K선 이미지 카드는 Phase 2에서 구현 예정입니다. 텍스트로 제공합니다."}
    return {"ok": True, "text": plain, "image_fallback": False}


def env_requirements() -> Dict[str, Any]:
    required = ["LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET", "LINE_PUBLIC_URL", "LINE_HOME_CHANNEL"]
    allow = ["LINE_ALLOWED_USERS", "LINE_ALLOWED_GROUPS"]
    missing = [name for name in required if not os.getenv(name)]
    if not any(os.getenv(name) for name in allow):
        missing.append("LINE_ALLOWED_USERS or LINE_ALLOWED_GROUPS")
    return {
        "required": required,
        "allowlist": allow,
        "missing": missing,
        "webhook_path": "/line/webhook",
        "config": "gateway.platforms.line.enabled: true",
        "cron_deliver": "line",
        "cron_target_env": "LINE_HOME_CHANNEL",
    }
