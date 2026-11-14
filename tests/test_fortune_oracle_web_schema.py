"""Provider schema failures stay failures in shared and web consumers."""
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from test_fortune_oracle_web import app, session, PROFILE
from hermes_ext.fortune_oracle import bazi_bridge as bridge


@pytest.mark.parametrize('clock,birthday', [('12:30', '1990-05-17'), ('', '1990-05-17'), ('', '2024-02-04')])
def test_real_node_golden(clock, birthday):
    result = bridge.calculate_bazi_from_profile({**PROFILE, 'birth_time': clock, 'birth_date': birthday})
    assert result.ok is True
    assert bridge.BaziResult.from_dict(asdict(result)).ok is True
    assert result.eight_char['day']
    if not clock:
        assert result.eight_char['time'] == ''
        assert result.dayun is None
    else:
        # Fictional date: JDN 2448029; (JDN + 49) % 60 == 18 (壬午).
        assert result.eight_char['day'] == '壬午'
        assert result.dayun['cycles']


@pytest.mark.parametrize('payload', [None, [], 1, 'bad', {}, {'ok': 'false'}, {'ok': 1},
    {'ok': True}, {'ok': True, 'eight_char': {}}, {'ok': True, 'dayun': {'start_reference': 'invalid'}}])
def test_malformed_provider_fails_shared_and_web(app, monkeypatch, payload):
    client = app.test_client(); headers = session(client)
    assert client.put('/api/profile', headers=headers, json=PROFILE).status_code == 200
    monkeypatch.setattr(bridge.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=''))
    result = bridge.calculate_bazi_from_profile(PROFILE)
    assert result.ok is False
    assert result.format_summary() == ''  # Shared Telegram summary cannot invent facts.
    response = client.get('/api/chart')
    assert response.status_code == 200
    assert response.json['computed'] is False


@pytest.mark.parametrize('change', [{'elements': {'목': True}}, {'elements': {'목': -1}},
    {'dayun': []}, {'dayun': {}}, {'dayun': {'start_date': 'invalid', 'cycles': []}},
    {'solar_term_month_mode': 'false'}, {'warnings': 'bad'}])
def test_corrupted_golden(change):
    result = bridge.calculate_bazi_from_profile(PROFILE)
    assert result.ok
    assert bridge.BaziResult.from_dict({**asdict(result), **change}).ok is False
