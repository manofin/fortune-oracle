"""Fortune Oracle — privacy/redaction audit helpers (Phase 28)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

SENSITIVE_FIELD_NAMES = (
    "birth_date",
    "birth_time",
    "name_hanja",
    "telegram_user_id",
    "profile_store_key",
)

RAW_REPR_MARKERS = (
    "YongshenResult(",
    "DayunResult(",
    "BaziRelationReport(",
    "dataclass",
    "default_factory",
    "warnings=[",
    "ok=True",
    "ok=False",
)

SAFE_SOURCE_PREFIXES = (
    "template",
    "deep_provider",
    "local_openai_compatible:",
)


def collect_known_sensitive_values(profile: Dict[str, Any] | None, *, extra: Iterable[str] = ()) -> List[str]:
    values: List[str] = []
    if isinstance(profile, dict):
        for key in ("birth_date", "birth_time", "name_hanja"):
            value = str(profile.get(key) or "").strip()
            if value:
                values.append(value)
    for value in extra:
        value = str(value or "").strip()
        if value:
            values.append(value)
    return list(dict.fromkeys(values))


def contains_sensitive_value(text: Any, sensitive_values: Iterable[str]) -> bool:
    haystack = str(text or "")
    return any(value and value in haystack for value in sensitive_values)


def contains_raw_repr(text: Any) -> bool:
    haystack = str(text or "")
    return any(marker in haystack for marker in RAW_REPR_MARKERS)


def redact_text(text: Any, sensitive_values: Iterable[str], replacement: str = "***") -> str:
    result = str(text or "")
    for value in sensitive_values:
        if value:
            result = result.replace(value, replacement)
    return result


def audit_text_blob(label: str, text: Any, sensitive_values: Iterable[str]) -> Dict[str, Any]:
    failures: List[str] = []
    if contains_sensitive_value(text, sensitive_values):
        failures.append("sensitive_value_leak")
    if contains_raw_repr(text):
        failures.append("raw_repr_leak")
    return {"label": label, "ok": not failures, "failures": failures}


def is_safe_deep_source(source: Any) -> bool:
    value = str(source or "")
    if not value:
        return True
    if any(secret in value for secret in ("birth_date", "birth_time", "name_hanja", "telegram:")):
        return False
    return value == "template" or value == "deep_provider" or value.startswith("local_openai_compatible:")
