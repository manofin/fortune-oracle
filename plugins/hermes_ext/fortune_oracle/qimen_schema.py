#!/usr/bin/env python3
"""Fortune Oracle — Qimen Dunjia schema (Phase 35 + Gate 4.1).

Dataclass 기반 결과 모델. kinqimen의 raw dict를 structured한 형태로 변환한다.
Gate 4.1: 격국(格局) 분석을 위한 QimenGeju 데이터 계약 추가 (판별 로직은 Subphase 4.2에서 구현).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 구궁 배열 상수 (고정)
PALACE_GRID: List[List[str]] = [
    ["巽", "離", "坤"],
    ["震", "中", "兌"],
    ["艮", "坎", "乾"],
]

# 팔괘 목록
EIGHT_PALACES: List[str] = ["巽", "離", "坤", "震", "兌", "艮", "坎", "乾"]

QIMEN_DISCLAIMER: str = (
    "이 기문둔갑 판은 자기성찰과 선택지 점검용 참고이며, "
    "의학, 투자, 법률 결정을 지시하지 않습니다."
)


@dataclass
class QimenQuery:
    """기문둔갑 질문 입력."""
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    question: str = ""
    method: str = "拆補"  # 기본 拆補 (option=1)

    def validate(self) -> Optional[str]:
        """검증 실패 시 오류 메시지 반환, 성공 시 None."""
        if self.year < 1900 or self.year > 2100:
            return f"년도는 1900~2100 사이여야 합니다: {self.year}"
        if self.month < 1 or self.month > 12:
            return f"월은 1~12 사이여야 합니다: {self.month}"
        if self.day < 1 or self.day > 31:
            return f"일은 1~31 사이여야 합니다: {self.day}"
        if self.hour < 0 or self.hour > 23:
            return f"시는 0~23 사이여야 합니다: {self.hour}"
        if self.minute < 0 or self.minute > 59:
            return f"분은 0~59 사이여야 합니다: {self.minute}"
        return None


@dataclass
class QimenPalace:
    """단일 궁위의 데이터."""
    palace_name: str = ""
    sky_stem: str = ""       # 천판
    earth_stem: str = ""     # 지판
    door: str = ""           # 八門
    star: str = ""           # 九星
    god: str = ""            # 八神
    life_phase: str = ""     # 장생운(천판 기준)


@dataclass
class QimenGeju:
    """기문둔갑 격국(格局) 분석 결과 컨테이너 (Gate 4.1: 데이터 계약 전용).

    판별 로직(복음/反吟, 길격/흉격)은 Subphase 4.2의 interpreter 계층에서 구현.
    이 dataclass는 순수 데이터 홀더이며, 계산을 수행하지 않는다.
    """
    fuyin: bool = False                    # 伏吟 (천반/지반 중복·정체 패턴)
    fanyin: bool = False                   # 反吟 (반대·충돌 패턴)
    detected_ji_ge: List[str] = field(default_factory=list)   # 검출된 길격 (e.g. "生門得位")
    detected_xiong_ge: List[str] = field(default_factory=list) # 검출된 흉격
    summary: str = ""                      # 안전한 한줄 요약 (disclaimer와 함께 사용)


@dataclass
class QimenChart:
    """기문둔갑 판 데이터."""
    method: str = ""         # 판식: 拆補 or 置閏
    ganzhi: str = ""         # 간지
    xun_shou: str = ""       #旬首
    xun_kong: str = ""       #旬空
    ju_day: str = ""         #局日
    pai_ju: str = ""         #排局
    jie_qi: str = ""         #節氣
    zhi_fu_stem: str = ""    #值符天干
    zhi_fu_star: str = ""    #值符星宮
    zhi_shi_door: str = ""   #值使門宮
    tian_yi: str = ""        #天乙
    horse_star: Dict[str, str] = field(default_factory=dict)  #馬星
    palaces: Dict[str, QimenPalace] = field(default_factory=dict)
    geju: Optional[QimenGeju] = None       # Gate 4.1 추가: 격국 분석 결과 (기본 None, 하위 호환)

    def get_palace(self, name: str) -> Optional[QimenPalace]:
        return self.palaces.get(name)

    def palace_list(self) -> List[QimenPalace]:
        """구궁 배열 순서로 palace 반환."""
        result: List[QimenPalace] = []
        for row in PALACE_GRID:
            for palace_name in row:
                p = self.palaces.get(palace_name)
                if p:
                    result.append(p)
        return result


@dataclass
class QimenResult:
    """기문둔갑 계산 결과."""
    ok: bool
    chart: Optional[QimenChart] = None
    query: Optional[QimenQuery] = None
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    message: str = ""
    disclaimer: str = QIMEN_DISCLAIMER

    @classmethod
    def error(cls, error_code: str, message: str, warnings: Optional[List[str]] = None) -> "QimenResult":
        return cls(ok=False, error_code=error_code, message=message, warnings=warnings or [])
