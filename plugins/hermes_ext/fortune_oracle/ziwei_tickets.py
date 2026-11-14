"""Ziwei Doushu — Pure Ticket Issuer (v1, no scoring).

각 시스템을 거친 5원형(리더·독립·사고·온화·실행) "티켓"으로 발급.
- 점수화 완전 제거
- 티켓 = 해당 원형이다 / 아니다 (관대한 기준)
- 라벨은 보조 설명, 경쟁 아님

규칙:
1. 명궁 주성 → 베이스 티켓 (쌍성이면 둘 다).
2. 화과(化科, sihua["科"] 별) → 독립 티켓 추가.
3. 살성(煞星: 화성/영성/경양/타라) 2+ 회조 → 독립 티켓 추가.
   회조 = 명궁 동일궁 또는 인접(三合/三刑).
4. 밝기 함/한 → 해당 주성에 "약화"/"변질" 라벨.
   함 = 陷/死 (weak); 한 = 廟/旺 (strong transformation).
5. 무주성(명궁 주성 없음) → 대궁(命宫+6, 對宮) 티켓 + "차용(환경반응)" 라벨.
6. 길성(吉星: 천괴/천월/좌보/우필/문창/문곡) 2+ → 베이스 티켓에 "안정 발현" 라벨.

확인 후: 호출부에서 facts로부터 tickets 생성.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# 14정성 → 거친 5원형 베이스 매핑 (iztra 중국어 별명 기준, 작가님 명리 판단)
MAIN_STAR_TO_ARCHETYPE: Dict[str, str] = {
    "紫微": "리더",
    "破軍": "리더",
    "七殺": "리더",
    "太陽": "리더",
    "武曲": "독립",
    "巨門": "독립",
    "貪狼": "독립",
    "天機": "사고",
    "天梁": "사고",
    "太陰": "온화",
    "天同": "온화",
    "天相": "온화",
    "天府": "실행",
    "廉貞": "실행",
}

# 한국어 별 → 중국어 별 보조 맵 (aux_stars/문자열 변환 대비)
STAR_KR_TO_CN: Dict[str, str] = {
    "자미": "紫微",
    "파군": "破軍",
    "칠살": "七殺",
    "태양": "太陽",
    "무곡": "武曲",
    "거문": "巨門",
    "탐랑": "貪狼",
    "천기": "天機",
    "천량": "天梁",
    "태음": "太陰",
    "천동": "天同",
    "천상": "天相",
    "천부": "天府",
    "염정": "廉貞",
}

# bright labels (한자) → label type
_BRIGHT_WEAKEN = {"陷", "死"}
_BRIGHT_TRANSFORM = {"廟", "旺"}

# 4살성 (煞星) — 회조 집계용
_SHACHENG = {"화성", "영성", "경양", "타라"}

# 4길성 (吉星) — 안정 발현 라벨 기준
_JICHENG = {"천괴", "천월", "좌보", "우필", "문창", "문곡"}

# 12지지 index(0=子, 1=丑 ... 11=亥) — 인접(三合) 정의
_SAN_HE = {
    0: [4, 8],   # 子 → 辰 申
    1: [7, 11],  # 丑 → 未 亥
    2: [6, 10],  # 寅 → 午 戌
    3: [9, 1],   # 卯 → 酉 丑
    4: [0, 8],   # 辰 → 子 申
    5: [3, 9],   # 巳 → 卯 酉
    6: [2, 10],  # 午 → 寅 戌
    7: [1, 11],  # 未 → 丑 亥
    8: [0, 4],   # 申 → 子 辰
    9: [3, 5],   # 酉 → 卯 巳
    10: [2, 6],  # 戌 → 寅 午
    11: [1, 7],  # 亥 → 丑 未
}

# 12지지 이름 → index
_BRANCH_IDX = {
    "子": 0, "丑": 1, "寅": 2, "卯": 3, "辰": 4, "巳": 5,
    "午": 6, "未": 7, "申": 8, "酉": 9, "戌": 10, "亥": 11,
}


def _branch_to_idx(branch: str) -> Optional[int]:
    return _BRANCH_IDX.get(branch)


def _is_san_ho(b1: str, b2: str) -> bool:
    i1 = _branch_to_idx(b1)
    i2 = _branch_to_idx(b2)
    if i1 is None or i2 is None:
        return False
    return i2 in _SAN_HE.get(i1, [])


def issue_tickets(facts: Dict[str, Any]) -> Dict[str, Any]:
    """ziwei facts → pure ticket structure.

    Returns:
        {
            "ok": bool,
            "tickets": [str, ...],               # 원형 리스트 (관대: 1~4개 가능)
            "labels": {원형: [라벨, ...]},       # 각 티켓 부착 설명
            "raw_hints": {...},                  # 근거 스니펫 (검증용)
        }
    """
    if not facts:
        return {"ok": False, "tickets": [], "labels": {}, "raw_hints": {}}

    ming = facts.get("ming_gong", {}) or {}
    ming_branch = ming.get("branch", "")
    ming_idx = ming.get("index")
    brightness_map: Dict[str, str] = facts.get("brightness", {}) or {}
    sihua: Dict[str, Any] = facts.get("sihua", {}) or {}
    aux: Dict[str, str] = facts.get("aux_stars", {}) or {}

    tickets: List[str] = []
    labels: Dict[str, List[str]] = {}
    hints: Dict[str, Any] = {
        "ming_branch": ming_branch,
        "main_stars": [],
        "borrowed_stars": [],
        "sihua_ke": "",
        "brightness": {},
        "shach_count": 0,
        "jich_count": 0,
        "no_main_star": False,
    }

    # 1. 명궁 주성 분리
    base_stars: List[str] = []
    for e in ming.get("main_stars", []) or []:
        s = e.get("star", "") if isinstance(e, dict) else str(e)
        if s:
            base_stars.append(s)

    borrowed_stars_raw: List[dict] = list(ming.get("borrowed_stars", []) or [])
    borrowed_stars_names: List[str] = []
    for e in borrowed_stars_raw:
        s = e.get("star", "") if isinstance(e, dict) else str(e)
        if s:
            borrowed_stars_names.append(s)

    hints["main_stars"] = base_stars + borrowed_stars_names
    hints["borrowed_stars"] = borrowed_stars_names

    is_no_main = len(base_stars) == 0 and len(borrowed_stars_names) == 0
    hints["no_main_star"] = is_no_main

    if is_no_main:
        # 5. 무주성 → 대궁(명궁+6) 티켓 발급
        if ming_idx is not None:
            opp_idx = (ming_idx + 6) % 12
            opp_branch = _IDX_TO_BRANCH[opp_idx] if 0 <= opp_idx < 12 else ""
            opp_str = str(opp_idx)
            opp_palace_stars = facts.get("stars", {}).get(opp_str, []) or []
            for s in opp_palace_stars:
                arch = MAIN_STAR_TO_ARCHETYPE.get(s)
                if arch and arch not in tickets:
                    tickets.append(arch)
                    labels.setdefault(arch, []).append("차용(환경반응)")
            hints["opposite_palace"] = {"index": opp_idx, "branch": opp_branch, "stars": opp_palace_stars}
    else:
        # 베이스 주성
        for s in base_stars:
            arch = MAIN_STAR_TO_ARCHETYPE.get(s)
            if arch and arch not in tickets:
                tickets.append(arch)
                labels.setdefault(arch, []).append("베이스")
        # 차용 주성
        for e in borrowed_stars_raw:
            s = e.get("star", "") if isinstance(e, dict) else str(e)
            branch = e.get("branch", "") if isinstance(e, dict) else ""
            arch = MAIN_STAR_TO_ARCHETYPE.get(s)
            if arch and arch not in tickets:
                tickets.append(arch)
                labels.setdefault(arch, []).append("차용(환경반응)")

    # 밝기 체크 (4번 규칙) — base_stars는 ming_idx, borrowed_stars는 해당 궁 idx
    def _brightness_for(star_name: str, palace_idx: Optional[int]) -> str:
        if palace_idx is None:
            return ""
        return brightness_map.get(f"{palace_idx}_{star_name}", "")

    for s in base_stars:
        b = _brightness_for(s, ming_idx)
        if b:
            arch = MAIN_STAR_TO_ARCHETYPE.get(s)
            if arch:
                hints["brightness"][s] = b
                if b in _BRIGHT_WEAKEN:
                    label = "약화"
                elif b in _BRIGHT_TRANSFORM:
                    label = "변질"
                else:
                    label = None
                if label and label not in (labels.get(arch) or []):
                    labels.setdefault(arch, []).append(label)

    for e in borrowed_stars_raw:
        s = e.get("star", "") if isinstance(e, dict) else str(e)
        branch = e.get("branch", "") if isinstance(e, dict) else ""
        b_idx = _branch_to_idx(branch)
        b = _brightness_for(s, b_idx)
        if b:
            arch = MAIN_STAR_TO_ARCHETYPE.get(s)
            if arch:
                hints["brightness"][s] = b
                if b in _BRIGHT_WEAKEN:
                    label = "약화"
                elif b in _BRIGHT_TRANSFORM:
                    label = "변질"
                else:
                    label = None
                if label and label not in (labels.get(arch) or []):
                    labels.setdefault(arch, []).append(label)

    # 2. 화과(化科) → sihua["科"] 별 확인
    hua_ke = sihua.get("科", {}) or {}
    ke_star = hua_ke.get("star", "") or ""
    hints["sihua_ke"] = ke_star
    if ke_star:
        arch = MAIN_STAR_TO_ARCHETYPE.get(ke_star)
        if arch and arch not in tickets:
            tickets.append(arch)
            labels.setdefault(arch, []).append("화과")
        elif arch:
            # 이미 베이스 티켓 존재 → "화과" 라벨만 부착
            labels.setdefault(arch, []).append("화과")

    # 3. 살성 2+ 회조 → 독립 추가
    shach_in_ming: List[str] = []
    for name, branch in aux.items():
        if name in _SHACHENG and branch == ming_branch:
            shach_in_ming.append(name)
    # 인접궁 살성도 회조로 간주 (三合만 엄격 적용, 三刑은 제외)
    for name, branch in aux.items():
        if name in _SHACHENG and _is_san_ho(branch, ming_branch):
            if name not in shach_in_ming:
                shach_in_ming.append(name)

    hints["shach_count"] = len(shach_in_ming)
    if len(shach_in_ming) >= 2:
        if "독립" not in tickets:
            tickets.append("독립")
        if "독립(sal)" not in labels.get("독립", []):
            labels.setdefault("독립", []).append("살성회조")

    # 6. 길성 2+ → 베이스 티켓에 "안정 발현" 라벨
    jich_in_ming: List[str] = []
    for name, branch in aux.items():
        if name in _JICHENG and branch == ming_branch:
            jich_in_ming.append(name)
    hints["jich_count"] = len(jich_in_ming)
    if len(jich_in_ming) >= 2 and tickets:
        # 베이스 티켓(가장 먼저 발급된 것)에 라벨
        base = tickets[0]
        if "안정 발현" not in labels.get(base, []):
            labels.setdefault(base, []).append("안정 발현")

    # 정리: 중복 라벨 제거
    for k in list(labels.keys()):
        labels[k] = list(dict.fromkeys(labels[k]))

    return {
        "ok": True,
        "tickets": tickets,
        "labels": labels,
        "raw_hints": hints,
    }


def format_tickets(ticket_result: Dict[str, Any]) -> str:
    """티켓 결과를 사람이 읽을 수 있는 텍스트로 변환 (검증 디버그용)."""
    if not ticket_result.get("ok"):
        return "티켓 발급 실패"

    lines: List[str] = []
    lines.append(f"티켓: {', '.join(ticket_result['tickets'])}")
    labels = ticket_result.get("labels", {})
    for arch in ticket_result["tickets"]:
        lbl = labels.get(arch, [])
        if lbl:
            lines.append(f"  {arch}: {', '.join(lbl)}")
        else:
            lines.append(f"  {arch}: (라벨 없음)")
    return "\n".join(lines)


# 12지지 순서 → index 매핑
_IDX_TO_BRANCH = [
    "子", "丑", "寅", "卯", "辰", "巳",
    "午", "未", "申", "酉", "戌", "亥",
]
