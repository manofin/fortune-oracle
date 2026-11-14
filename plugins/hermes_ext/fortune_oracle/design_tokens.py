"""Fortune Oracle — Kami-inspired Design Tokens (Phase 8A).

Kami(tw93/Kami)의 디자인 원칙을 Fortune Oracle Telegram 카드에 맞게 adaptation한
color/typography/spacing 토큰 모음.

차용 원칙:
- warm parchment canvas (cold gray/pure white 금지)
- ink-blue single accent
- warm neutral palette
- editorial rhythm (hard shadow 금지, ring/whisper border)
- 과도한 색상·장식·emoji 금지

운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Canvas / Background
# ---------------------------------------------------------------------------

CANVAS_PARCHMENT = "#F5F4ED"    # 따뜻한 양피지 — 메인 배경
SURFACE_IVORY    = "#FAF9F5"    # 더 밝은 아이보리 — 패널 내부
WARM_SAND        = "#E8E6DC"    # 그리드/구분선 (아주 연한)
WARM_SAND_LIGHT  = "#EFEDE5"    # 호버/서브 패널

# ---------------------------------------------------------------------------
# Ink — 주요 텍스트 / 단일 accent
# ---------------------------------------------------------------------------

INK_BLUE         = "#1B365D"    # 유일한 accent — 제목, 강조 데이터
DEEP_INK         = "#1F2320"    # 본문 텍스트 (거의 검정)
WARM_STONE       = "#7A7668"    # 보조 텍스트 / label
OLIVE_NOTE       = "#6F735D"    # disclaimer / 아주 작은 메모

# ---------------------------------------------------------------------------
# Candle colors — ink/warm neutral 계열로 과도한 원색 회피
# ---------------------------------------------------------------------------

YANG_WARM        = "#C4502A"    # 양봉: 따뜻한 적갈색 (bright red 금지)
YIN_MUTED        = "#3A6B8A"    # 음봉: 차분한 slate blue (bright green/teal 금지)
DOJI_SAND        = "#9E9A8E"    # 도지: warm sand gray

# ---------------------------------------------------------------------------
# Border / Ring
# ---------------------------------------------------------------------------

RING_WHISPER     = "#D6D3C8"    # 카드 외곽 ring border (hard shadow 금지)
RING_INNER       = "#C8C5BA"    # 패널 내부 구분선

# ---------------------------------------------------------------------------
# Typography scale (relative hints — actual font controlled by renderer)
# ---------------------------------------------------------------------------

FONT_OVERLINE_SIZE = 6.5        # "FORTUNE ORACLE · K-LINE" 상단 overline
FONT_TITLE_SIZE    = 11.0       # 차트 제목
FONT_LABEL_SIZE    = 7.0        # axis label, legend
FONT_TICK_SIZE     = 6.5        # tick label
FONT_DISCLAIMER_SIZE = 5.5      # footer disclaimer

# ---------------------------------------------------------------------------
# Spacing
# ---------------------------------------------------------------------------

HEADER_PAD  = 8     # 제목 위 padding (points)
FOOTER_PAD  = 0.03  # fig.text y 오프셋 (figure fraction)

# ---------------------------------------------------------------------------
# Guard: 금지된 색상 목록 (정적 검사용)
# ---------------------------------------------------------------------------

_FORBIDDEN_COLORS: tuple[str, ...] = (
    "#FFFFFF",  # pure white
    "#ffffff",
    "#F3F4F6",  # cool gray (Tailwind gray-100)
    "#f3f4f6",
    "#1a1a2e",  # 구 다크 배경 (이제 사용 안 함)
    "#16213e",  # 구 다크 패널
)

# accent color 집합 — 단일 accent 준수 여부 검사용
_ACCENT_COLORS: tuple[str, ...] = (INK_BLUE,)


def validate_tokens() -> list[str]:
    """토큰 유효성 검사. 위반 메시지 목록 반환 (비어 있으면 PASS)."""
    errors: list[str] = []
    all_bg = (CANVAS_PARCHMENT, SURFACE_IVORY, WARM_SAND, WARM_SAND_LIGHT)
    for color in all_bg:
        if color.upper() in (f.upper() for f in _FORBIDDEN_COLORS):
            errors.append(f"Forbidden color used as background: {color}")
        if not color.startswith("#") or len(color) not in (4, 7):
            errors.append(f"Invalid hex format: {color}")
    if len(_ACCENT_COLORS) != 1:
        errors.append(f"Accent color count must be 1, got {len(_ACCENT_COLORS)}")
    return errors
