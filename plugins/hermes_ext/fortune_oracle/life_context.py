"""Fortune Oracle — optional life context helpers (Phase 27).

Only user-provided real-life context may be used.  This module never infers
occupation, career history, family status, project names, or recent events from
birth data or bazi output.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

ALLOWED_LIFE_CONTEXT_FIELDS = (
    "occupation_context",
    "creative_context",
    "recent_context",
    "project_context",
)

_MAX_FIELD_CHARS = 120
_MAX_SUMMARY_CHARS = 360
_SENSITIVE_KEYS = ("birth_date", "birth_time", "name_hanja")
_RAW_DUMP_MARKERS = (
    "YongshenResult(",
    "DayunResult(",
    "BaziRelationReport(",
    "dataclass",
    "default_factory",
    "warnings=[",
    "ok=True",
    "ok=False",
)


def _clean_value(value: Any, max_chars: int = _MAX_FIELD_CHARS) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    text = str(value or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in _RAW_DUMP_MARKERS):
        return ""
    text = " ".join(text.split())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def normalize_life_context(raw: Any) -> Dict[str, str]:
    """Return a sanitized life_context dict containing allowlisted fields only."""
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for key in ALLOWED_LIFE_CONTEXT_FIELDS:
        value = _clean_value(raw.get(key))
        if value:
            result[key] = value
    return result


def has_life_context(profile: Dict[str, Any] | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return bool(normalize_life_context(profile.get("life_context")))


def build_life_context_summary(profile: Dict[str, Any] | None, *, max_chars: int = _MAX_SUMMARY_CHARS) -> str:
    """Build a provider/fallback-safe summary from explicitly provided context.

    No birth_date, birth_time, name_hanja, Telegram ids, or profile keys are read.
    """
    if not isinstance(profile, dict):
        return ""
    ctx = normalize_life_context(profile.get("life_context"))
    if not ctx:
        return ""
    labels = {
        "occupation_context": "직업 맥락",
        "creative_context": "창작 맥락",
        "recent_context": "최근 맥락",
        "project_context": "프로젝트 맥락",
    }
    parts = [f"{labels[key]}: {ctx[key]}" for key in ALLOWED_LIFE_CONTEXT_FIELDS if key in ctx]
    summary = " / ".join(parts)
    return summary if len(summary) <= max_chars else summary[: max_chars - 1].rstrip() + "…"


def life_context_presence_mask(profile: Dict[str, Any] | None) -> Dict[str, bool]:
    ctx = normalize_life_context(profile.get("life_context")) if isinstance(profile, dict) else {}
    return {key: key in ctx for key in ALLOWED_LIFE_CONTEXT_FIELDS}


def assert_no_sensitive_life_context_keys(keys: Iterable[str]) -> bool:
    return not any(key in _SENSITIVE_KEYS for key in keys)
