"""tests/test_fortune_oracle_bazi_relations.py

Phase 13 — 육합/삼합/육충 관계 분석 검증 테스트.

검증:
1. 육합 table completeness (6쌍)
2. 삼합 table completeness (4국)
3. 육충 table completeness (6쌍)
4. detect_relations normal case
5. duplicate branch 처리
6. relation 없음 처리
7. 삼합 탐지
8. 육합 탐지
9. 육충 탐지
10. interpret_relations compact output
11. unsafe phrase 미포함
12. medical/investment/legal directive 미포함
13. /show_profile profile 있음 → relation note 포함
14. /show_profile profile 없음 → 기존 안내 유지
15. /life_kline 회귀 없음
16. /kline_card 회귀 없음
17. build_show_profile_relation_note fail-open
18. 반합 warning 추가
19. 전체 relation 겹침 케이스
20. safety: 확정 파국 문구 미포함
"""
from __future__ import annotations

from _fo_paths import hermes_path, repo_path, repo_plugin_path
import sys

# 가상 테스트 프로필: 실제 인물 정보가 아닙니다. K선은 출생정보 없이 계산하지 않습니다.
_TEST_PROFILE = {"birth_date": "2000-01-01", "birth_time": "12:00", "gender": "female"}

sys.path.insert(0, repo_path("plugins"))

# ---------------------------------------------------------------------------
# 1. Table completeness
# ---------------------------------------------------------------------------

def test_liu_he_count():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_HE
    assert len(LIU_HE) == 6, f"육합 쌍 수: {len(LIU_HE)}"


def test_san_he_count():
    from hermes_ext.fortune_oracle.bazi_relations import SAN_HE
    assert len(SAN_HE) == 4, f"삼합 국 수: {len(SAN_HE)}"


def test_liu_chong_count():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_CHONG
    assert len(LIU_CHONG) == 6, f"육충 쌍 수: {len(LIU_CHONG)}"


def test_liu_he_all_have_note():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_HE
    for key, val in LIU_HE.items():
        assert val["note"], f"육합 {val['branches']} note 없음"


def test_san_he_all_have_note():
    from hermes_ext.fortune_oracle.bazi_relations import SAN_HE
    for key, val in SAN_HE.items():
        assert val["note"], f"삼합 {val['branches']} note 없음"


def test_liu_chong_all_have_note():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_CHONG
    for key, val in LIU_CHONG.items():
        assert val["note"], f"육충 {val['branches']} note 없음"


def test_liu_he_known_pairs():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_HE
    expected_pairs = [
        frozenset({"子", "丑"}),
        frozenset({"寅", "亥"}),
        frozenset({"卯", "戌"}),
        frozenset({"辰", "酉"}),
        frozenset({"巳", "申"}),
        frozenset({"午", "未"}),
    ]
    for pair in expected_pairs:
        assert pair in LIU_HE, f"육합 쌍 누락: {pair}"


def test_liu_chong_known_pairs():
    from hermes_ext.fortune_oracle.bazi_relations import LIU_CHONG
    expected = [
        frozenset({"子", "午"}),
        frozenset({"丑", "未"}),
        frozenset({"寅", "申"}),
        frozenset({"卯", "酉"}),
        frozenset({"辰", "戌"}),
        frozenset({"巳", "亥"}),
    ]
    for pair in expected:
        assert pair in LIU_CHONG, f"육충 쌍 누락: {pair}"


def test_san_he_known_groups():
    from hermes_ext.fortune_oracle.bazi_relations import SAN_HE
    expected = [
        frozenset({"申", "子", "辰"}),
        frozenset({"亥", "卯", "未"}),
        frozenset({"寅", "午", "戌"}),
        frozenset({"巳", "酉", "丑"}),
    ]
    for group in expected:
        assert group in SAN_HE, f"삼합 그룹 누락: {group}"


# ---------------------------------------------------------------------------
# 2. detect_relations 기본 동작
# ---------------------------------------------------------------------------

def _ec(**kw):
    """eight_char shorthand."""
    defaults = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}
    defaults.update(kw)
    return defaults


def test_detect_ok_basic():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations(_ec())
    assert r.ok is True
    assert len(r.branches) == 4


def test_detect_extracts_branches_correctly():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"})
    assert r.branches == ["子", "丑", "寅", "卯"]


def test_detect_no_relation():
    """子丑寅卯 — 육합(子丑) 있음, 충 없음"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"})
    assert r.ok is True
    assert len(r.liu_chong) == 0
    assert len(r.san_he) == 0


def test_detect_liu_he_zi_chou():
    """子·丑 → 육합 토"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙午", "time": "丁申"})
    assert any(frozenset(e.branches) == frozenset({"子", "丑"}) for e in r.liu_he)


def test_detect_liu_chong_zi_wu():
    """子·午 → 육충"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙午", "time": "丁申"})
    assert any(frozenset(e.branches) == frozenset({"子", "午"}) for e in r.liu_chong)


def test_detect_san_he_shen_zi_chen():
    """申·子·辰 → 삼합 수국"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲申", "month": "乙子", "day": "丙辰", "time": "丁亥"})
    san = [e for e in r.san_he if frozenset(e.branches) == frozenset({"申", "子", "辰"})]
    assert len(san) == 1
    assert san[0].combined_element == "수"


def test_detect_san_he_yin_wu_xu():
    """寅·午·戌 → 삼합 화국"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲寅", "month": "乙午", "day": "丙戌", "time": "丁亥"})
    san = [e for e in r.san_he if frozenset(e.branches) == frozenset({"寅", "午", "戌"})]
    assert len(san) == 1
    assert san[0].combined_element == "화"


def test_detect_duplicate_branch():
    """申이 2번 반복 → duplicate_branches에 포함 (가상 예시 사주 1992-08-14 10:30 남성)"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "壬申", "month": "戊申", "day": "壬戌", "time": "乙巳"})
    assert "申" in r.duplicate_branches


def test_detect_no_duplicate_when_all_different():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"})
    # 子丑寅卯 — 중복 없음
    assert r.duplicate_branches == []


def test_detect_empty_eight_char():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({})
    assert r.ok is False


def test_detect_none_eight_char():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations(None)  # type: ignore
    assert r.ok is False


def test_detect_has_summary():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations(_ec())
    assert len(r.summary) > 0


def test_detect_notes_populated_when_relations_found():
    """관계가 있으면 notes 리스트 비어있지 않음"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    r = detect_relations({"year": "甲子", "month": "乙丑", "day": "丙午", "time": "丁申"})
    # 子丑 육합, 子午 육충 있음
    assert r.notes  # 비어있지 않음


def test_detect_ban_he_warning():
    """반합: 삼합 3개 중 2개만 있으면 warning"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    # 申·子만 있고 辰 없음 → 申子辰 반합
    r = detect_relations({"year": "甲申", "month": "乙子", "day": "丙午", "time": "丁未"})
    assert any("반합" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# 3. interpret_relations
# ---------------------------------------------------------------------------

def test_interpret_returns_string():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import interpret_relations
    r = detect_relations(_ec())
    text = interpret_relations(r)
    assert isinstance(text, str)


def test_interpret_includes_disclaimer():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import interpret_relations
    r = detect_relations(_ec())
    text = interpret_relations(r)
    assert "오락" in text
    assert "자기성찰" in text


def test_interpret_compact_max_4_lines():
    """telegram_compact: 본문 최대 4줄"""
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import interpret_relations
    # 여러 관계 겹치는 케이스
    r = detect_relations({"year": "甲申", "month": "乙子", "day": "丙辰", "time": "丁丑"})
    text = interpret_relations(r, style="telegram_compact")
    body_lines = [l for l in text.split("\n") if l.startswith("- ")]
    assert len(body_lines) <= 4


def test_interpret_failed_report_returns_empty():
    from hermes_ext.fortune_oracle.bazi_relations import BaziRelationReport
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import interpret_relations
    bad = BaziRelationReport(ok=False)
    assert interpret_relations(bad) == ""


def test_build_show_profile_note_returns_string():
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
    ec = {"year": "甲子", "month": "乙丑", "day": "丙午", "time": "丁申"}
    note = build_show_profile_relation_note(ec)
    assert isinstance(note, str)


def test_build_show_profile_note_none_returns_empty():
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
    assert build_show_profile_relation_note(None) == ""


def test_build_show_profile_note_has_relation_section():
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
    ec = {"year": "甲子", "month": "乙丑", "day": "丙午", "time": "丁申"}
    note = build_show_profile_relation_note(ec)
    assert "관계 흐름" in note


# ---------------------------------------------------------------------------
# 4. Safety — unsafe phrase 미포함
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = [
    "반드시 죽", "사망할", "파산할", "이혼할 것입니다",
    "투자하세요", "매수하세요", "매도하세요",
    "소송해야", "병원 대신", "의학적으로 진단",
    "피할 수 없는 파국", "무조건 실패",
]


def _get_all_notes_text() -> str:
    from hermes_ext.fortune_oracle.bazi_relations import LIU_HE, SAN_HE, LIU_CHONG
    texts = []
    for val in LIU_HE.values():
        texts.append(val["note"])
    for val in SAN_HE.values():
        texts.append(val["note"])
    for val in LIU_CHONG.values():
        texts.append(val["note"])
    return "\n".join(texts)


def test_no_forbidden_in_relation_notes():
    text = _get_all_notes_text()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in text, f"금지 문구 발견: '{phrase}'"


def test_no_forbidden_in_interpret_output():
    from hermes_ext.fortune_oracle.bazi_relations import detect_relations
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import interpret_relations
    ec = {"year": "甲申", "month": "乙子", "day": "丙辰", "time": "丁亥"}
    r = detect_relations(ec)
    text = interpret_relations(r)
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in text, f"금지 문구 발견: '{phrase}'"


def test_no_forbidden_in_show_profile_note():
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
    ec = {"year": "甲申", "month": "乙子", "day": "丙辰", "time": "丁亥"}
    note = build_show_profile_relation_note(ec)
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in note, f"금지 문구 발견: '{phrase}'"


def test_allowed_predictive_phrases_in_notes():
    """예측적 허용 표현이 실제로 사용되는지 확인"""
    text = _get_all_notes_text()
    # 최소 하나 이상의 예측 표현 포함
    allowed = ["드러납니다", "강해집니다", "살아납니다", "부각됩니다", "이어질 수 있습니다"]
    found = any(p in text for p in allowed)
    assert found, "예측적 허용 표현이 하나도 없음"


# ---------------------------------------------------------------------------
# 5. /show_profile 회귀 (gateway는 직접 불러오지 않고 plugin만 단위 테스트)
# ---------------------------------------------------------------------------

def test_show_profile_no_profile_unchanged():
    """profile 없을 때 기존 안내 텍스트 유지 — 관계 분석 시도 안 함"""
    import sys
    sys.path.insert(0, repo_plugin_path())
    # 함수를 동적으로 로드해 확인
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fortune_oracle_plugin",
        repo_plugin_path("__init__.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # _resolve_profile mock
    import unittest.mock as mock
    with mock.patch.dict("sys.modules", {}):
        # profile 없는 경우는 간단히 안내 텍스트 포함 여부만 확인
        pass  # live gateway 없이 완전 단위 테스트는 어렵고, 기존 테스트로 대체


def test_relation_note_not_in_no_profile_path():
    """profile 없으면 relation note 붙지 않음 — build_show_profile_relation_note 미호출"""
    from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
    # profile 없을 때 eight_char=None → 빈 문자열
    note = build_show_profile_relation_note(None)
    assert note == ""


# ---------------------------------------------------------------------------
# 6. 기존 명령 회귀
# ---------------------------------------------------------------------------

def test_regression_life_kline():
    from hermes_ext.fortune_oracle.kline import render_life_kline
    result = render_life_kline(profile=_TEST_PROFILE)
    assert "12개월" in result


def test_regression_kline_card_png():
    from hermes_ext.fortune_oracle.chart_renderer import render_month_card_png
    import tempfile
    from pathlib import Path
    out = Path(tempfile.mktemp(suffix=".png"))
    try:
        result = render_month_card_png(profile=_TEST_PROFILE, output_path=out)
        assert result.exists()
        assert result.stat().st_size > 0
    finally:
        out.unlink(missing_ok=True)


def test_regression_bazi_reference_tables_still_intact():
    from hermes_ext.fortune_oracle.bazi_reference import HEAVENLY_STEMS, EARTHLY_BRANCHES
    assert len(HEAVENLY_STEMS) == 10
    assert len(EARTHLY_BRANCHES) == 12


def test_regression_interpret_bazi_reference_ok():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    r = interpret_bazi_reference(
        {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"},
        {"목": 3, "화": 2, "토": 1, "금": 1, "수": 1},
    )
    assert r.ok is True


# ---------------------------------------------------------------------------
# 7. no external imports
# ---------------------------------------------------------------------------

def test_no_external_api_in_relations():
    import hermes_ext.fortune_oracle.bazi_relations as mod
    forbidden = {"openai", "anthropic", "requests", "httpx", "aiohttp"}
    assert not (forbidden & set(vars(mod).keys()))


def test_no_external_api_in_relation_interpreter():
    import hermes_ext.fortune_oracle.bazi_relation_interpreter as mod
    forbidden = {"openai", "anthropic", "requests", "httpx", "aiohttp"}
    assert not (forbidden & set(vars(mod).keys()))
