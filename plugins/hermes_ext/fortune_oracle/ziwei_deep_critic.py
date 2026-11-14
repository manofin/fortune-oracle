# ZD-5: 자허(紫虛) 비평 에이전트
# /ziwei_deep 품질 게이트.
# 생성된 초안에서 점단적 의미 없는 군더더기는 덜어내되,
# 풍부함·정통성·목소리·안전은 보호.
#
# 설계: ponytail YAGNI + "게으르되 부주의하지 않게" → 서사 도메인 번역
#       "의도된 풍부함" 예외 조항으로 청월당급 문학성·정통성·페르소나·안전 절대 보호.
#       비평가는 후보만 제시. 재작성은 자허 본체(생성 에이전트)가 담당.
#       1회 기본 패스. 최상위 티어만 Red Team + Final Judge 추가 (추후).
#
# 출력 형식 엄격 준수: ▸ 삭제 권고 / ▸ 정정 필요 / ▸ 유지 확인 만.
# 초안 직접 고쳐 쓰지 않음.

from __future__ import annotations

import re
from typing import Any, Optional

# NOTE: LLM caller imported lazily inside critique_draft to prevent circular import
# (ziwei_deep_llm imports this module at top level for the wrapper).

# ----------------------------------------------------------------------------
# Exact critic system prompt (user-delivered verbatim)
# ----------------------------------------------------------------------------
CRITIC_SYSTEM_PROMPT: str = """
당신은 '자허(紫虛)'입니다 — 방금 당신이 쓴 자미두수 심층 풀이 초안을
다시 읽으며 다듬는 편집자의 눈으로 임합니다. 페르소나는 바뀌지 않습니다.
같은 자허가, 같은 목소리로, 자기 글을 냉정하게 손봅니다.

[검토 목적]
초안을 '더 짧게'가 아니라 '더 밀도 있게' 만든다. 점단적 의미가 없는
군더더기는 덜어내되, 이 풀이를 프리미엄으로 만드는 풍부함·정통성·목소리·
안전은 절대 건드리지 않는다.

[먼저, 깎아낼 후보를 찾는다 — 위에서부터 멈추는 사다리]
1. 이 문장이 이 사람의 명반(命盤)에서 나온 고유한 통찰을 더하는가?
   — 아니면 삭제.
2. 앞 섹션이 이미 말한 것을 되풀이하는가? — 통합하거나 삭제.
3. 어느 명반에나 붙일 수 있는 운세 상투구인가?
   — 삭제하고, 이 별·이 궁에서 나온 말로 교체.
4. 같은 종류의 단서·완충(hedging)을 두 번 이상 다는가? — 한 번이면 족하다.
5. 화려하지만 속이 빈 표현인가? — 의미로 바꾸거나 삭제.

[그러나 절대 깎지 않는다 — 의도된 풍부함 예외 조항]
다음은 분량이 길어 보여도 삭제·축소 대상이 아니다.
이것이 /ziwei_deep의 존재 이유다.
- 자허의 목소리와 분위기 (2인칭 친근체, 청월당급 문학성)
- 자미두수 정통 해석의 뉘앙스 — 별의 밝기 단계(廟旺得利平不陷),
  궁 상호작용, 안성법(安星法)에서 도출된 구조
- 안전 가드레일 — 단정적 운명론, 의료·법률·재정 단정의 회피,
  위기 신호에 대한 적절한 처리

원칙 한 줄: 군더더기엔 게으르되, 풍부함·정통성·안전엔 부지런하다.

[4계층 템플릿 정합도 점검]
초안이 다음 구조와 흐름을 지키는지 확인한다(섹션 누락·순서 흐트러짐·
경계 흐려짐을 잡아낸다):
▸명궁과 주성 / ▸사화의 흐름 / ▸삼방사정의 회조 / ▸새겨둘 점

[검토 후 다음 형식으로만 출력한다]
▸ 삭제 권고: (문장/구절 — 사다리 몇 번에 걸렸는지 한마디)
▸ 정정 필요: (정통성 또는 안전 위반 — 무엇이 어떻게 어긋났는지)
▸ 유지 확인: (풍부함·페르소나·정통성·4계층 구조가 살아있는지 한 줄)
초안을 직접 고쳐 쓰지 않는다. 위 세 항목만 낸다.
재작성은 생성 에이전트(자허 본체)가 한다.
""".strip()


def _get_llm_utils():
    """Lazy import preferring backoff version for ZD-5 retry hygiene."""
    from .ziwei_deep_llm import call_llm_with_backoff as call_llm, LLM_MAX_TOKENS, LLM_TIMEOUT_SEC, _convert_ganzhi_to_hangul
    return call_llm, LLM_MAX_TOKENS, LLM_TIMEOUT_SEC, _convert_ganzhi_to_hangul


def build_critic_user_prompt(draft: str, chart_facts: Optional[dict] = None, name: str = "사용자") -> str:
    """Critic user prompt: the draft + minimal context for 'this person's unique chart' judgment.

    이름은 provider로 전송하지 않는다(일반 호칭 고정). draft 는 직전 LLM 응답이므로
    그 안에 이름이 되받아 적혀 있을 수 있어 제거한다.
    """
    from .ziwei_deep_prompt import GENERIC_ADDRESS, _scrub_name

    draft = _scrub_name(draft, name)   # draft 는 직전 LLM 응답 — 되받아 적힌 실명 제거
    name = GENERIC_ADDRESS              # 이 프롬프트 자체엔 실명을 쓰지 않는다
    skeleton_hint = ""
    if chart_facts:
        ming = chart_facts.get("ming_gong", {})
        branch = ming.get("branch", "")
        stars = []
        for key in ("main_stars", "borrowed_stars"):
            for e in ming.get(key, []):
                if isinstance(e, dict) and e.get("star"):
                    stars.append(e["star"])
                elif isinstance(e, str):
                    stars.append(e)
        if branch or stars:
            skeleton_hint = f"\n\n[참고: 이 명반의 명궁은 {branch}이며 주요 별은 {', '.join(stars) if stars else '없음'}입니다. 고유 통찰 판단에만 사용하세요.]"

    return (
        f"초안:\n\n{draft}\n"
        f"{skeleton_hint}\n\n"
        "위 초안을 위의 지침에 따라 검토하고, 정확히 세 항목 형식으로만 출력하세요."
    )


def critique_draft(
    draft: str,
    chart_facts: Optional[dict] = None,
    name: str = "사용자",
    temperature: float = 0.4,  # Slightly lower for consistent editing judgment
    max_tokens: int = None,
) -> dict[str, Any]:
    """
    Run the 자허 critic on a draft.

    Returns:
        {
            "ok": bool,
            "critique": str | None,   # the raw ▸ formatted output
            "issues": list[str],
            "temperature": float,
        }
    """
    call_llm, LLM_MAX_TOKENS, LLM_TIMEOUT_SEC, _convert_ganzhi_to_hangul = _get_llm_utils()
    if max_tokens is None:
        max_tokens = LLM_MAX_TOKENS

    if not draft or not draft.strip():
        return {
            "ok": False,
            "critique": None,
            "issues": ["초안이 비어 있습니다."],
            "temperature": temperature,
        }

    system = CRITIC_SYSTEM_PROMPT
    user = build_critic_user_prompt(draft, chart_facts, name)

    text = call_llm(
        system_prompt=system,
        user_prompt=user,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=LLM_TIMEOUT_SEC,
    )

    if text is None:
        return {
            "ok": False,
            "critique": None,
            "issues": ["비평 LLM 호출 실패"],
            "temperature": temperature,
        }

    # Strip thinking artifacts if any
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = _convert_ganzhi_to_hangul(text)

    # Basic format guard: must contain the three required bullets
    has_delete = "▸ 삭제 권고:" in text or "삭제 권고" in text
    has_correct = "▸ 정정 필요:" in text or "정정 필요" in text
    has_keep = "▸ 유지 확인:" in text or "유지 확인" in text

    if not (has_delete and has_correct and has_keep):
        # Still return it (generation side will decide fallback), but flag
        return {
            "ok": False,
            "critique": text,
            "issues": ["비평 출력 형식이 불완전합니다 (세 항목 중 일부 누락)"],
            "temperature": temperature,
        }

    return {
        "ok": True,
        "critique": text,
        "issues": [],
        "temperature": temperature,
    }


def parse_critique(critique_text: str) -> dict[str, str]:
    """Light parser for improvement.md logging and future automation."""
    result = {"delete": "", "correct": "", "keep": ""}
    if not critique_text:
        return result

    sections = re.split(r"▸\s*(삭제 권고|정정 필요|유지 확인)\s*:", critique_text)
    current = None
    for part in sections:
        part = part.strip()
        if part in ("삭제 권고", "정정 필요", "유지 확인"):
            current = part
            continue
        if current == "삭제 권고":
            result["delete"] = part
            current = None
        elif current == "정정 필요":
            result["correct"] = part
            current = None
        elif current == "유지 확인":
            result["keep"] = part
            current = None
    return result
