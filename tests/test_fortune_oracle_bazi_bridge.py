"""tests/test_fortune_oracle_bazi_bridge.py

Phase 3 — Bazi Bridge 테스트
Node bridge + Python wrapper 정상/비정상 경로 검증.
"""

import json
import subprocess
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.bazi_bridge import (
    BaziInput,
    BaziResult,
    _BRIDGE_SCRIPT,
    _SCRIPTS_DIR,
    bridge_available,
    calculate_bazi,
    calculate_bazi_from_profile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _valid_input() -> BaziInput:
    return BaziInput(
        birth_date="1990-01-01",
        birth_time="08:30",
        birth_place="Seoul",
        timezone="Asia/Seoul",
        gender="unknown",
    )


def _valid_profile() -> dict:
    return {
        "birth_date": "1990-01-01",
        "birth_time": "08:30",
        "birth_place": "Seoul",
        "timezone": "Asia/Seoul",
        "gender": "unknown",
    }


# ---------------------------------------------------------------------------
# BaziInput 검증
# ---------------------------------------------------------------------------

def test_bazi_input_valid():
    assert _valid_input().validate() is None


def test_bazi_input_missing_date():
    b = BaziInput(birth_date="")
    assert b.validate() is not None


def test_bazi_input_bad_date_format():
    b = BaziInput(birth_date="01/01/1990")
    err = b.validate()
    assert err is not None
    assert "YYYY-MM-DD" in err


def test_bazi_input_bad_time_format():
    b = BaziInput(birth_date="1990-01-01", birth_time="8시30분")
    err = b.validate()
    assert err is not None


def test_bazi_input_invalid_hour():
    b = BaziInput(birth_date="1990-01-01", birth_time="25:00")
    err = b.validate()
    assert err is not None


def test_bazi_input_invalid_minute():
    b = BaziInput(birth_date="1990-01-01", birth_time="08:60")
    err = b.validate()
    assert err is not None


# ---------------------------------------------------------------------------
# bridge_available
# ---------------------------------------------------------------------------

def test_bridge_available_reflects_state():
    result = bridge_available()
    # 결과는 bool이어야 한다
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Node bridge 직접 호출 (Node 필요)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_valid_input_returns_ok_true():
    inp = json.dumps({
        "birth_date": "1990-01-01",
        "birth_time": "08:30",
        "birth_place": "Seoul",
        "timezone": "Asia/Seoul",
        "gender": "unknown",
    })
    r = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=inp,
        capture_output=True, text=True, timeout=10,
        cwd=str(_SCRIPTS_DIR),
    )
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert data["engine"] == "lunar-javascript"
    assert "eight_char" in data
    assert "year" in data["eight_char"]
    assert "month" in data["eight_char"]
    assert "day" in data["eight_char"]
    assert "time" in data["eight_char"]
    assert "zodiac" in data
    assert "disclaimer" in data


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_invalid_date_returns_ok_false():
    inp = json.dumps({"birth_date": "1990-13-01", "birth_time": "08:30"})
    r = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=inp, capture_output=True, text=True, timeout=10,
        cwd=str(_SCRIPTS_DIR),
    )
    data = json.loads(r.stdout)
    assert data["ok"] is False
    assert "error_code" in data


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_invalid_time_returns_ok_false():
    inp = json.dumps({"birth_date": "1990-01-01", "birth_time": "25:00"})
    r = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=inp, capture_output=True, text=True, timeout=10,
        cwd=str(_SCRIPTS_DIR),
    )
    data = json.loads(r.stdout)
    assert data["ok"] is False


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_stdout_is_json_only():
    """stdout은 순수 JSON이어야 한다 (텍스트 없음)."""
    inp = json.dumps({"birth_date": "1990-01-01", "birth_time": "08:30"})
    r = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=inp, capture_output=True, text=True, timeout=10,
        cwd=str(_SCRIPTS_DIR),
    )
    # stdout이 유효한 JSON인지 확인
    data = json.loads(r.stdout.strip())
    assert isinstance(data, dict)


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_out_of_range_year_returns_ok_false():
    inp = json.dumps({"birth_date": "1700-01-01", "birth_time": "00:00"})
    r = subprocess.run(
        ["node", str(_BRIDGE_SCRIPT)],
        input=inp, capture_output=True, text=True, timeout=10,
        cwd=str(_SCRIPTS_DIR),
    )
    data = json.loads(r.stdout)
    assert data["ok"] is False
    assert data["error_code"] == "UNSUPPORTED_DATE"


# ---------------------------------------------------------------------------
# Python wrapper — calculate_bazi
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_calculate_bazi_valid():
    result = calculate_bazi(_valid_input())
    assert isinstance(result, BaziResult)
    assert result.ok is True
    assert result.eight_char is not None
    assert result.zodiac != ""


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_calculate_bazi_invalid_date():
    result = calculate_bazi(BaziInput(birth_date="bad-date", birth_time="08:30"))
    assert result.ok is False
    assert result.error_code == "INVALID_INPUT"


@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_calculate_bazi_from_profile():
    result = calculate_bazi_from_profile(_valid_profile())
    assert result.ok is True


def test_calculate_bazi_from_profile_missing_date():
    result = calculate_bazi_from_profile({"birth_time": "08:30"})
    assert result.ok is False


# ---------------------------------------------------------------------------
# fail-open 테스트 (mock 사용)
# ---------------------------------------------------------------------------

def test_node_missing_fail_open():
    """node binary가 없으면 ok=False를 반환하고 예외를 전파하지 않는다."""
    with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._NODE_BIN", None):
        result = calculate_bazi(_valid_input())
    assert result.ok is False
    assert result.error_code == "DEPENDENCY_MISSING"


def test_bridge_script_missing_fail_open(tmp_path):
    """bridge 스크립트가 없으면 ok=False 반환."""
    fake_script = tmp_path / "nonexistent.mjs"
    with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._BRIDGE_SCRIPT", fake_script):
        with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._NODE_BIN", "node"):
            result = calculate_bazi(_valid_input())
    assert result.ok is False
    assert result.error_code == "DEPENDENCY_MISSING"


def test_timeout_fail_open():
    """timeout 발생 시 ok=False 반환, 예외 전파 안 함."""
    with mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="node", timeout=5),
    ):
        with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._NODE_BIN", "node"):
            result = calculate_bazi(_valid_input())
    assert result.ok is False
    assert result.error_code == "TIMEOUT"


def test_json_parse_failure_fail_open():
    """bridge가 비JSON을 출력해도 ok=False 반환."""
    fake_proc = mock.MagicMock()
    fake_proc.stdout = "this is not json at all"
    fake_proc.stderr = ""
    fake_proc.returncode = 0
    with mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._NODE_BIN", "node"):
            result = calculate_bazi(_valid_input())
    assert result.ok is False
    assert result.error_code == "ENGINE_ERROR"


def test_empty_stdout_fail_open():
    """bridge가 빈 stdout을 반환해도 ok=False."""
    fake_proc = mock.MagicMock()
    fake_proc.stdout = ""
    fake_proc.stderr = ""
    fake_proc.returncode = 0
    with mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        with mock.patch("hermes_ext.fortune_oracle.bazi_bridge._NODE_BIN", "node"):
            result = calculate_bazi(_valid_input())
    assert result.ok is False


# ---------------------------------------------------------------------------
# Static safety 검증
# ---------------------------------------------------------------------------

def test_no_shell_true_in_bazi_bridge():
    """bazi_bridge.py에 shell=True 실행 코드가 없어야 한다."""
    import ast
    src = Path(__file__).parent.parent / "plugins" / "hermes_ext" / "fortune_oracle" / "bazi_bridge.py"
    content = src.read_text()
    # AST 파싱으로 subprocess.run(..., shell=True) 호출 확인
    # 간단한 방법: 주석/docstring 제외 코드 라인에서 확인
    code_lines = []
    in_docstring = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if not in_docstring and not stripped.startswith("#"):
            code_lines.append(line)
    code_only = "\n".join(code_lines)
    assert "shell=True" not in code_only, "bazi_bridge.py 코드에 shell=True 발견"


def test_no_network_calls_in_bridge_script():
    """Node bridge 스크립트에 네트워크 관련 import가 없어야 한다."""
    content = _BRIDGE_SCRIPT.read_text()
    forbidden = ["fetch(", "http.get", "https.get", "axios", "node-fetch", "XMLHttpRequest"]
    for pattern in forbidden:
        assert pattern not in content, f"bridge 스크립트에 네트워크 패턴 발견: '{pattern}'"


def test_no_ai_calls_in_bridge_script():
    """Node bridge 스크립트에 AI/LLM API 호출이 없어야 한다."""
    content = _BRIDGE_SCRIPT.read_text()
    forbidden = ["openai", "anthropic", "gemini", "ollama", "lmstudio", "ChatCompletion"]
    for pattern in forbidden:
        assert pattern not in content, f"bridge 스크립트에 AI 패턴 발견: '{pattern}'"


def test_no_server_start_in_bridge_script():
    """Node bridge 스크립트에 서버 실행 코드가 없어야 한다."""
    content = _BRIDGE_SCRIPT.read_text()
    forbidden = ["createServer", "listen(", ".listen(", "express(", "http.createServer"]
    for pattern in forbidden:
        assert pattern not in content, f"bridge 스크립트에 서버 패턴 발견: '{pattern}'"


# ---------------------------------------------------------------------------
# BaziResult.format_summary
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not bridge_available(), reason="Node + bridge not available")
def test_format_summary_contains_pillar():
    result = calculate_bazi(_valid_input())
    if result.ok:
        summary = result.format_summary()
        assert "팔자:" in summary
        assert len(summary) > 0
