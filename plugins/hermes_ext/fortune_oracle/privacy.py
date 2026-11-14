#!/usr/bin/env python3
"""Privacy helpers: redaction for sensitive fields and tokens."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping

SENSITIVE_KEYS = {
    "birth_date",
    "birth_time",
    "birth_place",
    "name_hanja",
    "line_channel_access_token",
    "line_channel_secret",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
    "telegram_bot_token",
    "TELEGRAM_BOT_TOKEN",
}

GROUP_CHAT_TYPES = {"group", "room", "supergroup"}


def redact_sensitive(value: Any) -> Any:
    """Recursively redact birth profile fields and tokens."""
    if isinstance(value, Mapping):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_text in SENSITIVE_KEYS or key_lower in SENSITIVE_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def redact_for_disk(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Keep actual profile values on disk, but never persist tokens."""
    import json

    cleaned = json.loads(json.dumps(data, ensure_ascii=False))
    for key in ("LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET", "TELEGRAM_BOT_TOKEN"):
        cleaned.pop(key, None)
    return cleaned


def profile_for_display(
    profile: Mapping[str, Any], *, source_type: str = "user"
) -> Dict[str, Any]:
    """Never expose raw birth fields in group/room displays."""
    if source_type in GROUP_CHAT_TYPES:
        return redact_sensitive(dict(profile))
    return dict(profile)


def is_group_chat(source_type: str) -> bool:
    """Return True if the source is a group/room/supergroup context."""
    return source_type in GROUP_CHAT_TYPES
