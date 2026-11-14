"""Tests for Fortune Oracle deep_review.py (Phase 18)"""

import sys
import types
import pytest
from pathlib import Path

# ensure plugins path is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))


# ---------------------------------------------------------------------------
# Guard: no external LLM client imports at module level
# ---------------------------------------------------------------------------

def test_no_external_api_import():
    """deep_review 모듈이 외부 LLM 라이브러리를 import 하지 않는다."""
    forbidden = {"openai", "anthropic", "google.generativeai", "cohere"}
    import importlib
    # import the module fresh
    mod_name = "hermes_ext.fortune_oracle.deep_review"
    if mod_name in sys.modules:
        mod = sys.modules[mod_name]
    else:
        import hermes_ext.fortune_oracle.deep_review as mod
    for lib in forbidden:
        assert lib not in sys.modules, f"{lib} should not be imported"


def test_no_client_created_on_import():
    """모듈 import 시 client 객체가 생성되지 않는다 (side-effect 없음)."""
    import hermes_ext.fortune_oracle.deep_review as mod
    # If no exception and no client attribute, we're good
    assert not hasattr(mod, "_client")
    assert not hasattr(mod, "_llm_client")


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

import hermes_ext.fortune_oracle.deep_review as dr


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_review_mode_status_exists():
    assert hasattr(dr, "REVIEW_MODE_STATUS")
    assert isinstance(dr.REVIEW_MODE_STATUS, str)
    assert "PENDING" in dr.REVIEW_MODE_STATUS


def test_activation_runbook_exists():
    assert hasattr(dr, "ACTIVATION_RUNBOOK")
    rb = dr.ACTIVATION_RUNBOOK
    assert isinstance(rb, dict)
    assert "env_var" in rb
    assert "provider_required" in rb
    assert rb["provider_required"] is True
    assert "timeout_seconds" in rb
    assert rb["timeout_seconds"] == 30
    assert "unsafe_filter" in rb
    assert rb["unsafe_filter"] is True
    assert "live_test_required" in rb


# ---------------------------------------------------------------------------
# analyze_deep_review — fallback paths
# ---------------------------------------------------------------------------

def test_default_off_returns_fallback():
    """enabled=False → fallback 반환"""
    result = dr.analyze_deep_review({}, enabled=False, provider=None)
    assert result["source"] == "template"
    assert result["sections"] == []
    assert any("fallback" in w for w in result["warnings"])


def test_provider_none_returns_fallback():
    """provider=None, enabled=True → fallback 반환"""
    result = dr.analyze_deep_review({}, enabled=True, provider=None)
    assert result["source"] == "template"
    assert any("fallback" in w for w in result["warnings"])


def test_fake_provider_success():
    """정상 provider → sections 있음, source=deep_provider"""
    import json

    def fake_provider(prompt: str) -> str:
        return json.dumps({
            "sections": [{"title": "기본 기질", "summary": "강한 목 기운", "reflection_question": ""}],
            "reflection_question": "오늘 어떤 선택을 하셨나요?",
            "disclaimer": "오락 용도",
            "source": "deep_provider",
            "warnings": [],
        })

    result = dr.analyze_deep_review({}, enabled=True, provider=fake_provider)
    assert result["source"] == "deep_provider"
    assert len(result["sections"]) >= 1


def test_fake_provider_timeout_returns_fallback():
    """provider가 30초 초과 → fallback 반환"""
    import time

    def slow_provider(prompt: str) -> str:
        time.sleep(60)
        return "{}"

    # patch timeout to 1s for test speed
    original_timeout = 30

    def patched_call(provider, prompt, timeout):
        return dr._call_provider_with_timeout(provider, prompt, timeout=1)

    result = dr._call_provider_with_timeout(slow_provider, "", timeout=1)
    assert result is None


def test_analyze_deep_review_timeout_fallback(monkeypatch):
    """analyze_deep_review: timeout → fallback"""
    import time

    def slow_provider(prompt: str) -> str:
        time.sleep(60)
        return "{}"

    monkeypatch.setattr(dr, "_call_provider_with_timeout",
                        lambda p, prompt, timeout: None)

    result = dr.analyze_deep_review({}, enabled=True, provider=slow_provider)
    assert result["source"] == "template"
    assert any("timeout" in w or "fallback" in w for w in result["warnings"])


def test_fake_provider_invalid_json_returns_fallback():
    """provider가 invalid JSON → fallback 반환"""
    def bad_provider(prompt: str) -> str:
        return "NOT JSON {{{"

    result = dr.analyze_deep_review({}, enabled=True, provider=bad_provider)
    assert result["source"] == "template"
    assert any("fallback" in w for w in result["warnings"])


def test_unsafe_phrase_returns_fallback():
    """provider 출력에 unsafe phrase → fallback"""
    import json

    def unsafe_provider(prompt: str) -> str:
        return json.dumps({
            "sections": [{"title": "경고", "summary": "반드시 조심해야 합니다", "reflection_question": ""}],
            "reflection_question": "",
            "disclaimer": "",
            "source": "deep_provider",
            "warnings": [],
        })

    result = dr.analyze_deep_review({}, enabled=True, provider=unsafe_provider)
    assert result["source"] == "template"
    assert any("unsafe" in w or "fallback" in w for w in result["warnings"])


def test_source_deep_provider_on_success():
    """정상 provider → source == 'deep_provider'"""
    import json

    def ok_provider(prompt: str) -> str:
        return json.dumps({
            "sections": [{"title": "흐름", "summary": "안전한 요약", "reflection_question": "무엇을 점검할까요?"}],
            "reflection_question": "...",
            "disclaimer": "오락",
            "source": "deep_provider",
            "warnings": [],
        })

    result = dr.analyze_deep_review({}, enabled=True, provider=ok_provider)
    assert result["source"] == "deep_provider"


def test_source_template_on_fallback():
    """fallback → source == 'template'"""
    result = dr.analyze_deep_review({}, enabled=False)
    assert result["source"] == "template"


# ---------------------------------------------------------------------------
# build_deep_review_context — privacy checks
# ---------------------------------------------------------------------------

def _make_bazi():
    from types import SimpleNamespace
    return SimpleNamespace(
        eight_char={"year": "甲子", "month": "乙丑", "day": "丙寅", "time": "丁卯"},
        season="봄",
        elements={"목": 3, "화": 2},
    )


def _make_profile():
    return {
        "display_name": "테스트",
        "birth_date": "1990-01-01",
        "birth_time": "08:00",
        "name_hanja": "試驗",
    }


def test_build_context_no_birth_date():
    ctx = dr.build_deep_review_context(
        _make_profile(), _make_bazi(), None, None, None, None
    )
    assert "birth_date" not in str(ctx)
    assert "1990-01-01" not in str(ctx)


def test_build_context_no_birth_time():
    ctx = dr.build_deep_review_context(
        _make_profile(), _make_bazi(), None, None, None, None
    )
    assert "birth_time" not in str(ctx)
    assert "08:00" not in str(ctx)


def test_build_context_no_name_hanja():
    ctx = dr.build_deep_review_context(
        _make_profile(), _make_bazi(), None, None, None, None
    )
    assert "name_hanja" not in str(ctx)
    assert "試驗" not in str(ctx)


def test_build_context_has_required_keys():
    ctx = dr.build_deep_review_context(
        _make_profile(), _make_bazi(), None, None, None, None
    )
    for key in ("profile_summary", "eight_char", "season", "elements",
                "relation_summary", "dayun_summary", "yongshen_summary"):
        assert key in ctx, f"missing key: {key}"


def test_build_context_eight_char_present():
    ctx = dr.build_deep_review_context(
        _make_profile(), _make_bazi(), None, None, None, None
    )
    assert "甲子" in ctx["eight_char"]
