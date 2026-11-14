"""Fortune Oracle — deep provider controlled pilot helpers (Phase 23).

No network call is made at import time.  Live checks are opt-in helper calls.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

DEFAULT_MODEL = "gemma-crack"
DEFAULT_MODEL_LABEL = "gemma-crack"
DEFAULT_PROVIDER = "local_openai_compatible"


def deep_provider_env_snapshot(env: Optional[dict[str, str]] = None) -> Dict[str, Any]:
    e = env if env is not None else os.environ
    return {
        "enabled": e.get("FORTUNE_DEEP_ANALYSIS", "").strip() == "1",
        "provider": e.get("FORTUNE_DEEP_PROVIDER", DEFAULT_PROVIDER) or DEFAULT_PROVIDER,
        # 주소 기본값 없음: 미지정이면 빈 문자열로 남긴다. 호출자는
        # deep_qopus_provider.resolve_base_url()로 유효성을 판단하고,
        # 주소가 없으면 네트워크 호출을 시도하지 않는다.
        "base_url": (e.get("FORTUNE_DEEP_BASE_URL", "") or "").strip(),
        "model": e.get("FORTUNE_DEEP_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
        "model_label": e.get("FORTUNE_DEEP_MODEL_LABEL", DEFAULT_MODEL_LABEL) or DEFAULT_MODEL_LABEL,
        "timeout_sec": int(e.get("FORTUNE_DEEP_TIMEOUT_SEC", "30") or "30"),
    }


def deep_provider_default_off(env: Optional[dict[str, str]] = None) -> bool:
    e = env if env is not None else os.environ
    return e.get("FORTUNE_DEEP_ANALYSIS", "").strip() != "1"


def build_provider_source(snapshot: Optional[Dict[str, Any]] = None) -> str:
    snap = snapshot or deep_provider_env_snapshot()
    label = str(snap.get("model_label") or snap.get("model") or DEFAULT_MODEL_LABEL)
    if "gemma" in label.lower() or "crack" in label.lower():
        label = "gemma-crack"
    return f"local_openai_compatible:{label}"


def provider_readiness_check(
    *,
    check_models: Optional[Callable[[str, int], Dict[str, Any]]] = None,
    env: Optional[dict[str, str]] = None,
) -> Dict[str, Any]:
    """Return readiness metadata. Optional check_models performs live /v1/models smoke."""
    snap = deep_provider_env_snapshot(env)
    result: Dict[str, Any] = {
        "ok": True,
        "live_checked": False,
        "default_off": not snap["enabled"],
        "source": build_provider_source(snap),
        "snapshot": snap,
        "warnings": [],
    }
    if snap["enabled"]:
        result["warnings"].append("enabled mode requires explicit operator approval before production use")
    if check_models is None:
        result["warnings"].append("live /v1/models check not executed")
        return result
    if not snap["enabled"]:
        result["warnings"].append("disabled: live check not executed")
        return result
    # 주소가 없으면 조회 자체를 하지 않는다 — 빈 문자열로 호출하지 않는다.
    if not str(snap["base_url"]).strip():
        result["ok"] = False
        result["live_checked"] = False
        result["warnings"].append(
            "provider endpoint 미지정: FORTUNE_DEEP_BASE_URL 설정이 필요합니다"
            " (live check를 실행하지 않음)"
        )
        return result
    try:
        live = check_models(str(snap["base_url"]), int(snap["timeout_sec"]))
        result["live_checked"] = True
        result["models"] = live.get("models", []) if isinstance(live, dict) else []
        result["ok"] = bool(live.get("reachable")) if isinstance(live, dict) else False
        if not result["ok"]:
            result["warnings"].append("models endpoint unreachable")
    except Exception as exc:
        result["ok"] = False
        result["live_checked"] = True
        result["warnings"].append(f"readiness check failed: {type(exc).__name__}")
    return result
