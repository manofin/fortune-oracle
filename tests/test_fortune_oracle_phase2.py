"""tests/test_fortune_oracle_phase2.py

Fortune Oracle Phase 2 — /kline_card PNG 이미지 카드 생성 검증.

요구사항 7개 항목 직접 검증:
1. /kline_card 호출 시 plugin handler 응답 (unknown/unrecognized 아님)
2. PNG 파일 생성 성공
3. 파일 크기 > 0
4. PNG 시그니처 검증 (\\x89PNG\\r\\n\\x1a\\n)
5. 이미지 생성 실패 시 텍스트 fallback 동작
6. 한글 제목/캡션 처리 검증
7. 텔레그램 응답 포맷 검증 (MEDIA: + 캡션)

운세는 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

from _fo_paths import repo_plugin_path
import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.chart_renderer import render_available
from hermes_ext.fortune_oracle.core import render_kline_card

# 가상 테스트 프로필: 실제 인물 정보가 아닙니다. K선은 출생정보 없이 계산하지 않습니다.
_TEST_PROFILE = {"birth_date": "2000-01-01", "birth_time": "12:00", "gender": "female"}

# ---------------------------------------------------------------------------
# 요구사항 1: /kline_card plugin handler 응답 (dispatch 경로)
# ---------------------------------------------------------------------------

@pytest.fixture
def registered_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("FORTUNE_ORACLE_STORE", str(tmp_path / "store.json"))
    monkeypatch.delenv("FORTUNE_ORACLE_PROFILE", raising=False)
    monkeypatch.delenv("FORTUNE_ORACLE_USER", raising=False)
    spec = importlib.util.spec_from_file_location("fo_card_test", repo_plugin_path("__init__.py"))
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    commands = {}
    class Context:
        def register_command(self, name, *, handler, description=""):
            commands[name] = handler
    plugin.register(Context())
    return commands


def test_kline_card_plugin_handler_registered(registered_commands):
    """Test repository registration without discovering installed plugins."""
    assert "kline-card" in registered_commands


def test_kline_card_plugin_handler_returns_non_empty(registered_commands):
    """handler가 호출됐을 때 비어있지 않은 문자열을 반환해야 한다."""
    result: str = ""
    try:
        result = registered_commands["kline-card"]("")
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        # 생성된 PNG 정리
        if result and result.startswith("MEDIA:"):
            png_path = result.split("\n")[0][len("MEDIA:"):].strip()
            Path(png_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 요구사항 2~3: PNG 파일 생성 성공 및 크기 > 0
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_png_file_created():
    """render_kline_card가 실제 PNG 파일을 생성한다."""
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    try:
        assert png_path.exists(), f"PNG not created: {png_path}"
        assert png_path.stat().st_size > 0, "PNG file is empty"
    finally:
        png_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 요구사항 4: PNG 시그니처 검증
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_png_signature():
    """생성된 파일이 올바른 PNG 시그니처(\\x89PNG...)를 가진다."""
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    try:
        header = png_path.read_bytes()[:8]
        assert header == PNG_SIGNATURE, f"Not a valid PNG: first 8 bytes = {header!r}"
    finally:
        png_path.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_png_signature_year_period():
    """연간 카드도 유효한 PNG 시그니처를 가진다."""
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
    result = render_kline_card(profile=_TEST_PROFILE, period="year", year=2026)
    assert result.startswith("MEDIA:")
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    try:
        header = png_path.read_bytes()[:8]
        assert header == PNG_SIGNATURE
    finally:
        png_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 요구사항 5: 이미지 생성 실패 시 텍스트 fallback
# ---------------------------------------------------------------------------

def test_phase2_fallback_on_renderer_failure():
    """render_month_card_png 예외 → MEDIA: 없는 텍스트 fallback."""
    with mock.patch(
        "hermes_ext.fortune_oracle.chart_renderer.render_month_card_png",
        side_effect=RuntimeError("simulated renderer crash"),
    ):
        result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert not result.startswith("MEDIA:"), (
        f"Expected text fallback, got MEDIA: tag: {result[:80]}"
    )
    assert len(result) > 0, "Fallback must not be empty"


def test_phase2_fallback_is_informative():
    """fallback 텍스트는 비어있지 않고 사용자가 읽을 수 있는 내용이어야 한다."""
    with mock.patch(
        "hermes_ext.fortune_oracle.chart_renderer.render_month_card_png",
        side_effect=RuntimeError("simulated crash"),
    ):
        result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert not result.startswith("MEDIA:")
    # 최소 20자 이상의 유의미한 fallback
    assert len(result) >= 20, f"Fallback too short: {result!r}"


# ---------------------------------------------------------------------------
# 요구사항 6: 한글 캡션 처리 검증
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_korean_caption_in_response():
    """MEDIA: 응답에 한글 캡션이 포함되어야 한다."""
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    # 응답 전체에 한글이 있어야 함
    has_korean = any("\uac00" <= ch <= "\ud7a3" for ch in result)
    assert has_korean, f"No Korean characters found in response: {result!r}"
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    png_path.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_korean_display_name_in_caption():
    """display_name이 한글이면 캡션에 포함된다."""
    result = render_kline_card(
        profile={**_TEST_PROFILE, "display_name": "홍길동"},
        period="month",
    )
    assert result.startswith("MEDIA:")
    assert "홍길동" in result, f"display_name not found in caption: {result!r}"
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    png_path.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_disclaimer_in_korean():
    """고지 문구(오락/자기성찰용)가 캡션에 포함된다."""
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert "오락" in result or "자기성찰" in result, (
        f"Disclaimer not found in: {result!r}"
    )
    png_path = Path(result.split("\n")[0][len("MEDIA:"):].strip())
    png_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 요구사항 7: 텔레그램 응답 포맷 검증
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_media_tag_format():
    """MEDIA: 태그 형식이 gateway 전송 규격에 맞아야 한다."""
    import re
    # gateway/platforms/base.py 패턴
    MEDIA_RE = re.compile(
        r"MEDIA:\s*(?P<path>(?:~/|/)\S+\.png)"
    )
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    first_line = result.split("\n")[0]
    m = MEDIA_RE.match(first_line)
    png_path = Path(m.group("path")) if m else None
    try:
        assert m is not None, f"MEDIA: format invalid: {first_line!r}"
        assert png_path and png_path.exists()
    finally:
        if png_path:
            png_path.unlink(missing_ok=True)


@pytest.mark.skipif(not render_available(), reason="matplotlib not installed")
def test_phase2_response_has_caption_after_media():
    """MEDIA: 첫 줄 다음에 caption이 이어져야 한다."""
    result = render_kline_card(profile=_TEST_PROFILE, period="month")
    assert result.startswith("MEDIA:")
    lines = result.split("\n")
    assert len(lines) >= 2, f"No caption after MEDIA tag: {result!r}"
    caption = "\n".join(lines[1:]).strip()
    assert len(caption) > 0, "Caption is empty"
    png_path = Path(lines[0][len("MEDIA:"):].strip())
    png_path.unlink(missing_ok=True)
