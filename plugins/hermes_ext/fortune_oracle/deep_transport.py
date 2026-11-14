"""Shared opt-in and bounded response handling for existing deep providers."""
import json
import math
import os

MAX_RESPONSE_BYTES = 128 * 1024
MAX_TIMEOUT_SECONDS = 30


def deep_enabled():
    return os.environ.get("FORTUNE_DEEP_ANALYSIS", "").strip() == "1"


def bounded_timeout(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("invalid_provider_timeout")
    return min(seconds, MAX_TIMEOUT_SECONDS)


def read_json_response(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("provider_response_too_large")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("invalid_provider_response")
    return result
