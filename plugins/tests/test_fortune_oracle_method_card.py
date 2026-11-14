#!/usr/bin/env python3
"""Phase 37C — Oracle Method Card tests."""

import pytest

from hermes_ext.fortune_oracle.oracle_method_card import (
    DISCLAIMER,
    ERR_CALCULATION_FAILED,
    ERR_DEPENDENCY_MISSING,
    ERR_INSUFFICIENT_BIRTH_DATA,
    METHOD_LABEL_KO,
    OracleMethodCard,
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_RUNNABLE,
)


class TestOracleMethodCardConstruction:
    def test_defaults(self):
        card = OracleMethodCard()
        assert card.method == ""
        assert card.label_ko == ""
        assert card.status == STATUS_BLOCKED
        assert card.facts == {}
        assert card.interpretation == ""
        assert card.confidence == 0.0
        assert card.blockers == []
        assert card.warnings == []
        assert card.precision_notes == []
        assert card.evidence == []
        assert card.disclaimer == DISCLAIMER

    def test_full(self):
        card = OracleMethodCard.runnable(
            method="bazi",
            facts={"pillar": "甲子"},
            interpretation="일주가 강함",
            confidence=0.9,
        )
        assert card.method == "bazi"
        assert card.label_ko == "팔자"
        assert card.status == STATUS_RUNNABLE
        assert card.confidence == 0.9

    def test_is_ok_runnable(self):
        card = OracleMethodCard.runnable("bazi", {})
        assert card.is_ok() is True

    def test_is_ok_partial(self):
        card = OracleMethodCard.partial("bazi", {})
        assert card.is_ok() is True

    def test_is_ok_blocked(self):
        card = OracleMethodCard.blocked("bazi", ERR_DEPENDENCY_MISSING, "Node missing")
        assert card.is_ok() is False

    def test_add_warning(self):
        card = OracleMethodCard()
        card.add_warning("test warning")
        assert "test warning" in card.warnings

    def test_add_warning_no_duplicate(self):
        card = OracleMethodCard()
        card.add_warning("test")
        card.add_warning("test")
        assert card.warnings.count("test") == 1

    def test_add_evidence(self):
        card = OracleMethodCard()
        card.add_evidence("test evidence")
        assert "test evidence" in card.evidence

    def test_add_precision_note(self):
        card = OracleMethodCard()
        card.add_precision_note("test note")
        assert "test note" in card.precision_notes


class TestBlockedFactory:
    def test_blocked(self):
        card = OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_DEPENDENCY_MISSING,
            message="Node.js not found",
        )
        assert card.method == "ziwei"
        assert card.status == STATUS_BLOCKED
        assert card.confidence == 0.0
        assert len(card.blockers) == 1

    def test_blocked_with_custom_blockers(self):
        card = OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_DEPENDENCY_MISSING,
            message="Node.js not found",
            blockers=["block1", "block2"],
        )
        assert card.blockers == ["block1", "block2"]

    def test_blocked_label_ko(self):
        card = OracleMethodCard.blocked("bazi", "ERR", "msg")
        assert card.label_ko == "팔자"

    def test_blocked_label_ko_fallback(self):
        card = OracleMethodCard.blocked("unknown", "ERR", "msg")
        assert card.label_ko == "unknown"


class TestPartialFactory:
    def test_partial(self):
        card = OracleMethodCard.partial(
            method="bazi",
            facts={"pillar": "甲子"},
            interpretation="일주가 강함",
            warnings=["출생 시간 없음"],
            precision_notes=["기본값 사용"],
        )
        assert card.status == STATUS_PARTIAL
        assert card.facts == {"pillar": "甲子"}
        assert card.confidence == 0.5

    def test_partial_custom_confidence(self):
        card = OracleMethodCard.partial(
            method="bazi",
            facts={},
            confidence=0.3,
        )
        assert card.confidence == 0.3


class TestRunnableFactory:
    def test_runnable(self):
        card = OracleMethodCard.runnable(
            method="western",
            facts={"sun": "Aries 15°"},
            interpretation="태양이 양자리",
        )
        assert card.status == STATUS_RUNNABLE
        assert card.confidence == 0.8

    def test_runnable_custom_confidence(self):
        card = OracleMethodCard.runnable(
            method="bazi",
            facts={},
            confidence=0.95,
        )
        assert card.confidence == 0.95


class TestFormatCard:
    def test_format_blocked(self):
        card = OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_DEPENDENCY_MISSING,
            message="Node.js not found",
        )
        text = card.format_card()
        assert "자미두수" in text
        assert "blocked" in text.lower()
        assert "차단" in text

    def test_format_runnable(self):
        card = OracleMethodCard.runnable(
            method="bazi",
            facts={"pillar": "甲子", "elements": {"wood": 3}},
        )
        text = card.format_card()
        assert "팔자" in text
        assert "runnable" in text.lower()

    def test_format_partial(self):
        card = OracleMethodCard.partial(
            method="western",
            facts={"sun": "Aries"},
            warnings=["위치 부족"],
        )
        text = card.format_card()
        assert "서양 점성술" in text
        assert "partial" in text.lower()

    def test_no_raw_repr(self):
        """raw dataclass repr가 출력에 노출되면 안 됨."""
        card = OracleMethodCard.runnable("bazi", {"pillar": "甲子"})
        text = card.format_card()
        # dataclass repr 금지 패턴
        assert "dataclass" not in text
        assert "OracleMethodCard(" not in text
        assert "default_factory" not in text

    def test_max_facts_limit(self):
        card = OracleMethodCard.runnable(
            method="bazi",
            facts={f"key{i}": f"val{i}" for i in range(10)},
        )
        text = card.format_card(max_facts=3)
        # 3개 facts만 표시 (카드 헤더 1줄 + 최대 3개 fact)
        lines = text.split("\n")
        fact_lines = [l for l in lines if l.strip().startswith("  key")]
        assert len(fact_lines) <= 3

    def test_format_blocked_summary(self):
        card = OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_DEPENDENCY_MISSING,
            message="Node.js not found",
        )
        summary = card.format_blocked_summary()
        assert "자미두수" in summary
        assert "blocked" in summary.lower()

    def test_format_blocked_summary_no_blockers(self):
        card = OracleMethodCard.blocked("ziwei", "ERR", "msg")
        card.blockers = []
        summary = card.format_blocked_summary()
        assert "이유 미상" in summary


class TestFromAstroMethodCard:
    def test_conversion(self):
        """AstroMethodCard → OracleMethodCard 변환."""
        from hermes_ext.fortune_oracle.astro_method_card import AstroMethodCard
        astro = AstroMethodCard.runnable(
            method="western",
            facts={"planets": ["Sun in Aries"]},
            interpretation="test",
            warnings=["no location"],
        )
        card = OracleMethodCard.from_astro_method_card(astro)
        assert card.method == "western"
        assert card.label_ko == "서양 점성술"
        assert card.status == STATUS_RUNNABLE
        assert "no location" in card.warnings

    def test_conversion_blocked(self):
        from hermes_ext.fortune_oracle.astro_method_card import AstroMethodCard
        astro = AstroMethodCard.blocked(
            method="vedic",
            error_code="CALC_FAILED",
            message="calculation failed",
        )
        card = OracleMethodCard.from_astro_method_card(astro)
        assert card.status == STATUS_BLOCKED
        assert card.label_ko == "베딕 점성술"


class TestMethodLabelKo:
    def test_all_labels(self):
        assert METHOD_LABEL_KO["bazi"] == "팔자"
        assert METHOD_LABEL_KO["western"] == "서양 점성술"
        assert METHOD_LABEL_KO["vedic"] == "베딕 점성술"
        assert METHOD_LABEL_KO["ziwei"] == "자미두수"
        assert METHOD_LABEL_KO["qimen"] == "기문둔갑"
