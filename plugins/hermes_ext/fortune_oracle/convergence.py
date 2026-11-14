"""Grand Convergence — Pure Ticket Convergence Judge.

3시스템(자미두수·베딕·서양) 티켓 → 수렴 판정.
점수화 없음. 티켓 투표 기반.

수렴 규칙 (동점 엄격):
  3표          → 강한 수렴
  2표(단일)    → 수렴 (한 원형만 2표, 나머지는 ≤1표)
  2:1          → 부분 수렴 (두 원형만, 하나는 2표 하나는 1표)
  2:2          → 다면적 (동점 = 갈림)
  1:1:1        → 다면적
  1:1          → 다면적

동점(2:2)은 수렴 아님. 두 원형이 갈리는 것이므로 다면성.
수렴은 한 원형이 명확히 앞설 때만.

자미두수 특별 규칙 (Tie-breaker):
  1:1:1일 때 → 자미두수 투표 결과를 "명궁 본질(core)"으로 보고,
                나머지 두 개는 "외부/관계/후천"으로 매핑
  2:1에서 1표가 자미두수 → 보조 원형 더 강하게 서술
  2표에 자미두수 포함 → "주된 원형이 명궁과 일치하여 더욱 안정적"

출력: 수렴 판정 + 서술용 요약 + 내부 갈등 포인트 + 스토리 활용 제안
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

_ARCHETYPES = {"온화", "실행", "리더", "독립", "사고"}

# 시스템별 라벨
_SYSTEM_LABEL = {
    "ziwei": "자미두수(명궁)",
    "vedic": "베딕(카르마)",
    "western": "서양(심리/잠재력)",
}

# 1:1:1일 때 시스템별 외부 설명 매핑
_SYSTEM_EXTERNAL = {
    "ziwei": "타고난 본질(명궁)",
    "vedic": "카르마적 축",
    "western": "심리/잠재력 축",
}

_ARCHETYPE_DESC = {
    "온화": "감정 깊고, 관계 중심이며, 치유와 보호 본능이 강한",
    "실행": "행동 지향적이고, 체계적이고, 목표를 향해 꾸준히 나아가는",
    "리더": "주도적이고, 영향력이 크며, 다른 사람을 이끄는",
    "독립": "자주적이고, 경계가 뚜렷하며, 타의에 휘둘리지 않는",
    "사고": "분석적이며, 지성을 중시하고, 아이디어와 가능성에 끌리는",
}


def _top_archetypes(tickets: List[str], n: int = 3) -> List[Tuple[str, int]]:
    """티켓에서 상위 n개 원형 + 투표 수."""
    counter = Counter(tickets)
    return counter.most_common(n)


def _count_per_archetype(tickets: List[str]) -> Dict[str, int]:
    counter = Counter(tickets)
    return dict(counter)


def _convergence_type(top: List[Tuple[str, int]], vote_detail: Dict[str, List[str]]) -> str:
    """상위 원형 분포 → 수렴 판정 (구조 조건, 점수 임계 금지).

    구조:
      - 다면적: 1등이 동점(2개 이상 최다 동률).
      - 명확 수렴: 1등이 단일이며, 그 원형이 시스템 과반(2/3)에서 *단독* 지목되고,
                  2등 표수가 1 이하.
      - 약한 수렴: 1등이 단일이되 명확 조건을 만족하지 않음 (동점 아님).
    """
    if not top:
        return "무표"

    top_count = top[0][1]
    top_holders = sum(1 for _, c in top if c == top_count)
    second_count = top[1][1] if len(top) > 1 else 0

    # 다면적: 1등이 동점
    if top_holders >= 2:
        return "다면적"

    # 1등이 단일 (top_holders == 1)
    primary = top[0][0]

    # 명확 수렴 조건: 1등이 과반 시스템에서 단독 지목 + 2등 1표 이하
    systems_with_primary = 0
    systems_with_primary_only = 0
    for sys_tickets in vote_detail.values():
        if primary in sys_tickets:
            systems_with_primary += 1
            if len(sys_tickets) == 1:
                systems_with_primary_only += 1

    has_majority_sole = systems_with_primary >= 2 and systems_with_primary_only >= 2
    if has_majority_sole and second_count <= 1:
        return "명확 수렴"

    # 그 외 단일 1등 → 약한 수렴
    return "약한 수렴"


def _narrative_summary(conv_type: str, primary: str, secondary: Optional[str],
                       ziwei_in_primary: bool, ziwei_in_secondary: bool,
                       tertiary: Optional[str]) -> str:
    """수렴 판정 → 서술용 한 줄 요약 (주/보조 서열 없음)."""
    desc = _ARCHETYPE_DESC.get(primary, "")

    if conv_type == "명확 수렴":
        return (f"세 시스템이 '{primary}'를 강하게 지목하며, 이 인물은 {desc}"
                f"본질적으로 안정된 핵심을 가진 존재다. 다른 신호가 있어도"
                f" 수렴은 '{primary}'다.")

    if conv_type == "약한 수렴":
        other = ""
        if secondary:
            sec_desc = _ARCHETYPE_DESC.get(secondary, "")
            other = f" '{secondary}'({sec_desc.rstrip()}) 신호도 함께 나타난다."
        return (f"'{primary}'로 기울며{other}"
                f" 기본은 {desc} 존재다.")

    if conv_type == "수렴":
        stability = "명궁과 일치하여" if ziwei_in_primary else ""
        return (f"'{primary}'가 주된 흐름{stability}, 특정 상황에서는 다른 면이"
                f" 드러나기도 하나, 기본은 {desc} 존재다.")

    # 다면적
    parts = [primary]
    if secondary:
        parts.append(secondary)
    if tertiary:
        parts.append(tertiary)
    archetypes_str = "·".join(parts)
    return (f"세 시스템이 서로 다른 원형('{archetypes_str}')을"
            f" 지목할 정도로, 이 인물은 단일한 본질로 환원되지 않는 복합적인 존재다."
            f" 상황과 관계에 따라 전혀 다른 면이 드러나며,"
            f" 이는 종종 본인조차도 예상하지 못한 행동으로 이어진다.")


def _conflict_points(primary: str, secondary: Optional[str],
                     tertiary: Optional[str]) -> List[str]:
    """수렴 판정 → 내부 갈등 포인트 추출."""
    points = []
    if secondary:
        p1 = _ARCHETYPE_DESC.get(primary, "")
        p2 = _ARCHETYPE_DESC.get(secondary, "")
        points.append(f"'{primary}'({p1.rstrip()})와 '{secondary}'({p2.rstrip()})의 공존")
    if tertiary:
        p3 = _ARCHETYPE_DESC.get(tertiary, "")
        points.append(f"'{tertiary}'({p3.rstrip()})의 추가 층위")
    return points


def _story_suggestion(conv_type: str, primary: str,
                      secondary: Optional[str], tertiary: Optional[str]) -> str:
    """수렴 판정 → 스토리 활용 제안."""
    if conv_type == "강한 수렴":
        return (f"'{primary}'가 매우 안정적이므로, 이 인물이 '{primary}'를"
                f" 상실하는 시나리오에서 가장 큰 드라마가 나온다.")
    if conv_type == "부분 수렴" and secondary:
        return (f"'{primary}'와 '{secondary}' 사이의 내적 갈등을"
                f" 스토리의 핵심 모티브로 활용 가능.")
    if conv_type == "다면적":
        return (f"다면적이므로, 다른 캐릭터가 이 인물에 대해 서로 다른 해석을"
                f" 가지는 설정이 자연스럽게 작동한다.")
    return f"'{primary}'를 기반으로 스토리를 전개."


def judge_convergence(
    ziwei_tickets: List[str],
    vedic_tickets: List[str],
    western_tickets: List[str],
) -> Dict[str, Any]:
    """3시스템 티켓 → 수렴 판정.

    Args:
        ziwei_tickets: 자미두수 티켓 (1~3개 원형)
        vedic_tickets: 베딕 티켓 (1~3개 원형)
        western_tickets: 서양 티켓 (1~3개 원형)

    Returns:
        {
            "convergence_type": str,     # 강한 수렴 / 수렴 / 부분 수렴 / 다면적
            "primary": str,              # 주된 원형
            "secondary": str or None,    # 보조 원형
            "tertiary": str or None,     # 3번째 원형 (다면적일 때)
            "ziwei_in_primary": bool,    # 자미두수가 주 원형에 포함
            "ziwei_in_secondary": bool,  # 자미두수가 보조 원형에 포함
            "narrative_summary": str,    # 서술용 한 줄 요약
            "conflict_points": List[str],# 내부 갈등 포인트
            "story_suggestion": str,     # 스토리 활용 제안
            "vote_detail": Dict[str, List[str]],  # 시스템별 투표 상세
        }
    """
    # 유효 티켓만 (5원형 기준)
    ziwei_valid = [t for t in ziwei_tickets if t in _ARCHETYPES]
    vedic_valid = [t for t in vedic_tickets if t in _ARCHETYPES]
    western_valid = [t for t in western_tickets if t in _ARCHETYPES]

    vote_detail = {
        "ziwei": ziwei_valid,
        "vedic": vedic_valid,
        "western": western_valid,
    }

    # 모든 투표 합치기
    all_votes = ziwei_valid + vedic_valid + western_valid

    if not all_votes:
        return {
            "convergence_type": "무표",
            "primary": None,
            "secondary": None,
            "tertiary": None,
            "ziwei_in_primary": False,
            "ziwei_in_secondary": False,
            "narrative_summary": "3시스템 모두에서 유효한 티켓이 없습니다.",
            "conflict_points": [],
            "story_suggestion": "",
            "vote_detail": vote_detail,
        }

    top = _top_archetypes(all_votes, 5)
    conv_type = _convergence_type(top, vote_detail)

    primary = top[0][0] if top else None
    secondary = top[1][0] if len(top) > 1 else None
    tertiary = top[2][0] if len(top) > 2 else None

    if primary is None:
        # 이미 위에서 무표 케이스 처리됨이지만 타입 안전
        return {
            "convergence_type": "무표",
            "primary": None,
            "secondary": None,
            "tertiary": None,
            "ziwei_in_primary": False,
            "ziwei_in_secondary": False,
            "narrative_summary": "유효한 원형이 없습니다.",
            "conflict_points": [],
            "story_suggestion": "",
            "vote_detail": vote_detail,
        }

    # 자미두수 위치 확인
    ziwei_in_primary = primary in ziwei_valid
    ziwei_in_secondary = bool(secondary and secondary in ziwei_valid)

    summary = _narrative_summary(
        conv_type, primary, secondary,
        ziwei_in_primary, ziwei_in_secondary, tertiary,
    )
    conflicts = _conflict_points(primary, secondary, tertiary)
    suggestion = _story_suggestion(conv_type, primary, secondary, tertiary)

    return {
        "convergence_type": conv_type,
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "ziwei_in_primary": ziwei_in_primary,
        "ziwei_in_secondary": ziwei_in_secondary,
        "narrative_summary": summary,
        "conflict_points": conflicts,
        "story_suggestion": suggestion,
        "vote_detail": vote_detail,
    }


def format_convergence(result: Dict[str, Any]) -> str:
    """수렴 판정 → 가독성 포맷 (주/보조 서열 없음)."""
    if result["convergence_type"] == "무표":
        return result["narrative_summary"]

    conv = result["convergence_type"]
    primary = result["primary"]

    lines = [f"수렴 판정: {conv}"]

    if conv in ("명확 수렴", "약한 수렴", "수렴"):
        lines.append(f"수렴 원형: {primary}")
        if result["ziwei_in_primary"]:
            lines.append("※ 명궁과 일치")
    elif conv == "다면적":
        parts = []
        if result["primary"]:
            parts.append(result["primary"])
        if result["secondary"]:
            parts.append(result["secondary"])
        if result["tertiary"]:
            parts.append(result["tertiary"])
        if parts:
            lines.append(f"두드러지는 원형: {'·'.join(parts)}")

    if result.get("secondary") and conv not in ("다면적",):
        # 수렴일 때 additional 신호 표기 (보조 아님)
        lines.append(f"다른 신호: {result['secondary']}")
    if result.get("tertiary"):
        lines.append(f"추가 신호: {result['tertiary']}")

    lines.append("")
    lines.append(f"[서술] {result['narrative_summary']}")
    lines.append("")
    if result["conflict_points"]:
        lines.append("[내부 갈등]")
        for p in result["conflict_points"]:
            lines.append(f"  - {p}")
    lines.append("")
    if result["story_suggestion"]:
        lines.append(f"[스토리 제안] {result['story_suggestion']}")

    return "\n".join(lines)
