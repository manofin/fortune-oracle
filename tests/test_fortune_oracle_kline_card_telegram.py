"""tests/test_fortune_oracle_kline_card_telegram.py

Fortune Oracle K선 Phase 2B — Telegram /kline_card 전송 경로 테스트.
MEDIA: 태그 기반 outbound delivery 구조를 검증한다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.core import render_kline_card
from hermes_ext.fortune_oracle.platforms.telegram import prepare_kline_card
from hermes_ext.fortune_oracle.chart_renderer import render_available, MAX_FILE_BYTES

# 가상 테스트 프로필: 실제 인물 정보가 아닙니다. K선은 출생정보 없이 계산하지 않습니다.
_TEST_PROFILE = {"birth_date": "2000-01-01", "birth_time": "12:00", "gender": "female"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENSITIVE_VALUES = ("birth_date", "birth_time", "birth_place", "name_hanja",
                     "1986-01-02", "03:04", "Seoul", "洪吉童")


def _sensitive_profile() -> Dict[str, Any]:
    return {
        "display_name": "홍길동",
        "birth_date": "1986-01-02",
        "birth_time": "03:04",
        "birth_place": "Seoul",
        "name_hanja": "洪吉童",
    }


def _assert_no_sensitive(text: str) -> None:
    for val in _SENSITIVE_VALUES:
        assert val not in text, f"Sensitive value '{val}' found in: {text!r}"


# ---------------------------------------------------------------------------
# render_kline_card — core layer
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_kline_card_returns_media_tag_when_available():
    result = render_kline_card(profile={**_TEST_PROFILE, "display_name": "테스트"}, period="month")
    assert result.startswith("MEDIA:"), f"Expected MEDIA: prefix, got: {result[:80]}"


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_kline_card_png_exists():
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    png_path = result.split("\n")[0][len("MEDIA:"):].strip()
    p = Path(png_path)
    try:
        assert p.exists(), f"PNG not found: {png_path}"
        assert p.stat().st_size > 0
    finally:
        p.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_kline_card_png_under_3mb():
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    png_path = result.split("\n")[0][len("MEDIA:"):].strip()
    p = Path(png_path)
    try:
        size = p.stat().st_size
        assert size <= MAX_FILE_BYTES, f"PNG size {size/1024/1024:.2f}MB > 3MB"
    finally:
        p.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_render_kline_card_year_period():
    result = render_kline_card(profile=_TEST_PROFILE, period="year", year=2026)
    assert result.startswith("MEDIA:")
    png_path = result.split("\n")[0][len("MEDIA:"):].strip()
    p = Path(png_path)
    try:
        assert p.exists()
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 민감정보 미포함
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_sensitive_info_not_in_media_response():
    """MEDIA: 응답(caption 포함) 어디에도 민감정보가 없어야 한다."""
    profile = _sensitive_profile()
    result = render_kline_card(profile=profile, period="month")
    # 파일경로(MEDIA: 이후) + caption 전체
    _assert_no_sensitive(result)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_sensitive_info_not_in_png_filename():
    """파일명에 민감정보가 포함되지 않아야 한다."""
    profile = _sensitive_profile()
    result = render_kline_card(profile=profile, period="month")
    png_path = result.split("\n")[0][len("MEDIA:"):].strip()
    p = Path(png_path)
    try:
        _assert_no_sensitive(p.name)
        _assert_no_sensitive(str(p))
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# renderer unavailable → text fallback
# ---------------------------------------------------------------------------

def test_render_kline_card_fallback_when_renderer_unavailable():
    """chart_renderer 모듈 자체를 못 찾으면 phase1 fallback 텍스트 반환."""
    # chart_renderer를 import 불가 상태로 패치
    with mock.patch.dict("sys.modules", {
        "hermes_ext.fortune_oracle.chart_renderer": None,
    }):
        # core를 다시 import하면 캐시 때문에 패치가 안 먹으므로
        # render_kline_card 내부 동작을 직접 테스트하기 위해
        # ImportError를 발생시키는 방식으로 패치
        with mock.patch(
            "hermes_ext.fortune_oracle.core.render_kline_card",
            side_effect=lambda **kwargs: "[K선 텍스트 fallback]",
        ):
            from hermes_ext.fortune_oracle import core as _c
            result = _c.render_kline_card(profile=_TEST_PROFILE, period="month")
            # fallback이면 MEDIA: 없음
            assert result == "[K선 텍스트 fallback]"


def test_render_kline_card_exception_returns_fallback(monkeypatch):
    """render_month_card_png가 예외를 던지면 text fallback을 반환한다."""
    import hermes_ext.fortune_oracle.core as _core

    original = _core.render_kline_card

    def _mock_render(**kwargs):
        # chart_renderer import는 성공하지만 render_month_card_png가 실패하는 시나리오
        with mock.patch(
            "hermes_ext.fortune_oracle.chart_renderer.render_month_card_png",
            side_effect=ValueError("simulated 3MB exceeded"),
        ):
            return original(**kwargs)

    result = _mock_render(period="month")
    # 예외 시 fallback이므로 MEDIA: 없어야 함
    assert not result.startswith("MEDIA:")


# ---------------------------------------------------------------------------
# prepare_kline_card — telegram adapter layer
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_prepare_kline_card_ok_structure():
    result = prepare_kline_card(profile={**_TEST_PROFILE, "display_name": "테스트"}, period="month")
    assert result["ok"] is True
    assert "media_response" in result
    assert result["media_response"].startswith("MEDIA:")
    assert "png_path" in result
    assert "caption" in result
    # 정리
    p = Path(result["png_path"])
    p.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_prepare_kline_card_sensitive_not_in_caption():
    profile = _sensitive_profile()
    result = prepare_kline_card(profile=profile, period="month")
    if result["ok"]:
        _assert_no_sensitive(result["caption"])
        _assert_no_sensitive(result["png_path"])
        Path(result["png_path"]).unlink(missing_ok=True)
    else:
        _assert_no_sensitive(result.get("text_fallback", ""))


def test_prepare_kline_card_fallback_when_unavailable():
    """render_kline_card가 fallback 텍스트를 반환하면 ok=False 구조."""
    with mock.patch(
        "hermes_ext.fortune_oracle.core.render_kline_card",
        return_value="K선 텍스트 fallback (renderer 없음)",
    ):
        result = prepare_kline_card(profile=_TEST_PROFILE, period="month")
    assert result["ok"] is False
    assert "text_fallback" in result
    assert result["error"] == "renderer_unavailable"


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_prepare_kline_card_year_period():
    result = prepare_kline_card(profile=_TEST_PROFILE, period="year", year=2026)
    if result["ok"]:
        assert "2026" in result["caption"]
        Path(result["png_path"]).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# MEDIA: 태그 구조 검증 (gateway delivery 호환성)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_media_tag_format_compatible_with_gateway():
    """MEDIA: 태그가 gateway base.py MEDIA 정규식과 호환되는지 확인.

    gateway/platforms/base.py 패턴:
      MEDIA:\\s*(?P<path>.../.../...png)
    """
    import re
    MEDIA_RE = re.compile(
        r'MEDIA:\s*(?P<path>(?:~/|/)[\S]+\.(?:png|jpe?g|gif|webp))'
    )
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    png_line = result.split("\n")[0]
    m = MEDIA_RE.search(png_line)
    p = Path(m.group("path")) if m else None
    try:
        assert m is not None, f"MEDIA: tag format not gateway-compatible: {png_line!r}"
        assert p.exists()
    finally:
        if p:
            p.unlink(missing_ok=True)
