"""Same computed cards, English evidence, privacy and channel/CLI routing."""
from copy import deepcopy
import json
import re
import subprocess
import sys
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle.oracle_method_card import OracleMethodCard
from hermes_ext.fortune_oracle.oracle_renderer import render_final_reading
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading
from hermes_ext.fortune_oracle import combined_reading

PROFILE = {"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male",
           "timezone": "Asia/Seoul", "latitude": 37.5665, "longitude": 126.978,
           "display_name": "PRIVATE_NAME", "language": "en"}


def cards():
    return [OracleMethodCard(method="bazi", status="runnable", backend="lunar-javascript",
                            calculation_mode="computed", facts={"eight_char": {"day": "庚辰"}}),
            OracleMethodCard(method="western", status="runnable", backend="skyfield-jpl-de440s",
                            calculation_mode="computed", facts={"planet_positions": [
                                {"name": "Sun", "longitude": 280.25, "retrograde": False}],
                                "provenance": {"ephemeris": "DE440s", "sha256": "a" * 64}}),
            OracleMethodCard(method="vedic", status="partial", backend="builtin-vedic",
                            calculation_mode="approximate", facts={"graha_positions": [
                                {"name": "Moon", "rashi": "Tula", "degree": 12.5}]}),
            OracleMethodCard(method="ziwei", status="partial", backend="iztro",
                            calculation_mode="computed", facts={"ming_gong": {"branch": "子"},
                                "stars": {"0": ["太陽"]}, "sihua": {"祿": {"star": "太陽"}}}),
            OracleMethodCard(method="qimen", status="runnable", backend="kinqimen",
                            calculation_mode="computed", facts={"ganzhi": "甲子", "palaces": {
                                "坎": {"door": "休", "star": "蓬"}}})]


def test_all_five_english_charts_preserve_facts_and_show_limits():
    source = cards()
    before = deepcopy(source)
    text = render_final_reading(source, language="en-US", include_qimen=True)
    assert source == before
    for fact in ("Geng-Chen", "Capricorn 10.2500°", "Moon: Tula 12.5000°", "太陽", "甲子", "休", "蓬"):
        assert fact in text
    for evidence in ("DE440s", "a" * 64, "UTC", "barycenters", "approximation", "question-time"):
        assert evidence in text
    assert not re.search(r"[가-힣]", text)
    assert "Qimen" not in render_final_reading(source, language="en")


def test_empty_success_and_private_provider_errors_are_not_published():
    source = [OracleMethodCard.runnable("bazi", {"eight_char": {}}, "PRIVATE interpretation"),
              OracleMethodCard.blocked("western", "CALCULATION_FAILED", "PRIVATE_NAME 1990-05-15 Traceback")]
    text = render_final_reading(source, language="en")
    assert "No calculated reading" in text and "CALCULATION_FAILED" in text
    assert "PRIVATE" not in text and "1990-05-15" not in text and "Traceback" not in text
    assert source[0].status == "runnable"


@pytest.mark.parametrize("command", ["deep_fortune", "oracle_short"])
def test_channel_route_computes_once_in_requested_language(command):
    with patch.object(combined_reading, "adapt_all", return_value=cards()[:4]) as engine:
        result = prepare_reading('/' + command, profile=PROFILE)
    engine.assert_called_once()
    assert result['ok'] and result['language'] == 'en'
    assert len(result['methods']) == 4 and 'Four Pillars' in result['text']
    assert 'PRIVATE_NAME' not in result['text'] and PROFILE['birth_date'] not in result['text']


def test_question_route_is_separate_and_not_echoed():
    with patch.object(combined_reading, "adapt_qimen", return_value=cards()[-1]) as engine, \
         patch.object(combined_reading, "adapt_all", side_effect=AssertionError):
        result = prepare_reading('/qimen PRIVATE_QUESTION', profile=PROFILE)
    engine.assert_called_once()
    assert result['kind'] == 'qimen' and 'Qimen Dunjia' in result['text']
    assert 'PRIVATE_QUESTION' not in result['text']


def test_combined_voice_uses_same_completed_english_reading_once():
    with patch.object(combined_reading, 'adapt_all', return_value=cards()[:4]) as engine, \
         patch('hermes_ext.fortune_oracle.speech.synthesize_reading', side_effect=lambda reading, **kw: reading) as speech:
        result = prepare_reading('/voice_fortune deep_fortune', profile=PROFILE)
    engine.assert_called_once()
    assert speech.call_args.args[0]['text'] == result['text']
    assert result['language'] == 'en'


def test_actual_english_four_method_calculation_and_provenance():
    result = prepare_reading('/deep_fortune', profile=PROFILE)
    assert result['ok']
    methods = {method['method']: method for method in result['methods']}
    assert methods['bazi']['status'] == 'runnable'
    assert methods['western']['calculation_mode'] == 'computed'
    assert methods['vedic']['calculation_mode'] == 'computed'
    assert methods['vedic']['backend'] == 'swisseph-moshier'
    assert methods['vedic']['used_in_reading'] is True
    assert 'DE440s' in result['text'] and 'Geng-Chen' in result['text']
    assert not re.search(r'[가-힣]', result['text'])
    assert PROFILE['birth_date'] not in result['text'] and PROFILE['birth_time'] not in result['text']
    assert ''.join(result['messages']) == result['text']
    assert all(len(message) <= 3500 for message in result['messages'])
    assert result['text'].endswith('Not medical, investment or legal advice.')


def test_message_chunks_preserve_long_facts_and_final_evidence():
    from hermes_ext.fortune_oracle.platforms.telegram import split_plain_text
    text = ('Long fact ' * 600) + '\nSHA256: ' + 'a' * 64 + '\n' + ('Evidence\n' * 600)
    messages = split_plain_text(text)
    assert len(messages) > 1 and ''.join(messages) == text
    assert all(len(message) <= 3500 for message in messages)


def test_cli_combined_english_has_real_evidence(tmp_path):
    profile_path = tmp_path / 'profile.json'
    profile_path.write_text(json.dumps(PROFILE))
    completed = subprocess.run([sys.executable, '-m', 'hermes_ext.fortune_oracle',
                                'deep_fortune', '--profile', str(profile_path), '--lang', 'en', '--json'],
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    reading = json.loads(completed.stdout)
    assert reading['ok'] and 'DE440s' in reading['text']
    assert 'PRIVATE_NAME' not in completed.stdout
