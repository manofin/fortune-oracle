#!/usr/bin/env python3
"""Slice 1 — Deterministic personalized daily fortune engine.

Replaces the hardcoded static text in core._render_fortune with a fortune that is
derived from chart element counts and today's day pillar (일진).
Scores are entertainment heuristics, not calibrated probabilities. The two least
represented elements approximate favorable elements, not a full 용신 analysis;
Dayun pillars and solar-term start are computed by lunar-javascript (sect 2).
Its calendar-year cycle intervals feed an explicit, bounded interpretive score
adjustment; this is not an empirically calibrated prediction. Missing gender or
birth time leaves that adjustment at zero instead of inventing a cycle.

Design constraints:
- Deterministic: same profile + same date => same output. No RNG, no LLM.
- Privacy: never emits birth_date, birth_time, birth_place, name_hanja.
- Fail-closed: if the chart cannot be computed, returns None so the caller can
  fall back to the existing static text. Never raises into the bot handler.
- Recomputes per call (the existing kline.py does the same); the dominant cost is
  a single Node subprocess, which bazi_bridge already bounds with a 5s timeout.

Not a medical, investment, or legal instruction. 오락과 자기성찰용.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

KST_OFFSET_HOURS = 9

# 오행 상생/상극 관계 (bazi_element_strength와 동일한 표를 쓰지 않고
# 여기서 자기완결적으로 정의 — 의존성 없이 동작하기 위함)
SHENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
KE = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}

ELEMENT_KEYWORD = {
    "목": ("시작", "성장", "방향", "계획", "배움", "연결"),
    "화": ("속도", "표현", "관심", "행동", "관계의 온도"),
    "토": "안정 묵묵함 저축 안정감 정돈 마무리".split(),
    "금": "정리 결단 기준 선별 단호함 숫자".split(),
    "수": "회복 유연 이동 대처 균형".split(),
}

ASPECT_ELEMENT = {
    "종합": None,
    "활동": "화",
    "관계": "목",
    "재물": "금",
    "건강": "수",
}

ASPECT_TITLE = {
    "종합": "종합 운세",
    "활동": "활동·업무 운세",
    "관계": "관계·소통 운세",
    "재물": "재물 운세",
    "건강": "컨디션 운세",
}

FORTUNE_MASTERS = {
    "관음": "고민을 말로 꺼내놓으면 정리됩니다.",
    "태허": "큰 틀보다 오늘의 한 걸음을 먼저 두는 편이 좋습니다.",
    "티코": "일정 하나를 지우면 속도가 나옵니다.",
    "자허": "미뤄 둔 답장 하나를 짧게 끝내 보세요.",
}


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=KST_OFFSET_HOURS))).date()


def _stem_element(stem: str) -> str:
    """천간 → 오행. 엔진은 한자(庚), 내부 표는 한글(경) — 둘 다 받는다."""
    s = _to_korean_stem(stem)
    return {
        "갑": "목", "을": "목",
        "병": "화", "정": "화", "무": "토",
        "기": "토",
        "경": "금", "신": "금",
        "임": "수", "계": "수",
    }.get(s, "")


def _branch_element(branch: str) -> str:
    """지지 → 오행. 한자/한글 양쪽 수용."""
    s = _to_korean_branch(branch)
    return {
        "인": "목", "묘": "목", "진": "토",
        "사": "화", "오": "화", "유": "금",
        "신": "금", "술": "토", "축": "토", "미": "토",
        "해": "수", "자": "수",
    }.get(s, "")


_HANZI_STEM = {
    "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
    "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
}
_HANZI_BRANCH = {
    "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진", "巳": "사",
    "午": "오", "未": "미", "申": "신", "酉": "유", "戌": "술", "亥": "해",
}


def _to_korean_stem(ch: str) -> str:
    return _HANZI_STEM.get(ch, ch)


def _to_korean_branch(ch: str) -> str:
    return _HANZI_BRANCH.get(ch, ch)


def _element_key(raw: str) -> str:
    """'화(火)' → '화', '火' → '화', '화' → '화'."""
    for ko, han in (("목", "木"), ("화", "火"), ("토", "土"), ("금", "金"), ("수", "水")):
        if raw.startswith(ko) or raw.startswith(han):
            return ko
    return raw


def _day_pillar_for(target: date) -> Optional[str]:
    """일진(날짜의 천간지지) — JDN 기반 결정론적 계산.

    2000-01-01은 무오일. (JDN + 49) % 60 → 0=甲子.
    """
    a = (14 - target.month) // 12
    y = target.year + 4800 - a
    m = target.month + 12 * a - 3
    jdn = target.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    stems = list("갑을병정무기경신임계")  # 10간 정순 — 순서를 틀면 전 날짜가 밀린다
    branches = list("자축인묘진사오미신유술해")  # 12지
    idx = (jdn + 49) % 60  # lunar-javascript getDayInGanZhiExact와 17/17 일치 검증됨
    return stems[idx % 10] + branches[idx % 12]


def _strength_score(elements: Mapping[str, int]) -> float:
    """오행 분포 → 0..1 균형도. 한 오행이 몰수록 낮다."""
    total = sum(elements.values())
    if total <= 0:
        return 0.0
    max_share = max(elements.values()) / total
    return max(0.0, min(1.0, 1.0 - (max_share - 0.2) / 0.6))


def _element_day_relation(day_master_element: str, day_element: str) -> str:
    """일간 기준 일진 오행의 관계."""
    if not day_master_element or not day_element:
        return "unknown"
    if day_element == day_master_element:
        return "same"          # 비견/겁재 — 자기 확장에 편한 날
    if SHENG.get(day_master_element) == day_element:
        return "output"        # 식상 — 말이 나오고 표현이 풀리는 날
    if SHENG.get(day_element) == day_master_element:
        return "input"         # 인성 — 배우고 안정되는 날
    if KE.get(day_master_element) == day_element:
        return "wealth"        # 재성 — 일간이 극하는 오행
    if KE.get(day_element) == day_master_element:
        return "pressure"      # 관성 — 일간을 극하는 오행
    return "unknown"


RELATION_LINE = {
    "same": "같은 오행이므로, 자기 기준을 점검하는 주제로 읽습니다.",
    "output": "내 오행이 날짜의 오행을 돕는 관계이므로, 표현하는 주제로 읽습니다.",
    "input": "날짜의 오행이 내 오행을 돕는 관계이므로, 배우고 정리하는 주제로 읽습니다.",
    "pressure": "날짜의 오행이 내 오행을 제어하는 관계이므로, 요구와 여유를 점검하는 주제로 읽습니다.",
    "wealth": "내 오행이 날짜의 오행을 제어하는 관계이므로, 자원과 책임을 점검하는 주제로 읽습니다.",
    "unknown": "관계를 확인할 수 없어 일반적인 점검 주제로만 읽습니다.",
}

RELATION_THEME = {
    "same": "중요하게 여길 기준 하나를 돌아보는 주제로 읽습니다.",
    "output": "생각을 짧고 분명하게 전하는 주제로 읽습니다.",
    "input": "필요한 것을 배우고 정리하는 주제로 읽습니다.",
    "pressure": "해야 할 일과 쉴 여유를 함께 점검하는 주제로 읽습니다.",
    "wealth": "쓸 수 있는 자원과 맡을 책임을 살피는 주제로 읽습니다.",
    "unknown": "계산 관계를 확인할 수 없어 일반적인 점검 주제로만 읽습니다.",
}

# Suggestions follow the symbolic relation, not claims about the user's life.
RELATION_PRACTICE = {
    "same": ("우선순위 하나를 적어 보세요.", "내 기준만으로 다른 사람의 뜻을 단정하지 마세요."),
    "output": ("전할 말 하나를 짧게 적고 보내기 전에 읽어 보세요.", "표현이 잘 통할 것이라 가정하지 말고 상대의 뜻을 확인하세요."),
    "input": ("필요한 자료 하나를 읽고 핵심을 한 줄로 정리해 보세요.", "준비만 늘리기보다 작은 실행 하나로 확인하세요."),
    "pressure": ("해야 할 일 하나의 마감과 범위를 확인하고 쉴 틈을 남겨 보세요.", "점수를 근거로 무리하거나 건강 상태를 판단하지 마세요."),
    "wealth": ("지출이나 약속을 앞두고 있다면 조건 하나를 확인해 보세요.", "금전적 이익이나 손실을 예고하는 뜻은 아니니 중요한 결정은 실제 정보로 판단하세요."),
    "unknown": ("할 수 있는 작은 일 하나를 정해 보세요.", "계산되지 않은 상황을 추측하지 마세요."),
}


def _score_for(
    base: float,
    day_master_element: str,
    day_element: str,
    favorable: set,
    aspect: str,
) -> float:
    """0..100 점수. 세기가 아니라 '오늘의 체감 지수'."""
    rel = _element_day_relation(day_master_element, day_element)
    rel_bonus = {
        "same": 8, "output": 5, "input": 3, "pressure": -7, "wealth": -4,
    }.get(rel, 0)
    fav_bonus = 9 if day_element in favorable else (-5 if favorable else 0)
    aspect_el = ASPECT_ELEMENT.get(aspect)
    aspect_bonus = 8 if (aspect_el and day_element == aspect_el) else 0
    return max(0.0, min(100.0, base + rel_bonus + fav_bonus + aspect_bonus))


def _aspect_component(elements: Mapping[str, int], aspect: str) -> float:
    """영역별 소수 보정 (-6..+6).

    종합은 0. 그 외 4개 영역은 해당 오행이 원국에 얼마나 있는지를 반영해
    같은 날짜·같은 사람이라도 영역별로 체감 지수가 달라지게 한다.
    """
    el = ASPECT_ELEMENT.get(aspect)
    if not el:
        return 0.0
    total = sum(elements.values()) or 1
    share = elements.get(el, 0) / total
    # 20%면 중립, 그 위는 +, 아래는 -
    return max(-6.0, min(6.0, (share - 0.2) * 40.0))


def _grade(score: float) -> str:
    if score >= 78:
        return "아주 좋은 날"
    if score >= 62:
        return "순풍"
    if score >= 46:
        return "평온"
    if score >= 32:
        return "조심"
    return "여유를 두는 날"


def build_personalized_daily(
    profile: Optional[Mapping[str, Any]],
    *,
    target_date: Optional[date] = None,
    aspect: str = "종합",
    language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """개인화 일일 운세 생성. 실패 시 None.

    Returns dict with keys: score, grade, date, day_pillar, day_element,
    relation, keywords, lines, dayun_theme, disclaimer.
    """
    if not isinstance(profile, Mapping):
        return None
    birth_date = profile.get("birth_date")
    if not isinstance(birth_date, str):
        return None
    birth_date = birth_date.strip()
    if not birth_date:
        return None

    try:
        from . import bazi_bridge  # type: ignore
    except Exception:
        try:
            from plugins.hermes_ext.fortune_oracle import bazi_bridge  # type: ignore
        except Exception:
            return None

    try:
        result = bazi_bridge.calculate_bazi_from_profile(dict(profile))
    except Exception:
        return None
    if not getattr(result, "ok", False) or not getattr(result, "eight_char", None):
        return None

    try:
        from .localization import localize_daily, language_code
        reading = _daily_from_chart(profile, result, target_date or _profile_today(profile), aspect)
        return localize_daily(reading, language_code(language if language is not None else profile.get("language")))
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return None


def build_personalized_series(
    profile: Optional[Mapping[str, Any]], dates: list[date], *, aspect: str = "종합",
) -> Optional[list[Dict[str, Any]]]:
    """Calculate a chart once per request, then score every date; never return partial data."""
    if not isinstance(profile, Mapping) or not isinstance(profile.get("birth_date"), str):
        return None
    if not profile["birth_date"].strip():
        return None
    try:
        from .bazi_bridge import calculate_bazi_from_profile
        result = calculate_bazi_from_profile(dict(profile))
        if not result.ok or not result.eight_char:
            return None
        readings = [_daily_from_chart(profile, result, d, aspect) for d in dates]
        return readings if all(readings) else None
    except Exception:
        return None


def _profile_today(profile=None):
    from .localization import local_today, reading_zone
    # Preserve the existing default clock seam while honoring explicit overseas zones.
    zone = reading_zone(profile)
    return _kst_today() if zone.key == "Asia/Seoul" else local_today(profile)


def _daily_from_chart(profile: Mapping[str, Any], result: Any, target_date: date, aspect: str) -> Dict[str, Any]:
    """Shared interpretation for single-day and period readings. No subprocesses."""
    birth_date = profile["birth_date"].strip()
    ec = result.eight_char
    if any(not ec.get(key) for key in ('year', 'month', 'day')):
        raise ValueError('Unresolved birth pillars cannot support a numeric score')
    if not result.ok or not result.elements:
        raise ValueError("Incomplete chart")
    counts = {_element_key(k): v for k, v in result.elements.items()}
    if any(k not in ("목", "화", "토", "금", "수") or type(v) is not int or v < 0
           for k, v in counts.items()):
        raise ValueError("Invalid element counts")
    # Equal counts use canonical order: 목, 화, 토, 금, 수.
    # Only successful calculations may omit zero-count elements.
    elements = {e: counts.get(e, 0) for e in "목화토금수"}
    day_pillar_today = _day_pillar_for(target_date)
    if not day_pillar_today:
        raise ValueError("Missing day pillar")

    day_master = ec.get("day", "")[:1]
    dm_element = _stem_element(day_master)
    day_element = _branch_element(day_pillar_today[1]) or _stem_element(day_pillar_today[0])
    if not dm_element or not elements or sum(elements.values()) <= 0:
        raise ValueError("Incomplete chart")

    # 용신(오용) 근사: 세기가 낮은 오행을 보강. 전용 세력 모듈 대신
    # 오행 분포의 최약 2개로 근사 — heuristic임을 문서에 명시.
    ordered = sorted(elements.items(), key=lambda kv: kv[1])
    favorable = {e for e, _ in ordered[:2]}

    base = 40.0 + 30.0 * _strength_score(elements)
    # 영역별 점수: 같은 날이라도 영역마다 기준이 달라야 한다.
    # 일진 오행 하나로는 5개 영역이 구분되지 않으므로, 오행 분포에서
    # 해당 영역 오행의 체감 세기를 반영한다.
    aspect_scores = {
        name: max(0.0, min(100.0,
            _score_for(base, dm_element, day_element, favorable, name)
            + _aspect_component(elements, name)))
        for name in ASPECT_TITLE
    }
    score = aspect_scores.get(aspect, aspect_scores["종합"])
    relation = _element_day_relation(dm_element, day_element)

    # 실제 절기 기반 대운 간지. 연도 구간 선택과 해석 보정은 명시적으로 분리한다.
    dayun_theme = ""
    dayun_pillar = ""
    dayun_years = None
    dayun_adjustment = 0.0
    dayun_data = getattr(result, "dayun", None)
    if isinstance(dayun_data, dict):
        for cycle in dayun_data.get("cycles", []):
            if cycle["start_year"] <= target_date.year <= cycle["end_year"]:
                dayun_pillar = cycle["pillar"]
                dayun_years = (cycle["start_year"], cycle["end_year"])
                cycle_element = _stem_element(dayun_pillar[:1])
                if not cycle_element:
                    raise ValueError("Invalid dayun pillar")
                cycle_relation = _element_day_relation(dm_element, cycle_element)
                dayun_adjustment = {"same": 2, "output": 1, "input": 2,
                                    "pressure": -2, "wealth": -1}.get(cycle_relation, 0)
                dayun_adjustment += 2 if cycle_element in favorable else -2
                dayun_theme = f"{dayun_pillar}({cycle_element}) · 연도 구간 {cycle['start_year']}–{cycle['end_year']}"
                break
    aspect_scores = {name: max(0.0, min(100.0, value + dayun_adjustment))
                     for name, value in aspect_scores.items()}
    score = aspect_scores.get(aspect, aspect_scores["종합"])

    keywords = list(ELEMENT_KEYWORD.get(day_element) or ["정리"])
    # 일간이 다르면 일간 오행 키워드를 섞어 개인화
    if dm_element and dm_element != day_element:
        dm_kw = list(ELEMENT_KEYWORD.get(dm_element) or [])
        keywords = keywords[:2] + dm_kw[:1]

    action, caution = RELATION_PRACTICE.get(relation, RELATION_PRACTICE['unknown'])
    distribution = ' · '.join(f'{e} {n}' for e, n in elements.items())
    favorable_label = '·'.join(e for e, _ in ordered[:2])
    favorable_match = '포함되어 가점' if day_element in favorable else '포함되지 않아 감점'
    lines = [
        f"{ASPECT_TITLE.get(aspect, '종합 운세')} · {score:.0f}점 — {_grade(score)}",
        f"이날의 해석: {RELATION_THEME.get(relation, RELATION_THEME['unknown'])}",
        f"해볼 일: {action}",
        f"주의할 점: {caution}",
        f"해석 근거: 일간(나를 나타내는 기준) {dm_element} · 일진 {day_pillar_today}의 지지(날짜의 아래 글자) {day_element}. "
        f"{RELATION_LINE.get(relation, RELATION_LINE['unknown'])}",
        f"점수 근거: 계산된 오행 수는 {distribution}입니다. 개수가 적은 순서로 두 오행을 선택하고, "
        "같은 개수일 때는 목·화·토·금·수 순서를 따릅니다.",
        f"이 점수 규칙에서 선택한 오행은 {favorable_label}입니다. 해당 날짜의 오행({day_element})이 {favorable_match}됩니다. "
        "정밀한 용신 분석은 아닙니다.",
        f"{target_date.isoformat()}의 키워드는 {' · '.join(keywords)}입니다.",
    ]
    if dayun_theme:
        lines.append(f"절기 기반 대운 {dayun_theme} · 해석 보정 {dayun_adjustment:+.0f}점 (예측 확률이 아님).")
    else:
        lines.append("대운 보정 미적용: 계산 결과에서 이 날짜에 적용할 대운 구간을 확인하지 못했습니다.")
    birth_basis = dict(getattr(result, 'time_basis', {}) or {})
    if birth_basis:
        lines.append("출생 일·시주는 현지 민간시 기준이며 진태양시 보정은 적용하지 않았습니다.")
        if birth_basis.get('solar_terms') == 'civil_day_interval_confirmed':
            lines.append("년·월주는 현지 출생일 하루 전체에서 동일함을 확인했습니다. 시주와 대운은 제외합니다.")
        elif birth_basis.get('solar_terms') != 'birth_instant_utc_plus_8':
            lines.append("출생시각 미확정 — 절기 경계의 년·월주는 불확실합니다.")

    return {
        "ok": True,
        "score": round(score, 1),
        "grade": _grade(score),
        "aspect_scores": {k: round(v, 1) for k, v in aspect_scores.items()},
        "date": (target_date).isoformat(),
        "day_pillar": day_pillar_today,
        "day_element": day_element,
        "day_master": day_master,
        "relation": relation,
        "aspect": aspect,
        "keywords": keywords,
        "dayun_theme": dayun_theme,
        "dayun_pillar": dayun_pillar,
        "dayun_years": dayun_years,
        "dayun_adjustment": dayun_adjustment,
        "dayun_basis": "lunar-javascript sect 2 / calendar_year" if dayun_data else "unavailable",
        "birth_time_basis": birth_basis,
        "lines": lines,
        "favorable_elements": sorted(favorable),
        "disclaimer": "해석의 한계: 점수와 조언은 경험적 해석이며 예측 확률이 아닙니다. 실제 성격·상황이나 미래를 확인한 결과가 아닙니다. 이 운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
    }


def daily_display_lines(reading: Mapping[str, Any], *, action_override: Optional[str] = None,
                        caution_override: Optional[str] = None) -> list[str]:
    """Copy detailed lines and optionally replace an action/caution pair.

    Situation suggestions are explicitly labelled and never mutate the reading
    or rely on an array position or a parsed heading.
    """
    lines = list(reading["lines"])
    if action_override is None and caution_override is None:
        return lines
    if any(not isinstance(value, str) or not value.strip()
           for value in (action_override, caution_override)):
        raise ValueError("Daily action and caution overrides must be supplied together")
    action, caution = RELATION_PRACTICE.get(reading["relation"], RELATION_PRACTICE["unknown"])
    replacements = {
        f"해볼 일: {action}":
            f"해볼 일 (선택한 상황에 맞춘 제안 · 별도 점수·성공 확률 아님): {action_override}",
        f"주의할 점: {caution}": f"주의할 점 (선택한 상황에 맞춘 제안): {caution_override}",
    }
    if any(lines.count(original) != 1 for original in replacements):
        raise ValueError("Daily action/caution paragraphs are unavailable or ambiguous")
    return [replacements.get(line, line) for line in lines]


def render_daily_channel_text(reading: Mapping[str, Any], *, reading_timezone: Optional[str] = None) -> str:
    """Render the calculated daily result for a short message or narration.

    Detailed ``lines`` remain available to the web renderer. Build the Korean
    summary from calculated fields, without parsing or truncating those lines.
    English retains its existing localized presentation.
    """
    from .localization import language_code
    zone_suffix = f" · {reading_timezone}" if reading_timezone else ""
    if language_code(reading.get("language")) == "en":
        header = f"Interpretation of calculated chart data (heuristic) · {reading['date']}{zone_suffix}"
        return "\n".join([header, *reading["lines"], reading["disclaimer"]])
    relation = reading["relation"]
    action, caution = RELATION_PRACTICE.get(relation, RELATION_PRACTICE["unknown"])
    cycle = (f"대운 보정 {reading['dayun_adjustment']:+.0f}점."
             if reading["dayun_pillar"] else "대운 보정 미적용.")
    lines = [
        f"계산된 사주·일진의 경험적 해석 · {reading['date']} · {ASPECT_TITLE.get(reading['aspect'], '종합 운세')} · "
        f"{reading['score']:.0f}점 — {reading['grade']}{zone_suffix}",
        f"이날의 해석: {RELATION_THEME.get(relation, RELATION_THEME['unknown'])}",
        f"해볼 일: {action}",
        f"주의할 점: {caution}",
        f"계산 근거: 일간 {_stem_element(reading['day_master'])}·일진 {reading['day_pillar']}"
        f"({reading['day_element']})의 관계와 오행 수를 반영했습니다. {cycle}",
        f"{reading['date']}의 키워드는 {' · '.join(reading['keywords'])}입니다.",
    ]
    birth_basis = reading.get("birth_time_basis", {})
    if birth_basis.get("solar_terms") == "civil_day_interval_confirmed":
        lines.append("출생시각 미확정: 시주·대운은 제외했습니다.")
    elif birth_basis and birth_basis.get("solar_terms") != "birth_instant_utc_plus_8":
        lines.append("출생시각 미확정: 절기 경계의 년·월주는 불확실합니다.")
    lines.append("점수와 조언은 경험적 해석이며 예측 확률이 아닙니다. "
                 "오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.")
    return "\n".join(lines)


def render_personalized_daily_text(
    profile: Optional[Mapping[str, Any]],
    *,
    target_date: Optional[date] = None,
    aspect: str = "종합",
    language: Optional[str] = None,
) -> Optional[str]:
    """짧은 메시지용 텍스트. 실패 시 None(호출부가 기존 정적 문구로 폴백)."""
    d = build_personalized_daily(profile, target_date=target_date, aspect=aspect, language=language)
    if not d:
        return None
    return render_daily_channel_text(d)
