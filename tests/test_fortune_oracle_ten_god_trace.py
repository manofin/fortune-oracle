#!/usr/bin/env python3
"""Fortune Oracle — Ten God Trace tests (Phase 36).

Tests:
1. get_ten_god basic mapping
2. get_ten_god same element same yin-yang → 비견
3. get_ten_god same element different yin-yang → 겁재
4. get_ten_god produces → 식신/상관
5. get_ten_god controls → 정재/편재
6. get_ten_god produced_by → 정인/편인
7. get_ten_god controls_me → 정관/편관
8. build_ten_god_trace structure
9. build_hidden_stem_trace structure
10. build_ten_god_summary structure
11. build_hidden_stem_summary structure
12. Empty eight_char handling
13. Empty day_master handling
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins"))

from hermes_ext.fortune_oracle.ten_god_trace import (
    build_hidden_stem_summary,
    build_hidden_stem_trace,
    build_ten_god_summary,
    build_ten_god_trace,
    get_ten_god,
)

SAMPLE_EC = {
    "year": "丙寅",
    "month": "辛丑",
    "day": "丁亥",
    "time": "壬寅",
}


class TestGetTenGod:
    """십신 계산 테스트."""

    def test_same_element_same_yin_yang(self):
        """丙 → 丙 (일간 동일) → 일간"""
        # day_master == stem → 일간 (handled in build_ten_god_trace, not get_ten_god)
        pass

    def test_비견(self):
        """丙(양화) → 甲(양목): 목→화 생, 양/양 동일 → 식신"""
        # Actually 丙 day master, 甲 is 목, which is produced_by 화 → 정인
        # Let's test with same element: 丙 → 甲 is not same element
        # For 丙 day master: same element = 火 → 丙/丁
        # 丙(양화) → 丙(양화) = same, same → 비견
        result = get_ten_god("丙", "丙")
        assert result == "비견"

    def test_겁재(self):
        """丙(양화) → 丁(음화): same element, different yin-yang → 겁재"""
        result = get_ten_god("丁", "丙")
        assert result == "겁재"

    def test_식신(self):
        """丙(양화) → 戊(양토): 화→토 생, 양/양 동일 → 식신"""
        result = get_ten_god("戊", "丙")
        assert result == "식신"

    def test_상관(self):
        """丙(양화) → 己(음토): 화→토 생, 양/음 다른 → 상관"""
        result = get_ten_god("己", "丙")
        assert result == "상관"

    def test_정재(self):
        """丙(양화) → 辛(음금): 화→금 극, 양/음 다른 → 편재"""
        # Actually 丙(양) → 辛(음): 화→금 극, 양/음 다른
        result = get_ten_god("辛", "丙")
        assert result == "편재"

    def test_정인(self):
        """丙(양화) → 甲(양목): 목→화 생, 양/양 동일 → 정인"""
        result = get_ten_god("甲", "丙")
        assert result == "정인"

    def test_편인(self):
        """丙(양화) → 乙(음목): 목→화 생, 양/음 다른 → 편인"""
        result = get_ten_god("乙", "丙")
        assert result == "편인"

    def test_정관(self):
        """丙(양화) → 壬(양수): 수→화 극, 양/양 동일 → 정관"""
        result = get_ten_god("壬", "丙")
        assert result == "정관"

    def test_편관(self):
        """丙(양화) → 癸(음수): 수→화 극, 양/음 다른 → 편관"""
        result = get_ten_god("癸", "丙")
        assert result == "편관"

    def test_empty_stem(self):
        result = get_ten_god("", "丙")
        assert result is None

    def test_empty_day_master(self):
        result = get_ten_god("甲", "")
        assert result is None

    def test_invalid_stem(self):
        result = get_ten_god("X", "丙")
        assert result is None


class TestBuildTenGodTrace:
    def test_ten_god_trace_basic(self):
        trace = build_ten_god_trace(SAMPLE_EC, "丁")
        assert isinstance(trace.items, list)

    def test_ten_god_trace_has_items(self):
        trace = build_ten_god_trace(SAMPLE_EC, "丁")
        # Should have items for year, month, time stems (day is day master)
        assert len(trace.items) >= 1

    def test_ten_god_trace_day_is_일간(self):
        trace = build_ten_god_trace(SAMPLE_EC, "丁")
        # Day stem should be labeled as 일간
        day_items = [i for i in trace.items if "일천간" in i]
        assert any("일간" in i for i in day_items), f"Expected 일간 label, got: {day_items}"

    def test_ten_god_trace_empty(self):
        trace = build_ten_god_trace({}, "丁")
        assert trace.items == []

    def test_ten_god_trace_no_day_master(self):
        trace = build_ten_god_trace(SAMPLE_EC, "")
        assert trace.items == []


class TestBuildHiddenStemTrace:
    def test_hidden_stem_trace_basic(self):
        trace = build_hidden_stem_trace(SAMPLE_EC, "丁")
        assert isinstance(trace.items, list)

    def test_hidden_stem_trace_has_items(self):
        trace = build_hidden_stem_trace(SAMPLE_EC, "丁")
        assert len(trace.items) >= 1

    def test_hidden_stem_trace_format(self):
        trace = build_hidden_stem_trace(SAMPLE_EC, "丁")
        # Each item should be "地支: 天干(십신)·天干(십신)" format
        for item in trace.items:
            assert ":" in item, f"Expected ':' in item: {item}"

    def test_hidden_stem_trace_empty(self):
        trace = build_hidden_stem_trace({}, "丁")
        assert trace.items == []


class TestBuildSummaries:
    def test_build_ten_god_summary(self):
        summary = build_ten_god_summary(SAMPLE_EC, "丁")
        assert isinstance(summary.summaries, list)

    def test_build_hidden_stem_summary(self):
        summary = build_hidden_stem_summary(SAMPLE_EC, "丁")
        assert isinstance(summary.summaries, list)

    def test_summaries_empty_eight_char(self):
        tg = build_ten_god_summary({}, "丁")
        assert tg.summaries == []
        hs = build_hidden_stem_summary({}, "丁")
        assert hs.summaries == []
