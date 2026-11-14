"""tests/test_fortune_oracle_kline.py

운세 K선 모듈 테스트.
life-kline 개념 참고 (miounet11/life-kline, Apache-2.0) — 표현 방식만 적용,
전체 앱/서버는 통합하지 않음.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle import oracle
from hermes_ext.fortune_oracle.kline import (
    FortuneCandle,
    build_daily_candle,
    build_monthly_kline,
    build_yearly_kline,
    summarize_kline,
    render_life_kline,
    render_month_kline,
    kline_card_phase1_fallback,
)
from hermes_ext.fortune_oracle.platforms import telegram


# ---------------------------------------------------------------------------
# 1. FortuneCandle 값 범위 0~100 테스트
# ---------------------------------------------------------------------------

def test_fortune_candle_values_in_range():
    candle = build_daily_candle(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, target_date=date(2026, 5, 25))
    for attr in ("open", "close", "high", "low"):
        val = getattr(candle, attr)
        assert 0.0 <= val <= 100.0, f"{attr}={val} out of range"


# ---------------------------------------------------------------------------
# 2. high >= max(open, close), low <= min(open, close) invariant 테스트
# ---------------------------------------------------------------------------

def test_fortune_candle_ohlc_invariant():
    for day in range(1, 32):
        try:
            d = date(2026, 5, day)
        except ValueError:
            break
        candle = build_daily_candle(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, target_date=d)
        assert candle.high >= max(candle.open, candle.close), (
            f"{d}: high={candle.high} < max(open={candle.open}, close={candle.close})"
        )
        assert candle.low <= min(candle.open, candle.close), (
            f"{d}: low={candle.low} > min(open={candle.open}, close={candle.close})"
        )


def test_fortune_candle_manual_invariant_enforcement():
    """생성자에 잘못된 값을 넣어도 invariant가 자동 교정되는지 확인."""
    c = FortuneCandle(
        date=date(2026, 1, 1),
        open=60.0,
        close=80.0,
        high=50.0,   # 잘못됨 — open/close보다 낮음
        low=90.0,    # 잘못됨 — open/close보다 높음
    )
    assert c.high >= max(c.open, c.close)
    assert c.low <= min(c.open, c.close)
    assert 0.0 <= c.high <= 100.0
    assert 0.0 <= c.low <= 100.0


# ---------------------------------------------------------------------------
# 3. daily fortune 5~8줄 정책 유지 테스트
# ---------------------------------------------------------------------------

def test_daily_fortune_still_5_to_8_lines_after_kline_addition():
    text = oracle.render_daily_fortune("today", profile={"display_name": "홍길동"})
    lines = [line for line in text.splitlines() if line.strip()]
    assert 5 <= len(lines) <= 8, f"line count={len(lines)}: {lines}"
    assert "태허" in text
    assert "오락" in text and "자기성찰" in text
    assert "**" not in text and "#" not in text and "```" not in text


# ---------------------------------------------------------------------------
# 4. Telegram /life_kline, /인생K선 alias parser 테스트
# ---------------------------------------------------------------------------

def test_telegram_kline_alias_parser():
    assert telegram.parse_command("/life_kline") == {
        "command": "life_kline", "args": "", "raw": "/life_kline"
    }
    assert telegram.parse_command("인생K선") == {
        "command": "life_kline", "args": "", "raw": "인생K선"
    }
    assert telegram.parse_command("/인생K선") == {
        "command": "life_kline", "args": "", "raw": "/인생K선"
    }
    assert telegram.parse_command("/year_kline") == {
        "command": "year_kline", "args": "", "raw": "/year_kline"
    }
    assert telegram.parse_command("/올해운세") == {
        "command": "year_kline", "args": "", "raw": "/올해운세"
    }
    assert telegram.parse_command("/month_kline") == {
        "command": "month_kline", "args": "", "raw": "/month_kline"
    }
    assert telegram.parse_command("/월간운세") == {
        "command": "month_kline", "args": "", "raw": "/월간운세"
    }
    assert telegram.parse_command("/운세차트") == {
        "command": "month_kline", "args": "", "raw": "/운세차트"
    }
    assert telegram.parse_command("/kline_card") == {
        "command": "kline_card", "args": "", "raw": "/kline_card"
    }


def test_telegram_kline_canonical_commands_are_bot_safe():
    expected_new = {"life_kline", "year_kline", "month_kline", "kline_card"}
    cmds = set(telegram.bot_command_names())
    assert expected_new.issubset(cmds)
    assert telegram.validate_canonical_bot_commands() is True


# ---------------------------------------------------------------------------
# 5. LINE text fallback 테스트
# ---------------------------------------------------------------------------

def test_line_kline_text_fallback_without_public_url():
    from hermes_ext.fortune_oracle.platforms.line import prepare_kline_text
    kline_text = render_month_kline(platform="line")
    result = prepare_kline_text(kline_text, public_url=None)
    assert result["ok"] is True
    assert result["image_fallback"] is True
    assert "Phase 2" in result["note"]
    # plain text — no markdown
    assert "**" not in result["text"]


def test_line_kline_text_no_fallback_with_public_url():
    from hermes_ext.fortune_oracle.platforms.line import prepare_kline_text
    kline_text = render_month_kline(platform="line")
    result = prepare_kline_text(kline_text, public_url="https://example.com")
    assert result["ok"] is True
    assert result["image_fallback"] is False


# ---------------------------------------------------------------------------
# 6. group/room redaction 테스트 — kline 출력에도 적용
# ---------------------------------------------------------------------------

def test_kline_output_does_not_contain_raw_birth_fields():
    profile = {
        "birth_date": "1986-01-02",
        "birth_time": "03:04",
        "birth_place": "Seoul",
        "name_hanja": "洪吉童",
        "display_name": "홍길동",
    }
    text = render_life_kline(profile, year=2026, platform="telegram")
    assert "1986-01-02" not in text
    assert "03:04" not in text
    assert "Seoul" not in text
    assert "洪吉童" not in text
    # display_name은 허용
    assert "홍길동" in text


def test_kline_summarize_includes_disclaimer():
    candles = build_monthly_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, year=2026, month=5)
    text = summarize_kline(candles)
    assert "오락" in text and "자기성찰" in text
    assert "의학" in text and "투자" in text and "법률" in text


# ---------------------------------------------------------------------------
# 7. /kline_card Phase 1 text fallback 테스트
# ---------------------------------------------------------------------------

def test_kline_card_phase1_returns_text_fallback():
    for platform in ("telegram", "line"):
        result = kline_card_phase1_fallback(platform)
        assert "Phase 2" in result
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 8. 기존 test_fortune_oracle.py 호환 — oracle facade로 kline 접근 가능
# ---------------------------------------------------------------------------

def test_oracle_exports_kline_symbols():
    assert hasattr(oracle, "FortuneCandle")
    assert hasattr(oracle, "build_daily_candle")
    assert hasattr(oracle, "build_monthly_kline")
    assert hasattr(oracle, "build_yearly_kline")
    assert hasattr(oracle, "summarize_kline")
    assert hasattr(oracle, "render_life_kline")
    assert hasattr(oracle, "render_month_kline")
    assert hasattr(oracle, "kline_card_phase1_fallback")
    assert hasattr(oracle, "get_daily_candle_score")


def test_get_daily_candle_score_in_range():
    score = oracle.get_daily_candle_score(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# 9-10. Hermes core runtime 미수정 확인 (기존과 동일)
# ---------------------------------------------------------------------------

def test_core_runtime_files_still_unmodified():
    forbidden = [
        Path("run_agent.py"),
        Path("gateway/run.py"),
        Path("gateway/config.py"),
        Path("gateway/platforms/__init__.py"),
        Path("hermes_cli/config.py"),
    ]
    changed = oracle.changed_core_runtime_files()
    assert not changed.intersection(set(forbidden))
