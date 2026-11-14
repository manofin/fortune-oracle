"""tests/test_fortune_oracle_bazi_reference.py

Phase 12 — Bazi Reference Tables & Interpreter 검증 테스트.

검증:
- reference tables 완전성 (10천간, 12지지, 5오행)
- 십신 helper deterministic
- 지장간 helper deterministic
- 시진 helper (야자시 23:00 경계 경고)
- 오행 균형 helper
- 월간 간지 도출
- 안전 문구 포함 (disclaimer)
- 안전 금지 패턴 미포함 (medical/invest/legal/예언)
- 외부 import 없음 (정적)
- 기존 /kline_card, /life_kline, /show_profile 회귀 없음
"""
from __future__ import annotations

from _fo_paths import hermes_path, repo_path
import sys

sys.path.insert(0, repo_path("plugins"))

# ---------------------------------------------------------------------------
# 1. Reference tables 완전성
# ---------------------------------------------------------------------------

def test_heavenly_stems_count():
    from hermes_ext.fortune_oracle.bazi_reference import HEAVENLY_STEMS
    assert len(HEAVENLY_STEMS) == 10


def test_heavenly_stems_required_fields():
    from hermes_ext.fortune_oracle.bazi_reference import HEAVENLY_STEMS
    required = {"kor", "element", "polarity", "traits", "tendency"}
    for stem, data in HEAVENLY_STEMS.items():
        missing = required - set(data.keys())
        assert not missing, f"{stem} missing fields: {missing}"


def test_earthly_branches_count():
    from hermes_ext.fortune_oracle.bazi_reference import EARTHLY_BRANCHES
    assert len(EARTHLY_BRANCHES) == 12


def test_earthly_branches_required_fields():
    from hermes_ext.fortune_oracle.bazi_reference import EARTHLY_BRANCHES
    required = {"kor", "zodiac", "element", "polarity", "hidden_stems", "traits"}
    for branch, data in EARTHLY_BRANCHES.items():
        missing = required - set(data.keys())
        assert not missing, f"{branch} missing fields: {missing}"


def test_earthly_branches_hidden_stems_nonempty():
    from hermes_ext.fortune_oracle.bazi_reference import EARTHLY_BRANCHES
    for branch, data in EARTHLY_BRANCHES.items():
        assert len(data["hidden_stems"]) >= 1, f"{branch} hidden_stems empty"


def test_five_element_reflections_complete():
    from hermes_ext.fortune_oracle.bazi_reference import ELEMENT_REFLECTIONS
    for elem in ["목", "화", "토", "금", "수"]:
        assert elem in ELEMENT_REFLECTIONS
        assert len(ELEMENT_REFLECTIONS[elem]) > 10


def test_element_generates_cycle():
    from hermes_ext.fortune_oracle.bazi_reference import ELEMENT_GENERATES
    # 목→화→토→금→수→목 순환
    assert ELEMENT_GENERATES["목"] == "화"
    assert ELEMENT_GENERATES["화"] == "토"
    assert ELEMENT_GENERATES["토"] == "금"
    assert ELEMENT_GENERATES["금"] == "수"
    assert ELEMENT_GENERATES["수"] == "목"


def test_element_controls_cycle():
    from hermes_ext.fortune_oracle.bazi_reference import ELEMENT_CONTROLS
    assert ELEMENT_CONTROLS["목"] == "토"
    assert ELEMENT_CONTROLS["토"] == "수"
    assert ELEMENT_CONTROLS["수"] == "화"
    assert ELEMENT_CONTROLS["화"] == "금"
    assert ELEMENT_CONTROLS["금"] == "목"


# ---------------------------------------------------------------------------
# 2. 십신 helper deterministic
# ---------------------------------------------------------------------------

def test_ten_god_same_element_same_polarity():
    """甲 vs 甲 → 비견"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "甲")
    assert result is not None
    assert result["name"] == "비견"


def test_ten_god_same_element_diff_polarity():
    """甲 vs 乙 → 겁재 (목·음 vs 목·양 아님, 甲양·乙음)"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "乙")
    assert result is not None
    assert result["name"] == "겁재"


def test_ten_god_output_same_polarity():
    """甲(목·양) vs 丙(화·양) → 식신 (목이 화를 생)"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "丙")
    assert result is not None
    assert result["name"] == "식신"


def test_ten_god_output_diff_polarity():
    """甲(목·양) vs 丁(화·음) → 상관"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "丁")
    assert result is not None
    assert result["name"] == "상관"


def test_ten_god_resource_direct():
    """甲(목·양) vs 癸(수·음) → 정인 (수가 목을 생, 극성 다름)"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "癸")
    assert result is not None
    assert result["name"] == "정인"


def test_ten_god_resource_indirect():
    """甲(목·양) vs 壬(수·양) → 편인 (수가 목을 생, 극성 같음)"""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    result = get_ten_god("甲", "壬")
    assert result is not None
    assert result["name"] == "편인"


def test_ten_god_deterministic():
    """같은 입력은 항상 같은 결과."""
    from hermes_ext.fortune_oracle.bazi_reference import get_ten_god
    r1 = get_ten_god("丙", "壬")
    r2 = get_ten_god("丙", "壬")
    assert r1 == r2


def test_ten_god_all_have_reflection():
    """모든 십신 항목에 reflection 필드 존재."""
    from hermes_ext.fortune_oracle.bazi_reference import TEN_GODS_TABLE
    for key, val in TEN_GODS_TABLE.items():
        assert "reflection" in val, f"Missing reflection in {key}"


# ---------------------------------------------------------------------------
# 3. 지장간 helper deterministic
# ---------------------------------------------------------------------------

def test_hidden_stems_zi():
    from hermes_ext.fortune_oracle.bazi_reference import get_hidden_stems
    assert get_hidden_stems("子") == ["癸"]


def test_hidden_stems_chou():
    from hermes_ext.fortune_oracle.bazi_reference import get_hidden_stems
    assert get_hidden_stems("丑") == ["己", "癸", "辛"]


def test_hidden_stems_yin():
    from hermes_ext.fortune_oracle.bazi_reference import get_hidden_stems
    assert get_hidden_stems("寅") == ["甲", "丙", "戊"]


def test_hidden_stems_all_branches():
    from hermes_ext.fortune_oracle.bazi_reference import EARTHLY_BRANCHES, get_hidden_stems
    for branch in EARTHLY_BRANCHES:
        hs = get_hidden_stems(branch)
        assert len(hs) >= 1, f"{branch} hidden_stems empty"


# ---------------------------------------------------------------------------
# 4. 시진 helper + 야자시 경고
# ---------------------------------------------------------------------------

def test_shichen_midnight_is_zi():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, _ = get_shichen(0, 30)
    assert branch == "子"


def test_shichen_23_is_zi_with_yajashi_warning():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, is_boundary = get_shichen(23, 0)
    assert branch == "子"
    assert is_boundary is True


def test_shichen_23_30_still_zi():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, is_boundary = get_shichen(23, 30)
    assert branch == "子"
    assert is_boundary is True


def test_shichen_noon_is_wu():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, is_boundary = get_shichen(12, 0)
    assert branch == "午"
    assert is_boundary is False


def test_shichen_early_morning():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, _ = get_shichen(3, 30)
    assert branch == "寅"


def test_shichen_22_is_hai():
    from hermes_ext.fortune_oracle.bazi_reference import get_shichen
    branch, is_boundary = get_shichen(22, 0)
    assert branch == "亥"
    assert is_boundary is False


# ---------------------------------------------------------------------------
# 5. 오행 균형 helper
# ---------------------------------------------------------------------------

def test_element_balance_missing():
    from hermes_ext.fortune_oracle.bazi_reference import analyze_element_balance
    result = analyze_element_balance({"목": 3, "화": 2, "토": 0, "금": 1, "수": 2})
    assert "토" in result["missing"]
    assert "토" in result["balance_note"]


def test_element_balance_even():
    from hermes_ext.fortune_oracle.bazi_reference import analyze_element_balance
    result = analyze_element_balance({"목": 2, "화": 2, "토": 2, "금": 2, "수": 2})
    assert "고르게" in result["balance_note"]


def test_element_balance_dominant():
    from hermes_ext.fortune_oracle.bazi_reference import analyze_element_balance
    result = analyze_element_balance({"목": 5, "화": 1, "토": 1, "금": 1, "수": 0})
    assert result["dominant"] == "목"


def test_element_balance_empty():
    from hermes_ext.fortune_oracle.bazi_reference import analyze_element_balance
    result = analyze_element_balance({})
    assert result["balance_note"] == "오행 정보 없음"


# ---------------------------------------------------------------------------
# 6. 월간 간지 도출
# ---------------------------------------------------------------------------

def test_month_ganzhi_jia_year_yin_month():
    """甲년 寅月 → 丙寅"""
    from hermes_ext.fortune_oracle.bazi_reference import get_month_ganzhi
    result = get_month_ganzhi("甲", "寅")
    assert result == "丙寅"


def test_month_ganzhi_jia_year_mao_month():
    """甲년 卯月 → 丁卯"""
    from hermes_ext.fortune_oracle.bazi_reference import get_month_ganzhi
    result = get_month_ganzhi("甲", "卯")
    assert result == "丁卯"


def test_month_ganzhi_ji_year_same_as_jia():
    """己년은 甲년과 같은 월간 도출"""
    from hermes_ext.fortune_oracle.bazi_reference import get_month_ganzhi
    assert get_month_ganzhi("己", "寅") == get_month_ganzhi("甲", "寅")


def test_month_ganzhi_unknown_returns_none():
    from hermes_ext.fortune_oracle.bazi_reference import get_month_ganzhi
    result = get_month_ganzhi("X", "寅")
    assert result is None


# ---------------------------------------------------------------------------
# 7. interpreter 통합 테스트
# ---------------------------------------------------------------------------

def _sample_eight_char():
    return {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}


def _sample_elements():
    return {"목": 3, "화": 2, "토": 1, "금": 1, "수": 1}


def test_interpret_ok():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert result.ok is True


def test_interpret_has_day_master_note():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert len(result.day_master_note) > 0
    assert "丙" in result.day_master_note or "병" in result.day_master_note


def test_interpret_has_element_balance():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert len(result.element_balance_note) > 0


def test_interpret_has_hidden_stems():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert "寅" in result.hidden_stems_note


def test_interpret_ten_god_notes_nonempty():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert len(result.ten_god_notes) >= 1


def test_interpret_yajashi_warning_23h():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(
        _sample_eight_char(), _sample_elements(), birth_hour=23, birth_minute=30
    )
    assert len(result.yajashi_warning) > 0
    assert "야자시" in result.yajashi_warning


def test_interpret_no_yajashi_for_noon():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(
        _sample_eight_char(), _sample_elements(), birth_hour=12
    )
    assert result.yajashi_warning == ""


def test_interpret_has_disclaimer():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    assert "오락" in result.disclaimer
    assert "자기성찰" in result.disclaimer


def test_interpret_no_eight_char():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(None, _sample_elements())
    assert result.ok is False


def test_to_telegram_text_includes_disclaimer():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    text = result.to_telegram_text()
    assert "오락" in text
    assert "의학" in text


# ---------------------------------------------------------------------------
# 8. 안전 금지 패턴 미포함
# ---------------------------------------------------------------------------

def test_no_unsafe_advice_in_telegram_text():
    from hermes_ext.fortune_oracle.bazi_reference_interpreter import interpret_bazi_reference
    result = interpret_bazi_reference(_sample_eight_char(), _sample_elements())
    text = result.to_telegram_text(include_ten_gods=True)
    # 확정 예언/진단/투자/법률 지시 금지
    forbidden = [
        "반드시 죽", "사망", "파산", "이혼할 것",
        "투자하세요", "소송에서", "의학적으로 진단",
        "당신의 수명", "불치병",
    ]
    for pat in forbidden:
        assert pat not in text, f"Forbidden pattern found: '{pat}'"


def test_traits_no_hard_predictions():
    """traits/tendency 필드에 확정적 예언 없음."""
    from hermes_ext.fortune_oracle.bazi_reference import HEAVENLY_STEMS
    forbidden = ["반드시", "확실히 죽", "파산", "이혼"]
    for stem, data in HEAVENLY_STEMS.items():
        for field in ["traits", "tendency"]:
            val = data.get(field, "")
            for pat in forbidden:
                assert pat not in val, f"{stem}.{field} contains '{pat}'"


# ---------------------------------------------------------------------------
# 9. 외부 import 없음 (정적)
# ---------------------------------------------------------------------------

def test_no_external_api_in_reference():
    """bazi_reference.py에 외부 LLM/network client import 없음."""
    import hermes_ext.fortune_oracle.bazi_reference as ref
    forbidden_names = {"openai", "anthropic", "requests", "httpx", "aiohttp"}
    module_vars = set(vars(ref).keys())
    overlap = forbidden_names & module_vars
    assert not overlap, f"Forbidden imports found: {overlap}"


def test_no_external_api_in_interpreter():
    import hermes_ext.fortune_oracle.bazi_reference_interpreter as interp
    forbidden_names = {"openai", "anthropic", "requests", "httpx", "aiohttp"}
    module_vars = set(vars(interp).keys())
    overlap = forbidden_names & module_vars
    assert not overlap, f"Forbidden imports found: {overlap}"


# ---------------------------------------------------------------------------
# 10. Attribution/라이선스 메타
# ---------------------------------------------------------------------------

def test_attribution_present():
    from hermes_ext.fortune_oracle.bazi_reference import ATTRIBUTION
    assert "source_repo" in ATTRIBUTION
    assert "jinchenma94" in ATTRIBUTION["source_repo"]
    assert ATTRIBUTION["license"] == "MIT"
    assert "disclaimer" in ATTRIBUTION


# ---------------------------------------------------------------------------
# 11. 기존 명령 회귀 없음
# ---------------------------------------------------------------------------

def test_regression_life_kline_unit():
    from hermes_ext.fortune_oracle.kline import render_life_kline
    result = render_life_kline(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"})
    assert "12개월" in result
    assert "생성할 수 없습니다" in render_life_kline()


def test_regression_kline_card_png():
    from hermes_ext.fortune_oracle.chart_renderer import render_month_card_png
    import tempfile
    from pathlib import Path
    out = Path(tempfile.mktemp(suffix=".png"))
    try:
        result = render_month_card_png(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, output_path=out)
        assert result.exists()
        assert result.stat().st_size > 0
    finally:
        out.unlink(missing_ok=True)


def test_regression_design_tokens_valid():
    from hermes_ext.fortune_oracle.design_tokens import validate_tokens
    errors = validate_tokens()
    assert errors == [], f"Token errors: {errors}"
