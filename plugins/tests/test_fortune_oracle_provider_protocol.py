"""Offline transport, parser, retry and mixed-version contracts.

No provider or gateway configuration is changed. Unexpected URL requests and
real backoff sleeps fail the test, even when production code catches exceptions.
"""

import secrets

import http.client
import json
import socket
from pathlib import Path
from unittest.mock import Mock
import urllib.error
import urllib.request

import pytest

from hermes_ext.fortune_oracle import deep_qopus_provider as qopus
from hermes_ext.fortune_oracle import deep_review as review
from hermes_ext.fortune_oracle import ziwei_deep_llm as ziwei
from hermes_ext.fortune_oracle.ziwei_deep_critic import parse_critique


URL = "https://operator.example.invalid/v1"
CONTEXT = {"eight_char": "년주:甲子 월주:丙寅 일주:戊午 시주:庚申"}
MIXED_VERSIONS = json.loads(
    (Path(__file__).parent / "fixtures" / "deep_review_mixed_versions.json").read_text()
)


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
    monkeypatch.setenv("FORTUNE_DEEP_BASE_URL", URL)
    monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", "0")
    yield
    network.assert_not_called()
    connections.assert_not_called()
    sleep.assert_not_called()


@pytest.fixture
def enabled_deep(isolate_io, monkeypatch):
    monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", "1")


class Response:
    def __init__(self, raw=None, error=None):
        self.raw = raw
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if self.error:
            raise self.error
        return self.raw[:size] if size >= 0 else self.raw


def envelope(content):
    return json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()


def wire(monkeypatch, *, raw=None, error=None):
    transport = Mock(return_value=Response(raw, error))
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    return transport


def assert_fallback(result):
    assert result["source"] == "template"
    assert result["sections"] == []
    assert result["warnings"]
    assert result["disclaimer"]


@pytest.mark.parametrize("raw", [
    b'{"choices": [', b'null', b'[]', b'{"choices":null}',
    b'{"choices":[]}', b'{"choices":[{"message":null}]}',
    b'{"choices":[{"message":{"content":[]}}]}', b'\xff',
], ids=["truncated-json", "null-envelope", "list-envelope", "null-choices",
        "empty-choices", "null-message", "nontext-content", "bad-utf8"])
def test_malformed_wire_response_preserves_template_fallback(monkeypatch, enabled_deep, raw):
    transport = wire(monkeypatch, raw=raw)
    result = review.analyze_deep_review(CONTEXT, provider=qopus.make_qopus_provider(base_url=URL), enabled=True)
    assert_fallback(result)
    assert transport.call_count == 1


@pytest.mark.parametrize("failure", ["timeout", "http-503", "mid-response-close"])
def test_transport_failure_does_not_publish_partial_reading(monkeypatch, enabled_deep, failure):
    transport = wire(monkeypatch)
    if failure == "mid-response-close":
        transport.return_value = Response(error=http.client.IncompleteRead(b'{"choices":', 100))
    elif failure == "http-503":
        transport.side_effect = urllib.error.HTTPError(URL, 503, "unavailable", {}, None)
    else:
        transport.side_effect = TimeoutError("fixture timeout")
    result = review.analyze_deep_review(CONTEXT, provider=qopus.make_qopus_provider(base_url=URL), enabled=True)
    assert_fallback(result)
    assert transport.call_count == 1


@pytest.mark.parametrize("size", [7999, 8000, 8001])
def test_review_response_length_boundary(size):
    payload = {"sections": [{"title": "흐름", "summary": ""}]}
    blank = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload["sections"][0]["summary"] = "가" * (size - len(blank))
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert len(raw) == size
    result = review.analyze_deep_review(CONTEXT, provider=lambda _: raw, enabled=True)
    if size <= 8000:
        assert result["source"] == "deep_provider"
        assert result["sections"] == payload["sections"]
    else:
        assert_fallback(result)


@pytest.mark.parametrize("case", MIXED_VERSIONS, ids=lambda case: case["id"])
@pytest.mark.parametrize("fence", [False, True], ids=["plain-json", "markdown-json"])
def test_mixed_version_response_uses_current_output_contract(monkeypatch, enabled_deep, case, fence):
    content = json.dumps(case["response"], ensure_ascii=False)
    transport = wire(monkeypatch, raw=envelope(f"```json\n{content}\n```" if fence else content))
    result = review.analyze_deep_review(CONTEXT, provider=qopus.make_qopus_provider(base_url=URL), enabled=True)
    transport.assert_called_once()
    if case["id"] == "mixed_legacy_and_new_sections":
        # Current Q&A validation requires body in every section; a legacy
        # summary cannot masquerade as a Q&A body in a mixed response.
        assert_fallback(result)
        assert "missing section body" in " ".join(result["warnings"])
        return
    assert result["sections"] == case["expected_sections"]
    assert result["style"] == (case["style"] or "short")
    assert result["source"] == "deep_provider"
    assert "future_metadata" not in result
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result


@pytest.mark.parametrize("prompt", [
    "줄 1\n줄 2\t탭", '따옴표 "quoted" · 역슬래시 \\',
    "한국어 · 甲子 · 🙂 · e\u0301", "null\x00문자\r\n다음 줄",
])
def test_request_json_round_trip_and_explicit_http_contract(monkeypatch, enabled_deep, prompt):
    transport = wire(monkeypatch, raw=envelope("응답"))
    api_key = secrets.token_hex(32)
    provider = qopus.make_qopus_provider(base_url=URL, model="fixture-model", api_key=api_key, timeout=7)
    assert provider(prompt) == "응답"
    transport.assert_called_once()
    request = transport.call_args.args[0]
    assert request.full_url == URL + "/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == f"Bearer {api_key}"
    assert transport.call_args.kwargs["timeout"] == 7
    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "fixture-model"
    assert body["messages"] == [{"role": "user", "content": prompt}]


@pytest.mark.parametrize("outcomes,budget,delay,expected_calls,expected_result,expected_waits", [
    (["done"], 2, 0.125, 1, "done", []),
    ([None, "done"], 2, 0.125, 2, "done", [0.125]),
    ([None, None, "done"], 3, 0.125, 2, None, [0.125]),
    ([None, None, None], 100, 100, 2, None, [1.0]),
    (["done"], 0, 0.125, 1, "done", []),
], ids=["immediate", "one-retry", "two-attempt-cap", "bounded-wait", "minimum-one-attempt"])
def test_backoff_stops_at_success_or_budget_without_real_sleep(
    monkeypatch, enabled_deep, outcomes, budget, delay, expected_calls, expected_result, expected_waits,
):
    call = Mock(side_effect=outcomes)
    sleep = Mock()
    monkeypatch.setattr(ziwei, "call_llm", call)
    monkeypatch.setattr(ziwei.time, "sleep", sleep)
    result = ziwei.call_llm_with_backoff("system", "user", max_attempts=budget, initial_delay=delay)
    assert result == expected_result
    assert call.call_count == expected_calls
    assert [args.args[0] for args in sleep.call_args_list] == expected_waits


@pytest.mark.parametrize("flag", [None, "", "0", "false"])
def test_disabled_provider_never_calls_transport_or_sleeps(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("FORTUNE_DEEP_ANALYSIS")
    else:
        monkeypatch.setenv("FORTUNE_DEEP_ANALYSIS", flag)
    provider = qopus.make_qopus_provider(base_url=URL)
    failure = json.loads(provider("unused"))
    assert failure["ok"] is False and failure["sections"] == []
    assert "disabled" in " ".join(failure["warnings"])
    assert ziwei.call_llm("system", "user") is None
    assert ziwei.call_llm_with_backoff("system", "user", max_attempts=3, initial_delay=20) is None
    assert qopus.check_qopus_reachable()["error"] == "disabled"
    # isolate_io checks both urllib and socket mocks after the product has
    # handled any exceptions, so swallowed connection attempts also fail.


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_critic_parser_round_trip_retains_multiline_unicode(newline):
    expected = {"delete": '첫 문장 "반복"\n둘째 줄', "correct": "없음 🙂", "keep": "명궁: 자미"}
    text = newline.join(f"▸ {heading}: {expected[key]}" for heading, key in
                        [("삭제 권고", "delete"), ("정정 필요", "correct"), ("유지 확인", "keep")])
    parsed = parse_critique(text)
    assert parsed == expected
    assert json.loads(json.dumps(parsed, ensure_ascii=False)) == expected


@pytest.mark.parametrize("text,expected", [
    ("", {"delete": "", "correct": "", "keep": ""}),
    ("▸ 정정 필요: 마지막 프레임", {"delete": "", "correct": "마지막 프레임", "keep": ""}),
])
def test_partial_critic_does_not_invent_missing_sections(text, expected):
    assert parse_critique(text) == expected
