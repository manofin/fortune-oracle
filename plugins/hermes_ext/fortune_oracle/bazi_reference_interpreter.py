"""Fortune Oracle — Bazi Reference Interpreter (Phase 12).

bazi_reference.py의 테이블을 기반으로
BaziResult → 사람이 읽을 수 있는 참고 노트를 생성한다.

원칙:
- 오락/자기성찰 톤 유지
- 단정 금지 (진단·예언·투자·법률 지시 없음)
- birth_date/birth_time/name_hanja 미노출
- 외부 네트워크/AI 호출 없음
- deterministic: 같은 입력 → 항상 같은 출력

이 결과는 오락과 자기성찰 용도이며
의학, 투자, 법률 결정을 지시하지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hermes_ext.fortune_oracle.bazi_reference import (
    HEAVENLY_STEMS,
    EARTHLY_BRANCHES,
    ELEMENT_REFLECTIONS,
    TEN_GODS_TABLE,
    ATTRIBUTION,
    get_ten_god,
    get_hidden_stems,
    get_shichen,
    analyze_element_balance,
)

_DISCLAIMER = ATTRIBUTION["disclaimer"]

# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class BaziReferenceNote:
    """bazi_reference 해석 결과."""
    ok: bool
    day_master_note: str = ""          # 일간 기질 참고
    element_balance_note: str = ""     # 오행 균형 참고
    hidden_stems_note: str = ""        # 지장간 참고
    ten_god_notes: List[str] = field(default_factory=list)  # 십신 참고
    shichen_note: str = ""             # 시진 참고
    yajashi_warning: str = ""          # 야자시 경고 (있으면)
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = _DISCLAIMER

    def to_telegram_text(self, include_ten_gods: bool = False) -> str:
        """Telegram 텍스트 포맷. 간결하게 핵심만."""
        parts: List[str] = []

        if self.day_master_note:
            parts.append(f"일간 기질\n{self.day_master_note}")

        if self.element_balance_note:
            parts.append(f"오행 균형\n{self.element_balance_note}")

        if self.hidden_stems_note:
            parts.append(f"지장간\n{self.hidden_stems_note}")

        if include_ten_gods and self.ten_god_notes:
            parts.append("십신 참고\n" + "\n".join(f"  {n}" for n in self.ten_god_notes[:3]))

        if self.shichen_note:
            parts.append(f"시진\n{self.shichen_note}")

        if self.yajashi_warning:
            parts.append(f"⚠ {self.yajashi_warning}")

        if not parts:
            return ""

        body = "\n\n".join(parts)
        return f"{body}\n\n{_DISCLAIMER}"


# ---------------------------------------------------------------------------
# 핵심 해석 함수
# ---------------------------------------------------------------------------

def interpret_bazi_reference(
    eight_char: Optional[Dict[str, str]],
    elements: Optional[Dict[str, int]],
    birth_hour: Optional[int] = None,
    birth_minute: int = 0,
) -> BaziReferenceNote:
    """BaziResult의 eight_char + elements를 참고 테이블로 해석.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
        elements:   {"목": 3, "화": 2, ...}
        birth_hour: 출생 시각 (시), None이면 시진/야자시 스킵
        birth_minute: 출생 분

    Returns:
        BaziReferenceNote
    """
    if not eight_char:
        return BaziReferenceNote(ok=False, warnings=["eight_char 없음"])

    notes = BaziReferenceNote(ok=True)

    # 1. 일간 기질
    day_ganzhi = eight_char.get("day", "")
    day_stem = day_ganzhi[0] if day_ganzhi else ""
    day_branch = day_ganzhi[1] if len(day_ganzhi) > 1 else ""

    if day_stem and day_stem in HEAVENLY_STEMS:
        dm = HEAVENLY_STEMS[day_stem]
        notes.day_master_note = (
            f"{dm['kor']}({day_stem}) — {dm['element']} {dm['polarity']}\n"
            f"{dm['tendency']}"
        )
    else:
        notes.warnings.append(f"일간 '{day_stem}' 테이블 미등록")

    # 2. 오행 균형
    if elements:
        bal = analyze_element_balance(elements)
        notes.element_balance_note = bal["balance_note"]
        if bal["dominant"]:
            elem_ref = ELEMENT_REFLECTIONS.get(bal["dominant"], "")
            if elem_ref:
                notes.element_balance_note += f"\n  {elem_ref}"

    # 3. 지장간 — 일지 기반
    if day_branch:
        hs = get_hidden_stems(day_branch)
        if hs:
            hs_text = " · ".join(
                f"{s}({HEAVENLY_STEMS[s]['element']} {HEAVENLY_STEMS[s]['polarity']})"
                if s in HEAVENLY_STEMS else s
                for s in hs
            )
            notes.hidden_stems_note = f"일지({day_branch}) 지장간: {hs_text}"

    # 4. 십신 — 년간/월간/시간 vs 일간
    if day_stem:
        for pillar_name, pillar_key in [("년간", "year"), ("월간", "month"), ("시간", "time")]:
            pillar_ganzhi = eight_char.get(pillar_key, "")
            pillar_stem = pillar_ganzhi[0] if pillar_ganzhi else ""
            if pillar_stem and pillar_stem in HEAVENLY_STEMS:
                tg = get_ten_god(day_stem, pillar_stem)
                if tg:
                    notes.ten_god_notes.append(
                        f"{pillar_name}({pillar_stem}): {tg['name']}({tg['hanja']}) — {tg['reflection']}"
                    )

    # 5. 시진 + 야자시 경고
    if birth_hour is not None:
        shichen_branch, is_boundary = get_shichen(birth_hour, birth_minute)
        sc_data = EARTHLY_BRANCHES.get(shichen_branch, {})
        notes.shichen_note = (
            f"{shichen_branch}시({sc_data.get('hour_range', '?')}) — "
            f"{sc_data.get('element', '?')} {sc_data.get('polarity', '?')}"
        )
        if is_boundary:
            notes.yajashi_warning = (
                "출생 시각이 23:00~00:00 사이입니다 (야자시 경계). "
                "일부 사주 유파에서는 이 시간대를 '야자시'로 구분해 "
                "다음 날 子時로 처리합니다. 결과에 차이가 있을 수 있습니다."
            )

    return notes


def build_reference_note_from_bazi_result(bazi_result) -> Optional[BaziReferenceNote]:
    """BaziResult 객체에서 직접 BaziReferenceNote를 생성.

    bazi_result가 ok=False이거나 eight_char가 없으면 None 반환.
    """
    if not getattr(bazi_result, "ok", False):
        return None
    if not getattr(bazi_result, "eight_char", None):
        return None

    # birth_hour 추출 — bazi_result.input에서 시도
    birth_hour: Optional[int] = None
    birth_minute: int = 0
    inp = getattr(bazi_result, "input", None) or {}
    birth_time_str = inp.get("birth_time", "")
    if birth_time_str and ":" in birth_time_str:
        try:
            h, m = birth_time_str.split(":")[:2]
            birth_hour = int(h)
            birth_minute = int(m)
        except (ValueError, TypeError):
            pass

    return interpret_bazi_reference(
        eight_char=bazi_result.eight_char,
        elements=bazi_result.elements,
        birth_hour=birth_hour,
        birth_minute=birth_minute,
    )
