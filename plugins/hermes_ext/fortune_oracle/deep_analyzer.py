"""Fortune Oracle — Deep Analyzer Wrapper (Phase 5 / Phase 11 강화)

기본값: DISABLED. 외부 API를 호출하지 않는다.
provider function injection 방식으로만 LLM 연결 가능.
실제 운영 활성화는 사용자가 검토 후 결정한다.

Phase 11 개선:
- reflection_question 필드 output contract 추가
- provider timeout (threading) 안전 처리
- 과긴 출력 → safe fallback (truncate 없이)
- source 필드 일관화 ("deep_provider" vs "template")
- 모든 fallback 경로 명시적 warning 기록
- _FORBIDDEN_PATTERNS 2개 추가

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .bazi_bridge import BaziResult
from .bazi_template_analyzer import TemplateAnalysisResult, analyze_bazi_template

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

_ENV_FLAG = os.environ.get("FORTUNE_DEEP_ANALYSIS", "").strip()
DEEP_ANALYSIS_ENABLED_BY_DEFAULT: bool = _ENV_FLAG == "1"

PROVIDER_TIMEOUT_SECONDS: int = int(os.environ.get("FORTUNE_DEEP_TIMEOUT", "30"))
MAX_RESPONSE_CHARS: int = 8000

# ---------------------------------------------------------------------------
# Provider type
# ---------------------------------------------------------------------------

ProviderFn = Callable[[str], str]

# ---------------------------------------------------------------------------
# Prompt contract
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
당신은 동양 철학 기반의 자기성찰 안내자입니다.
다음 규칙을 반드시 지키세요:

1. 이 분석은 오락과 자기성찰 용도입니다.
2. 의학, 투자, 법률 결정을 지시하거나 암시하지 마세요.
3. 불길한 단정이나 확정적 예언을 하지 마세요.
4. 특정 사건(사망, 사고, 질병)을 예언하지 마세요.
5. 인간관계, 건강, 금전에 대한 확정적 예측을 하지 마세요.
6. 개인의 이름, 생년월일, 주민번호 등 민감 정보를 반복 출력하지 마세요.
7. 섹션 구조를 유지하고 각 섹션은 2-3문장으로 간결하게 작성하세요.
8. 응답은 JSON 형식으로만 반환하세요.
"""

_RESPONSE_SCHEMA = """\
{
  "ok": true,
  "source": "deep_provider",
  "sections": [
    {
      "title": "섹션 제목",
      "summary": "내용 (2-3문장)",
      "reflection_question": "자기성찰 질문 (선택, 없으면 빈 문자열)",
      "confidence": "llm",
      "disclaimer": ""
    }
  ],
  "warnings": [],
  "disclaimer": "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
}
"""


def build_deep_prompt(
    bazi_result: BaziResult,
    template_result: TemplateAnalysisResult,
    *,
    kline_summary: Optional[str] = None,
    relation_summary: Optional[str] = None,
    dayun_summary: Optional[str] = None,
    yongshen_summary: Optional[str] = None,
) -> str:
    """LLM에 전달할 prompt 문자열 생성.

    Privacy contract:
    - birth_date, birth_time, birth_place, name_hanja 미포함
    - 간지, 띠, 오행, 템플릿 요약, K선 요약만 포함
    - Phase 14: relation/dayun/yongshen summary 추가 (raw 민감정보 제외)
    """
    eight_char = bazi_result.eight_char or {}
    elements = bazi_result.elements or {}
    zodiac = bazi_result.zodiac or "미상"

    ec_summary = (
        f"년주:{eight_char.get('year','')} "
        f"월주:{eight_char.get('month','')} "
        f"일주:{eight_char.get('day','')} "
        f"시주:{eight_char.get('time','')}"
    )
    elem_summary = ", ".join(
        f"{k}:{v}개" for k, v in sorted(elements.items(), key=lambda x: -x[1])
    )

    template_summaries = []
    for sec in (template_result.sections or []):
        if sec.confidence == "disclaimer":
            continue
        template_summaries.append(f"[{sec.title}] {sec.summary[:100]}")

    kline_part = f"\n운세 K선 요약: {kline_summary[:200]}" if kline_summary else ""

    # Phase 14: 관계/대운/용신 summary (privacy-safe)
    phase14_parts = []
    if relation_summary:
        phase14_parts.append(f"관계 흐름 요약: {str(relation_summary)[:200]}")
    if dayun_summary:
        phase14_parts.append(f"대운 흐름 요약: {str(dayun_summary)[:200]}")
    if yongshen_summary:
        phase14_parts.append(f"용신 참고 요약: {str(yongshen_summary)[:200]}")
    phase14_block = ("\n\n=== Phase 14 확장 참고 ===\n" + "\n".join(phase14_parts)) if phase14_parts else ""

    prompt = f"""{_SYSTEM_PROMPT}
=== 팔자 정보 (계산 결과, 개인 식별 정보 제외) ===
간지: {ec_summary}
띠: {zodiac}
오행: {elem_summary}
{kline_part}{phase14_block}

=== 기존 템플릿 분석 (참고용) ===
{chr(10).join(template_summaries)}

=== 출력 형식 ===
아래 JSON 스키마를 정확히 따르세요:
{_RESPONSE_SCHEMA}

요청: 위 팔자 정보를 바탕으로 자기성찰에 도움이 되는 심층 분석을 작성해 주세요.
섹션: 기본 기질, 강점, 주의할 흐름, 올해 에너지, 자기성찰 질문 3개를 포함하세요.
"""
    return prompt


# ---------------------------------------------------------------------------
# Deep analysis result
# ---------------------------------------------------------------------------

@dataclass
class DeepAnalysisResult:
    ok: bool
    source: str = "template"
    sections: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    message: str = ""
    disclaimer: str = "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."

    def to_telegram_summary(self, max_chars: int = 1000) -> str:
        if not self.ok or not self.sections:
            return f"심층 분석 불가: {self.message}"
        lines = []
        for sec in self.sections:
            title = sec.get("title", "")
            summary = sec.get("summary", "")
            rq = sec.get("reflection_question", "")
            if sec.get("confidence") == "disclaimer":
                continue
            block = f"**{title}**\n{summary}"
            if rq:
                block += f"\n→ {rq}"
            lines.append(block)
        text = "\n\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars - 3] + "..."
        return text


# ---------------------------------------------------------------------------
# Provider timeout helper
# ---------------------------------------------------------------------------

def _call_provider_with_timeout(
    provider: ProviderFn,
    prompt: str,
    timeout: int,
) -> Optional[str]:
    """provider를 별도 thread에서 실행. timeout 초과 시 None 반환."""
    result_holder: List[Optional[str]] = [None]
    exc_holder: List[Optional[Exception]] = [None]

    def _run():
        try:
            result_holder[0] = provider(prompt)
        except Exception as e:
            exc_holder[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        logger.warning("deep_analyze: provider timeout (%ds) — template fallback", timeout)
        return None
    if exc_holder[0] is not None:
        raise exc_holder[0]
    return result_holder[0]


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def deep_analyze(
    bazi_result: BaziResult,
    *,
    enabled: bool = DEEP_ANALYSIS_ENABLED_BY_DEFAULT,
    provider: Optional[ProviderFn] = None,
    kline_summary: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    timeout: int = PROVIDER_TIMEOUT_SECONDS,
) -> DeepAnalysisResult:
    """심층 분석 실행.

    Args:
        enabled: True이고 provider != None일 때만 LLM 호출. 기본 False.
        provider: prompt(str) -> str 주입 함수. module import 시 생성 금지.
        timeout: provider 응답 대기 초.

    Privacy contract:
        - birth_date, birth_time, birth_place, name_hanja → prompt에 미포함
        - 간지, 띠, 오행 요약만 포함
    """
    template_result = analyze_bazi_template(
        bazi_result, kline_summary=kline_summary, profile=profile
    )

    if not enabled or provider is None:
        logger.debug(
            "deep_analyze: enabled=%s, provider_set=%s — template fallback",
            enabled, provider is not None,
        )
        return _from_template(template_result)

    import json
    import re as _re
    try:
        prompt = build_deep_prompt(bazi_result, template_result, kline_summary=kline_summary)

        raw_response = _call_provider_with_timeout(provider, prompt, timeout)
        if raw_response is None:
            return _from_template(
                template_result,
                warning=f"LLM 응답 시간 초과 ({timeout}s) — 템플릿 사용",
            )

        if not raw_response.strip():
            logger.warning("deep_analyze: empty LLM response — template fallback")
            return _from_template(template_result, warning="LLM 빈 응답 — 템플릿 사용")

        # 과긴 출력 → safe fallback (truncate 없이)
        if len(raw_response) > MAX_RESPONSE_CHARS:
            logger.warning(
                "deep_analyze: response too long (%d > %d) — template fallback",
                len(raw_response), MAX_RESPONSE_CHARS,
            )
            return _from_template(
                template_result,
                warning=f"LLM 응답 과다 ({len(raw_response)}자) — 템플릿 사용",
            )

        # JSON 추출
        raw_stripped = raw_response.strip()
        if "```" in raw_stripped:
            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_stripped, _re.DOTALL)
            if m:
                raw_stripped = m.group(1)

        data = json.loads(raw_stripped)
        sections = data.get("sections", [])
        if not sections:
            return _from_template(template_result, warning="LLM 섹션 없음 — 템플릿 사용")

        warnings = list(data.get("warnings", []))
        _safety_check_sections(sections, warnings)

        return DeepAnalysisResult(
            ok=True,
            source="deep_provider",
            sections=sections,
            warnings=warnings,
            disclaimer=data.get(
                "disclaimer",
                "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
            ),
        )

    except json.JSONDecodeError as e:
        logger.warning("deep_analyze: JSON parse failed — template fallback")
        return _from_template(template_result, warning="LLM 응답 파싱 실패")
    except Exception as e:
        logger.warning("deep_analyze: provider error (%s) — template fallback", type(e).__name__)
        return _from_template(template_result, warning="LLM 오류 — 호출 실패")


def _from_template(
    template_result: TemplateAnalysisResult,
    warning: Optional[str] = None,
) -> DeepAnalysisResult:
    sections = []
    for sec in (template_result.sections or []):
        sections.append({
            "title": sec.title,
            "summary": sec.summary,
            "reflection_question": "",
            "confidence": sec.confidence,
            "disclaimer": sec.disclaimer,
        })
    warnings = list(template_result.warnings or [])
    if warning:
        warnings.append(warning)

    return DeepAnalysisResult(
        ok=template_result.ok,
        source="template",
        sections=sections,
        warnings=warnings,
        error_code=template_result.error_code,
        message=template_result.message,
    )


# ---------------------------------------------------------------------------
# Safety check
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    "반드시 죽", "사망", "큰 사고", "파산", "이혼할 것",
    "병에 걸릴", "불치병", "당신은 곧", "의학적으로",
    "투자하세요", "법적으로", "소송에서 이길",
    "반드시 일어날", "피할 수 없는",
]


def _safety_check_sections(sections: List[Dict], warnings: List[str]) -> None:
    """LLM 출력에서 금지 패턴 검출 시 warning 추가."""
    for sec in sections:
        text = (
            sec.get("summary", "")
            + sec.get("title", "")
            + sec.get("reflection_question", "")
        )
        for pat in _FORBIDDEN_PATTERNS:
            if pat in text:
                warnings.append(f"안전 경고: 금지 표현 감지 — '{pat}'")
