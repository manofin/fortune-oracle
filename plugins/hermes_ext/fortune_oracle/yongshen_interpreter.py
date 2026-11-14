"""Fortune Oracle — Yongshen Interpreter (Phase 17).

YongshenResult → Telegram compact text 변환.

표현 정책:
- rule-based 참고임을 명시
- 확정 예언 금지, 오락/자기성찰 톤 유지
- 의학/투자/법률 결정 지시 금지
- 공포 조장 금지
- birth_date/time/name_hanja 미노출

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

from typing import Optional

from hermes_ext.fortune_oracle.yongshen import YongshenResult, calculate_yongshen

# ---------------------------------------------------------------------------#
# 기존 상수 및 원본 함수 (절대 변경 금지)
# ---------------------------------------------------------------------------#

_DISCLAIMER = "이 판단은 rule-based 참고이며, 절대 판정은 아닙니다."

# 오행 운세 표현 (favorable)
_FAVORABLE_DESC = {
    "목": "木 기운이 흐름을 살리는 보조 기운으로 읽힙니다.",
    "화": "火 기운이 표현과 추진력을 살려주는 흐름입니다.",
    "토": "土 기운이 안정과 기반을 다지는 보조 기운으로 읽힙니다.",
    "금": "金 기운이 정제와 결단을 강화해주는 흐름입니다.",
    "수": "水 기운이 유연성과 성찰을 깊게 해주는 보조 기운으로 읽힙니다.",
}

# 오행 운세 표현 (caution)
_CAUTION_DESC = {
    "목": "木이 과하면 변화가 많아지고 산만해지는 흐름이 강해질 수 있습니다.",
    "화": "火가 과하면 충동적 결정과 에너지 소모가 늘어날 수 있습니다.",
    "토": "土가 과하면 정체와 답답함이 이어지는 흐름이 강해집니다.",
    "금": "金이 과하면 생각이 많아지고 결정이 늦어지는 흐름이 강해질 수 있습니다.",
    "수": "水가 과하면 소극적이고 불안한 흐름이 강해질 수 있습니다.",
}

_STRENGTH_KO = {
    "strong": "강",
    "balanced": "중",
    "weak": "약",
}


def build_yongshen_note(
    result: YongshenResult,
    max_lines: int = 3,
) -> str:
    """YongshenResult → /show_profile 용신 compact note.

    Args:
        result: calculate_yongshen 반환값
        max_lines: 최대 출력 줄 수

    Returns:
        용신 note 텍스트 (헤더 포함)
    """
    if not result.ok:
        return ""

    if not result.day_master:
        return "\n용신 참고\n- 일간 정보가 없어 용신 판단을 보류합니다."

    lines = []

    # 강약 정보 1줄 (일간·월지 계절·강약)
    strength_ko = _STRENGTH_KO.get(result.strength, result.strength)
    season_part = f"·{result.season}계절" if result.season else ""
    strength_line = f"일간 {result.day_master_element}{season_part}·{strength_ko}({result.confidence})"
    lines.append(strength_line)

    # favorable
    for elem in result.favorable_elements[:2]:
        desc = _FAVORABLE_DESC.get(elem, f"{elem} 기운이 보조 기운으로 읽힙니다.")
        lines.append(desc)

    # caution (1개만)
    for elem in result.caution_elements[:1]:
        desc = _CAUTION_DESC.get(elem, f"{elem}이 과하면 균형이 흔들릴 수 있습니다.")
        lines.append(desc)

    # disclaimer
    lines.append(_DISCLAIMER)

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n용신 참고\n{body}"


def build_show_profile_yongshen_note(
    eight_char: Optional[dict],
    max_lines: int = 2,
) -> str:
    """eight_char → /show_profile 용신 compact note (fail-open).

    eight_char 없거나 실패 시 빈 문자열 반환.
    birth_date/time/name_hanja 포함되지 않음.
    """
    if not eight_char:
        return ""
    try:
        result = calculate_yongshen(eight_char)
        return build_yongshen_note(result, max_lines=max_lines)
    except Exception:
        return ""


# ---------------------------------------------------------------------------#
# Gate 추가 함수들 (기존 함수 시그니처 100% 유지)
# ---------------------------------------------------------------------------#

# Gate 3.2
from .yongshen_eopbu import build_eopbu_analysis, build_eopbu_note as _build_eopbu_note_internal


def build_eopbu_note(eight_char: Optional[dict], max_lines: int = 3) -> str:
    """eight_char → 억부법 전용 compact note (신규, 기존 yongshen_note 영향 0)."""
    if not eight_char:
        return ""
    try:
        analysis = build_eopbu_analysis(eight_char)
        return _build_eopbu_note_internal(analysis, max_lines=max_lines)
    except Exception:
        return ""


def build_show_profile_eopbu_note(eight_char: Optional[dict], max_lines: int = 2) -> str:
    """fail-open wrapper for /show_profile (eopbu only)."""
    if not eight_char:
        return ""
    try:
        return build_eopbu_note(eight_char, max_lines=max_lines)
    except Exception:
        return ""


# Gate 3.3
from .yongshen_johu import build_johu_analysis, build_johu_note as _build_johu_note_internal


def build_johu_note(eight_char: Optional[dict], max_lines: int = 3) -> str:
    """eight_char → 조후법 전용 compact note (신규, 억부/기존 노트 영향 0)."""
    if not eight_char:
        return ""
    try:
        analysis = build_johu_analysis(eight_char)
        return _build_johu_note_internal(analysis, max_lines=max_lines)
    except Exception:
        return ""


def build_show_profile_johu_note(eight_char: Optional[dict], max_lines: int = 2) -> str:
    """fail-open wrapper for /show_profile (johu only, 병렬 제시용)."""
    if not eight_char:
        return ""
    try:
        return build_johu_note(eight_char, max_lines=max_lines)
    except Exception:
        return ""


# Gate 3.4
from .yongshen_tonggwan import build_tonggwan_analysis, build_tonggwan_note as _build_tonggwan_note_internal


def build_tonggwan_note(eight_char: Optional[dict], max_lines: int = 3) -> str:
    """eight_char → 통관법 전용 compact note (신규, 억부/조후/기존 노트 영향 0)."""
    if not eight_char:
        return ""
    try:
        analysis = build_tonggwan_analysis(eight_char)
        return _build_tonggwan_note_internal(analysis, max_lines=max_lines)
    except Exception:
        return ""


def build_show_profile_tonggwan_note(eight_char: Optional[dict], max_lines: int = 2) -> str:
    """fail-open wrapper for /show_profile (tonggwan only, 병렬 제시용)."""
    if not eight_char:
        return ""
    try:
        return build_tonggwan_note(eight_char, max_lines=max_lines)
    except Exception:
        return ""


# Gate 3.5
from .yongshen_gyeokguk import build_gyeokguk_analysis, build_gyeokguk_note as _build_gyeokguk_note_internal


def build_gyeokguk_note(eight_char: Optional[dict], max_lines: int = 3) -> str:
    """eight_char → 격국(1차 매핑) 전용 compact note (신규)."""
    if not eight_char:
        return ""
    try:
        analysis = build_gyeokguk_analysis(eight_char)
        return _build_gyeokguk_note_internal(analysis, max_lines=max_lines)
    except Exception:
        return ""


def build_show_profile_gyeokguk_note(eight_char: Optional[dict], max_lines: int = 2) -> str:
    """fail-open wrapper for /show_profile (gyeokguk only)."""
    if not eight_char:
        return ""
    try:
        return build_gyeokguk_note(eight_char, max_lines=max_lines)
    except Exception:
        return ""


# Gate 3.6 - 통합 Confidence Score
from .yongshen_confidence import calculate_confidence


def build_yongshen_confidence_note(eight_char: Optional[dict], max_lines: int = 8) -> str:
    """
    4가지 방법(Eopbu/Johu/Tonggwan/Gyeokguk) + Confidence Score 통합 노트.
    기존 build_yongshen_note 등 본문은 절대 변경하지 않음.
    """
    if not eight_char:
        return ""
    try:
        eopbu = build_eopbu_analysis(eight_char)
        johu = build_johu_analysis(eight_char)
        tonggwan = build_tonggwan_analysis(eight_char)
        gyeokguk = build_gyeokguk_analysis(eight_char)

        conf = calculate_confidence(
            eopbu_elem=eopbu.eopbu_favorable[0] if eopbu.eopbu_favorable else None,
            johu_elem=johu.johu_favorable[0] if johu.johu_favorable else None,
            tonggwan_elem=tonggwan.tonggwan_element,
            gyeokguk_elem=gyeokguk.gyeokguk,
        )

        lines = []
        lines.append("용신 종합 참고")

        if eopbu.ok and eopbu.eopbu_favorable:
            lines.append(f"- 억부: {', '.join(eopbu.eopbu_favorable[:2])}")
        if johu.ok and johu.johu_favorable:
            lines.append(f"- 조후: {', '.join(johu.johu_favorable[:2])}")
        if tonggwan.ok and tonggwan.tonggwan_element:
            lines.append(f"- 통관: {tonggwan.tonggwan_element}")
        if gyeokguk.ok and gyeokguk.gyeokguk:
            lines.append(f"- 격국: {gyeokguk.gyeokguk} (1차 매핑)")

        lines.append(conf.display_text)

        if "판단 보류" not in conf.display_text:
            lines.append("이 판단은 rule-based 참고이며, 절대 판정은 아닙니다.")

        body = "\n".join(f"- {l}" for l in lines[:max_lines])
        return f"\n{body}"
    except Exception:
        return ""
