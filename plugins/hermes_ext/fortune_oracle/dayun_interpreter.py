"""Fortune Oracle — Dayun Interpreter (Phase 14B).

DayunResult → Telegram compact text 변환.

표현 정책:
- 확정적 예언 금지, 오락/자기성찰 톤 유지
- gender unknown → 명확한 안내 메시지
- 의학/투자/법률 결정 지시 금지
- 공포 조장 금지
- birth_date/time/name_hanja 미노출

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

import datetime
from typing import Optional

from hermes_ext.fortune_oracle.dayun import DayunResult, calculate_dayun_skeleton

_DISCLAIMER = "이 결과는 오락과 자기성찰용 참고입니다."


def build_dayun_note(
    result: DayunResult,
    current_year: Optional[int] = None,
    birth_year: Optional[int] = None,
    max_lines: int = 3,
) -> str:
    """DayunResult → /show_profile 대운 compact note.

    Args:
        result: calculate_dayun_skeleton 반환값
        current_year: 현재 연도 (기본: 실제 현재 연도)
        birth_year: 출생 연도 (현재 대운 감지에 사용)
        max_lines: 최대 출력 줄 수

    Returns:
        대운 note 텍스트 (헤더 포함)
    """
    if current_year is None:
        current_year = datetime.date.today().year

    if not result.ok:
        return "\n대운 흐름\n- 대운 계산 불가: " + ", ".join(result.warnings)

    # gender unknown
    if result.direction == "unknown":
        lines = [
            "대운 방향 산정에는 성별 정보가 필요합니다.",
            "현재는 팔자 구조 기반의 장기 리듬 참고만 표시합니다.",
        ]
        body = "\n".join(f"- {l}" for l in lines[:max_lines])
        return f"\n대운 흐름\n{body}"

    # 현재 나이 계산
    current_age: Optional[int] = None
    if birth_year is not None:
        current_age = current_year - birth_year

    # 현재 대운 사이클
    current_cycle = None
    if current_age is not None and result.cycles:
        current_cycle = result.current_cycle(current_age)

    lines = []

    direction_label = "순행" if result.direction == "forward" else "역행"
    lines.append(f"대운은 {direction_label}으로 흐릅니다 (시작 나이 약 {result.start_age}세, 참고).")

    if current_cycle:
        lines.append(
            f"현재 대운 ({current_cycle.age_from}~{current_cycle.age_to}세): "
            f"{current_cycle.pillar} — {current_cycle.theme}."
        )
        # 다음 대운 preview
        next_cycles = [c for c in result.cycles if c.age_from > current_cycle.age_from]
        if next_cycles:
            nxt = next_cycles[0]
            lines.append(
                f"다음 대운 ({nxt.age_from}~{nxt.age_to}세): "
                f"{nxt.pillar} — {nxt.theme}."
            )
    elif result.cycles:
        # 현재 나이 불명 시 첫 대운 표시
        first = result.cycles[0]
        lines.append(
            f"첫 대운 ({first.age_from}~{first.age_to}세): "
            f"{first.pillar} — {first.theme}."
        )

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n대운 흐름\n{body}"


def build_show_profile_dayun_note(
    eight_char: Optional[dict],
    gender: Optional[str] = None,
    birth_year: Optional[int] = None,
    max_lines: int = 2,
) -> str:
    """eight_char → /show_profile 대운 compact note (fail-open).

    gender 없으면 unknown 안내 반환.
    eight_char 없거나 실패 시 빈 문자열 반환.
    """
    if not eight_char:
        return ""
    try:
        result = calculate_dayun_skeleton(eight_char, gender=gender, birth_year=birth_year)
        return build_dayun_note(result, birth_year=birth_year, max_lines=max_lines)
    except Exception:
        return ""
