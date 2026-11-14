"""Deep-provider contracts first written as strict xfails at HEAD 9a5a783.

DEEP-URL and DEEP-NAME were fixed by 813aeb6 (explicit deep endpoint, name
redaction); those tests now run as ordinary regressions. DEEP-SCHEMA was fixed
by section validation and is also an ordinary regression.
All provider requests and sleeps are intercepted; production configuration is
never used.
"""

import json
import socket
from unittest.mock import Mock
import urllib.request

import pytest

from hermes_ext.fortune_oracle import deep_provider_health as health
from hermes_ext.fortune_oracle import deep_qopus_provider as qopus
from hermes_ext.fortune_oracle import deep_review as review
from hermes_ext.fortune_oracle import ziwei_deep_critic as critic
from hermes_ext.fortune_oracle import ziwei_deep_llm as ziwei
from hermes_ext.fortune_oracle import ziwei_deep_prompt as prompt_builder


URL = "https://operator.example.invalid/v1"
NAME = "가상검증이름"


@pytest.fixture
def captured(monkeypatch, isolate_io):
    requests = []
    waits = Mock()

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            raw = json.dumps({"choices": [{"message": {"content": "검증 응답"}}]}).encode()
            return raw[:size] if size >= 0 else raw

    def capture(request, **kwargs):
        requests.append(json.loads(request.data) if request.data else {})
        return Reply()

    transport = Mock(side_effect=capture)
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    monkeypatch.setattr(ziwei.time, "sleep", waits)
    monkeypatch.setenv("FORTUNE_DEEP_BASE_URL", URL)
    yield requests, waits
    # Check outside the provider's exception handler so a swallowed transport
    # assertion cannot conceal an unexpected destination.
    for call in transport.call_args_list:
        assert call.args[0].full_url == URL + "/chat/completions"


@pytest.fixture(autouse=True)
def isolate_io(monkeypatch):
    network = Mock(side_effect=AssertionError("Unmocked network request"))
    connections = Mock(side_effect=AssertionError("Real socket connection"))
    sleep = Mock(side_effect=AssertionError("Unmocked backoff sleep"))
    monkeypatch.setattr(urllib.request, "urlopen", network)
    monkeypatch.setattr(socket.socket, "connect", connections)
    monkeypatch.setattr(socket.socket, "connect_ex", connections)
    monkeypatch.setattr(socket, "create_connection", connections)
    monkeypatch.setattr(ziwei.time, "sleep", sleep)
    monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", "0")
    yield
    network.assert_not_called()
    connections.assert_not_called()
    sleep.assert_not_called()


@pytest.fixture
def enabled_deep(captured, monkeypatch):
    # Only tests with intercepted transport explicitly opt in.
    monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", "1")


@pytest.fixture(params=[None, "", " \t\n"], ids=["unset", "empty", "whitespace"])
def no_address(monkeypatch, request):
    if request.param is None:
        monkeypatch.delenv("FORTUNE_DEEP_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("FORTUNE_DEEP_BASE_URL", request.param)
    return {} if request.param is None else {"FORTUNE_DEEP_BASE_URL": request.param}


def test_qopus_factory_rejects_unconfigured_address(captured, enabled_deep, no_address):
    rejected = False
    try:
        qopus.make_qopus_provider()
    except (ValueError, RuntimeError):
        rejected = True
    assert rejected, "Missing address must fail before constructing an enabled provider"
    assert captured[0] == []


def test_health_check_missing_address_never_calls_live_checker(captured, no_address):
    checker = Mock(return_value={"reachable": True, "models": []})
    result = health.provider_readiness_check(
        env={"FORTUNE_DEEP_ANALYSIS": "1", **no_address}, check_models=checker,
    )
    checker.assert_not_called()
    assert result["live_checked"] is False
    assert result["ok"] is False


def test_unconfigured_ziwei_backoff_makes_zero_requests_and_zero_waits(captured, enabled_deep, no_address):
    result = ziwei.call_llm_with_backoff("system", "user", max_attempts=3, initial_delay=20)
    assert captured[0] == []
    captured[1].assert_not_called()
    assert result is None


def assert_no_name(requests):
    assert len(requests) == 1, "The intended payload boundary was not exercised"
    messages = requests[0]["messages"]
    assert {item["role"] for item in messages} == {"system", "user"}
    assert all(NAME not in item["content"] for item in messages)


def test_initial_ziwei_request_uses_generic_address(captured, enabled_deep, monkeypatch):
    monkeypatch.setattr(ziwei, "safety_check", lambda *_: (True, []))
    ziwei.generate_deep_narrative({}, name=NAME, max_retries=0)
    assert_no_name(captured[0])


def test_critic_request_removes_known_name_from_model_draft(captured, enabled_deep):
    critic.critique_draft(f"{NAME}님의 명반 요약", {}, name=NAME)
    assert_no_name(captured[0])


def test_critique_to_rewrite_request_scrubs_echoed_name(captured, enabled_deep, monkeypatch):
    # Isolate feedback concatenation: the base prompt is already generic here.
    # A fix to the initial prompt alone cannot make this regression pass.
    monkeypatch.setattr(prompt_builder, "build_ziwei_deep_prompt", lambda *_: ("system", "사용자 명반"))
    monkeypatch.setattr(ziwei, "_generate_safe_draft", lambda *_: {"ok": True, "text": "일반 초안"})
    monkeypatch.setattr(ziwei, "critique_draft", lambda *a, **kw: {"ok": True, "critique": f"{NAME}님의 문장을 다듬으세요."})
    monkeypatch.setattr(ziwei, "safety_check", lambda *_: (True, []))
    ziwei.generate_deep_narrative_with_critique({}, name=NAME, use_critic=True)
    assert_no_name(captured[0])
    assert "사용자님의 문장을" in captured[0][0]["messages"][1]["content"]


@pytest.mark.parametrize("field,value", [("summary", None), ("body", ["unexpected"]), ("emphasis", 7)])
def test_nontext_section_fields_return_template_instead_of_raising(field, value, captured):
    section = {"title": "흐름", "summary": "차분히 정리합니다.", field: value}
    raw = json.dumps({"sections": [section]})
    result = review.analyze_deep_review({}, provider=lambda _: raw, enabled=True)
    assert result["source"] == "template"
    assert result["sections"] == []
    assert "invalid section text field" in " ".join(result["warnings"])


@pytest.mark.parametrize("flag", [None, "", "0", "false"])
def test_disabled_health_skips_checker_even_with_address(captured, flag):
    env = {"FORTUNE_DEEP_BASE_URL": URL}
    if flag is not None:
        env["FORTUNE_DEEP_ANALYSIS"] = flag
    checker = Mock()
    result = health.provider_readiness_check(env=env, check_models=checker)
    checker.assert_not_called()
    assert result["ok"] is True  # Disabled configuration is not a live health failure.
    assert result["default_off"] is True
    assert result["live_checked"] is False
    assert captured[0] == []
    captured[1].assert_not_called()
