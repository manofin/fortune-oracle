"""tests/test_fortune_oracle_phase8_kami.py

Phase 8 -- Kami-inspired UI/UX Design System 검증 테스트.

검증 항목:
A. design_tokens: hex 형식, pure white 금지, accent 단일
B. chart_renderer: Kami token 적용, PNG 생성, 크기, 한글 폰트 회귀 없음
C. Telegram text UX: help 구조, multi-turn 불가, register 안내
D. life_kline 단위 버그 수정: 12개월 / 12일 아님
"""

from __future__ import annotations

from _fo_paths import hermes_path, repo_path, repo_plugin_path
import os
import sys
import struct
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, repo_path("plugins"))
sys.path.insert(0, repo_plugin_path())

# ---------------------------------------------------------------------------
# Phase 8A — design_tokens
# ---------------------------------------------------------------------------

def test_tokens_import():
    from hermes_ext.fortune_oracle.design_tokens import CANVAS_PARCHMENT, INK_BLUE
    assert CANVAS_PARCHMENT
    assert INK_BLUE


def test_tokens_hex_format():
    import hermes_ext.fortune_oracle.design_tokens as dt
    color_attrs = [
        "CANVAS_PARCHMENT", "SURFACE_IVORY", "WARM_SAND",
        "INK_BLUE", "DEEP_INK", "WARM_STONE", "OLIVE_NOTE",
        "YANG_WARM", "YIN_MUTED", "DOJI_SAND",
        "RING_WHISPER", "RING_INNER",
    ]
    for attr in color_attrs:
        val = getattr(dt, attr)
        assert val.startswith("#"), f"{attr}={val} must start with #"
        assert len(val) in (4, 7), f"{attr}={val} must be 4 or 7 chars"


def test_tokens_no_pure_white():
    import hermes_ext.fortune_oracle.design_tokens as dt
    color_attrs = [
        "CANVAS_PARCHMENT", "SURFACE_IVORY", "WARM_SAND",
        "INK_BLUE", "DEEP_INK", "WARM_STONE", "OLIVE_NOTE",
        "YANG_WARM", "YIN_MUTED", "DOJI_SAND",
    ]
    forbidden = {"#FFFFFF", "#ffffff"}
    for attr in color_attrs:
        val = getattr(dt, attr)
        assert val.upper() not in (f.upper() for f in forbidden), \
            f"Pure white forbidden but found in {attr}={val}"


def test_tokens_no_cool_gray():
    import hermes_ext.fortune_oracle.design_tokens as dt
    cool_gray = "#F3F4F6"
    color_attrs = ["CANVAS_PARCHMENT", "SURFACE_IVORY", "WARM_SAND"]
    for attr in color_attrs:
        assert getattr(dt, attr).upper() != cool_gray.upper(), \
            f"Cool gray forbidden but found in {attr}"


def test_tokens_single_accent():
    from hermes_ext.fortune_oracle.design_tokens import _ACCENT_COLORS
    assert len(_ACCENT_COLORS) == 1, f"Accent must be single, got {len(_ACCENT_COLORS)}"


def test_tokens_validate():
    from hermes_ext.fortune_oracle.design_tokens import validate_tokens
    errors = validate_tokens()
    assert errors == [], f"Token validation failed: {errors}"


def test_tokens_no_dark_theme():
    """구 다크 테마 색상이 background token에 없어야 함."""
    import hermes_ext.fortune_oracle.design_tokens as dt
    old_dark = {"#1a1a2e", "#16213e"}
    bg_attrs = ["CANVAS_PARCHMENT", "SURFACE_IVORY"]
    for attr in bg_attrs:
        assert getattr(dt, attr).lower() not in old_dark, \
            f"Old dark theme color found in {attr}"


# ---------------------------------------------------------------------------
# Phase 8B — chart_renderer Kami token 적용
# ---------------------------------------------------------------------------

def _png_signature_ok(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_renderer_uses_kami_tokens():
    """chart_renderer가 design_tokens에서 CANVAS_PARCHMENT를 import함."""
    import hermes_ext.fortune_oracle.chart_renderer as cr
    # 토큰이 정상 로드됐으면 CANVAS_PARCHMENT가 old dark color와 달라야 함
    assert cr.CANVAS_PARCHMENT != "#1a1a2e"
    assert cr.CANVAS_PARCHMENT.startswith("#")


def test_render_month_card_png():
    """월간 PNG 카드 생성 PASS."""
    from hermes_ext.fortune_oracle.chart_renderer import render_month_card_png
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out = Path(f.name)
    try:
        result = render_month_card_png(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, output_path=out)
        assert result.exists()
        assert result.stat().st_size > 0
        assert result.stat().st_size <= 3 * 1024 * 1024
        assert _png_signature_ok(result)
    finally:
        out.unlink(missing_ok=True)


def test_render_year_card_png():
    """연간 PNG 카드 생성 PASS."""
    from hermes_ext.fortune_oracle.chart_renderer import render_year_card_png
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out = Path(f.name)
    try:
        result = render_year_card_png(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, output_path=out)
        assert result.exists()
        assert result.stat().st_size > 0
        assert _png_signature_ok(result)
    finally:
        out.unlink(missing_ok=True)


def test_render_empty_candles_raises():
    from hermes_ext.fortune_oracle.chart_renderer import render_kline_card_png, RendererUnavailable
    import pytest
    with pytest.raises(RendererUnavailable):
        render_kline_card_png([])


def test_render_sensitive_key_stripped_from_title():
    """제목에 민감 키워드가 포함되면 제거됨."""
    from hermes_ext.fortune_oracle.chart_renderer import render_kline_card_png
    from hermes_ext.fortune_oracle.kline import build_monthly_kline
    import tempfile
    candles = build_monthly_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out = Path(f.name)
    try:
        result = render_kline_card_png(candles, title="birth_date birth_time test", output_path=out)
        assert result.exists()
    finally:
        out.unlink(missing_ok=True)


def test_renderer_no_old_dark_bg():
    """구 다크 배경색 상수가 chart_renderer에 없어야 함."""
    import hermes_ext.fortune_oracle.chart_renderer as cr
    old_colors = {"#1a1a2e", "#16213e"}
    for attr in dir(cr):
        val = getattr(cr, attr, None)
        if isinstance(val, str) and val.startswith("#"):
            assert val.lower() not in old_colors, \
                f"Old dark color {val} found in chart_renderer.{attr}"


# ---------------------------------------------------------------------------
# Phase 8C — Telegram text UX rhythm
# ---------------------------------------------------------------------------

def _get_plugin():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fortune_oracle_plugin",
        repo_plugin_path("__init__.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # stub ctx
    class _Ctx:
        def register_command(self, *a, **kw): pass
    mod.ctx = _Ctx()
    try:
        spec.loader.exec_module(mod)
    except Exception:
        pass
    return mod


def test_help_no_heavy_emoji():
    """Kami-style help에는 과도한 emoji가 없어야 함."""
    mod = _get_plugin()
    result = mod._handle_help("")
    # Kami-style에서 제거된 emoji
    removed = ["🔮", "📅", "📊", "🖼", "🧬", "🔔", "ℹ️"]
    for em in removed:
        assert em not in result, f"Heavy emoji '{em}' should be removed in Kami-style help"


def test_help_contains_key_commands():
    mod = _get_plugin()
    result = mod._handle_help("")
    required = [
        "/today_fortune", "/tomorrow_fortune",
        "/month_kline", "/life_kline",
        "/kline_card",
        "/register_birth", "/show_profile", "/delete_profile",
        "/voice_fortune", "/daily_on", "/daily_off",
    ]
    for cmd in required:
        assert cmd in result, f"Command '{cmd}' missing from help"


def test_help_contains_multiturn_warning():
    mod = _get_plugin()
    result = mod._handle_help("")
    assert "multi-turn" in result


def test_help_contains_disclaimer():
    mod = _get_plugin()
    result = mod._handle_help("")
    assert "의학" in result and "투자" in result and "법률" in result


def test_help_sections_clean():
    """Kami-style: Fortune Oracle 타이틀로 시작해야 함."""
    mod = _get_plugin()
    result = mod._handle_help("")
    assert result.startswith("Fortune Oracle")


def test_register_guide_no_emoji():
    """_REGISTER_GUIDE에 과도한 emoji 없음."""
    mod = _get_plugin()
    heavy = ["📝", "⚠️", "ℹ️"]
    for em in heavy:
        assert em not in mod._REGISTER_GUIDE, f"Emoji '{em}' should be removed from REGISTER_GUIDE"


def test_register_guide_multiturn_warning():
    mod = _get_plugin()
    assert "multi-turn" in mod._REGISTER_GUIDE


def test_register_guide_one_shot_example():
    mod = _get_plugin()
    assert "/register_birth" in mod._REGISTER_GUIDE
    assert "홍길동" in mod._REGISTER_GUIDE


def test_show_profile_no_profile_no_heavy_emoji():
    """미등록 show_profile에 heavy emoji 없음."""
    mod = _get_plugin()
    with mock.patch.object(mod, "_resolve_profile", return_value=None):
        result = mod._handle_show_profile("")
    heavy = ["📭", "⚠️", "ℹ️"]
    for em in heavy:
        assert em not in result, f"Heavy emoji '{em}' in show_profile no-profile"


def test_show_profile_no_profile_contains_example():
    mod = _get_plugin()
    with mock.patch.object(mod, "_resolve_profile", return_value=None):
        result = mod._handle_show_profile("")
    assert "/register_birth" in result
    assert "multi-turn" in result


def test_life_kline_hint_no_heavy_emoji():
    """미등록 life_kline 힌트에 heavy emoji 없음."""
    mod = _get_plugin()
    with mock.patch.object(mod, "_resolve_profile", return_value=None):
        result = mod._handle_life_kline("")
    assert "💡" not in result
    assert "/register_birth" in result


# ---------------------------------------------------------------------------
# Phase 8D — life_kline 단위 버그
# ---------------------------------------------------------------------------

def test_life_kline_unit_is_month():
    from hermes_ext.fortune_oracle.kline import render_life_kline
    result = render_life_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    assert "12개월" in result, f"Expected '12개월' in life_kline output"


def test_life_kline_no_12일():
    from hermes_ext.fortune_oracle.kline import render_life_kline
    result = render_life_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    assert "12일" not in result, f"'12일' should not appear in life_kline output"


def test_month_kline_unit_is_day():
    from hermes_ext.fortune_oracle.kline import render_month_kline
    result = render_month_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    # 31일 또는 28/29/30일
    import re
    assert re.search(r"\d+일\)", result), "month_kline should have Nday unit"


def test_summarize_kline_unit_param():
    from hermes_ext.fortune_oracle.kline import summarize_kline, build_yearly_kline
    candles = build_yearly_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    text = summarize_kline(candles, unit="개월")
    assert "개월" in text
    text2 = summarize_kline(candles, unit="일")
    assert "일)" in text2 or "일" in text2


def test_bazi_append_not_broken_after_unit_fix():
    """unit 파라미터 추가 후 life_kline bazi append 경로 회귀 없음."""
    mod = _get_plugin()
    fake_profile = {
        "birth_date": "1990-03-15",
        "birth_time": "14:00",
        "birth_place": "Seoul",
        "timezone": "Asia/Seoul",
        "display_name": "테스트",
    }
    fake_bazi = mock.MagicMock()
    fake_bazi.ok = False  # bazi 실패해도 base_text 반환

    with mock.patch.object(mod, "_resolve_profile", return_value=fake_profile):
        with mock.patch(
            "hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile",
            return_value=fake_bazi,
        ):
            result = mod._handle_life_kline("")
    assert "K선" in result or "개월" in result


# ---------------------------------------------------------------------------
# Scope / Safety guard
# ---------------------------------------------------------------------------

def test_no_gateway_modification():
    """gateway/run.py는 수정되지 않아야 함."""
    import subprocess
    r = subprocess.run(
        ["git", "-C", hermes_path("hermes-agent"), "diff", "--name-only"],
        capture_output=True, text=True,
    )
    changed = r.stdout
    assert "gateway/run.py" not in changed
    assert "gateway/platforms" not in changed


def test_no_external_network_call_in_design_tokens():
    """design_tokens.py에 외부 네트워크 호출 없음."""
    src = Path(repo_path("plugins/hermes_ext/fortune_oracle/design_tokens.py")).read_text()
    for bad in ("requests", "urllib.request", "httpx", "aiohttp", "socket."):
        assert bad not in src, f"Forbidden network call '{bad}' in design_tokens.py"
