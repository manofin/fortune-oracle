"""Fortune Oracle — Deep Review Mode (Phase 18)

기본값: DISABLED. 외부 API를 호출하지 않는다.
provider function injection 방식으로만 LLM 연결 가능.
실제 운영 활성화는 사용자가 검토 후 결정한다.

Privacy contract:
- birth_date, birth_time, name_hanja 를 prompt/log/context 에 미포함
- display_name 만 profile 에서 사용
- 간지, 오행, 요약 정보만 포함

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature status constants
# ---------------------------------------------------------------------------

REVIEW_MODE_STATUS: str = "PENDING: 사용자 검토 후 활성화 가능"

ACTIVATION_RUNBOOK: Dict[str, Any] = {
    "env_var": "FORTUNE_DEEP_ANALYSIS=1",
    "provider_required": True,
    "timeout_seconds": 30,
    "unsafe_filter": True,
    "live_test_required": True,
    "steps": [
        "1. 테스트 환경에서 provider 함수 주입 후 live_test_required 항목 모두 통과 확인",
        "2. FORTUNE_DEEP_ANALYSIS=1 환경 변수 설정",
        "3. 운영 배포 전 unsafe_filter 동작 재검증",
        "4. 사용자(운영자)가 결과를 직접 검토 후 활성화 승인",
        "5. gateway 및 Telegram command 수정 없이 provider injection 방식으로만 연결",
    ],
    "forbidden": [
        "gateway 수정",
        "Telegram live 에 새 command 자동 등록",
        "외부 LLM client import (openai, anthropic, google 등)",
        "birth_date/birth_time/name_hanja 노출",
    ],
}

# ---------------------------------------------------------------------------
# Unsafe phrase filter
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES: List[str] = [
    "반드시",
    "건강 문제",
    "투자",
    "법적",
    "파산",
    "사망",
    # Observed live output turned heuristic indices into event predictions.
    "예상됩니다",
    "예상되는",
    "좌우",
    "통계적 경향",
    "통계적 패턴",
]

# ---------------------------------------------------------------------------
# Provider type
# ---------------------------------------------------------------------------

ProviderFn = Callable[[str], str]

# ---------------------------------------------------------------------------
# ReviewContext dataclass
# ---------------------------------------------------------------------------


@dataclass
class ReviewContext:
    profile_summary: str = ""
    eight_char: str = ""
    season: str = ""
    elements: str = ""
    relation_summary: str = ""
    dayun_summary: str = ""
    yongshen_summary: str = ""


# ---------------------------------------------------------------------------
# Fallback result
# ---------------------------------------------------------------------------

_FALLBACK_DISCLAIMER = (
    "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
)

_MAX_PROVIDER_RESPONSE_CHARS = 8000


def _fallback_result(reason: str) -> Dict[str, Any]:
    return {
        "sections": [],
        "reflection_question": "",
        "disclaimer": _FALLBACK_DISCLAIMER,
        "source": "template",
        "warnings": [f"fallback: {reason}"],
    }


def _strip_json_code_fence(raw: str) -> str:
    """Provider가 JSON을 Markdown fence로 감싼 경우 fence만 제거한다."""
    text = raw.strip()
    if text.startswith("```json") and text.endswith("```"):
        return text[len("```json"): -len("```")].strip()
    if text.startswith("```") and text.endswith("```"):
        return text[len("```"): -len("```")].strip()
    return text


# ---------------------------------------------------------------------------
# Unsafe phrase check
# ---------------------------------------------------------------------------


def _contains_unsafe(text: str) -> bool:
    for phrase in _FORBIDDEN_PHRASES:
        # Keep the check conservative: a later disclaimer cannot cancel a
        # preceding assertion. This deliberately may reject harmless negation.
        if phrase in text:
            return True
    return False


# ---------------------------------------------------------------------------
# build_deep_review_context
# ---------------------------------------------------------------------------

_ELEMENT_HANJA: Dict[str, str] = {
    "목": "木",
    "화": "火",
    "토": "土",
    "금": "金",
    "수": "水",
}

_ELEMENT_NATURE: Dict[str, str] = {
    "목": "상상력과 회복력을 보태는 기운",
    "화": "표현력과 실행감을 밝히는 기운",
    "토": "현실 감각과 버티는 힘을 다지는 기운",
    "금": "정리와 결단을 돕는 기운",
    "수": "유연성과 성찰을 깊게 하는 기운",
}

_STRENGTH_KO: Dict[str, str] = {
    "strong": "강한 편",
    "balanced": "균형권",
    "weak": "약한 편",
}


def _clean_line(text: Any, max_chars: int = 220) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = " ".join(value.split())
    return value if len(value) <= max_chars else value[: max_chars - 1].rstrip() + "…"


def _element_label(element: str) -> str:
    if not element:
        return ""
    hanja = _ELEMENT_HANJA.get(element, "")
    return f"{element}({hanja})" if hanja else element


def format_yongshen_for_deep_review(yongshen_result: Any) -> str:
    """YongshenResult를 사용자용 deep review 요약 문장으로 변환한다.

    dataclass repr, dict/list raw dump를 반환하지 않는다.
    """
    if yongshen_result is None:
        return ""
    if isinstance(yongshen_result, str):
        return _clean_line(yongshen_result, 260)
    if getattr(yongshen_result, "ok", True) is False:
        return "용신 참고는 현재 명식 정보 부족으로 보류합니다. 이 판단은 rule-based 참고이며 절대 판정은 아닙니다."

    day_master = _clean_line(getattr(yongshen_result, "day_master", ""), 20)
    dm_element = _clean_line(getattr(yongshen_result, "day_master_element", ""), 20)
    strength = _STRENGTH_KO.get(getattr(yongshen_result, "strength", ""), "참고 수준")
    favorable = [str(e) for e in (getattr(yongshen_result, "favorable_elements", None) or []) if e]
    caution = [str(e) for e in (getattr(yongshen_result, "caution_elements", None) or []) if e]

    lines: List[str] = []
    if day_master or dm_element:
        master = f"{day_master}{dm_element}" if day_master and dm_element else (day_master or dm_element)
        lines.append(f"{master} 일간은 현재 구조에서 {strength}으로 읽힙니다.")
    if favorable:
        labels = "과 ".join(_element_label(e) for e in favorable[:2])
        desc = ", ".join(_ELEMENT_NATURE.get(e, f"{e} 기운") for e in favorable[:2])
        lines.append(f"{labels}은 현재 구조에서 흐름을 보조하는 기운으로 읽힙니다. {desc}입니다.")
    if caution:
        labels = "과 ".join(_element_label(e) for e in caution[:2])
        lines.append(f"{labels}은 과해질 때 균형 점검이 필요한 기운으로 참고합니다.")
    lines.append("이 판단은 rule-based 참고이며 절대 판정은 아닙니다.")
    return " ".join(_clean_line(line, 220) for line in lines if _clean_line(line))


def format_dayun_for_deep_review(dayun_result: Any) -> str:
    """DayunResult를 사용자용 deep review 요약 문장으로 변환한다."""
    if dayun_result is None:
        return ""
    if isinstance(dayun_result, str):
        return _clean_line(dayun_result, 260)
    if getattr(dayun_result, "ok", True) is False:
        return "대운 계산은 현재 명식 정보 부족으로 보류합니다. 장기 리듬은 참고 수준으로만 봅니다."

    direction = getattr(dayun_result, "direction", "unknown") or "unknown"
    if direction == "unknown":
        return "대운 방향 산정에는 성별 정보가 필요합니다. 현재는 팔자 구조 기반의 장기 리듬만 참고로 표시합니다."

    direction_label = "순행" if direction == "forward" else "역행" if direction == "reverse" else "미정"
    start_age = getattr(dayun_result, "start_age", 0)
    cycles = list(getattr(dayun_result, "cycles", None) or [])
    lines = [f"대운은 {direction_label} 흐름으로 산정되며 시작 나이는 약 {start_age}세로 참고합니다."]
    if cycles:
        first = cycles[0]
        pillar = _clean_line(getattr(first, "pillar", ""), 20)
        theme = _clean_line(getattr(first, "theme", ""), 120)
        age_from = getattr(first, "age_from", "")
        age_to = getattr(first, "age_to", "")
        if pillar:
            lines.append(f"초기 대운({age_from}~{age_to}세)은 {pillar} 흐름이며, {theme or '기운의 전환을 점검하는 구간'}으로 읽습니다.")
    lines.append("대운은 확정 예언이 아니라 장기 리듬을 보는 참고 지표입니다.")
    return " ".join(_clean_line(line, 220) for line in lines if _clean_line(line))


def format_relation_for_deep_review(relation_report: Any) -> str:
    """BaziRelationReport를 사용자용 deep review 요약 문장으로 변환한다."""
    if relation_report is None:
        return ""
    if isinstance(relation_report, str):
        return _clean_line(relation_report, 260)
    if getattr(relation_report, "ok", True) is False:
        return "관계 흐름은 현재 지지 정보 부족으로 보류합니다. 특정 사건보다 내적 기준과 선택의 재배치로 일반화해 봅니다."

    summary = _clean_line(getattr(relation_report, "summary", ""), 260)
    if summary:
        return summary

    notes = [_clean_line(n, 160) for n in (getattr(relation_report, "notes", None) or []) if _clean_line(n)]
    if notes:
        return " ".join(notes[:2])
    return "관계 흐름은 특정 사건보다 내적 기준과 선택의 재배치로 일반화해 읽습니다."


def build_deep_review_context(
    profile: Dict[str, Any],
    bazi: Any,
    kline: Any,
    relation: Any,
    dayun: Any,
    yongshen: Any,
) -> Dict[str, Any]:
    """privacy-safe 분석 context 빌드.

    privacy contract:
    - profile 에서 display_name 만 사용
    - birth_date, birth_time, name_hanja 미포함
    """
    # profile: display_name 만
    display_name = profile.get("display_name", "") if isinstance(profile, dict) else ""
    profile_summary = f"display_name:{display_name}" if display_name else ""

    # bazi: eight_char, season, elements
    eight_char = ""
    season = ""
    elements = ""
    if bazi is not None:
        ec = getattr(bazi, "eight_char", None) or {}
        if isinstance(ec, dict):
            eight_char = (
                f"년주:{ec.get('year','')} "
                f"월주:{ec.get('month','')} "
                f"일주:{ec.get('day','')} "
                f"시주:{ec.get('time','')}"
            ).strip()
        raw_season = getattr(bazi, "season", None)
        if raw_season:
            season = str(raw_season)
        raw_elem = getattr(bazi, "elements", None) or {}
        if isinstance(raw_elem, dict):
            elements = ", ".join(
                f"{k}:{v}개" for k, v in sorted(raw_elem.items(), key=lambda x: -x[1])
            )

    # optional life_context: 사용자가 명시 제공한 현실 맥락만 allowlist로 포함
    life_context_summary = ""
    try:
        from hermes_ext.fortune_oracle.life_context import build_life_context_summary
        life_context_summary = build_life_context_summary(profile)
    except Exception:
        life_context_summary = ""

    # summaries (최대 200자 clip)
    def _safe_summary(obj: Any, kind: str = "") -> str:
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj[:200]
        if kind == "relation":
            return format_relation_for_deep_review(obj)[:200]
        if kind == "dayun":
            return format_dayun_for_deep_review(obj)[:200]
        if kind == "yongshen":
            return format_yongshen_for_deep_review(obj)[:200]
        summary = getattr(obj, "summary", None)
        if summary:
            return str(summary)[:200]
        return ""

    return {
        "profile_summary": profile_summary,
        "eight_char": eight_char,
        "season": season,
        "elements": elements,
        "relation_summary": _safe_summary(relation, "relation"),
        "dayun_summary": _safe_summary(dayun, "dayun"),
        "yongshen_summary": _safe_summary(yongshen, "yongshen"),
        "life_context_summary": life_context_summary,
    }


# ---------------------------------------------------------------------------
# Provider timeout helper
# ---------------------------------------------------------------------------


def _call_provider_with_timeout(
    provider: ProviderFn,
    prompt: str,
    timeout: int,
) -> Optional[str]:
    result_holder: List[Optional[str]] = [None]
    exc_holder: List[Optional[Exception]] = [None]

    def _run() -> None:
        try:
            result_holder[0] = provider(prompt)
        except Exception as exc:
            exc_holder[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning("deep_review: provider timeout (%ds)", timeout)
        return None
    if exc_holder[0]:
        logger.warning("deep_review: provider raised %s", type(exc_holder[0]).__name__)
        return None
    return result_holder[0]


# ---------------------------------------------------------------------------
# Build prompt from context
# ---------------------------------------------------------------------------


def _build_prompt(context: Dict[str, Any]) -> str:
    interpretation_rules = """출력은 새 계산 결과가 아니라 외부 모델의 해석입니다.
계산된 간지·오행·지수와 경험적 관계·용신 해석을 구분하세요. 용신을 확정하지 마세요.
입력에 없는 사건·심리 상태·인과관계를 만들지 마세요. 연간 지수에서 특정 월의 피로,
혼란, 회복, 성과를 추론하지 마세요. 과거 날짜를 앞으로 일어날 일처럼 표현하지 마세요.
K선은 경험 규칙 지수이며 통계 검증이나 확률 근거가 없습니다. 통계적 경향·패턴으로
표현하지 마세요. 특정 월을 회복·실행 기간으로 권고하거나 미래 날짜를 완료된 경험처럼 묻지 마세요.
미래 예측이나 결과를 좌우한다는 단정 대신 현재 점검할 자기성찰 질문을 제시하세요.
본문마다 '해석(경험적 참고):'로 시작하고, 알려지지 않은 사실은 채워 넣지 마세요.
"""
    parts = []
    if context.get("eight_char"):
        parts.append(f"간지: {context['eight_char']}")
    if context.get("season"):
        parts.append(f"계절: {context['season']}")
    if context.get("elements"):
        parts.append(f"오행: {context['elements']}")
    if context.get("relation_summary"):
        parts.append(f"관계 흐름 요약: {context['relation_summary']}")
    if context.get("dayun_summary"):
        parts.append(f"대운 흐름 요약: {context['dayun_summary']}")
    if context.get("yongshen_summary"):
        parts.append(f"용신 참고 요약: {context['yongshen_summary']}")
    if context.get("kline_summary"):
        parts.append(f"K선 요약: {context['kline_summary']}")
    if context.get("life_context_summary"):
        parts.append(f"사용자 제공 현실 맥락: {context['life_context_summary']}")

    body = "\n".join(parts)
    if context.get("style") == "taheo_qna":
        return f"""당신은 태허의 운명분석 Question & Answer 형식의 동양 철학 기반 자기성찰 안내자입니다.
이 분석은 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
개인 식별 정보(생년월일, 생시, 이름 한자)는 포함되지 않았습니다.
{interpretation_rules}
사용자가 제공하지 않은 현실 정보는 절대 만들지 마세요. life_context가 없으면 직업명·경력·사건을 특정하지 말고 일반화하세요.
공포 조장, 파국 단정, 실제 행동 강제, 의료·투자·법률 지시는 금지합니다.

=== 팔자·흐름 요약 ===
{body}

아래 JSON 형식으로만 응답하세요:
{{
  "ok": true,
  "style": "taheo_qna",
  "title": "태허의 운명분석 Question & Answer",
  "sections": [{{"heading": "명식 산출 검토", "body": "...", "emphasis": "..."}}],
  "final_advice": "...",
  "disclaimer": "이 결과는 오락과 자기성찰용 참고입니다.",
  "source": "deep_provider",
  "warnings": []
}}
섹션은 가능한 한 다음 순서를 따르세요: 명식 산출 검토, 해석의 핵심 구조, 일간/월지/시주의 상징, 관계 흐름과 재배치 압력, 대운·세운 흐름, 현실 연결, 최종 조언.
"""

    return f"""당신은 동양 철학 기반의 자기성찰 안내자입니다.
이 분석은 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
개인 식별 정보(생년월일, 생시, 이름 한자)는 포함되지 않았습니다.
{interpretation_rules}

=== 팔자 요약 ===
{body}

아래 JSON 형식으로만 응답하세요:
{{
  "sections": [{{"title": "...", "summary": "...", "reflection_question": "..."}}],
  "reflection_question": "...",
  "disclaimer": "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
  "source": "deep_provider",
  "warnings": []
}}
"""


# ---------------------------------------------------------------------------
# analyze_deep_review — main entry point
# ---------------------------------------------------------------------------


def analyze_deep_review(
    context: Dict[str, Any],
    *,
    provider: Optional[ProviderFn] = None,
    enabled: bool = False,
) -> Dict[str, Any]:
    """심층 리뷰 분석 실행.

    enabled=False  → 즉시 deterministic fallback
    provider=None  → deterministic fallback
    provider 있고 enabled=True → 최대 30초 timeout thread
    """
    if not enabled:
        return _fallback_result("deep_review disabled")

    if provider is None:
        return _fallback_result("no provider injected")

    prompt = _build_prompt(context)
    raw = _call_provider_with_timeout(provider, prompt, timeout=30)

    if raw is None:
        return _fallback_result("provider timeout or error")

    if not isinstance(raw, str) or not raw.strip():
        logger.warning("deep_review: empty provider response")
        return _fallback_result("empty provider response")

    raw = _strip_json_code_fence(raw)

    if len(raw) > _MAX_PROVIDER_RESPONSE_CHARS:
        logger.warning("deep_review: provider response too long (%d chars)", len(raw))
        return _fallback_result("provider response too long")

    # JSON parse
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("deep_review: invalid JSON from provider")
        return _fallback_result("invalid JSON from provider")

    if not isinstance(data, dict):
        logger.warning("deep_review: provider JSON is not object")
        return _fallback_result("provider JSON is not object")

    if data.get("ok") is False:
        reason = "provider reported failure"
        logger.warning("deep_review: provider reported failure")
        return _fallback_result(reason)

    sections = data.get("sections", [])
    if not isinstance(sections, list) or not sections:
        logger.warning("deep_review: missing sections from provider")
        return _fallback_result("missing sections from provider")

    # Reject malformed output before rendering. Never stringify objects into
    # user-visible prose, and use the requested style rather than model choice.
    for key in ("title", "reflection_question", "final_advice", "style", "disclaimer"):
        if key in data and not isinstance(data[key], str):
            return _fallback_result("invalid provider text field")
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        return _fallback_result("invalid provider warnings")
    style = context.get("style") or data.get("style") or "short"
    body_key = "body" if style == "taheo_qna" else "summary"

    # Check each displayed field independently, including the Q&A title.
    # Disclaimer/warnings are metadata; the product appends its own disclaimer.
    _check_parts: List[str] = []
    for sec in sections:
        if not isinstance(sec, dict):
            logger.warning("deep_review: invalid section from provider")
            return _fallback_result("invalid section from provider")
        for key in ("title", "summary", "reflection_question", "heading", "body", "emphasis"):
            value = sec.get(key, "")
            if not isinstance(value, str):
                return _fallback_result("invalid section text field")
            _check_parts.append(value)
        if not sec.get(body_key, "").strip():
            return _fallback_result("missing section body")
    _check_parts.extend(data.get(key, "") for key in ("title", "reflection_question", "final_advice"))
    if any(_contains_unsafe(part) for part in _check_parts):
        logger.warning("deep_review: unsafe phrase detected, returning fallback")
        return _fallback_result("unsafe phrase detected")

    # normalise fields
    result: Dict[str, Any] = {
        "sections": sections[:7] if style == "taheo_qna" else sections[:3],
        "reflection_question": data.get("reflection_question", ""),
        "final_advice": data.get("final_advice", ""),
        "title": data.get("title", ""),
        "style": style,
        "disclaimer": data.get(
            "disclaimer",
            _FALLBACK_DISCLAIMER,
        ),
        "source": "deep_provider",
        "warnings": warnings,
    }
    return result
