"""Product boundary: calculated interpretation, unavailable result, general copy."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest

from hermes_ext.fortune_oracle import core, daily_reading, daily_fortune_engine
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading

PROFILE = {'birth_date': '1990-05-15', 'birth_time': '07:30',
           'timezone': 'Asia/Seoul', 'gender': 'male', 'display_name': 'PRIVATE_NAME'}
NOW = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize('command', ['today_fortune', 'tomorrow_fortune', 'week_fortune'])
@pytest.mark.parametrize('language,notice', [('ko', '계산 결과가 아님'), ('en', 'Not a calculated result')])
@pytest.mark.parametrize('profile', [None, {}, {'display_name': 'PRIVATE_NAME'}])
def test_missing_birth_never_calls_engine(monkeypatch, command, language, notice, profile):
    def unexpected(*args, **kwargs):
        pytest.fail('Missing birth information must not trigger a calculation')
    monkeypatch.setattr(daily_reading, 'build_personalized_daily', unexpected)
    monkeypatch.setattr(daily_reading, 'build_personalized_series', unexpected)
    result = prepare_reading('/' + command, profile=profile, language=language, now=NOW)
    assert result['text'].splitlines()[0] == notice
    assert not result['ok'] and result['computed'] is False
    assert 'reading' not in result and 'readings' not in result
    assert 'PRIVATE_NAME' not in result['text']


@pytest.mark.parametrize('command', ['today_fortune', 'tomorrow_fortune', 'week_fortune'])
@pytest.mark.parametrize('exception', [False, True])
def test_registered_calculation_failure_does_not_invent_result(monkeypatch, command, exception):
    def fail(*args, **kwargs):
        if exception:
            raise RuntimeError('synthetic backend failure')
        return None
    monkeypatch.setattr(daily_reading, 'build_personalized_daily', fail)
    monkeypatch.setattr(daily_reading, 'build_personalized_series', fail)
    result = prepare_reading('/' + command, profile=PROFILE, now=NOW)
    assert result['text'].startswith('계산 결과가 아님\n개인화 계산 불가')
    assert result['computed'] is False and not result['ok']
    assert 'reading' not in result and 'readings' not in result
    assert 'PRIVATE_NAME' not in result['text']


@pytest.mark.parametrize('language', ['ko', 'en'])
@pytest.mark.parametrize('command,date', [('today_fortune', '2026-10-06'), ('tomorrow_fortune', '2026-10-07')])
def test_actual_calculation_uses_requested_date_and_labels_interpretation(command, date, language):
    result = prepare_reading('/' + command, profile=PROFILE, language=language, now=NOW)
    assert result['ok'] and result['computed'] is True
    assert result['reading']['day_pillar']
    assert result['date'] == result['reading']['date'] == date
    first = result['text'].splitlines()[0]
    assert ('경험적 해석' if language == 'ko' else 'heuristic') in first
    assert ('계산된' if language == 'ko' else 'calculated') in first
    assert '계산 결과가 아님' not in result['text']
    assert 'Not a calculated result' not in result['text']
    if language == 'ko':
        assert f'{date}의 키워드는' in result['text']
        assert '오늘의 키워드' not in result['text']


@pytest.mark.parametrize('profile', [None, PROFILE])
@pytest.mark.parametrize('day', ['today', 'tomorrow', 'week'])
def test_legacy_general_copy_is_labeled_before_body(monkeypatch, profile, day):
    monkeypatch.setattr(daily_fortune_engine, 'render_personalized_daily_text', lambda *a, **k: None)
    text = core.render_fortune(day, profile=profile)
    assert text.splitlines()[0].startswith('계산 결과가 아님')
    for misleading in ('PRIVATE_NAME', '당신의 사주', '당신의 계산 결과'):
        assert misleading not in text
    assert '일반 성찰 문구' in text


@pytest.mark.parametrize('kwargs', [{'language': 'unsupported'}, {'reading_timezone': 'Invalid/Zone'}])
def test_invalid_request_is_not_presented_as_a_result(kwargs):
    result = prepare_reading('/tomorrow_fortune', profile=PROFILE, now=NOW, **kwargs)
    assert not result['ok'] and result['computed'] is False
    assert result['text'].startswith('계산 결과가 아님')


@pytest.fixture
def plugin():
    # Load the repository entry point, never the installed plugin or production store.
    path = Path(__file__).resolve().parents[1] / 'fortune_oracle_plugin' / '__init__.py'
    spec = importlib.util.spec_from_file_location('stage2_fortune_plugin', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('handler', ['_handle_today_fortune', '_handle_tomorrow_fortune', '_handle_week_fortune'])
def test_plugin_unexpected_failure_is_labeled_first(plugin, monkeypatch, handler):
    def fail(*a, **k):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(plugin, '_daily', fail)
    assert getattr(plugin, handler)('').startswith('계산 결과가 아님\n')


@pytest.mark.parametrize('handler', ['_handle_today_fortune', '_handle_tomorrow_fortune'])
def test_plugin_missing_profile_keeps_notice_before_registration_hint(plugin, monkeypatch, handler):
    monkeypatch.setattr(plugin, '_resolve_profile', lambda: None)
    text = getattr(plugin, handler)('')
    assert text.startswith('계산 결과가 아님\n')
    assert '/register_birth' in text


def test_plugin_help_explains_calculation_limits(plugin):
    text = plugin._handle_help('')
    assert '계산 결과가 아님' in text
    assert '경험적 해석' in text


@pytest.mark.parametrize('command', ['today_fortune', 'tomorrow_fortune'])
def test_invalid_birth_date_never_becomes_a_calculated_result(command):
    result = prepare_reading('/' + command, profile={**PROFILE, 'birth_date': 'invalid'}, now=NOW)
    assert not result['ok'] and result['computed'] is False
    assert result['text'].startswith('계산 결과가 아님\n개인화 계산 불가')
    assert 'reading' not in result


def test_empty_response_is_labeled_before_registration_hint(plugin, monkeypatch):
    monkeypatch.setattr(plugin, '_resolve_profile', lambda: None)
    monkeypatch.setattr(plugin, '_prepare', lambda *a, **k: {'text': ''})
    assert plugin._handle_tomorrow_fortune('').startswith('계산 결과가 아님\n')
