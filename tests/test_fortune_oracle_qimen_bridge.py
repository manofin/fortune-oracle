#!/usr/bin/env python3
"""Fortune Oracle — Qimen Bridge tests (Phase 35).

Tests qimen_schema, qimen_bridge with both real and stub scenarios.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.qimen_schema import (
    EIGHT_PALACES,
    PALACE_GRID,
    QIMEN_DISCLAIMER,
    QimenChart,
    QimenPalace,
    QimenQuery,
    QimenResult,
)
from hermes_ext.fortune_oracle.qimen_bridge import (
    calculate_qimen,
    bridge_available,
    _ensure_kinqimen,
    _scoped_kinqimen_config,
)


# --- Schema tests ---

def test_qimen_query_valid():
    q = QimenQuery(2026, 5, 28, 12, 30)
    assert q.validate() is None


def test_qimen_query_invalid_year():
    q = QimenQuery(1800, 5, 28, 12, 30)
    assert q.validate() is not None


def test_qimen_query_invalid_hour():
    q = QimenQuery(2026, 5, 28, 25, 30)
    assert q.validate() is not None


def test_qimen_query_invalid_month():
    q = QimenQuery(2026, 13, 28, 12, 30)
    assert q.validate() is not None


def test_qimen_result_error_factory():
    r = QimenResult.error("TEST", "test error")
    assert r.ok is False
    assert r.error_code == "TEST"
    assert r.message == "test error"
    assert r.disclaimer == QIMEN_DISCLAIMER


def test_qimen_chart_get_palace():
    chart = QimenChart(
        palaces={"坎": QimenPalace(palace_name="坎", sky_stem="戊")}
    )
    p = chart.get_palace("坎")
    assert p is not None
    assert p.sky_stem == "戊"
    assert chart.get_palace("離") is None


def test_palace_grid_structure():
    assert len(PALACE_GRID) == 3
    assert len(PALACE_GRID[0]) == 3
    # Check corners
    assert PALACE_GRID[0][0] == "巽"
    assert PALACE_GRID[1][1] == "中"
    assert PALACE_GRID[2][2] == "乾"


def test_eight_palaces():
    assert "巽" in EIGHT_PALACES
    assert "離" in EIGHT_PALACES
    assert "中" not in EIGHT_PALACES  # 중앙은 팔괘에 포함 안됨


# --- Bridge tests ---

def test_qimen_bridge_input_validation():
    q = QimenQuery(1800, 5, 28, 12, 30)
    result = calculate_qimen(q)
    assert result.ok is False
    assert result.error_code == "INVALID_INPUT"


def test_qimen_bridge_empty_question_allowed():
    q = QimenQuery(2026, 5, 28, 12, 30, question="")
    result = calculate_qimen(q)
    # Should not fail on empty question — either ok or DEPENDENCY_MISSING
    assert result.error_code != "INVALID_INPUT"


def test_bridge_available_is_bool():
    avail = bridge_available()
    assert isinstance(avail, bool)


def test_ensure_kinqimen_returns_bool():
    result = _ensure_kinqimen()
    assert isinstance(result, bool)
    # Second call should return same result (cached)
    result2 = _ensure_kinqimen()
    assert result == result2


def test_qimen_bridge_invalid_minute():
    q = QimenQuery(2026, 5, 28, 12, 60)
    result = calculate_qimen(q)
    assert result.ok is False
    assert result.error_code == "INVALID_INPUT"


def test_scoped_config_is_context_manager(monkeypatch):
    """_scoped_kinqimen_config가 context manager로 동작하고 sys.modules를 복원하는지 확인."""
    import sys
    from types import ModuleType
    from hermes_ext.fortune_oracle import qimen_bridge

    # This tests module scoping, independently of the optional calculator.
    scoped_config = ModuleType("kinqimen.config")
    original_config = ModuleType("host_config")
    monkeypatch.setattr(qimen_bridge, "_QI_CONFIG_MODULE", scoped_config)
    monkeypatch.setitem(sys.modules, "config", original_config)

    # 기존 상태 확인
    original_config = sys.modules.get("config")

    # scoped 호출
    with _scoped_kinqimen_config():
        # 컨텍스트 내부에서는 config가 설정되어 있어야 함
        assert sys.modules.get("config") is scoped_config

    # 컨텍스트 외부에서는 원상복원
    after_config = sys.modules.get("config")
    if original_config is not None:
        assert after_config is original_config
    else:
        assert after_config is None or "config" not in sys.modules


def test_scoped_config_does_not_leak(monkeypatch):
    """scoped config가 여러 번 호출되어도 leak이 없는지 확인."""
    import sys
    from types import ModuleType
    from hermes_ext.fortune_oracle import qimen_bridge

    scoped_config = ModuleType("kinqimen.config")
    monkeypatch.setattr(qimen_bridge, "_QI_CONFIG_MODULE", scoped_config)
    monkeypatch.delitem(sys.modules, "config", raising=False)

    for _ in range(5):
        with _scoped_kinqimen_config():
            assert sys.modules.get("config") is scoped_config
        assert "config" not in sys.modules
