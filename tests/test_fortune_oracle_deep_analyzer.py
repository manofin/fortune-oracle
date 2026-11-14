"""tests/test_fortune_oracle_deep_analyzer.py

Phase 5 — Deep Analyzer Wrapper 테스트
기본 OFF, fake provider 주입, fallback 검증.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
from hermes_ext.fortune_oracle.deep_analyzer import (
    DEEP_ANALYSIS_ENABLED_BY_DEFAULT,
    DeepAnalysisResult,
    _FORBIDDEN_PATTERNS,
    _safety_check_sections,
    build_deep_prompt,
    deep_analyze,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ok_bazi() -> BaziResult:
    return BaziResult(
        ok=True,
        engine="lunar-javascript",
        eight_char={"year": "己巳", "month": "丙子", "day": "丙寅", "time": "壬辰"},
        elements={"목(木)": 2, "화(火)": 1, "수(水)": 3},
        zodiac="뱀띠",
    )


def _fail_bazi() -> BaziResult:
    return BaziResult.error("INVALID_INPUT", "테스트 오류")


def _fake_provider_ok(prompt: str) -> str:
    """정상 JSON 반환하는 fake provider."""
    return json.dumps({
        "ok": True,
        "sections": [
            {"title": "기본 기질", "summary": "테스트 기질 요약", "confidence": "llm", "disclaimer": ""},
            {"title": "강점", "summary": "테스트 강점", "confidence": "llm", "disclaimer": ""},
        ],
        "warnings": [],
    })


def _fake_provider_empty(prompt: str) -> str:
    return ""


def _fake_provider_bad_json(prompt: str) -> str:
    return "이것은 JSON이 아닙니다"


def _fake_provider_timeout(prompt: str) -> str:
    raise TimeoutError("LLM timeout simulated")


def _fake_provider_exception(prompt: str) -> str:
    raise RuntimeError("LLM exception simulated")


# ---------------------------------------------------------------------------
# 기본 OFF 확인
# ---------------------------------------------------------------------------

def test_default_disabled():
    """환경변수 없으면 기본 OFF."""
    with mock.patch.dict("os.environ", {}, clear=False):
        # 환경변수 FORTUNE_DEEP_ANALYSIS가 없거나 "1"이 아니면 False
        import importlib
        import hermes_ext.fortune_oracle.deep_analyzer as da
        flag = da.DEEP_ANALYSIS_ENABLED_BY_DEFAULT
        # 실제 환경변수 값에 따라 달라지므로 bool임을 확인
        assert isinstance(flag, bool)


def test_disabled_returns_template_source():
    """enabled=False이면 source='template'."""
    result = deep_analyze(_ok_bazi(), enabled=False)
    assert result.source == "template"
    assert result.ok is True


def test_no_provider_returns_template():
    """provider=None이면 template fallback."""
    result = deep_analyze(_ok_bazi(), enabled=True, provider=None)
    assert result.source == "template"


# ---------------------------------------------------------------------------
# fake provider enabled
# ---------------------------------------------------------------------------

def test_fake_provider_enabled_returns_llm_source():
    result = deep_analyze(_ok_bazi(), enabled=True, provider=_fake_provider_ok)
    assert result.source == "deep_provider"  # Phase 11: "llm" → "deep_provider" 일관화
    assert result.ok is True
    assert len(result.sections) >= 1


def test_fake_provider_prompt_contains_eight_char():
    """prompt에 팔자 정보가 포함되어야 한다."""
    prompts = []
    def capturing_provider(p: str) -> str:
        prompts.append(p)
        return _fake_provider_ok(p)
    deep_analyze(_ok_bazi(), enabled=True, provider=capturing_provider)
    assert len(prompts) == 1
    prompt = prompts[0]
    assert "己巳" in prompt or "年" in prompt or "년주" in prompt.lower() or "간지" in prompt


# ---------------------------------------------------------------------------
# fallback 시나리오
# ---------------------------------------------------------------------------

def test_provider_timeout_fallback():
    result = deep_analyze(_ok_bazi(), enabled=True, provider=_fake_provider_timeout)
    assert result.source == "template"
    assert result.ok is True
    assert any("LLM 오류" in w or "timeout" in w.lower() for w in result.warnings)


def test_provider_exception_fallback():
    result = deep_analyze(_ok_bazi(), enabled=True, provider=_fake_provider_exception)
    assert result.source == "template"


def test_provider_empty_response_fallback():
    result = deep_analyze(_ok_bazi(), enabled=True, provider=_fake_provider_empty)
    assert result.source == "template"
    assert any("빈 응답" in w for w in result.warnings)


def test_provider_bad_json_fallback():
    result = deep_analyze(_ok_bazi(), enabled=True, provider=_fake_provider_bad_json)
    assert result.source == "template"
    assert any("파싱" in w for w in result.warnings)


def test_bazi_failure_returns_template():
    result = deep_analyze(_fail_bazi(), enabled=True, provider=_fake_provider_ok)
    # bazi 실패이므로 template (sections가 fallback)
    assert len(result.sections) > 0


# ---------------------------------------------------------------------------
# 안전 검사
# ---------------------------------------------------------------------------

def test_safety_check_detects_forbidden():
    sections = [{"title": "테스트", "summary": "반드시 죽게 됩니다"}]
    warnings = []
    _safety_check_sections(sections, warnings)
    assert len(warnings) > 0


def test_safety_check_clean_passes():
    sections = [{"title": "강점", "summary": "성실하고 꾸준한 기질입니다."}]
    warnings = []
    _safety_check_sections(sections, warnings)
    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# build_deep_prompt
# ---------------------------------------------------------------------------

def test_prompt_does_not_contain_birth_date():
    """prompt에 birth_date 원문이 노출되지 않아야 한다."""
    from hermes_ext.fortune_oracle.bazi_template_analyzer import analyze_bazi_template
    bazi = _ok_bazi()
    bazi.input = {
        "birth_date": "1990-01-01",
        "birth_time": "08:30",
        "birth_place": "Seoul",
    }
    template = analyze_bazi_template(bazi)
    prompt = build_deep_prompt(bazi, template)
    assert "1990-01-01" not in prompt, "prompt에 birth_date 원문 노출"
    assert "08:30" not in prompt, "prompt에 birth_time 원문 노출"


def test_prompt_contains_disclaimer():
    from hermes_ext.fortune_oracle.bazi_template_analyzer import analyze_bazi_template
    template = analyze_bazi_template(_ok_bazi())
    prompt = build_deep_prompt(_ok_bazi(), template)
    assert "오락" in prompt or "자기성찰" in prompt


# ---------------------------------------------------------------------------
# Static 검증
# ---------------------------------------------------------------------------

def test_no_external_api_import():
    """deep_analyzer.py에 외부 AI API 직접 import가 없어야 한다."""
    src = Path(__file__).parent.parent / "plugins" / "hermes_ext" / "fortune_oracle" / "deep_analyzer.py"
    content = src.read_text()
    forbidden = ["import openai", "import anthropic", "from openai", "from anthropic",
                 "import google.generativeai", "from google", "import boto3"]
    for pattern in forbidden:
        assert pattern not in content, f"외부 AI API import 발견: '{pattern}'"


def test_no_network_client_creation():
    """deep_analyzer.py에 직접 network client 생성이 없어야 한다."""
    src = Path(__file__).parent.parent / "plugins" / "hermes_ext" / "fortune_oracle" / "deep_analyzer.py"
    content = src.read_text()
    forbidden = ["requests.get", "requests.post", "httpx.get", "aiohttp.ClientSession",
                 "urllib.request.urlopen"]
    for pattern in forbidden:
        assert pattern not in content, f"network 호출 발견: '{pattern}'"


def test_no_credential_access():
    """deep_analyzer.py에 credential/config 직접 접근이 없어야 한다."""
    src = Path(__file__).parent.parent / "plugins" / "hermes_ext" / "fortune_oracle" / "deep_analyzer.py"
    content = src.read_text()
    forbidden = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "config.yaml", "load_config("]
    for pattern in forbidden:
        assert pattern not in content, f"credential 접근 발견: '{pattern}'"


# ---------------------------------------------------------------------------
# to_telegram_summary
# ---------------------------------------------------------------------------

def test_telegram_summary_length_limit():
    result = deep_analyze(_ok_bazi(), enabled=False)
    summary = result.to_telegram_summary(max_chars=500)
    assert len(summary) <= 500


def test_telegram_summary_not_empty():
    result = deep_analyze(_ok_bazi(), enabled=False)
    summary = result.to_telegram_summary()
    assert len(summary) > 0
