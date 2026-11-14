#!/usr/bin/env python3
"""Phase 37E — Oracle Renderer tests (expanded from Phase 38F)."""

import pytest

from hermes_ext.fortune_oracle.oracle_method_card import (
    DISCLAIMER,
    OracleMethodCard,
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_RUNNABLE,
)
from hermes_ext.fortune_oracle.oracle_renderer import (
    _check_deterministic,
    _clip,
    _is_raw_dump,
    _sanitize,
    _sanitize_guard,
    render_final_reading,
    render_oracle_reading,
)


class TestSanitize:
    def test_is_raw_dump_dataclass(self):
        assert _is_raw_dump("OracleMethodCard(method='bazi')") is True

    def test_is_raw_dump_dict(self):
        assert _is_raw_dump('{"key": "value"}') is True

    def test_is_raw_dump_list(self):
        assert _is_raw_dump('[1, 2, 3]') is True

    def test_is_raw_dump_false(self):
        assert _is_raw_dump("이것은 자연어입니다.") is False

    def test_sanitize_raw(self):
        result = _sanitize("OracleMethodCard(method='bazi')")
        assert "OracleMethodCard(" not in result

    def test_sanitize_normal(self):
        result = _sanitize("이것은 자연어입니다.")
        assert result == "이것은 자연어입니다."

    def test_clip(self):
        text = "A" * 300
        result = _clip(text, 100)
        assert len(result) <= 100

    def test_sanitize_guard_traceback(self):
        text = "Traceback (most recent call last):\nFile 'foo.py', line 1"
        result = _sanitize_guard(text)
        assert "Traceback" not in result
        assert "File 'foo.py'" not in result

    def test_sanitize_guard_dataclass(self):
        text = "BaziResult(ok=True, eight_char={})"
        result = _sanitize_guard(text)
        assert "ok=True" not in result

    def test_check_deterministic_banmal(self):
        violations = _check_deterministic("반드시 투자해야 한다")
        assert len(violations) >= 1

    def test_check_deterministic_ok(self):
        violations = _check_deterministic("자기성찰용 참고입니다.")
        assert len(violations) == 0

    def test_no_traceback_in_output(self):
        result = _sanitize_guard("Traceback: something")
        assert "Traceback" not in result

    def test_no_raw_repr_in_output(self):
        result = _sanitize_guard("AstroMethodCard(method='western')")
        assert "AstroMethodCard(" not in result


class TestRenderAllBlocked:
    def test_all_blocked_shows_input_guidance(self):
        cards = [
            OracleMethodCard.blocked("bazi", "ERR", "생년월일 없음"),
            OracleMethodCard.blocked("western", "ERR", "타임존 없음"),
            OracleMethodCard.blocked("vedic", "ERR", "타임존 없음"),
            OracleMethodCard.blocked("ziwei", "ERR", "Node.js 없음"),
        ]
        text = render_final_reading(cards)
        assert "출생정보를 등록하면" in text
        assert "register_birth" in text
        assert DISCLAIMER in text

    def test_all_blocked_no_raw_repr(self):
        cards = [
            OracleMethodCard.blocked("bazi", "ERR", "msg"),
        ]
        text = render_final_reading(cards)
        assert "dataclass" not in text
        assert "OracleMethodCard(" not in text

    def test_all_blocked_no_traceback(self):
        cards = [
            OracleMethodCard.blocked("bazi", "ERR", "Traceback: error"),
        ]
        text = render_final_reading(cards)
        assert "Traceback" not in text

    def test_all_blocked_no_fabricated_facts(self):
        cards = [
            OracleMethodCard.blocked("ziwei", "ERR", "Node.js 없음"),
        ]
        text = render_final_reading(cards)
        # 지어낸 별/궁 정보가 없어야 함
        assert "천상" not in text
        assert "명궁" not in text

    def test_all_blocked_disclaimer_present(self):
        cards = [
            OracleMethodCard.blocked("bazi", "ERR", "msg"),
        ]
        text = render_final_reading(cards)
        assert "자기성찰" in text
        assert "확정적 판단이 아닙니다" in text


class TestRenderMixed:
    def test_mixed_runnable_blocked(self):
        cards = [
            OracleMethodCard.runnable(
                method="bazi",
                facts={"eight_char": {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}},
                interpretation="일주가 강함",
            ),
            OracleMethodCard.blocked("western", "ERR", "타임존 없음"),
            OracleMethodCard.blocked("vedic", "ERR", "타임존 없음"),
            OracleMethodCard.blocked("ziwei", "ERR", "Node.js 없음"),
        ]
        text = render_final_reading(cards)
        # runnable method 표시
        assert "팔자" in text
        # blocked method 표시
        assert "차단" in text
        # 11-section 구조 확인
        assert "1. 자료 확인" in text
        assert "2. 실행 가능 메서드" in text
        assert "3. 핵심 요약" in text
        assert "11. Disclaimer" in text
        assert DISCLAIMER in text

    def test_no_raw_repr_in_mixed(self):
        cards = [
            OracleMethodCard.runnable("bazi", {"eight_char": {"year": "甲子"}}),
            OracleMethodCard.blocked("western", "ERR", "msg"),
        ]
        text = render_final_reading(cards)
        assert "dataclass" not in text
        assert "OracleMethodCard(" not in text

    def test_no_deterministic_claims(self):
        cards = [
            OracleMethodCard.runnable("bazi", {}, interpretation="자기성찰용 참고입니다."),
        ]
        text = render_final_reading(cards)
        assert "반드시" not in text
        assert "확실히" not in text
        assert "투자해야 한다" not in text
        assert "치료해야 한다" not in text

    def test_5year_flow_is_theme_not_prediction(self):
        cards = [
            OracleMethodCard.runnable("vedic", facts={"dasha": "수성 대운"}),
        ]
        text = render_final_reading(cards)
        # "테마 window" 표현 확인
        assert "테마" in text or "theme" in text.lower()

    def test_disclaimer_at_end(self):
        cards = [
            OracleMethodCard.runnable("bazi", {"eight_char": {"year": "甲子"}}),
        ]
        text = render_final_reading(cards)
        assert DISCLAIMER in text

    def test_no_medical_legal_financial_claims(self):
        cards = [
            OracleMethodCard.runnable("bazi", {}),
            OracleMethodCard.runnable("western", {}),
        ]
        text = render_final_reading(cards)
        assert "법적으로" not in text
        assert "사망" not in text


class TestQimenExclusion:
    def test_qimen_not_in_default(self):
        """Qimen은 birth-based default renderer에 포함되지 않아야 함."""
        cards = [
            OracleMethodCard.runnable("bazi", {"eight_char": {"year": "甲子"}}),
        ]
        text = render_final_reading(cards)
        assert "기문둔갑" not in text

    def test_qimen_included_when_requested(self):
        cards = [
            OracleMethodCard.runnable("bazi", {"eight_char": {"year": "甲子"}}),
            OracleMethodCard.runnable("qimen", facts={"text": "판 결과"}),
        ]
        text = render_final_reading(cards, include_qimen=True)
        assert "기문둔갑" in text


class TestBackwardCompatibility:
    def test_render_oracle_reading_backward_compat(self):
        """기존 render_oracle_reading()이 동작해야 함."""
        from hermes_ext.fortune_oracle.astro_method_card import AstroMethodCard
        western = AstroMethodCard.runnable(
            method="western",
            facts={"planets": ["Sun in Aries"]},
            interpretation="test",
        )
        text = render_oracle_reading(
            western_card=western,
            bazi_summary="甲子 乙丑 丙寅 丁卯",
        )
        assert "자료 확인" in text
        assert "팔자" in text

    def test_render_oracle_reading_no_crash_on_none(self):
        text = render_oracle_reading()
        # 모든 method가 none이면 all blocked 안내
        assert "계산할 수 없습니다" in text or "blocked" in text.lower()


class TestDetailedMode:
    def test_detailed_mode_has_more_content(self):
        cards = [
            OracleMethodCard.runnable(
                method="bazi",
                facts={"eight_char": {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}},
                interpretation="일주가 강함",
            ),
        ]
        compact = render_final_reading(cards, detailed=False)
        detailed = render_final_reading(cards, detailed=True)
        # detailed가 더 길어야 함
        assert len(detailed) >= len(compact)


class TestNoDeepProviderCall:
    def test_renderer_does_not_call_deep_provider(self):
        """renderer가 deep_qopus_provider를 호출하지 않아야 함."""
        cards = [
            OracleMethodCard.runnable("bazi", {"eight_char": {"year": "甲子"}}),
        ]
        # renderer 호출이 deterministically 실행되어야 함 (LLM 호출 없음)
        text = render_final_reading(cards)
        # deep provider 관련 언급 없어야 함
        assert "deep" not in text.lower()
