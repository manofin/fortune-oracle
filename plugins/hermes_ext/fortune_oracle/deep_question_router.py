"""Fortune Oracle Phase 31 — /deep_fortune ask deterministic router."""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

from .oracle_phrase_bank import (
    ARCHETYPE_LABELS,
    DISCLAIMER,
    normalize_archetype,
    select_phrase,
    select_status_phrase,
)

ProviderFn = Callable[[str], str]

ASK_USAGE = (
    "질문을 함께 입력해 주세요.\n\n"
    "예: /deep_fortune ask 올해 창작을 밀고 가도 될까요?\n"
    "예: /심층운세 ask 지금 직장 흐름은 어떤가요?"
)

_MAX_PROVIDER_RESPONSE_CHARS = 8000
_UNSAFE_PATTERNS = (
    "반드시 이혼",
    "반드시 죽",
    "피할 수 없는 파국",
    "병원 대신",
    "치료 대신",
    "진단합니다",
    "매수",
    "매도",
    "투자하세요",
    "소송해야",
    "고소해야",
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "creation": ("창작", "글", "소설", "웹소설", "집필", "작품", "연재", "표현", "원고"),
    "career": ("직장", "일", "업무", "회사", "커리어", "이직", "퇴사", "승진", "역할", "프로젝트"),
    "relationship": ("관계", "연애", "배우자", "가족", "친구", "동료", "갈등", "화해", "사람"),
    "timing": ("언제", "시기", "올해", "내년", "지금", "때", "타이밍", "시작", "밀고", "가도"),
    "self_reflection": ("마음", "불안", "돌아", "성찰", "선택", "방향", "두려", "기준", "내가", "무엇"),
}


def is_ask_request(args: str | None) -> bool:
    tokens = str(args or "").strip().split(maxsplit=1)
    return bool(tokens and tokens[0].lower() == "ask")


def extract_question(args: str | None) -> str:
    text = str(args or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if not parts or parts[0].lower() != "ask":
        return ""
    return parts[1].strip() if len(parts) > 1 else ""


def classify_question(question: str | None) -> str:
    text = str(question or "").strip().lower()
    if not text or text == "?":
        return "unknown"
    scores: dict[str, int] = {}
    for archetype, keywords in _KEYWORDS.items():
        scores[archetype] = sum(1 for keyword in keywords if keyword.lower() in text)
    best = max(scores, key=lambda key: scores[key])
    if scores[best] <= 0:
        return "unknown"
    if best == "timing" and any(keyword in text for keyword in _KEYWORDS["creation"]):
        return "creation"
    return best


def _clip(value: Any, max_chars: int = 700) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    text = " ".join(str(value or "").split())
    if any(pattern in text for pattern in ("YongshenResult(", "DayunResult(", "BaziRelationReport(", "warnings=[", "ok=True", "ok=False")):
        return ""
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def _contains_unsafe(text: str) -> bool:
    return any(pattern in text for pattern in _UNSAFE_PATTERNS)


def _strip_json_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```json") and text.endswith("```"):
        return text[len("```json"): -len("```")].strip()
    if text.startswith("```") and text.endswith("```"):
        return text[len("```"): -len("```")].strip()
    return text


def _call_provider_with_timeout(provider: ProviderFn, prompt: str, timeout: int = 30) -> str | None:
    result: list[str | None] = [None]
    error: list[Exception | None] = [None]

    def run() -> None:
        try:
            result[0] = provider(prompt)
        except Exception as exc:  # pragma: no cover - defensive path
            error[0] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or error[0] is not None:
        return None
    return result[0]


def build_oracle_prompt(question: str, archetype: str, context: dict[str, Any]) -> str:
    safe_context = []
    for key, label in (
        ("eight_char", "간지"),
        ("elements", "오행"),
        ("relation_summary", "관계 흐름"),
        ("dayun_summary", "대운 흐름"),
        ("yongshen_summary", "용신 참고"),
        ("kline_summary", "K선"),
        ("life_context_summary", "사용자 제공 현실 맥락"),
    ):
        value = _clip(context.get(key), 220)
        if value:
            safe_context.append(f"{label}: {value}")
    body = "\n".join(safe_context)
    label = ARCHETYPE_LABELS.get(normalize_archetype(archetype), "흐름 점검")
    return f"""당신은 태허의 oracle Q&A 안내자입니다.
이 응답은 오락과 자기성찰용 참고이며 의학, 투자, 법률 결정을 지시하지 않습니다.
생년월일, 생시, 이름 한자는 제공되지 않았고 응답에 포함하면 안 됩니다.
질문 유형: {label}
사용자 질문: {question}

=== 안전한 흐름 맥락 ===
{body}

아래 JSON 형식으로만 응답하세요:
{{
  "ok": true,
  "style": "oracle_ask",
  "answer": "질문에 대한 2~4문장의 안전한 자기성찰 응답",
  "today_phrase": "짧은 oracle 문장 하나",
  "disclaimer": "이 결과는 오락과 자기성찰용 참고입니다.",
  "source": "deep_provider",
  "warnings": []
}}
확정 예언, 공포 조장, 의료·투자·법률 지시는 금지합니다.
"""


def build_phrase_bank_result(question: str, context: dict[str, Any] | None = None, *, reason: str = "disabled") -> dict[str, Any]:
    archetype = classify_question(question)
    context = context or {}
    base = select_phrase(archetype, seed_text=question)
    today = select_phrase(archetype, seed_text=question, bank="today")
    relation = _clip(context.get("relation_summary"), 180)
    yongshen = _clip(context.get("yongshen_summary"), 180)
    answer_parts = []
    if reason == "provider_failure":
        answer_parts.append(select_status_phrase("provider_failure", seed_text=question))
    elif reason == "no_profile":
        answer_parts.append(select_status_phrase("no_profile", seed_text=question))
    elif archetype == "unknown":
        answer_parts.append(select_status_phrase("ambiguous", seed_text=question))
    answer_parts.append(base)
    if relation:
        answer_parts.append(f"현재 관계·재배치 흐름은 이렇게 참고할 수 있습니다. {relation}")
    if yongshen:
        answer_parts.append(f"용신 참고는 절대 판정이 아니라 균형을 보는 보조 정보입니다. {yongshen}")
    return {
        "ok": True,
        "style": "oracle_ask",
        "question": question,
        "archetype": archetype,
        "answer": "\n".join(answer_parts),
        "today_phrase": today,
        "source": "template",
        "warnings": [reason],
        "disclaimer": DISCLAIMER,
    }


def analyze_oracle_question(
    question: str,
    context: dict[str, Any] | None = None,
    *,
    provider: ProviderFn | None = None,
    enabled: bool = False,
) -> dict[str, Any]:
    archetype = classify_question(question)
    context = dict(context or {})
    context["question"] = question
    context["question_archetype"] = archetype
    if not enabled or provider is None:
        return build_phrase_bank_result(question, context, reason="disabled")
    prompt = build_oracle_prompt(question, archetype, context)
    raw = _call_provider_with_timeout(provider, prompt, timeout=30)
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return build_phrase_bank_result(question, context, reason="provider_failure")
    raw = _strip_json_code_fence(raw)
    if len(raw) > _MAX_PROVIDER_RESPONSE_CHARS:
        return build_phrase_bank_result(question, context, reason="provider_failure")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return build_phrase_bank_result(question, context, reason="provider_failure")
    if not isinstance(data, dict) or data.get("ok") is False or data.get("style") != "oracle_ask":
        return build_phrase_bank_result(question, context, reason="provider_failure")
    answer = _clip(data.get("answer"), 900)
    today = _clip(data.get("today_phrase"), 180)
    check_text = " ".join([answer, today])
    if not answer or not today or _contains_unsafe(check_text):
        return build_phrase_bank_result(question, context, reason="provider_failure")
    return {
        "ok": True,
        "style": "oracle_ask",
        "question": question,
        "archetype": archetype,
        "answer": answer,
        "today_phrase": today,
        "source": "deep_provider",
        "warnings": data.get("warnings", []),
        "disclaimer": data.get("disclaimer") or DISCLAIMER,
    }


def format_oracle_answer(result: dict[str, Any], *, include_disabled_notice: bool = False) -> str:
    question = _clip(result.get("question"), 500)
    archetype = normalize_archetype(result.get("archetype"))
    label = ARCHETYPE_LABELS.get(archetype, "흐름 점검")
    lines: list[str] = []
    if include_disabled_notice:
        lines.extend([
            "심층 운세는 현재 비활성화되어 있습니다.",
            "",
            "provider를 호출하지 않고 기본 팔자·K선 맥락과 oracle phrase bank만 사용합니다.",
            "",
        ])
    lines.extend([
        "질문",
        question,
        "",
        "태허의 응답",
        _clip(result.get("answer"), 1200),
        "",
        f"질문 유형: {label} ({archetype})",
        "",
        "오늘의 문장",
        f"“{_clip(result.get('today_phrase'), 220)}”",
    ])
    source = _clip(result.get("source"), 120)
    if source and source != "template":
        lines.extend(["", f"source: {source}"])
    lines.extend(["", DISCLAIMER])
    return "\n".join(line for line in lines if line is not None).strip()
