#!/usr/bin/env python3
"""Platform-neutral Fortune Oracle core rendering and prompt policy."""

from __future__ import annotations

from typing import Any, Mapping, Optional
import logging
from .localization import NOT_CALCULATED_KO

logger = logging.getLogger(__name__)

FORTUNE_PROMPT_POLICY = {
    "purpose": "오락과 자기성찰용 운세",
    "must_include": "의학, 투자, 법률 결정을 지시하지 않습니다.",
    "characters": ["태허", "관음", "티코", "자허"],
    "daily_length": "5~8 non-empty lines",
}


def _render_fortune(day: str = "today", *, profile: Optional[Mapping[str, Any]] = None) -> str:
    if profile and profile.get("language"):
        from .localization import language_code
        try:
            code = language_code(profile["language"])
        except ValueError:
            return f"{NOT_CALCULATED_KO} / Not a calculated result\nUnsupported language; use ko or en. / 한국어(ko) 또는 영어(en)를 선택해 주세요."
        if code == "en":
            from .daily_reading import prepare_daily_reading
            return prepare_daily_reading(profile, day=day, language=code)["text"]
    # 개인화 일일 운세: 출생정보가 있으면 사주 기반 계산 결과를 우선 사용한다.
    # 일반 문구는 계산 결과와 구분한다. 점수를 임의로 만들지 않는다.
    personalization_failed = False
    if day == "today" and profile:
        try:
            from .daily_fortune_engine import render_personalized_daily_text

            personalized = render_personalized_daily_text(profile)
            if personalized:
                return personalized
        except Exception:
            pass
        personalization_failed = bool(profile.get('birth_date'))
    label = {"today": "오늘", "tomorrow": "내일", "week": "이번 주"}.get(day, "오늘")
    lines = [
        f"{NOT_CALCULATED_KO} — 아래는 계산 결과가 아닌 일반 성찰 문구입니다.",
        f"태허가 전하는 {label}의 일반 성찰 문구입니다.",
        "흐름을 크게 바꾸기보다 작은 정리를 먼저 해 보세요.",
        "관음은 말보다 듣는 쪽에 복이 있다고 봅니다.",
        "티코는 일정 하나를 줄이면 집중력이 살아난다고 조언합니다.",
        "자허는 오래 미룬 답장을 짧게 끝내라고 말합니다.",
        "이 운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
    ]
    if personalization_failed:
        lines.insert(1, "개인화 계산 불가 — 출생시각·시간대와 계산 환경을 확인해 주세요.")
    if day == "week":
        lines.insert(2, "주중에는 관계 정리, 주말에는 회복에 무게를 두세요.")
    return "\n".join(lines)


def render_daily_fortune(*, profile: Optional[Mapping[str, Any]] = None) -> str:
    return _render_fortune("today", profile=profile)


def render_tomorrow_fortune(*, profile: Optional[Mapping[str, Any]] = None) -> str:
    return _render_fortune("tomorrow", profile=profile)


def render_weekly_fortune(*, profile: Optional[Mapping[str, Any]] = None) -> str:
    return _render_fortune("week", profile=profile)


def render_fortune(day: str = "today", *, profile: Optional[Mapping[str, Any]] = None) -> str:
    if day == "tomorrow":
        return render_tomorrow_fortune(profile=profile)
    if day == "week":
        return render_weekly_fortune(profile=profile)
    return render_daily_fortune(profile=profile)


def render_kline_card(
    *,
    profile: Optional[Mapping[str, Any]] = None,
    period: str = "month",
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    """월간/연간 K선 PNG 카드를 생성하고 MEDIA: 태그 응답을 반환.

    반환 형식:
      - 성공: "MEDIA:/tmp/fortune_kline_XXXX.png\\n<caption>"
      - 실패(renderer 없음): phase1 fallback 텍스트

    민감 출생정보(birth_date, birth_time, birth_place, name_hanja)는
    caption과 파일명 어디에도 포함하지 않는다.

    Args:
        profile: 사용자 프로필. display_name만 사용.
        period: "month" 또는 "year"
        year: 연도 (None이면 오늘 기준)
        month: 월 (None이면 오늘 기준, period="month"일 때만 사용)

    Returns:
        MEDIA: 태그 + caption 텍스트 또는 text fallback.
    """
    import tempfile
    from pathlib import Path as _Path

    try:
        from .chart_renderer import render_month_card_png, render_year_card_png, RendererUnavailable
    except ImportError:
        if str((profile or {}).get("language", "")).lower().replace("_", "-").split("-")[0] == "en":
            return "The card renderer is unavailable. Please use a text K-line reading."
        from .kline import kline_card_phase1_fallback
        return kline_card_phase1_fallback("telegram")

    # display_name만 추출 — 민감 필드 완전 배제
    display_name = (profile or {}).get("display_name") if profile else None
    name_tag = f"{display_name}님의 " if display_name else ""

    output_path = _Path(tempfile.gettempdir()) / "fortune_kline_placeholder.png"
    try:
        # 임시 파일 — 민감정보를 경로에 넣지 않음
        tmp = tempfile.NamedTemporaryFile(
            prefix="fortune_kline_",
            suffix=".png",
            delete=False,
        )
        tmp.close()
        output_path = _Path(tmp.name)
        from .daily_fortune_engine import _profile_today
        today = _profile_today(profile)
        y = year or today.year
        m = month or today.month
        from .localization import language_code, DISCLAIMER_EN
        english = language_code((profile or {}).get("language")) == "en"

        if period == "year":
            out = render_year_card_png(
                profile=profile,
                year=y,
                output_path=output_path,
            )
            caption = (
                f"{name_tag}{y}년 인생 K선 카드\n"
                "이 운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
            )
        else:
            out = render_month_card_png(
                profile=profile,
                year=y,
                month=m,
                output_path=output_path,
            )
            caption = (
                f"{name_tag}{y}년 {m}월 운세 K선 카드\n"
                "이 운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
            )

        if english:
            caption = (f"{y} Annual K-line card" if period == "year" else f"{y}-{m:02d} K-line card") + "\n" + DISCLAIMER_EN
        return f"MEDIA:{out}\n{caption}"

    except Exception as exc:
        # Record only the error class: exception text/tracebacks may contain profile data.
        logger.warning("fortune-oracle: kline card failed (%s)", type(exc).__name__)
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        from .kline import CALCULATION_UNAVAILABLE
        english = str((profile or {}).get("language", "")).lower().replace("_", "-").split("-")[0] == "en"
        if isinstance(exc, RendererUnavailable) and str(exc) == CALCULATION_UNAVAILABLE:
            return ("Birth information is missing or calculation failed; no K-line can be generated."
                    if english else CALCULATION_UNAVAILABLE)
        return ("The K-line image could not be generated. Try /month_kline for a text reading, or try again later."
                if english else "K선 이미지를 만들지 못했습니다. /month_kline 으로 텍스트 풀이를 확인하거나 잠시 후 다시 시도해 주세요.")


def get_daily_candle_score(
    profile: Optional[Mapping[str, Any]] = None,
) -> Optional[float]:
    """오늘 일일 운세 캔들의 close 점수(0~100)를 반환.

    실제 점수 계산은 kline.build_daily_candle을 재사용한다.
    출생정보가 없거나 계산에 실패하면 None을 반환한다.
    """
    try:
        from .kline import build_daily_candle
        candle = build_daily_candle(profile)
        return candle.close if candle is not None else None
    except Exception:
        return None
