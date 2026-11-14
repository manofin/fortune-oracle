#!/usr/bin/env python3
from _fo_paths import hermes_path, repo_path, repo_plugin_path
"""Fortune Oracle — _handle_bazi_trace handler safety/smoke tests (Phase 40 final gate).

Tests the actual plugin handler outputs, not just the library layer.
Covers:
- raw dataclass repr leakage
- traceback leakage
- raw dict/list dump
- 건강/작명/개명/용신 단정 문구
- 경험적 참고/자기성찰용 disclaimer 존재
- profile/input 부족 시 crash 없이 안내
- /bazi_trace, /팔자강약, /show_profile handler smoke
"""

import pytest
from importlib.util import spec_from_file_location, module_from_spec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _load_plugin():
    """Load the fortune-oracle plugin module directly."""
    spec = spec_from_file_location(
        "fortune_oracle_plugin",
        repo_plugin_path("__init__.py"),
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def plugin():
    return _load_plugin()


# ---------------------------------------------------------------------------
# _handle_bazi_trace: no-profile path
# ---------------------------------------------------------------------------

class TestBaziTraceNoProfile:
    def test_no_profile_returns_safe_message(self, plugin):
        """프로필 없을 때 crash 없이 안내 메시지 반환."""
        # store를 비운 상태에서 호출
        result = plugin._handle_bazi_trace("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_profile_no_raw_repr(self, plugin):
        """프로필 없을 때 raw repr 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "BaziElementStrengthTrace(",
            "ElementContribution(",
            "YongshenResult(",
            "dataclass",
            "ok=True",
            "ok=False",
        ]
        for pattern in forbidden:
            assert pattern not in result, f"Raw repr leak: {pattern}"

    def test_no_profile_no_traceback(self, plugin):
        """프로필 없을 때 traceback 없음."""
        result = plugin._handle_bazi_trace("")
        assert "Traceback" not in result
        assert 'File "' not in result

    def test_no_profile_no_raw_dump(self, plugin):
        """프로필 없을 때 raw dict/list dump 없음."""
        result = plugin._handle_bazi_trace("")
        stripped = result.strip()
        assert not (stripped.startswith("{") and stripped.endswith("}"))
        assert not (stripped.startswith("[") and stripped.endswith("]"))

    def test_no_profile_no_assertions(self, plugin):
        """프로필 없을 때 용신/작명/건강 단정 문구 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "용신은 ~입니다", "용신이 ~입니다", "용신 판정:",
            "용신은 ~가 맞습니다",
            "이름을 바꿔야", "이름을 바꾸", "개명", "작명",
            "건강상", "건강 주의", "건강 위험", "병", "질병",
            "혼인", "결혼",
        ]
        for word in forbidden:
            assert word not in result, f"Assertion found: {word}"

    def test_no_profile_no_crash(self, plugin):
        """프로필 없을 때 예외 발생 없음 (fail-open)."""
        try:
            result = plugin._handle_bazi_trace("")
            assert isinstance(result, str)
        except Exception:
            pytest.fail("Crashed on no-profile input")


# ---------------------------------------------------------------------------
# _handle_bazi_trace: with-profile path (smoke)
# ---------------------------------------------------------------------------

class TestBaziTraceWithProfile:
    def test_returns_text_not_crash(self, plugin):
        """프로필 존재 시 crash 없이 텍스트 반환."""
        result = plugin._handle_bazi_trace("")
        assert isinstance(result, str)

    def test_output_no_raw_repr(self, plugin):
        """프로필 존재 시 raw dataclass repr 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "BaziElementStrengthTrace(",
            "ElementContribution(",
            "YongshenResult(",
            "dataclass",
            "default_factory",
            "ok=True",
            "ok=False",
            "warnings=[",
        ]
        for pattern in forbidden:
            assert pattern not in result, f"Raw repr leak: {pattern}"

    def test_output_no_traceback(self, plugin):
        """프로필 존재 시 traceback 없음."""
        result = plugin._handle_bazi_trace("")
        assert "Traceback" not in result
        assert 'File "' not in result

    def test_output_no_raw_dump(self, plugin):
        """프로필 존재 시 raw dict/list dump 없음."""
        result = plugin._handle_bazi_trace("")
        # 첫 줄이 { 또는 [로 시작하면 raw dump로 간주
        first_line = result.strip().split("\n")[0]
        assert not (first_line.startswith("{") and first_line.endswith("}"))
        assert not (first_line.startswith("[") and first_line.endswith("]"))

    def test_output_no_assertions(self, plugin):
        """프로필 존재 시 용신/작명/건강 단정 문구 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "용신은 ~입니다", "용신이 ~입니다", "용신 판정:",
            "용신은 ~가 맞습니다",
            "이름을 바꿔야", "이름을 바꾸", "개명", "작명",
            "건강상", "건강 주의", "건강 위험", "병", "질병",
            "혼인", "결혼",
        ]
        for word in forbidden:
            assert word not in result, f"Assertion found: {word}"

    def test_output_contains_disclaimer(self, plugin):
        """출력에 자기성찰/참고용 disclaimer 존재."""
        result = plugin._handle_bazi_trace("")
        # 자기성찰, 참고, 확정적 판단 아님 등의 문구가 포함되어야 함
        disclaimer_keywords = [
            "자기성찰", "참고", "확정적 판단", "판정이 아닙니다",
        ]
        found = any(kw in result for kw in disclaimer_keywords)
        assert found, f"No disclaimer found. Output: {result[:200]}"

    def test_output_contains_element_strength(self, plugin):
        """출력에 오행 강약 관련 내용 존재."""
        result = plugin._handle_bazi_trace("")
        # 오행 관련 키워드가 포함되어야 함
        element_keywords = ["목", "화", "토", "금", "수"]
        found = any(kw in result for kw in element_keywords)
        assert found, f"No element content found. Output: {result[:200]}"

    def test_output_no_health_marriage_naming(self, plugin):
        """출력에 건강/혼인/작명 단정 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "건강", "병", "질병", "혼인", "결혼",
            "작명", "개명", "이름 바꾸", "이름을",
        ]
        for word in forbidden:
            assert word not in result, f"Forbidden word found: {word}"

    def test_output_no_yongshen_assertion(self, plugin):
        """출력에 용신 단정 문구 없음."""
        result = plugin._handle_bazi_trace("")
        forbidden = [
            "용신은 ~입니다", "용신이 ~입니다",
            "용신 판정:", "용신은 ~가 맞습니다",
        ]
        for phrase in forbidden:
            assert phrase not in result, f"Yongshen assertion: {phrase}"

    def test_output_not_empty(self, plugin):
        """프로필 존재 시 비어 있지 않은 출력 반환."""
        result = plugin._handle_bazi_trace("")
        stripped = result.strip()
        assert len(stripped) > 50, f"Output too short: {stripped}"

    def test_output_contains_empirical_reference(self, plugin):
        """출력에 '경험적' 또는 '참고' 등 오행 강도가 확정적이지 않음을 나타내는 문구 존재."""
        result = plugin._handle_bazi_trace("")
        empirical_keywords = [
            "경험적", "참고", "판정이 아닙니다", "확정적 판단이 아닙니다",
            "자기성찰",
        ]
        found = any(kw in result for kw in empirical_keywords)
        assert found, f"No empirical reference found. Output: {result[:300]}"


# ---------------------------------------------------------------------------
# /show_profile handler smoke
# ---------------------------------------------------------------------------

class TestShowProfileHandlerSmoke:
    def test_no_crash(self, plugin):
        """/show_profile handler crash 없이 반환."""
        try:
            result = plugin._handle_show_profile("")
            assert isinstance(result, str)
        except Exception:
            pytest.fail("Crashed on show_profile")

    def test_no_raw_repr(self, plugin):
        """/show_profile 출력에 raw repr 없음."""
        result = plugin._handle_show_profile("")
        forbidden = [
            "BaziElementStrengthTrace(",
            "ElementContribution(",
            "YongshenResult(",
            "dataclass",
            "ok=True",
            "ok=False",
            "warnings=[",
        ]
        for pattern in forbidden:
            assert pattern not in result, f"Raw repr leak: {pattern}"

    def test_no_traceback(self, plugin):
        """/show_profile 출력에 traceback 없음."""
        result = plugin._handle_show_profile("")
        assert "Traceback" not in result
        assert 'File "' not in result

    def test_no_raw_dump(self, plugin):
        """/show_profile 출력에 raw dict/list dump 없음."""
        result = plugin._handle_show_profile("")
        first_line = result.strip().split("\n")[0]
        assert not (first_line.startswith("{") and first_line.endswith("}"))
        assert not (first_line.startswith("[") and first_line.endswith("]"))

    def test_no_assertions(self, plugin):
        """/show_profile 출력에 용신/작명/건강 단정 문구 없음."""
        result = plugin._handle_show_profile("")
        forbidden = [
            "용신은 ~입니다", "용신이 ~입니다", "용신 판정:",
            "용신은 ~가 맞습니다",
            "이름을 바꿔야", "이름을 바꾸", "개명", "작명",
            "건강상", "건강 주의", "건강 위험", "병", "질병",
            "혼인", "결혼",
        ]
        for word in forbidden:
            assert word not in result, f"Assertion found: {word}"

    def test_contains_disclaimer(self, plugin):
        """/show_profile 출력에 자기성찰/오락용 disclaimer 존재."""
        result = plugin._handle_show_profile("")
        disclaimer_keywords = [
            "오락", "자기성찰", "참고", "판단이 아닙니다",
            "결정", "지시하지",
        ]
        found = any(kw in result for kw in disclaimer_keywords)
        assert found, f"No disclaimer found. Output: {result[:300]}"


# ---------------------------------------------------------------------------
# /bazi_trace and /팔자강약 alias equivalence
# ---------------------------------------------------------------------------

class TestBaziTraceAliasEquivalence:
    def test_both_aliases_same_handler(self, plugin):
        """bazi-trace와 팔자강약이 같은 handler를 가리키는 확인."""
        init_py = open(repo_plugin_path("__init__.py")).read()
        assert '("bazi-trace",       _handle_bazi_trace' in init_py
        assert '("팔자강약",          _handle_bazi_trace' in init_py

    def test_bazi_trace_alias_registered(self, plugin):
        """bazi-trace alias가 register()에 등록됨."""
        init_py = open(repo_plugin_path("__init__.py")).read()
        assert '("bazi-trace",       _handle_bazi_trace' in init_py

    def test_korean_alias_registered(self, plugin):
        """팔자강약 alias가 register()에 등록됨."""
        init_py = open(repo_plugin_path("__init__.py")).read()
        assert '("팔자강약",          _handle_bazi_trace' in init_py
