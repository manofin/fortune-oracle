#!/usr/bin/env python3
"""Fortune Oracle — Qimen Dunjia Interpreter (Phase 35 + Gate 4.2).

기문둔갑 판 결과를 Telegram용 compact Korean 텍스트로 포맷팅한다.
raw dict/dataclass repr가 절대 Telegram에 노출되지 않도록 sanitize guard를 적용한다.

Gate 4.2: 격국 판별 추가 (패턴 서술형만, 단정 표현 금지, 중궁 규칙 명시).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .qimen_schema import (
    EIGHT_PALACES,
    PALACE_GRID,
    QIMEN_DISCLAIMER,
    QimenChart,
    QimenGeju,
    QimenPalace,
    QimenQuery,
    QimenResult,
)

# sanitize 금지 패턴 (raw repr/traceback/내부 구조 노출 방지)
_SANITIZE_PATTERNS = [
    re.compile(r"QimenChart\("),
    re.compile(r"QimenResult\("),
    re.compile(r"QimenPalace\("),
    re.compile(r"QimenQuery\("),
    re.compile(r"dataclass"),
    re.compile(r"default_factory"),
    re.compile(r"traceback", re.IGNORECASE),
    re.compile(r'File\s+\"[^\"]+\.py\", line \d+'),
    re.compile(r"^\s*<[^>]+>$", re.MULTILINE),
]

# 궁위 한글 매핑
PALACE_KR: dict = {
    "巽": "손(동남)",
    "離": "이(남)",
    "坤": "곤(서남)",
    "震": "진(동)",
    "中": "중(중앙)",
    "兌": "태(서)",
    "艮": "간(북동)",
    "坎": "감(북)",
    "乾": "건(서북)",
}

# 8문 한글 매핑
DOOR_KR: dict = {
    "開": "개문",
    "休": "휴문",
    "生": "생문",
    "傷": "상문",
    "杜": "두문",
    "景": "경문(景)",
    "死": "사문",
    "驚": "경문(驚)",
}

# 9성 한글 매핑 (일관된 '성' 표기)
STAR_KR: dict = {
    "蓬": "천봉성",
    "芮": "천예성",
    "沖": "천충성",
    "輔": "천보성",
    "禽": "천예·천금성",
    "心": "천심성",
    "柱": "천주성",
    "任": "천임성",
    "英": "천영성",
}

# 10신. 蛇는 등사. 虎·玄은 kinqimen 神 맵에 있어 함께 표기한다.
GOD_KR: dict = {
    "符": "직부",
    "蛇": "등사",
    "陰": "태음",
    "合": "육합",
    "勾": "구진",
    "雀": "백작",
    "虎": "백호",
    "玄": "현무",
    "天": "구천",
    "地": "구지",
}

_XUN_BY_STEM = {
    "戊": "甲子",
    "己": "甲戌",
    "庚": "甲申",
    "辛": "甲午",
    "壬": "甲辰",
    "癸": "甲寅",
}


def _xun_label(stem: str) -> str:
    name = _XUN_BY_STEM.get(stem)
    return f"{name}({stem})" if name else stem


# ------------------------------------------------------------------
# Gate 4.2: 격국(格局) 판별 (interpreter 계층 전용, bridge touch 0 엄격 유지)
# ------------------------------------------------------------------

def _detect_fuyin_fanyin(chart: QimenChart) -> tuple[bool, bool]:
    """복음(伏吟) / 반음(反吟) 단순 구조 판별.

    규칙 (현대 실전 공통 패턴, 《奇門遁甲大全》 계열 기반):
    - 伏吟: 8개 외곽 궁위(中 제외)에서 sky_stem == earth_stem 인 경우가 3개 이상.
      **중궁(中) 명시적 제외**: 중심 궁위는 문/성/신 배치가 특수하고 인위적 중복을 유발할 수 있어
      fuyin 카운트에서 제외. 이 선택은 Gate 4.2 전체에서 일관 유지.
    - 反吟: 현재는 간단 휴리스틱 (추후 확장). 기본은 False.
    """
    if not chart or not chart.palaces:
        return False, False

    fuyin_count = 0
    for palace_name in EIGHT_PALACES:
        p = chart.get_palace(palace_name)
        if p and p.sky_stem and p.earth_stem and p.sky_stem == p.earth_stem:
            fuyin_count += 1

    fuyin = fuyin_count >= 3
    fanyin = False
    return fuyin, fanyin


def _detect_basic_geju(chart: QimenChart) -> QimenGeju:
    """최소 길격/흉격 패턴 서술형 검출 (단정 표현 금지).

    규칙:
    - 반음은 별도 표기 없음 (추후 확장)
    """
    if not chart:
        return QimenGeju()

    fuyin, fanyin = _detect_fuyin_fanyin(chart)
    ji: list[str] = []
    xiong: list[str] = []

    for p in chart.palace_list():
        if p.palace_name == "中":
            continue
        # 길격 후보 1: 생문/개문 배치
        if p.door == "生":
            ji.append(f"生門이 {PALACE_KR.get(p.palace_name, p.palace_name)} 위치")
        if p.door == "開":
            ji.append(f"開門이 {PALACE_KR.get(p.palace_name, p.palace_name)} 위치")
        # 흉격 후보 1: 사문 배치
        if p.door == "死":
            xiong.append(f"死문이 {PALACE_KR.get(p.palace_name, p.palace_name)} 위치")
        # 흉격 후보 2: 상문 배치
        if p.door == "傷":
            xiong.append(f"傷門이 {PALACE_KR.get(p.palace_name, p.palace_name)} 위치")

    # 중궁(中) 명시적 제외

    summary = ""
    if ji or xiong or fuyin or fanyin:
        parts = []
        if fuyin:
            parts.append("伏吟 감지")
        if fanyin:
            parts.append("反吟 감지")
        if ji:
            parts.append(" · ".join(ji[:2]))
        if xiong:
            parts.append(" · ".join(xiong[:2]))
        summary = " · ".join(parts)

    return QimenGeju(
        fuyin=fuyin,
        fanyin=fanyin,
        detected_ji_ge=ji,
        detected_xiong_ge=xiong,
        summary=summary,
    )


def _sanitize(text: str) -> str:
    for pattern in _SANITIZE_PATTERNS:
        text = pattern.sub("[SANITIZED]", text)
    return text


def _format_palace_line(palace: QimenPalace) -> str:
    name = PALACE_KR.get(palace.palace_name, palace.palace_name)
    parts = [f"  {name}"]
    if palace.sky_stem:
        parts.append(f"천{palace.sky_stem}")
    if palace.earth_stem:
        parts.append(f"지{palace.earth_stem}")
    if palace.door:
        parts.append(DOOR_KR.get(palace.door, palace.door))
    if palace.star:
        parts.append(STAR_KR.get(palace.star, palace.star))
    if palace.god:
        parts.append(GOD_KR.get(palace.god, palace.god))
    if palace.life_phase:
        parts.append(f"생운{palace.life_phase}")
    return " | ".join(parts)


def _format_pai_ju_grid(chart: QimenChart) -> str:
    lines: list = []
    for row in PALACE_GRID:
        parts = []
        for palace_name in row:
            palace = chart.get_palace(palace_name)
            if palace:
                name = PALACE_KR.get(palace_name, palace_name)
                info = f"{palace.sky_stem}/{palace.earth_stem}"
                if palace.door:
                    info += f" {DOOR_KR.get(palace.door, palace.door)}"
                parts.append(f"{name}:{info}")
            else:
                parts.append(palace_name)
        lines.append("  ".join(parts))
    return "\n".join(lines)


def format_qimen_result(result: QimenResult) -> str:
    if not result.ok:
        return _sanitize(_format_error(result))

    chart = result.chart
    query = result.query
    if not chart or not any(p.door or p.star for p in chart.palaces.values()):
        return "계산 결과가 아님\n기문둔갑 판 데이터가 없습니다. 잠시 후 다시 시도해 주세요."

    geju = _detect_basic_geju(chart)

    lines: list = []
    lines.append("🔮 기문둔갑 질문 시각 판")
    lines.append(f"판식: {chart.method}")

    if query:
        time_str = f"{query.year}년 {query.month}월 {query.day}일 {query.hour}시 {query.minute}분"
        lines.append(f"질문 시각: {time_str} · Asia/Seoul (KST)")
    else:
        lines.append(f"간지: {chart.ganzhi}")

    lines.append("---")
    if chart.jie_qi:
        lines.append(f"절기: {chart.jie_qi}")
    if chart.pai_ju:
        lines.append(f"배국: {chart.pai_ju}")
    if chart.ganzhi:
        lines.append(f"간지: {chart.ganzhi}")
    xun_parts = []
    if chart.xun_shou:
        xun_parts.append(f"일순수 {_xun_label(chart.xun_shou)}")
    if chart.zhi_fu_stem:
        xun_parts.append(f"시순수 {_xun_label(chart.zhi_fu_stem)}")
    if xun_parts:
        lines.append(" / ".join(xun_parts))
    if chart.xun_kong:
        lines.append(f"순공: {chart.xun_kong}")
    if chart.ju_day:
        lines.append(f"국일: {chart.ju_day}")

    zf_parts = []
    if chart.zhi_fu_stem:
        zf_parts.append(f"직부: {chart.zhi_fu_stem}")
    if chart.zhi_fu_star:
        zf_parts.append(f"성: {STAR_KR.get(chart.zhi_fu_star, chart.zhi_fu_star)}")
    if chart.zhi_shi_door:
        zf_parts.append(f"직사: {DOOR_KR.get(chart.zhi_shi_door, chart.zhi_shi_door)}")
    if zf_parts:
        lines.append(f"직부직사: {' · '.join(zf_parts)}")

    if chart.tian_yi:
        lines.append(f"천을(天乙): {STAR_KR.get(chart.tian_yi, chart.tian_yi)}")
    if chart.horse_star:
        hs_parts = [f"{k}:{v}" for k, v in chart.horse_star.items()]
        lines.append(f"마성: {' · '.join(hs_parts)}")

    lines.append("---")
    lines.append("구궁:")
    lines.append(_format_pai_ju_grid(chart))

    lines.append("---")
    for palace_name in EIGHT_PALACES:
        palace = chart.get_palace(palace_name)
        if palace:
            lines.append(_format_palace_line(palace))

    if geju and (geju.fuyin or geju.fanyin or geju.detected_ji_ge or geju.detected_xiong_ge):
        lines.append("---")
        lines.append("격국 참고:")
        if geju.summary:
            lines.append(geju.summary)
        if geju.detected_ji_ge:
            lines.append("  길격 패턴: " + " · ".join(geju.detected_ji_ge[:3]))
        if geju.detected_xiong_ge:
            lines.append("  흉격 패턴: " + " · ".join(geju.detected_xiong_ge[:3]))
        lines.append("(패턴은 참고용이며 단정적 판단이 아닙니다.)")

    if result.warnings:
        lines.append("---")
        for w in result.warnings:
            lines.append(f"⚠ {w}")

    lines.append("---")
    lines.append(QIMEN_DISCLAIMER)

    text = "\n".join(lines)
    return _sanitize(text)


def _format_error(result: QimenResult) -> str:
    lines = ["계산 결과가 아님", "현재 기문둔갑 판을 준비하지 못했습니다."]
    if result.error_code == "DEPENDENCY_MISSING":
        lines.append("계산 기능을 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    elif result.error_code == "INVALID_INPUT":
        lines.append("실제 달력 날짜와 시각을 확인해 주세요. 질문 시각은 KST 기준입니다.")
        lines.append("올바른 형식: /qimen YYYY-MM-DD HH:MM [질문]")
    else:
        lines.append("잠시 후 다시 시도해 주세요.")
    lines.append("---")
    lines.append(QIMEN_DISCLAIMER)
    return "\n".join(lines)


def format_qimen_now(question: str = "") -> str:
    from .qimen_bridge import calculate_qimen
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    query = QimenQuery(year=now.year, month=now.month, day=now.day, hour=now.hour, minute=now.minute, question=question)
    result = calculate_qimen(query)
    return format_qimen_result(result)


def format_qimen_at(datetime_str: str, question: str = "") -> str:
    from .qimen_bridge import calculate_qimen
    try:
        value = datetime_str.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", value):
            raise ValueError("날짜/시간 형식 오류")
        at = datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except ValueError:
        return _format_error(QimenResult.error("INVALID_INPUT", ""))

    query = QimenQuery(year=at.year, month=at.month, day=at.day, hour=at.hour, minute=at.minute, question=question)
    result = calculate_qimen(query)
    return format_qimen_result(result)


def format_qimen_empty() -> str:
    return (
        "🔮 기문둔갑 참고\n"
        "현재 질문 시각(Asia/Seoul, KST)의 기문둔갑 판을 참고로 제공합니다.\n"
        "질문 시각을 지정하려면: /qimen YYYY-MM-DD HH:MM [질문]\n"
        "예: /qimen 2026-05-28 21:30 이사 방향 참고\n"
        "---\n"
        "참고: 현재 시각 기준 판을 계산합니다."
    )
