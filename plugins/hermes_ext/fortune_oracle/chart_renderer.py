#!/usr/bin/env python3
"""Fortune K선 PNG 카드 렌더러 (Phase 2A / Phase 8B Kami-style / Phase 9 Polish).

Phase 9 개선:
- typography spacing 일정화 (overline/title/chart/strip/footer 간격)
- 최고점/최저점 annotation (과하지 않게, 겹침 방지)
- data strip width/spacing 균등화, 숫자-label 위계 강화
- profile 있으면 display_name을 subtitle로 반영 (birth_date/time/name_hanja 제외)
- 월간/연간 동일 디자인 언어 보장

제약:
- 출력 PNG: 1024x512, 3MB 이하
- birth_date, birth_time, birth_place, name_hanja 원문 출력 금지
- 빈 candles → RendererUnavailable
- matplotlib 없으면 RendererUnavailable
- fail-open Korean font, text fallback 유지

운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
import warnings as _warnings
from pathlib import Path
from typing import Any, List, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .kline import FortuneCandle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CANDLES = 62
MAX_FILE_BYTES = 3 * 1024 * 1024
IMAGE_WIDTH_PX = 1024
IMAGE_HEIGHT_PX = 512

_SENSITIVE_KEYS = {"birth_date", "birth_time", "birth_place", "name_hanja"}

# ---------------------------------------------------------------------------
# Design tokens (Phase 8A) — Kami-inspired
# ---------------------------------------------------------------------------

try:
    from .design_tokens import (
        CANVAS_PARCHMENT, SURFACE_IVORY, WARM_SAND,
        INK_BLUE, DEEP_INK, WARM_STONE, OLIVE_NOTE,
        YANG_WARM, YIN_MUTED, DOJI_SAND,
        RING_WHISPER, RING_INNER,
        FONT_OVERLINE_SIZE, FONT_TITLE_SIZE, FONT_LABEL_SIZE,
        FONT_TICK_SIZE, FONT_DISCLAIMER_SIZE,
        HEADER_PAD, FOOTER_PAD,
    )
    _TOKENS_AVAILABLE = True
except ImportError:
    CANVAS_PARCHMENT = "#F5F4ED"
    SURFACE_IVORY    = "#FAF9F5"
    WARM_SAND        = "#E8E6DC"
    INK_BLUE         = "#1B365D"
    DEEP_INK         = "#1F2320"
    WARM_STONE       = "#7A7668"
    OLIVE_NOTE       = "#6F735D"
    YANG_WARM        = "#C4502A"
    YIN_MUTED        = "#3A6B8A"
    DOJI_SAND        = "#9E9A8E"
    RING_WHISPER     = "#D6D3C8"
    RING_INNER       = "#C8C5BA"
    FONT_OVERLINE_SIZE = 6.5
    FONT_TITLE_SIZE    = 11.0
    FONT_LABEL_SIZE    = 7.0
    FONT_TICK_SIZE     = 6.5
    FONT_DISCLAIMER_SIZE = 5.5
    HEADER_PAD  = 8
    FOOTER_PAD  = 0.03
    _TOKENS_AVAILABLE = False
    logger.warning("design_tokens not found — using fallback palette")


class RendererUnavailable(Exception):
    """matplotlib 미설치이거나 렌더링 불가 상태."""


# ---------------------------------------------------------------------------
# Korean font setup (fail-open)
# ---------------------------------------------------------------------------

_KOREAN_FONT_CANDIDATES = [
    "NanumGothic", "NanumBarunGothic", "NanumMyeongjo",
    "Noto Sans CJK KR", "NotoSansCJK-Regular", "Noto Sans KR",
    "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Unifont",
]


def _setup_korean_font() -> Optional[str]:
    """사용 가능한 한글 폰트를 matplotlib에 등록 (fail-open)."""
    try:
        import matplotlib.font_manager as fm
        available = {f.name for f in fm.fontManager.ttflist}
        for candidate in _KOREAN_FONT_CANDIDATES:
            if candidate in available:
                logger.debug("Korean font selected: %s", candidate)
                return candidate
        font_file_hints = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/unifont/unifont.otf",
        ]
        # Bundled fonts remain available on hosts without system Korean fonts.
        # Prefer Sans for charts; Serif is a fallback if the first file is damaged.
        font_dir = Path(__file__).resolve().parent / "fonts"
        font_file_hints.extend(str(font_dir / name) for name in (
            "NotoSansCJKkr-Regular.otf", "NotoSerifCJKkr-Medium.otf",
        ))
        for fpath in font_file_hints:
            if Path(fpath).exists():
                try:
                    prop = fm.FontProperties(fname=fpath)
                    font_name = prop.get_name()
                    fm.fontManager.addfont(fpath)
                    logger.info("Korean font loaded from file: %s (%s)", fpath, font_name)
                    return font_name
                except Exception as inner:
                    logger.debug("Font load failed for %s: %s", fpath, inner)
        logger.warning(
            "No Korean font found. Chart text may render as boxes. "
            "Install: sudo apt-get install -y fonts-nanum"
        )
        return None
    except Exception as exc:
        logger.warning("Korean font setup failed (non-fatal): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_display_name(profile: Optional[Mapping[str, Any]]) -> str:
    """민감 출생정보를 제외한 표시 이름만 반환."""
    if not profile:
        return ""
    name = profile.get("display_name", "")
    return str(name) if name else ""


def _strip_sensitive(text: str) -> str:
    for key in _SENSITIVE_KEYS:
        text = text.replace(key, "")
    return text


# ---------------------------------------------------------------------------
# Core renderer — Phase 9 polish
# ---------------------------------------------------------------------------

def render_kline_card_png(
    candles: "List[FortuneCandle]",
    title: str = "",
    output_path: Optional[Path | str] = None,
    *,
    profile: Optional[Mapping[str, Any]] = None,
) -> Path:
    """K선 캔들 목록을 Kami-style PNG 파일로 렌더링 (Phase 9 polish)."""
    from .localization import language_code, DISCLAIMER_EN
    english = language_code((profile or {}).get("language")) == "en"
    # 1. matplotlib 확인
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        _warnings.filterwarnings("ignore", message="Glyph.*missing from font")
        _warnings.filterwarnings("ignore", message=".*tight_layout.*")
    except ImportError as exc:
        raise RendererUnavailable(f"matplotlib not available: {exc}") from exc

    # 1b. 한글 폰트 (fail-open)
    korean_font = _setup_korean_font()
    if korean_font:
        import matplotlib as _mpl
        _mpl.rcParams["font.family"] = korean_font
        _mpl.rcParams["axes.unicode_minus"] = False

    # 2. 빈 candles fail-closed (출생정보 없이 계산된 None 캔들은 제외)
    candles = [c for c in (candles or []) if c is not None]
    if not candles:
        from .kline import CALCULATION_UNAVAILABLE
        raise RendererUnavailable(CALCULATION_UNAVAILABLE)

    # 3. 최대 candle 제한
    data = candles[-MAX_CANDLES:] if len(candles) > MAX_CANDLES else list(candles)
    n = len(data)

    # 4. 제목 (Phase 9: profile display_name → subtitle)
    display_name = _safe_display_name(profile)
    if not title:
        name_part = f"{display_name}님의 " if display_name else ""
        title = "K-line Reflection" if english else f"{name_part}운세 K선"
    title = _strip_sensitive(title)

    # 5. 출력 경로
    if output_path is None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        output_path = Path(tmp.name)
        tmp.close()
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # 6. figure 크기 (1024×512, 96dpi)
    dpi = 96
    fig_w = IMAGE_WIDTH_PX / dpi   # ~10.67 inches
    fig_h = IMAGE_HEIGHT_PX / dpi  # ~5.33 inches

    # 7. Phase 9 layout — 균등 spacing
    #    top=0.89: header overline+title 공간 확보
    #    bottom=0.14: footer disclaimer 공간 확보
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=CANVAS_PARCHMENT)
    gs = fig.add_gridspec(
        2, 1,
        height_ratios=[3.8, 1],
        hspace=0.06,
        left=0.07, right=0.96,
        top=0.87, bottom=0.13,
    )
    ax_main = fig.add_subplot(gs[0])
    ax_data = fig.add_subplot(gs[1])

    ax_main.set_facecolor(SURFACE_IVORY)
    ax_data.set_facecolor(WARM_SAND)

    # --- Statistics ---
    closes = [c.close for c in data]
    avg_score = sum(closes) / len(closes)
    max_c = max(data, key=lambda c: c.close)
    min_c = min(data, key=lambda c: c.close)
    max_idx = data.index(max_c)
    min_idx = data.index(min_c)
    yang_count = sum(1 for c in data if c.color == "yang")
    yin_count  = sum(1 for c in data if c.color == "yin")
    trend = "상승" if closes[-1] > closes[0] else "하락" if closes[-1] < closes[0] else "횡보"
    if english:
        trend = {"상승": "Rising", "하락": "Falling", "횡보": "Flat"}[trend]

    # --- Candle rendering ---
    candle_width = min(0.6, 0.85 * (MAX_CANDLES / max(n, 1)) ** 0.3)
    candle_width = max(0.35, min(candle_width, 0.65))

    for i, c in enumerate(data):
        col = YANG_WARM if c.color == "yang" else (YIN_MUTED if c.color == "yin" else DOJI_SAND)
        body_lo = min(c.open, c.close)
        body_hi = max(c.open, c.close)
        body_h  = max(body_hi - body_lo, 0.5)

        rect = mpatches.FancyBboxPatch(
            (i - candle_width / 2, body_lo), candle_width, body_h,
            boxstyle="square,pad=0",
            linewidth=0.35, edgecolor=RING_INNER, facecolor=col, alpha=0.85,
        )
        ax_main.add_patch(rect)
        # Wick
        ax_main.plot([i, i], [body_hi, c.high], color=col, linewidth=0.6, alpha=0.6)
        ax_main.plot([i, i], [body_lo, c.low],  color=col, linewidth=0.6, alpha=0.6)

    # --- Phase 9: Annotation (최고/최저, 겹침 방지) ---
    y_min = max(0,   min(c.low  for c in data) - 5)
    y_max = min(100, max(c.high for c in data) + 8)  # 위 여백 더 확보
    y_range = y_max - y_min

    def _annotate_point(ax, x_idx, y_val, label, above=True):
        """최고/최저 마커 — 작고 비침투적."""
        offset = y_range * 0.10 if above else -y_range * 0.10
        va = "bottom" if above else "top"
        ax.annotate(
            label,
            xy=(x_idx, y_val),
            xytext=(x_idx, y_val + offset),
            ha="center", va=va,
            fontsize=FONT_TICK_SIZE - 0.5,
            color=INK_BLUE,
            arrowprops=dict(
                arrowstyle="-",
                color=WARM_STONE,
                lw=0.5,
            ),
        )

    # 겹침 방지: 최고/최저 같은 위치면 하나만 표시
    if abs(max_idx - min_idx) >= max(1, n // 10):
        _annotate_point(ax_main, max_idx, max_c.high, f"▲{max_c.close:.0f}", above=True)
        _annotate_point(ax_main, min_idx, min_c.low,  f"▼{min_c.close:.0f}", above=False)
    else:
        # 겹침 — 최고만 표시
        _annotate_point(ax_main, max_idx, max_c.high, f"▲{max_c.close:.0f}", above=True)

    ax_main.set_ylim(y_min, y_max)
    ax_main.set_xlim(-0.8, n - 0.2)

    # Grid — warm sand, very subtle
    ax_main.grid(color=WARM_SAND, linestyle="-", linewidth=0.4, alpha=0.9, zorder=0)

    # Spine
    for spine in ax_main.spines.values():
        spine.set_edgecolor(RING_WHISPER)
        spine.set_linewidth(0.5)

    # X ticks (최대 12개)
    step = max(1, n // 12)
    tick_pos = list(range(n))[::step]
    tick_lab = [data[i].date.strftime("%m/%d") for i in tick_pos]
    ax_main.set_xticks(tick_pos)
    ax_main.set_xticklabels(tick_lab, rotation=30, fontsize=FONT_TICK_SIZE, color=WARM_STONE)
    ax_main.tick_params(colors=WARM_STONE, labelsize=FONT_TICK_SIZE, length=2)
    ax_main.set_ylabel("Index" if english else "에너지", color=WARM_STONE, fontsize=FONT_LABEL_SIZE, labelpad=4)

    # --- Phase 9: Data strip 균등 4칸 ---
    ax_data.set_xlim(0, 1)
    ax_data.set_ylim(0, 1)
    ax_data.axis("off")
    for spine in ax_data.spines.values():
        spine.set_visible(False)

    strip_items = [
        ("평균",  f"{avg_score:.0f}"),
        ("최고",  f"{max_c.close:.0f}  {max_c.date.strftime('%m/%d')}"),
        ("최저",  f"{min_c.close:.0f}  {min_c.date.strftime('%m/%d')}"),
        ("흐름",  f"{trend}  +{yang_count}/-{yin_count}"),
    ]
    if english:
        strip_items = [(label, value) for label, (_, value) in zip(("Average", "High", "Low", "Trend"), strip_items)]
    # 균등 x 위치: 0.06, 0.30, 0.55, 0.78
    strip_x = [0.06, 0.30, 0.55, 0.78]
    for k, ((label, value), sx) in enumerate(zip(strip_items, strip_x)):
        # label (small, warm stone)
        ax_data.text(sx, 0.78, label,
                     fontsize=FONT_LABEL_SIZE - 1.0, color=WARM_STONE,
                     va="top", ha="left", fontweight="normal")
        # value (larger, ink blue)
        ax_data.text(sx, 0.22, value,
                     fontsize=FONT_LABEL_SIZE + 1.5, color=INK_BLUE,
                     va="bottom", ha="left", fontweight="bold")

    # 수직 구분선 (아주 연하게)
    for sx in strip_x[1:]:
        ax_data.axvline(x=sx - 0.03, color=RING_WHISPER, linewidth=0.5, ymin=0.1, ymax=0.9)

    # --- Phase 9: Header spacing 일정화 ---
    # overline: y=0.960, title: y=0.918 (간격 0.042)
    fig.text(
        0.07, 0.960,
        "FORTUNE ORACLE  ·  K-LINE",
        ha="left", va="top",
        fontsize=FONT_OVERLINE_SIZE,
        color=WARM_STONE,
        alpha=0.85,
    )
    fig.text(
        0.07, 0.918,
        title,
        ha="left", va="top",
        fontsize=FONT_TITLE_SIZE,
        color=INK_BLUE,
        fontweight="bold",
    )

    # display_name subtitle (profile 있을 때만, 오른쪽 정렬)
    if display_name:
        fig.text(
            0.96, 0.960,
            display_name,
            ha="right", va="top",
            fontsize=FONT_OVERLINE_SIZE,
            color=WARM_STONE,
            alpha=0.70,
        )

    # --- Footer ---
    basis = "일진 기반 해석 지수 · 예측 확률이 아닙니다."
    if data[-1].dayun_theme:
        basis += f" 절기 기반 대운: {data[-1].dayun_theme} (해석 보정 반영)"
    footer = basis + "\n오락과 자기성찰용 · 의학 / 투자 / 법률 결정을 지시하지 않습니다."
    if english:
        basis = "Day-pillar interpretive index, not a predicted probability."
        if data[-1].dayun_theme:
            basis += f" Cycle: {data[-1].dayun_theme} (interpretive adjustment included)"
        footer = basis + "\n" + DISCLAIMER_EN
    fig.text(
        0.5, FOOTER_PAD,
        footer,
        ha="center", va="bottom",
        fontsize=FONT_DISCLAIMER_SIZE,
        color=OLIVE_NOTE,
        alpha=0.85,
    )

    # 카드 외곽 ring border
    fig.patch.set_linewidth(0.8)
    fig.patch.set_edgecolor(RING_WHISPER)

    # 8. 저장
    fig.savefig(
        output_path, dpi=dpi, format="png",
        bbox_inches="tight", facecolor=CANVAS_PARCHMENT,
    )
    plt.close(fig)

    # 9. 크기 검증
    file_size = output_path.stat().st_size
    if file_size > MAX_FILE_BYTES:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"Generated PNG exceeds 3MB: {file_size / 1024 / 1024:.2f}MB")

    return output_path


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def render_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def render_month_card_png(
    profile: Optional[Mapping[str, Any]] = None,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    output_path: Optional[Path | str] = None,
) -> Path:
    """월간 K선 PNG 카드 생성."""
    from .kline import build_monthly_kline
    from .daily_fortune_engine import _profile_today
    today = _profile_today(profile)
    y = year or today.year
    m = month or today.month
    candles = build_monthly_kline(profile, y, m)
    name_part = f"{_safe_display_name(profile)}님의 " if _safe_display_name(profile) else ""
    title = f"{name_part}{y}년 {m}월 운세 K선"
    from .localization import language_code
    if language_code((profile or {}).get("language")) == "en":
        title = f"{y}-{m:02d} K-line Reflection"
    return render_kline_card_png(candles, title=title, output_path=output_path, profile=profile)


def render_year_card_png(
    profile: Optional[Mapping[str, Any]] = None,
    *,
    year: Optional[int] = None,
    output_path: Optional[Path | str] = None,
) -> Path:
    """연간 K선 PNG 카드 생성."""
    from .kline import build_yearly_kline
    from .daily_fortune_engine import _profile_today
    y = year or _profile_today(profile).year
    candles = build_yearly_kline(profile, y)
    name_part = f"{_safe_display_name(profile)}님의 " if _safe_display_name(profile) else ""
    title = f"{name_part}{y}년 인생 K선"
    from .localization import language_code
    if language_code((profile or {}).get("language")) == "en":
        title = f"{y} Annual K-line Reflection"
    return render_kline_card_png(candles, title=title, output_path=output_path, profile=profile)
