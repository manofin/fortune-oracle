"""Fortune Oracle — local OpenAI-compatible local-writer provider (Phase 18A)

이 모듈은 운영이 지정한 OpenAI-compatible endpoint를 사용하는 provider
adapter입니다. endpoint 주소는 코드에 포함하지 않고 환경변수
``FORTUNE_DEEP_BASE_URL``에서만 읽습니다. 주소가 없으면 어떤 호출도
시도하지 않습니다(하드코딩 fallback 없음).

안전 원칙:
- import 시 client 생성 없음
- 명시적 호출 시에만 네트워크 접근
- FORTUNE_DEEP_ANALYSIS=1 설정 없이는 adapter가 활성화되지 않음
- FORTUNE_DEEP_BASE_URL 미설정/빈 값/공백이면 네트워크 호출 전에 차단
- birth_date, birth_time, name_hanja prompt 미포함
- timeout 필수 (기본 30초)
- 실패 시 exception 전파 없음 -> structured failure 반환
- 공급자 SDK나 숨은 endpoint fallback 없이 운영이 지정한 주소만 사용
- 지정 주소의 네트워크 범위와 운영 승인은 호출 전에 확인

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional
from .deep_transport import deep_enabled, bounded_timeout, read_json_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# local OpenAI-compatible endpoint 설정 상수 (import 시 네트워크 접근 없음)
# ---------------------------------------------------------------------------

QOPUS_DEFAULT_MODEL: str = "gemma-crack"
QOPUS_MODEL_ID: str = "gemma-crack"
QOPUS_DEFAULT_API_KEY = os.environ.get("FORTUNE_DEEP_API_KEY", "")
QOPUS_DEFAULT_TIMEOUT_SEC: int = 30
QOPUS_MAX_TOKENS: int = 1024
QOPUS_MAX_RESPONSE_CHARS: int = 8000

SUPPORTED_PROVIDER_NAME: str = "local_openai_compatible"
SUPPORTED_MODEL_ALIAS: str = "gemma-crack"

# 운영이 지정한 provider endpoint. 코드에 기본값을 두지 않는다 —
# 주소가 없으면 호출 자체를 하지 않는다(하드코딩 fallback 금지).
BASE_URL_ENV_VAR: str = "FORTUNE_DEEP_BASE_URL"


def resolve_base_url(explicit: Optional[str] = None) -> Optional[str]:
    """운영 지정 provider 주소를 반환한다. 없으면 None.

    판정 순서: 명시 인자 → 환경변수. 두 곳 모두 없거나 공백이면 None.
    None을 반환한 호출자는 네트워크 접근을 시도하지 않아야 한다.
    """
    for candidate in (explicit, os.environ.get(BASE_URL_ENV_VAR)):
        if candidate and candidate.strip():
            return candidate.strip()
    logger.warning(
        "%s 미설정 — provider 호출을 차단합니다(하드코딩 fallback 없음).", BASE_URL_ENV_VAR
    )
    return None


# ---------------------------------------------------------------------------
# Provider response sanitizing
# ---------------------------------------------------------------------------


def _strip_json_code_fence(content: str) -> str:
    """LLM이 JSON을 ```json fence로 감싼 경우 fence만 제거한다."""
    text = content.strip()
    if text.startswith("```json") and text.endswith("```"):
        return text[len("```json") : -len("```")].strip()
    if text.startswith("```") and text.endswith("```"):
        return text[len("```") : -len("```")].strip()
    return text


# ---------------------------------------------------------------------------
# Structured failure helper
# ---------------------------------------------------------------------------


def _make_failure_response(reason: str) -> str:
    """provider 실패 시 JSON fallback 문자열 반환."""
    payload: Dict[str, Any] = {
        "ok": False,
        "source": "local_openai_compatible:gemma-crack",
        "sections": [],
        "reflection_question": "",
        "disclaimer": "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
        "warnings": [f"local_openai_compatible provider failure: {reason}"],
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Source tag helper
# ---------------------------------------------------------------------------


def build_qopus_source_tag(model: str = QOPUS_DEFAULT_MODEL) -> str:
    """Provider source tag를 반환한다."""
    return f"{SUPPORTED_PROVIDER_NAME}:{model}"


# ---------------------------------------------------------------------------
# Environment-based enabled check
# ---------------------------------------------------------------------------


def is_qopus_enabled() -> bool:
    """FORTUNE_DEEP_ANALYSIS=1 AND FORTUNE_DEEP_PROVIDER=local_openai_compatible 인지 확인."""
    analysis_on = os.environ.get("FORTUNE_DEEP_ANALYSIS", "").strip() == "1"
    provider_match = os.environ.get("FORTUNE_DEEP_PROVIDER", "").strip() == SUPPORTED_PROVIDER_NAME
    return analysis_on and provider_match


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def make_qopus_provider(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Callable[[str], str]:
    """local OpenAI-compatible provider callable을 반환한다.

    import 시 네트워크 호출 없음. 명시적 호출 시에만 접근.
    """
    url = resolve_base_url(base_url)
    if url is None:
        raise RuntimeError(
            f"provider endpoint 미지정: {BASE_URL_ENV_VAR} 설정이 필요합니다 "
            "(하드코딩 fallback 없음)."
        )
    mdl = model or QOPUS_DEFAULT_MODEL
    key = api_key or QOPUS_DEFAULT_API_KEY
    to = bounded_timeout(timeout if timeout is not None else QOPUS_DEFAULT_TIMEOUT_SEC)

    def local_openai_compatible_gemma_crack_provider(prompt: str) -> str:
        """Call the local OpenAI-compatible endpoint."""
        if not deep_enabled():
            return _make_failure_response("disabled")
        payload = {
            "model": mdl,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": QOPUS_MAX_TOKENS,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{url}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=to) as resp:
                body = read_json_response(resp)
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            content = _strip_json_code_fence(content)
            if len(content) > QOPUS_MAX_RESPONSE_CHARS:
                content = content[: QOPUS_MAX_RESPONSE_CHARS]
            return content
        except Exception as exc:
            return _make_failure_response(type(exc).__name__)

    # Dynamic docstring with custom params
    local_openai_compatible_gemma_crack_provider.__doc__ = (
        f"Call the local OpenAI-compatible endpoint.\n\n"
        f"Model: {mdl}\nURL: {url}\nTimeout: {to}s"
    )
    return local_openai_compatible_gemma_crack_provider


# ---------------------------------------------------------------------------
# Reachability check (no network on import)
# ---------------------------------------------------------------------------


def check_qopus_reachable() -> Dict[str, Any]:
    """Qopus endpoint의 도달 가능성을 확인한다.

    Returns:
        {"reachable": bool, "error": str|None, "models": list}
    """
    if not deep_enabled():
        return {"reachable": False, "error": "disabled", "models": [], "target_model_found": False}
    url = resolve_base_url()
    if url is None:
        return {
            "reachable": False,
            "error": f"provider endpoint 미지정: {BASE_URL_ENV_VAR}",
            "models": [],
            "target_model_found": False,
        }
    try:
        req = urllib.request.Request(
            f"{url}/models",
            headers={"Authorization": f"Bearer {QOPUS_DEFAULT_API_KEY}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = read_json_response(resp)
        models = [m.get("id", "") for m in body.get("data", [])]
        return {
            "reachable": True,
            "error": None,
            "models": models,
            "target_model_found": QOPUS_DEFAULT_MODEL in models,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "error": type(exc).__name__,
            "models": [],
            "target_model_found": False,
        }


# ---------------------------------------------------------------------------
# Postprocess: update source tag
# ---------------------------------------------------------------------------


def postprocess_deep_review_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """deep_provider source를 실제 source tag로 업데이트한다."""
    if result.get("source") == "deep_provider":
        result["source"] = build_qopus_source_tag()
    return result
