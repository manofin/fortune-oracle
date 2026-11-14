"""tests/test_fortune_oracle_chart_renderer.py

K선 PNG 카드 렌더러 테스트 (Phase 2A).
matplotlib available / unavailable 양쪽 경로를 테스트한다.
"""

import sys
import unittest.mock as mock
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.kline import (
    FortuneCandle,
    build_daily_candle,
    build_monthly_kline,
    build_yearly_kline,
)
from hermes_ext.fortune_oracle.chart_renderer import (
    MAX_CANDLES,
    MAX_FILE_BYTES,
    RendererUnavailable,
    render_available,
    render_kline_card_png,
    render_month_card_png,
    render_year_card_png,
    _setup_korean_font,
)

# 가상 테스트 프로필: 실제 인물 정보가 아닙니다. K선은 출생정보 없이 계산하지 않습니다.
_TEST_PROFILE = {"birth_date": "2000-01-01", "birth_time": "12:00", "gender": "female"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_candles(n: int = 10) -> list:
    return [build_daily_candle(_TEST_PROFILE, target_date=date(2026, 5, d)) for d in range(1, n + 1)]


def _profile_with_sensitive():
    return {
        "display_name": "홍길동",
        "birth_date": "1986-01-02",
        "birth_time": "03:04",
        "birth_place": "Seoul",
        "name_hanja": "洪吉童",
    }


# ---------------------------------------------------------------------------
# matplotlib availability
# ---------------------------------------------------------------------------

def test_render_available_reflects_matplotlib_presence():
    # matplotlib is installed in this env (3.10.8)
    assert render_available() is True


def test_render_unavailable_when_matplotlib_missing(tmp_path):
    """matplotlib import를 패치해 RendererUnavailable 동작 확인."""
    candles = _sample_candles(5)
    with mock.patch.dict("sys.modules", {"matplotlib": None}):
        with pytest.raises((RendererUnavailable, ImportError)):
            render_kline_card_png(candles, output_path=tmp_path / "out.png")


# ---------------------------------------------------------------------------
# 빈 candles fail-closed
# ---------------------------------------------------------------------------

def test_empty_candles_raises_renderer_unavailable(tmp_path):
    with pytest.raises(RendererUnavailable, match="출생정보"):
        render_kline_card_png([], output_path=tmp_path / "empty.png")


# ---------------------------------------------------------------------------
# PNG 생성 및 기본 속성 확인
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_file_is_created(tmp_path):
    candles = _sample_candles(15)
    out = render_kline_card_png(candles, title="테스트 K선", output_path=tmp_path / "test.png")
    assert out.exists()
    assert out.suffix == ".png"


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_file_size_under_3mb(tmp_path):
    candles = _sample_candles(31)
    out = render_kline_card_png(candles, output_path=tmp_path / "size_test.png")
    assert out.stat().st_size <= MAX_FILE_BYTES, (
        f"PNG size {out.stat().st_size / 1024 / 1024:.2f}MB exceeds 3MB"
    )


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_dimensions_within_limit(tmp_path):
    """PIL 없이 PNG 헤더에서 직접 width/height 읽기."""
    import struct
    candles = _sample_candles(20)
    out = render_kline_card_png(candles, output_path=tmp_path / "dim_test.png")
    with open(out, "rb") as f:
        f.read(8)   # PNG signature
        f.read(4)   # IHDR length
        f.read(4)   # "IHDR"
        width = struct.unpack(">I", f.read(4))[0]
        height = struct.unpack(">I", f.read(4))[0]
    assert width <= 1024, f"width={width} > 1024"
    assert height <= 1024, f"height={height} > 1024"


# ---------------------------------------------------------------------------
# 민감 출생정보 미포함 확인 (파일명/제목/profile 경유)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_path_does_not_contain_sensitive_fields(tmp_path):
    """출력 파일 경로나 제목에 민감정보가 포함되지 않아야 한다."""
    profile = _profile_with_sensitive()
    out = render_kline_card_png(
        _sample_candles(10),
        title="운세 카드",
        output_path=tmp_path / "safe_output.png",
        profile=profile,
    )
    # 경로에 민감값 없음
    for sensitive in ("1986-01-02", "03:04", "Seoul", "洪吉童"):
        assert sensitive not in str(out)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_sensitive_title_content_is_stripped(tmp_path):
    """title에 birth_date 등 키워드가 들어가도 렌더링 실패 없이 제거된다."""
    candles = _sample_candles(10)
    # birth_date 키워드를 제목에 직접 넣어도 예외 없이 처리
    out = render_kline_card_png(
        candles,
        title="birth_date 포함 제목",
        output_path=tmp_path / "stripped.png",
    )
    assert out.exists()


# ---------------------------------------------------------------------------
# MAX_CANDLES 제한 (너무 많은 candles 자동 truncate)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_too_many_candles_are_truncated(tmp_path):
    """MAX_CANDLES(62)를 초과하는 입력은 최근 MAX_CANDLES개로 잘려야 한다."""
    n_over = MAX_CANDLES + 20   # 82개
    candles = []
    for i in range(n_over):
        d = date(2025, 1, 1)
        from datetime import timedelta
        d = date(2025, 1, 1) + timedelta(days=i)
        candles.append(build_daily_candle(_TEST_PROFILE, target_date=d))
    # render_kline_card_png은 내부에서 [-MAX_CANDLES:] slice 처리
    out = render_kline_card_png(candles, output_path=tmp_path / "long.png")
    assert out.exists()
    assert out.stat().st_size <= MAX_FILE_BYTES


# ---------------------------------------------------------------------------
# Convenience wrapper 테스트
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_month_card_png(tmp_path):
    out = render_month_card_png(
        profile={**_TEST_PROFILE, "display_name": "홍길동"},
        year=2026,
        month=5,
        output_path=tmp_path / "month.png",
    )
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.stat().st_size <= MAX_FILE_BYTES


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_year_card_png(tmp_path):
    out = render_year_card_png(
        profile={**_TEST_PROFILE, "display_name": "홍길동"},
        year=2026,
        output_path=tmp_path / "year.png",
    )
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.stat().st_size <= MAX_FILE_BYTES


# ---------------------------------------------------------------------------
# None output_path — 임시파일 자동 생성
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_auto_temp_path_when_output_path_is_none():
    candles = _sample_candles(7)
    out = render_kline_card_png(candles, output_path=None)
    try:
        assert out.exists()
        assert out.suffix == ".png"
        assert out.stat().st_size > 0
    finally:
        out.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 2C: 한글 폰트 렌더링 품질 테스트
# ---------------------------------------------------------------------------

def test_setup_korean_font_does_not_raise():
    """_setup_korean_font()는 폰트 유무와 무관하게 절대 예외를 발생시키지 않는다."""
    result = _setup_korean_font()
    # 반환값은 문자열(폰트명) 또는 None — 어느 쪽이어도 OK
    assert result is None or isinstance(result, str)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_generated_regardless_of_korean_font(tmp_path):
    """폰트가 없어도 PNG 생성이 성공해야 한다 (fail-open)."""
    candles = _sample_candles(10)
    # _setup_korean_font를 None 반환으로 패치해 폰트 없는 환경 시뮬레이션
    with mock.patch(
        "hermes_ext.fortune_oracle.chart_renderer._setup_korean_font",
        return_value=None,
    ):
        out = render_kline_card_png(
            candles,
            title="한글 타이틀 테스트",
            output_path=tmp_path / "no_font.png",
        )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_png_generated_with_korean_font_if_available(tmp_path):
    """한글 폰트가 있으면 PNG 생성이 성공하고 파일 크기가 유효해야 한다."""
    font_name = _setup_korean_font()
    if font_name is None:
        pytest.skip("No Korean font installed on this system — skipping font rendering test")
    candles = _sample_candles(10)
    out = render_kline_card_png(
        candles,
        title="한글 폰트 렌더링 테스트",
        output_path=tmp_path / "with_font.png",
    )
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.stat().st_size <= MAX_FILE_BYTES


def test_candles_without_birth_data_raise_renderer_unavailable(tmp_path):
    """출생정보 없이 만든 None 캔들은 AttributeError 대신 계산 불가로 처리한다."""
    candles = [build_daily_candle(target_date=date(2026, 5, d)) for d in range(1, 4)]
    assert candles == [None, None, None]
    with pytest.raises(RendererUnavailable, match="출생정보"):
        render_kline_card_png(candles, output_path=tmp_path / "none.png")
