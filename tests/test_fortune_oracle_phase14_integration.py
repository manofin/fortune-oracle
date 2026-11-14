"""Tests — Phase 14 integration: show_profile + deep context privacy.

최소 10개 테스트 (show_profile 5+ / deep context privacy 5+).
"""
from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path("plugins"))

import pytest
from hermes_ext.fortune_oracle.bazi_relation_interpreter import build_show_profile_relation_note
from hermes_ext.fortune_oracle.dayun_interpreter import build_show_profile_dayun_note
from hermes_ext.fortune_oracle.yongshen_interpreter import build_show_profile_yongshen_note

_SENSITIVE_FIELDS = ["birth_date", "birth_time", "name_hanja"]
_UNSAFE_PHRASES = [
    "반드시 파산합니다",
    "피할 수 없는 파국",
    "이혼한다",
    "사고가 난다",
    "병이 생긴다",
]

_EC = {"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"}

# ---------------------------------------------------------------------------
# 1. show_profile integration
# ---------------------------------------------------------------------------

def test_show_profile_relation_note_header():
    """relation note에 헤더 포함."""
    note = build_show_profile_relation_note(_EC)
    assert "관계 흐름" in note

def test_show_profile_dayun_note_gender_unknown_header():
    """dayun note (gender unknown)에 대운 헤더 포함."""
    note = build_show_profile_dayun_note(_EC, gender=None)
    assert "대운 흐름" in note

def test_show_profile_yongshen_note_header():
    """yongshen note에 용신 헤더 포함."""
    note = build_show_profile_yongshen_note(_EC)
    assert "용신" in note

def test_show_profile_combined_total_lines_under_limit():
    """관계+대운+용신 note 합쳐도 15줄 이내 (compact)."""
    r_note = build_show_profile_relation_note(_EC, max_lines=2)
    d_note = build_show_profile_dayun_note(_EC, gender=None, max_lines=2)
    y_note = build_show_profile_yongshen_note(_EC, max_lines=2)
    combined = r_note + d_note + y_note
    lines = [l for l in combined.split("\n") if l.strip()]
    assert len(lines) <= 15

def test_show_profile_fail_open_none_ec():
    """eight_char=None → 각 note 빈 문자열 반환 (fail-open)."""
    assert build_show_profile_relation_note(None) == ""
    assert build_show_profile_dayun_note(None) == ""
    assert build_show_profile_yongshen_note(None) == ""

# ---------------------------------------------------------------------------
# 2. deep context privacy tests
# ---------------------------------------------------------------------------

def test_deep_prompt_no_sensitive_fields():
    """build_deep_prompt에 민감정보 포함 안 됨."""
    from hermes_ext.fortune_oracle.deep_analyzer import build_deep_prompt
    from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
    from hermes_ext.fortune_oracle.bazi_template_analyzer import (
        TemplateAnalysisResult,
        TemplateSection,
    )

    bazi = BaziResult(
        ok=True,
        eight_char=_EC,
        elements={"목": 2, "화": 2, "토": 2, "금": 1, "수": 1},
        zodiac="쥐",
    )
    tmpl = TemplateAnalysisResult(ok=True, sections=[
        TemplateSection(title="기본 기질", summary="요약 내용", confidence="template"),
    ])
    prompt = build_deep_prompt(bazi, tmpl)
    for field in _SENSITIVE_FIELDS:
        assert field not in prompt, f"Sensitive field in prompt: {field}"

def test_deep_prompt_with_phase14_summaries():
    """Phase 14 summary가 prompt에 포함됨."""
    from hermes_ext.fortune_oracle.deep_analyzer import build_deep_prompt
    from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
    from hermes_ext.fortune_oracle.bazi_template_analyzer import (
        TemplateAnalysisResult,
        TemplateSection,
    )

    bazi = BaziResult(
        ok=True,
        eight_char=_EC,
        elements={"목": 2, "화": 2, "토": 2, "금": 1, "수": 1},
        zodiac="쥐",
    )
    tmpl = TemplateAnalysisResult(ok=True, sections=[])
    prompt = build_deep_prompt(
        bazi, tmpl,
        relation_summary="子·丑 육합이 있음",
        dayun_summary="순행 대운 7세 시작",
        yongshen_summary="火木이 유리한 기운",
    )
    assert "관계 흐름 요약" in prompt
    assert "대운 흐름 요약" in prompt
    assert "용신 참고 요약" in prompt

def test_deep_prompt_phase14_summaries_no_raw_sensitive():
    """Phase 14 summary에 raw 민감정보가 포함되지 않음."""
    from hermes_ext.fortune_oracle.deep_analyzer import build_deep_prompt
    from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
    from hermes_ext.fortune_oracle.bazi_template_analyzer import TemplateAnalysisResult

    bazi = BaziResult(ok=True, eight_char=_EC, elements={}, zodiac="쥐")
    tmpl = TemplateAnalysisResult(ok=True, sections=[])
    # 요약에 민감정보가 들어오더라도 200자 제한 후 포함
    # 실제로 민감정보를 주입하려 해도 summarizer가 birth_date 같은 필드를 포함하지 않아야 함
    prompt = build_deep_prompt(bazi, tmpl, relation_summary="테스트 요약")
    for field in _SENSITIVE_FIELDS:
        assert field not in prompt

def test_deep_analyzer_default_off():
    """deep_analyzer default OFF 확인 (FORTUNE_DEEP_ANALYSIS 미설정 시)."""
    import os
    # 환경변수가 없거나 '1'이 아니면 False
    import importlib
    import hermes_ext.fortune_oracle.deep_analyzer as da
    env_val = os.environ.get("FORTUNE_DEEP_ANALYSIS", "")
    expected = env_val == "1"
    assert da.DEEP_ANALYSIS_ENABLED_BY_DEFAULT == expected

def test_deep_analyzer_no_external_imports():
    """deep_analyzer에 외부 AI API import 없음."""
    import ast, os
    path = os.path.join(
        repo_path("plugins/hermes_ext/fortune_oracle"),
        "deep_analyzer.py"
    )
    with open(path) as f:
        tree = ast.parse(f.read())
    forbidden_modules = {"openai", "anthropic", "google.generativeai", "ollama"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in getattr(node, "names", []):
                mod = alias.name.split(".")[0]
                assert mod not in forbidden_modules, f"Forbidden import: {alias.name}"
            if hasattr(node, "module") and node.module:
                mod = node.module.split(".")[0]
                assert mod not in forbidden_modules, f"Forbidden import from: {node.module}"
