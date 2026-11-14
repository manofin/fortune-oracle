#!/usr/bin/env python3
"""Fortune K-Line module — 운세 K선 (캔들) 표현.

개념 참고: miounet11/life-kline (Apache-2.0)
- 참고한 것: 인생 운세를 금융 K선(캔들차트) 방식으로 점수화하는 표현 아이디어.
- 제외한 것: 전체 앱 서버, Node/React 프론트엔드, 실제 소스 코드.
- 이 모듈은 Python domain 로직만 구현한다.

운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------

@dataclass
class FortuneCandle:
    """하루(또는 한 달)의 운세를 K선 캔들 형식으로 표현.

    Invariants:
        high >= max(open, close)
        low  <= min(open, close)
        모든 값: 0.0 ~ 100.0
    """

    date: date
    open: float    # 시작 에너지 (0~100)
    close: float   # 마감 에너지 (0~100)
    high: float    # 최고 에너지 (0~100)
    low: float     # 최저 에너지 (0~100)
    aspect: str = "종합"   # 운세 영역: 활동, 관계, 재물, 건강, 종합
    label: str = ""        # 짧은 키워드 요약
    dayun_theme: str = ""  # 절기 기반 대운 간지와 연도 구간

    def __post_init__(self) -> None:
        # Clamp all values
        for attr in ("open", "close", "high", "low"):
            setattr(self, attr, max(0.0, min(100.0, float(getattr(self, attr)))))
        # Enforce OHLC invariant
        body_high = max(self.open, self.close)
        body_low = min(self.open, self.close)
        if self.high < body_high:
            self.high = body_high
        if self.low > body_low:
            self.low = body_low

    @property
    def color(self) -> str:
        """양봉(상승)/음봉(하락)/도지(중립)."""
        if self.close > self.open + 0.5:
            return "yang"   # 양봉 ↑
        if self.close < self.open - 0.5:
            return "yin"    # 음봉 ↓
        return "doji"       # 도지 —

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low


CALCULATION_UNAVAILABLE = "출생정보가 없거나 계산에 실패하여 K선을 생성할 수 없습니다. 출생정보를 확인하고 다시 시도해 주세요."


def _period_readings(profile, start, end, aspect):
    from .daily_fortune_engine import build_personalized_series
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return build_personalized_series(profile, dates, aspect=aspect)


def _daily_candle(previous, current, aspect, language="ko"):
    from .localization import localize_daily, pillar_label
    current = localize_daily(current, language)
    opening, closing = previous["score"], current["score"]
    return FortuneCandle(
        date=date.fromisoformat(current["date"]), open=opening, close=closing,
        high=max(opening, closing), low=min(opening, closing), aspect=aspect,
        label=f"{pillar_label(current['day_pillar']) if language == 'en' else current['day_pillar']} · {current['grade']}",
        dayun_theme=current["dayun_theme"],
    )


def build_daily_candle(profile=None, target_date=None, aspect="종합") -> Optional[FortuneCandle]:
    """Previous day's score → today's score. No invented intraday extremes."""
    from .daily_fortune_engine import _profile_today
    d = target_date or _profile_today(profile)
    readings = _period_readings(profile, d - timedelta(days=1), d, aspect)
    from .localization import language_code
    language = language_code((profile or {}).get("language"))
    return _daily_candle(*readings, aspect, language) if readings else None


def build_monthly_kline(profile=None, year=None, month=None, aspect="종합") -> List[FortuneCandle]:
    """One daily candle per calendar day, with one chart calculation for the month."""
    from .daily_fortune_engine import _profile_today
    today = _profile_today(profile)
    y, m = year or today.year, month or today.month
    first = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    readings = _period_readings(profile, first - timedelta(days=1), last, aspect)
    if not readings:
        return []
    from .localization import language_code
    language = language_code((profile or {}).get("language"))
    return [_daily_candle(a, b, aspect, language) for a, b in zip(readings, readings[1:])]


def build_yearly_kline(profile=None, year=None, aspect="종합") -> List[FortuneCandle]:
    """Monthly OHLC from all daily scores, with one chart calculation for the year."""
    from .daily_fortune_engine import _profile_today
    y = year or _profile_today(profile).year
    readings = _period_readings(profile, date(y, 1, 1), date(y, 12, 31), aspect)
    if not readings:
        return []
    candles = []
    from .localization import language_code, localize_daily
    language = language_code((profile or {}).get("language"))
    offset = 0
    for m in range(1, 13):
        days = calendar.monthrange(y, m)[1]
        batch = readings[offset:offset + days]
        scores = [item["score"] for item in batch]
        candles.append(FortuneCandle(
            date=date(y, m, 1), open=scores[0], close=scores[-1],
            high=max(scores), low=min(scores), aspect=aspect,
            label=f"{calendar.month_abbr[m]} daily-score aggregate" if language == "en" else f"{m}월 일별 점수 집계",
            dayun_theme=localize_daily(batch[-1], language)["dayun_theme"],
        ))
        offset += days
    return candles


# ---------------------------------------------------------------------------
# Text summarizer
# ---------------------------------------------------------------------------

_COLOR_SYMBOL = {"yang": "▲", "yin": "▽", "doji": "■"}
_COLOR_KR = {"yang": "양봉", "yin": "음봉", "doji": "도지"}


def _score_to_bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def summarize_kline(
    candles: List[FortuneCandle],
    *,
    title: str = "",
    platform: str = "telegram",
    unit: str = "일",
    language: str = "ko",
) -> str:
    """K선 목록을 텍스트로 요약 출력.

    Args:
        unit: 기간 단위 표시 ("일" 또는 "개월"). render_life_kline은 "개월" 전달.

    platform='telegram': Markdown 허용.
    platform='line': plain text.
    운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.
    """
    from .localization import language_code, DISCLAIMER_EN
    language = language_code(language)
    if not candles:
        return "Birth information is missing or calculation failed; no K-line can be generated." if language == "en" else CALCULATION_UNAVAILABLE

    closes = [c.close for c in candles]
    avg_score = sum(closes) / len(closes)
    max_candle = max(candles, key=lambda c: c.close)
    min_candle = min(candles, key=lambda c: c.close)
    yang_count = sum(1 for c in candles if c.color == "yang")
    yin_count = sum(1 for c in candles if c.color == "yin")
    doji_count = len(candles) - yang_count - yin_count
    trend = "상승" if closes[-1] > closes[0] else "하락" if closes[-1] < closes[0] else "횡보"

    if language == "en":
        trend = {"상승": "Rising", "하락": "Falling", "횡보": "Flat"}[trend]
        heading = title or "K-line reflection"
        lines = [f"**{heading}**" if platform == "telegram" else heading,
                 f"Period {candles[0].date} to {candles[-1].date} ({len(candles)} {'months' if unit == '개월' else 'days'})",
                 "Day-pillar interpretive index, not a predicted probability."]
        if candles[-1].dayun_theme:
            lines.append(f"Solar-term cycle: {candles[-1].dayun_theme} (interpretive adjustment included)")
        lines.extend([f"Trend {trend} · Average {avg_score:.1f}",
                      f"High {max_candle.date} ({max_candle.close:.0f}) · Low {min_candle.date} ({min_candle.close:.0f})",
                      f"Rising {yang_count} · Falling {yin_count} · Doji {doji_count}", "Recent values"])
        lines.extend(f"{c.date.strftime('%m/%d')} {_COLOR_SYMBOL[c.color]} {_score_to_bar(c.close, 8)} {c.close:.0f} · {c.label}" for c in candles[-7:])
        return "\n".join([*lines, DISCLAIMER_EN])

    lines: List[str] = []

    if platform == "telegram":
        lines.append(f"**{title or '운세 K선 요약'}**")
    else:
        lines.append(title or "운세 K선 요약")

    lines.append(f"기간  {candles[0].date} ~ {candles[-1].date}  ({len(candles)}{unit})")
    lines.append("일진 기반 해석 지수 · 예측 확률이 아닙니다.")
    if candles[-1].dayun_theme:
        lines.append(f"절기 기반 대운: {candles[-1].dayun_theme} (해석 보정 반영)")
    lines.append(f"흐름  {trend}  평균 에너지 {avg_score:.1f}")
    lines.append(f"최고  {max_candle.date} ({max_candle.close:.0f})  최저  {min_candle.date} ({min_candle.close:.0f})")
    lines.append(f"양봉 {yang_count} · 음봉 {yin_count} · 도지 {doji_count}")
    lines.append("")

    # Show last 7 candles as mini-chart
    recent = candles[-7:] if len(candles) >= 7 else candles
    if platform == "telegram":
        lines.append("**최근 흐름**")
    else:
        lines.append("최근 흐름")
    for c in recent:
        sym = _COLOR_SYMBOL[c.color]
        bar = _score_to_bar(c.close, 8)
        lines.append(f"{c.date.strftime('%m/%d')} {sym} {bar} {c.close:.0f}  {c.label}")

    lines.append("")
    lines.append("오락과 자기성찰용 · 의학, 투자, 법률 결정을 지시하지 않습니다.")
    return "\n".join(lines)


def render_life_kline(
    profile: Optional[Mapping[str, Any]] = None,
    *,
    year: Optional[int] = None,
    platform: str = "telegram",
) -> str:
    """연간 인생 K선 텍스트 요약.

    민감 출생정보(birth_date, birth_time, birth_place, name_hanja) 원문은
    출력에 포함되지 않는다.
    """
    from .daily_fortune_engine import _profile_today
    y = year or _profile_today(profile).year
    candles = build_yearly_kline(profile, y)
    display_name = (profile or {}).get("display_name")
    name_part = f"{display_name}님의 " if display_name else ""
    from .localization import language_code
    language = language_code((profile or {}).get("language"))
    return summarize_kline(
        candles,
        title=f"{y} Annual K-line" if language == "en" else f"{name_part}{y}년 인생 K선",
        platform=platform,
        unit="개월",
        language=language,
    )


def render_month_kline(
    profile: Optional[Mapping[str, Any]] = None,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    platform: str = "telegram",
) -> str:
    """월간 K선 텍스트 요약."""
    from .daily_fortune_engine import _profile_today
    today = _profile_today(profile)
    y = year or today.year
    m = month or today.month
    candles = build_monthly_kline(profile, y, m)
    display_name = (profile or {}).get("display_name")
    name_part = f"{display_name}님의 " if display_name else ""
    import calendar
    month_name = calendar.month_abbr[m]
    from .localization import language_code
    language = language_code((profile or {}).get("language"))
    return summarize_kline(
        candles,
        title=f"{month_name} {y} K-line" if language == "en" else f"{name_part}{y}년 {m}월 운세 K선",
        platform=platform,
        language=language,
    )


def kline_card_phase1_fallback(platform: str = "telegram") -> str:
    """Phase 1: 이미지 카드 미구현 — 텍스트 fallback 반환."""
    msg = (
        "운세 K선 카드 이미지는 Phase 2에서 구현 예정입니다.\n"
        "현재는 텍스트 K선 요약(/life_kline, /month_kline)을 사용하세요."
    )
    if platform == "line":
        return msg
    return msg
