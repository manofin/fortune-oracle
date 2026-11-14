"""Fortune Oracle — Bazi Relation Interpreter (Phase 13).

BaziRelationReport → Telegram compact text 변환.

표현 정책:
- 확정적/예측적 표현 허용: "강하게 드러납니다", "두드러집니다"
- 의학/투자/법률 결정 지시 금지
- 공포 조장 금지: "반드시 파국", "피할 수 없는 파멸" 등
- 충 관계는 "변화/긴장/재배치"로 표현하되 단정 금지
- birth_date/time/name_hanja 미노출

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

from typing import List, Optional

from hermes_ext.fortune_oracle.bazi_relations import BaziRelationReport, detect_relations

_DISCLAIMER = "이 결과는 오락과 자기성찰용 참고입니다."

# ---------------------------------------------------------------------------
# compact note 생성
# ---------------------------------------------------------------------------

def _compact_lines(report: BaziRelationReport, max_lines: int = 4) -> List[str]:
    """report → compact 운세 문장 리스트 (최대 max_lines개)."""
    lines: List[str] = []

    # 삼합 (우선순위 1)
    for entry in report.san_he:
        lines.append(
            f"{'/'.join(entry.branches)} 삼합 — "
            f"{entry.combined_element} 기운이 강하게 집중됩니다."
        )

    # 육합 (우선순위 2)
    for entry in report.liu_he:
        lines.append(
            f"{entry.branches[0]}·{entry.branches[1]} 육합 — "
            f"{entry.combined_element} 기운으로 합쳐지는 흐름입니다."
        )

    # 육충 (우선순위 3)
    for entry in report.liu_chong:
        lines.append(
            f"{entry.branches[0]}·{entry.branches[1]} 충 — "
            "긴장과 변화의 흐름이 드러납니다."
        )

    # 형 (Phase 14A, 우선순위 4)
    for entry in report.xing:
        if entry.xing_type == "자형":
            lines.append(f"{entry.branches[0]} 자형 — 내면의 기준이 높아지고 자기 점검이 강해집니다.")
        else:
            b_str = "·".join(entry.branches[:3])
            lines.append(f"{b_str} 형 — 내적 압박과 마찰이 드러날 수 있습니다.")

    # 해 (Phase 14A, 우선순위 5)
    for entry in report.hai:
        lines.append(
            f"{entry.branches[0]}·{entry.branches[1]} 해 — "
            "겉으론 조용하지만 속으로 피로가 쌓이기 쉬운 흐름입니다."
        )

    # 파 (Phase 14A, 우선순위 6)
    for entry in report.po:
        lines.append(
            f"{entry.branches[0]}·{entry.branches[1]} 파 — "
            "기존 패턴을 깨고 재배치하려는 압력이 나타납니다."
        )

    # 중복 지지
    if report.duplicate_branches:
        dups = "·".join(report.duplicate_branches)
        lines.append(f"{dups} 기운이 반복되어 해당 성향이 더욱 강하게 나타납니다.")

    # 관계 없음
    if not lines:
        lines.append("강한 합·충·형·해·파 구조 없이 비교적 고른 흐름입니다.")

    return lines[:max_lines]


def interpret_relations(
    report: BaziRelationReport,
    style: str = "telegram_compact",
) -> str:
    """BaziRelationReport → 운세 텍스트.

    Args:
        report: detect_relations 반환값
        style: "telegram_compact" (기본) | "full"

    Returns:
        포맷된 텍스트 (disclaimer 포함)
    """
    if not report.ok:
        return ""

    lines = _compact_lines(report, max_lines=4 if style == "telegram_compact" else 8)

    body = "\n".join(f"- {l}" for l in lines)
    return f"관계 흐름\n{body}\n\n{_DISCLAIMER}"


def build_show_profile_relation_note(
    eight_char: Optional[dict],
    max_lines: int = 4,
) -> str:
    """eight_char → /show_profile 하단에 붙일 compact relation note.

    eight_char가 없거나 탐지 실패 시 빈 문자열 반환 (fail-open).
    """
    if not eight_char:
        return ""
    try:
        report = detect_relations(eight_char)
        if not report.ok:
            return ""
        lines = _compact_lines(report, max_lines=max_lines)
        body = "\n".join(f"- {l}" for l in lines)
        return f"\n관계 흐름\n{body}"
    except Exception:
        return ""
