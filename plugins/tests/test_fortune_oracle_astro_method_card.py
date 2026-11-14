"""Fortune Oracle — Astro Method Card Tests (Phase 38B)."""

import sys
from pathlib import Path
import os
import pytest

_plugins_dir = str(Path(__file__).resolve().parents[1])
if _plugins_dir not in sys.path:
    sys.path.insert(0, _plugins_dir)

from hermes_ext.fortune_oracle.astro_method_card import (
    AstroMethodCard,
    DISCLAIMER,
    STATUS_RUNNABLE,
    STATUS_PARTIAL,
    STATUS_BLOCKED,
    ERR_DEPENDENCY_MISSING,
    ERR_CALCULATION_FAILED,
    ERR_INSUFFICIENT_BIRTH_DATA,
)

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestAstroMethodCardConstruction:
    def test_defaults(self):
        card = AstroMethodCard()
        assert card.method == ""
        assert card.status == STATUS_BLOCKED
        assert card.facts == {}
        assert card.interpretation == ""
        assert card.confidence == 0.0
        assert card.blockers == []
        assert card.warnings == []
        assert card.disclaimer == DISCLAIMER

# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------

class TestBlockedFactory:
    def test_blocked(self):
        card = AstroMethodCard.blocked(
            method="western",
            error_code=ERR_DEPENDENCY_MISSING,
            message="pyswisseph not installed",
        )
        assert card.status == STATUS_BLOCKED
        assert card.confidence == 0.0
        assert len(card.blockers) == 1
        assert "DEPENDENCY_MISSING" in card.blockers[0]

    def test_blocked_with_custom_blockers(self):
        card = AstroMethodCard.blocked(
            method="vedic",
            error_code=ERR_INSUFFICIENT_BIRTH_DATA,
            message="location missing",
            blockers=["no lat/lon"],
        )
        assert card.blockers == ["no lat/lon"]

class TestPartialFactory:
    def test_partial(self):
        card = AstroMethodCard.partial(
            method="western",
            facts={"planets": ["Sun Aries"]},
            interpretation="태양은 양자리입니다.",
            warnings=["house 계산 불가"],
        )
        assert card.status == STATUS_PARTIAL
        assert card.facts == {"planets": ["Sun Aries"]}
        assert card.confidence == 0.5
        assert len(card.warnings) == 1

class TestRunnableFactory:
    def test_runnable(self):
        card = AstroMethodCard.runnable(
            method="vedic",
            facts={"grahas": ["Surya Mesha"]},
            interpretation="수리야는 메샤 라시에 있습니다.",
            confidence=0.8,
        )
        assert card.status == STATUS_RUNNABLE
        assert card.confidence == 0.8

# ---------------------------------------------------------------------------
# is_ok
# ---------------------------------------------------------------------------

class TestIsOk:
    def test_runnable_is_ok(self):
        card = AstroMethodCard(status=STATUS_RUNNABLE)
        assert card.is_ok() is True

    def test_partial_is_ok(self):
        card = AstroMethodCard(status=STATUS_PARTIAL)
        assert card.is_ok() is True

    def test_blocked_is_not_ok(self):
        card = AstroMethodCard(status=STATUS_BLOCKED)
        assert card.is_ok() is False

# ---------------------------------------------------------------------------
# add_warning
# ---------------------------------------------------------------------------

class TestAddWarning:
    def test_add_warning(self):
        card = AstroMethodCard()
        card.add_warning("test warning")
        assert "test warning" in card.warnings

    def test_duplicate_warning(self):
        card = AstroMethodCard()
        card.add_warning("test")
        card.add_warning("test")
        assert card.warnings.count("test") == 1

    def test_empty_warning(self):
        card = AstroMethodCard()
        card.add_warning("")
        assert card.warnings == []

# ---------------------------------------------------------------------------
# DISCLAIMER
# ---------------------------------------------------------------------------

class TestDisclaimer:
    def test_disclaimer_present(self):
        card = AstroMethodCard()
        assert "자기성찰" in card.disclaimer
        assert "확정적 판단" in card.disclaimer
        assert "의학" in card.disclaimer
