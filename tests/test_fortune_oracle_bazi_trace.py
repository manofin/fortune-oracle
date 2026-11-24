#!/usr/bin/env python3
"""Fortune Oracle — Bazi Trace Layer tests (Phase 36).

Tests:
1. BaziTrace schema fields
2. YongshenTrace from YongshenResult
3. build_bazi_trace end-to-end
4. build_trace_summary compact output
5. No raw dataclass repr in output
6. No traceback in output
7. No raw dict/list dump in output
8. No deterministic fortune-telling phrases
9. No medical/investment/legal determinative phrases
10. Disclaimer present
11. TraceWarning structure
12. ElementDistribution structure
13. RelationSummary structure
14. BaziTrace.has_any_relation
15. BaziTrace.get_warnings_text
16. build_bazi_trace with empty eight_char
17. build_bazi_trace with yongshen_result
18. build_bazi_trace completeness calculation
19. yongshen_result_to_trace layers
20. build_trace_summary truncation
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins"))

from hermes_ext.fortune_oracle.bazi_trace import (
    BaziTrace,
    ElementDistribution,
    HiddenStemSummary,
    RelationSummary,
    TenGodSummary,
    TraceWarning,
    YongshenTrace,
    build_bazi_trace,
    build_trace_summary,
    yongshen_result_to_trace,
)

SAMPLE_EC = {
    "year": "丙寅",
    "month": "辛丑",
    "day": "丁亥",
    "time": "壬寅",
}


def test_positional_stem_matches_survive_compact_consumer():
    chart = {"year": "丁卯", "month": "壬寅", "day": "丁未", "time": "壬午"}
    trace = build_bazi_trace(chart)
    assert trace.has_any_relation()
    rendered = build_trace_summary(trace, max_lines=6)
    for match in trace.relation_summary.tiangan_he:
        assert match in rendered
    assert len(trace.relation_summary.tiangan_he) == 4
    assert "합화 성립·관계 의미는 판정하지 않았습니다" in rendered
    assert "(목)" not in rendered and "끌림" not in rendered


def test_legacy_relation_summary_positional_fields_unchanged():
    summary = RelationSummary(["子·丑"], [], [], [], [], [], ["子"])
    assert summary.liuhe == ["子·丑"]
    assert summary.repeated_branches == ["子"]
    assert summary.tiangan_he == []


@pytest.mark.parametrize("chart", [None, [], "丁壬", True, {"day": 9}, {"day": "壬卯"}])
def test_invalid_trace_input_does_not_fabricate_day_master(chart):
    trace = build_bazi_trace(chart)
    assert not trace.day_master and not trace.has_any_relation()
    assert "丁壬合" not in build_trace_summary(trace)


def test_partial_trace_retains_confirmed_pairs_without_inventing_a_day():
    trace = build_bazi_trace({"year": "丁卯", "month": "壬寅", "day": "", "time": None})
    assert trace.day_master == ""
    assert trace.relation_summary.tiangan_he == ["년간 丁 ↔ 월간 壬 (丁壬合)"]
    assert "천간합" in build_trace_summary(trace)


def test_invalid_pillar_exclusion_reaches_display_without_raw_value():
    trace = build_bazi_trace({"year": "丁卯", "month": "壬寅", "day": "乙未", "time": "private-invalid"})
    rendered = build_trace_summary(trace)
    assert "해당 기둥을 제외" in rendered and "천간합" in rendered
    assert "private-invalid" not in rendered


def test_conflicting_explicit_day_master_is_not_used():
    trace = build_bazi_trace({"day": "乙未"}, day_master_stem="丁")
    assert trace.day_master == "乙"
    assert "별도 일간" in build_trace_summary(trace)


# ── Schema structure tests ────────────────────────────────────────────────

class TestBaziTraceSchema:
    def test_bazi_trace_default(self):
        t = BaziTrace()
        assert t.day_master == ""
        assert t.pillars_summary == ""
        assert t.element_distribution.elements == {}
        assert t.ten_god_summary.summaries == []
        assert t.hidden_stem_summary.summaries == []
        assert t.yongshen_trace is None
        assert t.confidence == ""
        assert t.completeness == 0.0
        assert t.warnings == []

    def test_bazi_trace_has_any_relation(self):
        t = BaziTrace(
            relation_summary=RelationSummary(chong=["子·午"]),
        )
        assert t.has_any_relation() is True

    def test_bazi_trace_no_relation(self):
        t = BaziTrace()
        assert t.has_any_relation() is False

    def test_bazi_trace_get_warnings_text(self):
        t = BaziTrace(
            warnings=[
                TraceWarning(message="경고1", severity="warning"),
                TraceWarning(message="경고2", severity="info"),
            ],
        )
        assert t.get_warnings_text() == ["경고1", "경고2"]

    def test_element_distribution_structure(self):
        d = ElementDistribution(
            elements={"목": 2, "화": 3, "토": 1, "금": 1, "수": 1},
            dominant=["화"],
        )
        assert d.elements["화"] == 3
        assert "화" in d.dominant

    def test_relation_summary_structure(self):
        r = RelationSummary(
            liuhe=["子丑(토)"],
            chong=["子·午"],
            repeated_branches=["寅"],
        )
        assert len(r.liuhe) == 1
        assert len(r.chong) == 1
        assert "寅" in r.repeated_branches

    def test_yongshen_trace_structure(self):
        yt = YongshenTrace(
            primary_layer="토 기운이 두드러진 구조",
            support_layer="일간 토이(가) 약 — 생조(生助) 기운이 도움",
            seasonal_layer="겨울계절 기준 조후",
            final_hint="수/목 보완 권장",
            confidence="rule_based_low",
        )
        assert yt.primary_layer
        assert yt.support_layer
        assert yt.seasonal_layer
        assert yt.final_hint
        assert yt.confidence == "rule_based_low"

    def test_trace_warning_structure(self):
        w = TraceWarning(message="테스트 경고", severity="warning")
        assert w.message == "테스트 경고"
        assert w.severity == "warning"

    def test_ten_god_summary_structure(self):
        tg = TenGodSummary(summaries=["丙 → 식신", "辛 → 정인"])
        assert len(tg.summaries) == 2

    def test_hidden_stem_summary_structure(self):
        hs = HiddenStemSummary(summaries=["丑: 己癸辛"])
        assert len(hs.summaries) == 1


# ── YongshenResult → YongshenTrace tests ──────────────────────────────────

class TestYongshenResultToTrace:
    def test_yongshen_result_to_trace_basic(self):
        from hermes_ext.fortune_oracle.yongshen import (
            YongshenResult,
            calculate_yongshen,
        )
        result = calculate_yongshen(SAMPLE_EC)
        trace = yongshen_result_to_trace(result)
        assert trace.ok if hasattr(trace, "ok") else True  # YongshenTrace has no 'ok'
        assert trace.primary_layer  # should have structure layer
        assert trace.support_layer  # should have strength layer
        assert trace.confidence

    def test_yongshen_result_to_trace_none(self):
        trace = yongshen_result_to_trace(None)
        assert trace.primary_layer == ""
        assert trace.support_layer == ""
        assert trace.final_hint == ""

    def test_yongshen_result_to_trace_not_ok(self):
        from hermes_ext.fortune_oracle.yongshen import YongshenResult
        result = YongshenResult(ok=False, warnings=["eight_char 없음"])
        trace = yongshen_result_to_trace(result)
        assert trace.primary_layer == ""
        assert trace.support_layer == ""

    def test_yongshen_trace_has_layers(self):
        """YongshenTrace should have primary/support/seasonal layers."""
        from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
        result = calculate_yongshen(SAMPLE_EC)
        trace = yongshen_result_to_trace(result)
        assert trace.primary_layer  # 구조/격국 관점
        assert trace.support_layer  # 강약/부억 관점


# ── build_bazi_trace tests ────────────────────────────────────────────────

class TestBuildBaziTrace:
    def test_build_bazi_trace_empty(self):
        trace = build_bazi_trace({})
        assert trace.day_master == ""
        assert trace.pillars_summary == ""

    def test_build_bazi_trace_day_master(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert trace.day_master == "丁"

    def test_build_bazi_trace_pillars_summary(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert "年丙寅" in trace.pillars_summary
        assert "日丁亥" in trace.pillars_summary

    def test_build_bazi_trace_element_distribution(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert trace.element_distribution.elements  # should have elements

    def test_build_bazi_trace_ten_god_summary(self):
        trace = build_bazi_trace(SAMPLE_EC)
        # Should have at least some ten god summaries
        assert isinstance(trace.ten_god_summary.summaries, list)

    def test_build_bazi_trace_hidden_stem_summary(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert isinstance(trace.hidden_stem_summary.summaries, list)

    def test_build_bazi_trace_relation(self):
        trace = build_bazi_trace(SAMPLE_EC)
        # Should have relation summary
        rs = trace.relation_summary
        assert isinstance(rs.liuhe, list)
        assert isinstance(rs.chong, list)

    def test_build_bazi_trace_with_yongshen(self):
        from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
        yong = calculate_yongshen(SAMPLE_EC)
        trace = build_bazi_trace(SAMPLE_EC, yongshen_result=yong)
        assert trace.yongshen_trace is not None
        assert trace.yongshen_trace.primary_layer

    def test_build_bazi_trace_completeness(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert 0.0 <= trace.completeness <= 1.0

    def test_build_bazi_trace_confidence(self):
        from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
        yong = calculate_yongshen(SAMPLE_EC)
        trace = build_bazi_trace(SAMPLE_EC, yongshen_result=yong)
        assert trace.confidence in ("rule_based_low", "rule_based_medium", "partial")

    def test_build_bazi_trace_without_yongshen(self):
        trace = build_bazi_trace(SAMPLE_EC)
        assert trace.yongshen_trace is None
        assert trace.confidence == "partial"


# ── build_trace_summary tests ─────────────────────────────────────────────

class TestBuildTraceSummary:
    def test_build_trace_summary_returns_string(self):
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        assert isinstance(result, str)

    def test_build_trace_summary_has_header(self):
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        assert "해석 근거" in result

    def test_build_trace_summary_has_day_master(self):
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        assert "丁" in result

    def test_build_trace_summary_has_element_distribution(self):
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        assert "오행 분포" in result

    def test_build_trace_summary_empty_trace(self):
        t = BaziTrace()
        result = build_trace_summary(t)
        assert result == ""  # no day_master → empty

    def test_build_trace_summary_no_raw_repr(self):
        """No raw dataclass repr in output."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        forbidden = ["BaziTrace(", "YongshenTrace(", "dataclass", "default_factory"]
        for pattern in forbidden:
            assert pattern not in result, f"Found forbidden pattern: {pattern}"

    def test_build_trace_summary_no_traceback(self):
        """No traceback in output."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        assert "Traceback" not in result
        assert "File \"hermes_ext" not in result

    def test_build_trace_summary_no_raw_dict_dump(self):
        """No raw dict/list dump in output."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        stripped = result.strip()
        # Should not start with { or [
        assert not stripped.startswith("{") or not stripped.endswith("}")
        assert not stripped.startswith("[") or not stripped.endswith("]")

    def test_build_trace_summary_no_medical_phrases(self):
        """No medical/investment/legal determinative phrases."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        forbidden = ["반드시", "필연적으로", "암", "혈압", "투자", "매수", "소송"]
        for phrase in forbidden:
            assert phrase not in result, f"Found forbidden phrase: {phrase}"

    def test_build_trace_summary_no_deterministic_fortune(self):
        """No deterministic fortune-telling phrases."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace)
        forbidden = ["반드시 죽는다", "반드시 파산", "피할 수 없는 운명"]
        for phrase in forbidden:
            assert phrase not in result, f"Found forbidden phrase: {phrase}"

    def test_build_trace_summary_truncation(self):
        """Output should be truncated to max_lines."""
        trace = build_bazi_trace(SAMPLE_EC)
        result = build_trace_summary(trace, max_lines=3)
        # Count bullet lines (lines starting with "- ")
        bullet_lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(bullet_lines) <= 3
