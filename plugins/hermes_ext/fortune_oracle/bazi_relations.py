"""Fortune Oracle — Bazi Relation Tables & Detector (Phase 13/14A).

육합(六合) / 삼합(三合) / 육충(六冲) 탐지 및 의미 반환.
형(刑) / 해(害) / 파(破) — Phase 14A 추가.

원칙:
- 오락/자기성찰 톤 유지 (확정 예언 금지, 공포 조장 금지)
- 예측적 표현은 허용: "강하게 드러납니다", "두드러집니다"
- 의학/투자/법률 결정 지시 금지
- 순수 deterministic Python — 외부 네트워크/AI 없음
- birth_date/time/name_hanja 미노출

이 결과는 오락과 자기성찰용 참고입니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. 육합 (六合, Six Harmonies) — 2지지 쌍 조합
# ---------------------------------------------------------------------------

# (지지1, 지지2) → 합화 오행 + 기질 노트
_LIU_HE_RAW: List[Tuple[str, str, str, str]] = [
    ("子", "丑", "토",   "子와 丑이 만나 안정과 축적의 토 기운으로 합쳐집니다. 실리와 인내가 강해지는 흐름입니다."),
    ("寅", "亥", "목",   "寅과 亥가 만나 성장과 출발의 목 기운으로 합쳐집니다. 새로운 시작의 에너지가 살아납니다."),
    ("卯", "戌", "화",   "卯와 戌이 만나 표현과 열정의 화 기운으로 합쳐집니다. 감정과 창의가 두드러지는 조합입니다."),
    ("辰", "酉", "금",   "辰과 酉가 만나 정제와 결단의 금 기운으로 합쳐집니다. 선택과 집중이 부각됩니다."),
    ("巳", "申", "수",   "巳와 申이 만나 유연과 지혜의 수 기운으로 합쳐집니다. 전략적 사고가 살아나는 흐름입니다."),
    ("午", "未", "화토", "午와 未가 만나 따뜻함과 안정이 뒤섞인 화토 기운을 이룹니다. 관계와 조화가 강해집니다."),
]

LIU_HE: Dict[FrozenSet[str], Dict] = {}
for _b1, _b2, _elem, _note in _LIU_HE_RAW:
    LIU_HE[frozenset({_b1, _b2})] = {
        "branches": (_b1, _b2),
        "combined_element": _elem,
        "relation": "육합",
        "note": _note,
    }

# ---------------------------------------------------------------------------
# 2. 삼합 (三合, Three Harmonies) — 3지지 조합
# ---------------------------------------------------------------------------

_SAN_HE_RAW: List[Tuple[Tuple[str, str, str], str, str]] = [
    (("申", "子", "辰"), "수", "申·子·辰이 삼합하여 강한 수 기운의 국을 이룹니다. 지혜, 유연성, 깊은 성찰의 흐름이 두드러집니다."),
    (("亥", "卯", "未"), "목", "亥·卯·未가 삼합하여 강한 목 기운의 국을 이룹니다. 성장, 연결, 창의의 에너지가 살아납니다."),
    (("寅", "午", "戌"), "화", "寅·午·戌이 삼합하여 강한 화 기운의 국을 이룹니다. 열정, 추진력, 표현력이 강하게 드러납니다."),
    (("巳", "酉", "丑"), "금", "巳·酉·丑이 삼합하여 강한 금 기운의 국을 이룹니다. 정밀함, 원칙, 결단의 흐름이 부각됩니다."),
]

SAN_HE: Dict[FrozenSet[str], Dict] = {}
for _branches, _elem, _note in _SAN_HE_RAW:
    SAN_HE[frozenset(_branches)] = {
        "branches": _branches,
        "combined_element": _elem,
        "relation": "삼합",
        "note": _note,
    }

# ---------------------------------------------------------------------------
# 3. 육충 (六冲, Six Clashes) — 2지지 충돌
# ---------------------------------------------------------------------------

_LIU_CHONG_RAW: List[Tuple[str, str, str]] = [
    ("子", "午", "수와 화가 맞부딪히는 충으로, 감정과 이성 사이의 긴장이 두드러질 수 있습니다. 변화와 전환의 계기가 되기도 합니다."),
    ("丑", "未", "土끼리 충돌하는 기운으로, 고집과 안정 사이의 마찰이 강해집니다. 방향 재설정의 시기로 읽힙니다."),
    ("寅", "申", "목과 금의 충으로, 진취성과 제약 사이의 긴장이 뚜렷해집니다. 도전과 정리가 함께 오는 흐름입니다."),
    ("卯", "酉", "목과 금의 충으로, 유연함과 엄격함이 충돌합니다. 관계 재배치가 두드러지는 시기로 이어질 수 있습니다."),
    ("辰", "戌", "토끼리의 충으로, 실용과 고집이 부딪힙니다. 기반을 다시 점검하는 흐름이 강해집니다."),
    ("巳", "亥", "화와 수의 충으로, 열정과 신중함이 갈등을 일으킵니다. 새로운 시도와 내면 정리가 교차하는 흐름입니다."),
]

LIU_CHONG: Dict[FrozenSet[str], Dict] = {}
for _b1, _b2, _note in _LIU_CHONG_RAW:
    LIU_CHONG[frozenset({_b1, _b2})] = {
        "branches": (_b1, _b2),
        "relation": "육충",
        "note": _note,
    }

# ---------------------------------------------------------------------------
# 4. 형 (刑, Punishment) — Phase 14A
# ---------------------------------------------------------------------------

# 형은 쌍(2지지) 또는 삼형(3지지) 구조로 존재.
# 자묘형(子卯刑): 2지지
# 인사신(寅巳申): 3지지 삼형
# 축술미(丑戌未): 3지지 삼형
# 辰午酉亥 자형(自刑): 단일 지지 중복 → conservative 처리 (self_punishment)

_XING_PAIR_RAW: List[Tuple[str, str, str]] = [
    ("子", "卯", "子·卯 형의 기운이 있어 내적 압박과 자기 검열이 강해질 수 있습니다. 관계에서 예상치 못한 마찰이 올라오는 흐름입니다."),
]

XING_PAIR: Dict[FrozenSet[str], Dict] = {}
for _b1, _b2, _note in _XING_PAIR_RAW:
    XING_PAIR[frozenset({_b1, _b2})] = {
        "branches": (_b1, _b2),
        "relation": "형",
        "xing_type": "자묘형",
        "note": _note,
    }

_XING_TRIO_RAW: List[Tuple[Tuple[str, str, str], str, str]] = [
    (("寅", "巳", "申"), "인사신형", "寅·巳·申 삼형의 기운이 있어 내면의 긴장과 추진력이 동시에 강해집니다. 과도한 집착이나 자기 제한이 드러날 수 있습니다."),
    (("丑", "戌", "未"), "축술미형", "丑·戌·未 삼형의 기운이 있어 고집과 완고함이 두드러지는 흐름입니다. 방향 조정이 필요한 시기로 읽힙니다."),
]

XING_TRIO: Dict[FrozenSet[str], Dict] = {}
for _branches, _xing_type, _note in _XING_TRIO_RAW:
    XING_TRIO[frozenset(_branches)] = {
        "branches": _branches,
        "relation": "형",
        "xing_type": _xing_type,
        "note": _note,
    }

# 자형(自刑) 지지 목록 — 중복 시 conservative 처리
_SELF_XING = {"辰", "午", "酉", "亥"}

# ---------------------------------------------------------------------------
# 5. 해 (害, Harm) — Phase 14A
# ---------------------------------------------------------------------------

_HAI_RAW: List[Tuple[str, str, str]] = [
    ("子", "未", "子·未 해의 흐름은 겉으로는 부드러워 보여도 속으로 피로가 쌓이기 쉬운 구조입니다. 관계의 마찰이 조용히 올라옵니다."),
    ("丑", "午", "丑·午 해의 기운이 있어 기대와 현실 사이의 간극이 불편함을 만들어냅니다. 인내와 조율이 필요한 흐름입니다."),
    ("寅", "巳", "寅·巳 해의 흐름은 목표를 향한 추진력에 예기치 못한 저항이 생기기 쉬운 구조입니다. 유연한 전략이 도움이 됩니다."),
    ("卯", "辰", "卯·辰 해의 기운이 있어 표현과 실행 사이에 엇갈림이 생길 수 있습니다. 소통을 세심하게 조율하는 시기로 읽힙니다."),
    ("申", "亥", "申·亥 해의 흐름은 논리와 직관이 서로 충돌하는 구조를 만듭니다. 결정 전 충분한 점검이 흐름을 살립니다."),
    ("酉", "戌", "酉·戌 해의 기운이 있어 완벽주의와 현실 사이의 피로가 쌓일 수 있습니다. 기준을 유연하게 조정하는 흐름이 유리합니다."),
]

HAI: Dict[FrozenSet[str], Dict] = {}
for _b1, _b2, _note in _HAI_RAW:
    HAI[frozenset({_b1, _b2})] = {
        "branches": (_b1, _b2),
        "relation": "해",
        "note": _note,
    }

# ---------------------------------------------------------------------------
# 6. 파 (破, Break) — Phase 14A
# ---------------------------------------------------------------------------

_PO_RAW: List[Tuple[str, str, str]] = [
    ("子", "酉", "子·酉 파의 기운은 기존 패턴을 깨고 새 방식으로 재배치하려는 압력으로 읽힙니다. 변화 뒤에 안정이 따라옵니다."),
    ("丑", "辰", "丑·辰 파의 흐름은 견고해 보이던 구조에 균열이 생기는 시기를 만듭니다. 정리와 재배치의 기운이 강하게 나타납니다."),
    ("寅", "亥", "寅·亥 파의 기운이 있어 시작했던 흐름에 방향 전환의 압력이 올라옵니다. 유연한 대응이 기회를 만듭니다."),
    ("卯", "午", "卯·午 파의 흐름은 감정과 표현 사이의 마찰을 일으킬 수 있습니다. 충동적 결정보다 잠깐의 여유가 흐름을 살립니다."),
    ("巳", "申", "巳·申 파의 기운은 계획과 실행 사이의 간극을 드러냅니다. 전략을 다시 점검하고 재정비하는 흐름으로 읽힙니다."),
    ("未", "戌", "未·戌 파의 흐름은 관계나 환경에서 기존 익숙함을 흔드는 압력으로 나타납니다. 재배치 후 새로운 안정이 찾아옵니다."),
]

PO: Dict[FrozenSet[str], Dict] = {}
for _b1, _b2, _note in _PO_RAW:
    PO[frozenset({_b1, _b2})] = {
        "branches": (_b1, _b2),
        "relation": "파",
        "note": _note,
    }

# ---------------------------------------------------------------------------
# 7. 결과 데이터클래스
# ---------------------------------------------------------------------------

@dataclass
class RelationEntry:
    """개별 관계 항목."""
    relation: str            # "육합" | "삼합" | "육충" | "형" | "해" | "파"
    branches: Tuple[str, ...]
    combined_element: str = ""   # 삼합/육합만
    note: str = ""
    xing_type: str = ""          # 형 세부 유형 (자묘형/인사신형/축술미형/자형)


@dataclass
class BaziRelationReport:
    """detect_relations 결과."""
    ok: bool
    branches: List[str] = field(default_factory=list)   # 4주 지지 목록
    liu_he: List[RelationEntry] = field(default_factory=list)
    san_he: List[RelationEntry] = field(default_factory=list)
    liu_chong: List[RelationEntry] = field(default_factory=list)
    xing: List[RelationEntry] = field(default_factory=list)        # Phase 14A
    hai: List[RelationEntry] = field(default_factory=list)         # Phase 14A
    po: List[RelationEntry] = field(default_factory=list)          # Phase 14A
    self_xing: List[str] = field(default_factory=list)             # Phase 14A 자형
    duplicate_branches: List[str] = field(default_factory=list)  # 중복 지지
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = "이 결과는 오락과 자기성찰용 참고입니다."

    def has_any_relation(self) -> bool:
        return bool(self.liu_he or self.san_he or self.liu_chong
                    or self.xing or self.hai or self.po)

# ---------------------------------------------------------------------------
# 5. 탐지 함수
# ---------------------------------------------------------------------------

def _extract_branches(eight_char: Dict[str, str]) -> List[str]:
    """eight_char → 4주 지지 순서대로 추출.
    간지가 2글자이면 두 번째 글자가 지지.
    """
    result: List[str] = []
    for key in ("year", "month", "day", "time"):
        gz = eight_char.get(key, "")
        if len(gz) >= 2:
            result.append(gz[1])
        elif gz:
            result.append(gz)  # 단일 글자 fallback
    return result


def detect_relations(eight_char: Dict[str, str]) -> BaziRelationReport:
    """사주 four pillars의 지지에서 육합/삼합/육충/형/해/파를 탐지.

    Args:
        eight_char: {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}

    Returns:
        BaziRelationReport
    """
    if not eight_char:
        return BaziRelationReport(ok=False, warnings=["eight_char 없음"])

    branches = _extract_branches(eight_char)
    if not branches:
        return BaziRelationReport(ok=False, warnings=["지지 추출 실패"])

    report = BaziRelationReport(ok=True, branches=branches)

    # 중복 지지 탐지
    seen: Dict[str, int] = {}
    for b in branches:
        seen[b] = seen.get(b, 0) + 1
    report.duplicate_branches = [b for b, cnt in seen.items() if cnt > 1]

    branch_set = set(branches)

    # ── 육합 탐지 ──────────────────────────────────────────────
    for key, val in LIU_HE.items():
        b1, b2 = val["branches"]
        if b1 in branch_set and b2 in branch_set:
            report.liu_he.append(RelationEntry(
                relation="육합",
                branches=(b1, b2),
                combined_element=val["combined_element"],
                note=val["note"],
            ))

    # ── 삼합 탐지 ──────────────────────────────────────────────
    for key, val in SAN_HE.items():
        trio = val["branches"]
        if all(b in branch_set for b in trio):
            report.san_he.append(RelationEntry(
                relation="삼합",
                branches=tuple(trio),
                combined_element=val["combined_element"],
                note=val["note"],
            ))
        else:
            # 반합 탐지 (3개 중 2개)
            matched = [b for b in trio if b in branch_set]
            if len(matched) == 2:
                # 반합은 note만 경고 추가 (정식 관계로 등록하지 않음)
                report.warnings.append(
                    f"반합 가능성: {'/'.join(trio)} 중 {'·'.join(matched)}만 있어 "
                    f"삼합 {val['combined_element']} 국이 불완전합니다."
                )

    # ── 육충 탐지 ──────────────────────────────────────────────
    for key, val in LIU_CHONG.items():
        b1, b2 = val["branches"]
        if b1 in branch_set and b2 in branch_set:
            report.liu_chong.append(RelationEntry(
                relation="육충",
                branches=(b1, b2),
                note=val["note"],
            ))

    # ── 형 탐지 (Phase 14A) ─────────────────────────────────────
    # 자묘형 (2지지)
    for key, val in XING_PAIR.items():
        b1, b2 = val["branches"]
        if b1 in branch_set and b2 in branch_set:
            report.xing.append(RelationEntry(
                relation="형",
                branches=(b1, b2),
                xing_type=val["xing_type"],
                note=val["note"],
            ))

    # 삼형 (3지지)
    for key, val in XING_TRIO.items():
        trio = val["branches"]
        if all(b in branch_set for b in trio):
            report.xing.append(RelationEntry(
                relation="형",
                branches=tuple(trio),
                xing_type=val["xing_type"],
                note=val["note"],
            ))

    # 자형 (自刑) — 중복 지지 중 _SELF_XING에 해당하는 것
    for b in report.duplicate_branches:
        if b in _SELF_XING:
            report.self_xing.append(b)
            report.xing.append(RelationEntry(
                relation="형",
                branches=(b, b),
                xing_type="자형",
                note=f"{b} 자형의 기운이 있어 내면의 기준이 높아지고 자기 점검이 강해질 수 있습니다.",
            ))

    # ── 해 탐지 (Phase 14A) ─────────────────────────────────────
    for key, val in HAI.items():
        b1, b2 = val["branches"]
        if b1 in branch_set and b2 in branch_set:
            report.hai.append(RelationEntry(
                relation="해",
                branches=(b1, b2),
                note=val["note"],
            ))

    # ── 파 탐지 (Phase 14A) ─────────────────────────────────────
    for key, val in PO.items():
        b1, b2 = val["branches"]
        if b1 in branch_set and b2 in branch_set:
            report.po.append(RelationEntry(
                relation="파",
                branches=(b1, b2),
                note=val["note"],
            ))

    # ── summary 생성 ────────────────────────────────────────────
    parts: List[str] = []
    if report.san_he:
        elems = "·".join(r.combined_element for r in report.san_he)
        parts.append(f"삼합 {elems} 국이 형성되어 해당 오행의 기운이 강하게 집중됩니다.")
    if report.liu_he:
        pairs = "·".join(f"{r.branches[0]}{r.branches[1]}" for r in report.liu_he)
        parts.append(f"{pairs} 육합이 있어 두 기운이 서로 당기는 흐름입니다.")
    if report.liu_chong:
        pairs = "·".join(f"{r.branches[0]}{r.branches[1]}" for r in report.liu_chong)
        parts.append(f"{pairs} 육충이 있어 긴장과 변화의 흐름이 드러납니다.")
    if report.xing:
        xing_list = "·".join(
            f"{''.join(r.branches[:2]) if r.xing_type != '자형' else r.branches[0]}"
            for r in report.xing
        )
        parts.append(f"{xing_list} 형의 기운이 있어 내적 압박과 마찰이 드러날 수 있습니다.")
    if report.hai:
        hai_list = "·".join(f"{r.branches[0]}{r.branches[1]}" for r in report.hai)
        parts.append(f"{hai_list} 해의 흐름이 있어 겉으론 조용하지만 내면의 피로가 쌓이기 쉬운 구조입니다.")
    if report.po:
        po_list = "·".join(f"{r.branches[0]}{r.branches[1]}" for r in report.po)
        parts.append(f"{po_list} 파의 기운은 기존 패턴을 재배치하려는 압력으로 읽힙니다.")
    if report.duplicate_branches:
        dups = "·".join(report.duplicate_branches)
        parts.append(f"{dups} 기운이 반복되어 해당 성향이 더욱 강하게 나타납니다.")
    if not parts:
        parts.append("사주 지지 간 강한 합·충·형·해·파 구조는 없습니다.")

    report.summary = " ".join(parts)

    # notes 리스트 (각 관계의 note 모음)
    for entry in report.san_he + report.liu_he + report.liu_chong + report.xing + report.hai + report.po:
        if entry.note:
            report.notes.append(f"[{entry.relation}] {entry.note}")

    return report
