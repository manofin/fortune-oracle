from copy import deepcopy
from unittest.mock import patch
import subprocess

import pytest
from hermes_ext.fortune_oracle import compatibility as module
from hermes_ext.fortune_oracle.bazi_bridge import BaziResult
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading

A = {'birth_date':'1990-05-15','birth_time':'07:30','birth_place':'PRIVATE PLACE','name_hanja':'PRIVATE NAME'}
B = {'birth_date':'1988-03-02','birth_time':'22:10'}
CHART_A = {'year':'甲子','month':'乙丑','day':'丙寅','time':'丁卯'}
CHART_B = {'year':'戊辰','month':'己酉','day':'庚午','time':'辛未'}


def chart(pillars):
    return BaziResult(ok=True,engine='fixture',eight_char=deepcopy(pillars))


def test_only_cross_chart_evidence_no_intra_chart_relations():
    original_a,original_b = chart(CHART_A),chart(CHART_B)
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[original_a,original_b]) as calc:
        result = module.build_compatibility(A,B)
    assert calc.call_count == 2
    assert result['ok'] and result['status'] == 'runnable'
    assert len(result['cross_relations']) == 3
    assert all(m['relation'] == '육충' for m in result['cross_relations'])
    # A's 子丑 and B's 辰酉 are internal harmonies, never comparison evidence.
    assert not any(m['relation'] == '육합' for m in result['cross_relations'])
    assert result['day_master_relation'] == 'wealth'  # 丙火 controls 庚金
    assert original_a.eight_char == CHART_A and original_b.eight_char == CHART_B
    assert 'score' not in result
    for private in ('1990-05-15','07:30','PRIVATE PLACE','PRIVATE NAME'):
        assert private not in str(result)


def test_unknown_time_is_removed_from_pillars_and_elements():
    missing = {**A,'birth_time':None}
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[chart(CHART_A),chart(CHART_B)]) as calc:
        result = module.build_compatibility(missing,B)
    assert result['status'] == 'partial'
    assert 'birth_time' not in calc.call_args_list[0].args[0]
    assert 'time' not in result['charts'][0]['pillars']
    assert sum(result['charts'][0]['elements'].values()) == 6
    assert sum(result['charts'][1]['elements'].values()) == 8
    assert all(m['a_pillar'] != 'time' for m in result['cross_relations'])
    assert '시주 오행은 제외' in result['text']


def test_swapping_profiles_swaps_evidence_without_changing_pairs():
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[chart(CHART_A),chart(CHART_B)]):
        ab = module.build_compatibility(A,B)
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[chart(CHART_B),chart(CHART_A)]):
        ba = module.build_compatibility(B,A)
    pairs_ab = {(m['a_pillar'],m['b_pillar'],tuple(m['branches']),m['relation']) for m in ab['cross_relations']}
    pairs_ba = {(m['b_pillar'],m['a_pillar'],tuple(reversed(m['branches'])),m['relation']) for m in ba['cross_relations']}
    assert pairs_ab == pairs_ba
    assert ba['day_master_relation'] == 'pressure'


@pytest.mark.parametrize('profile', [None,{}, {'birth_date':'1990-02-30'},
    {'birth_date':'19900515'}, {'birth_date':'1990-05-15','birth_time':'24:00'},
    {'birth_date':'1990-05-15','birth_time':123}])
def test_invalid_profile_blocks_before_calculation(profile):
    with patch.object(module,'calculate_bazi_from_profile') as calc:
        result = module.build_compatibility(profile,B)
    assert result['ok'] is False
    assert not calc.called
    assert 'charts' not in result


def test_second_chart_failure_never_returns_half_comparison_or_private_error():
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[chart(CHART_A),RuntimeError('PRIVATE SECRET')]):
        result = module.build_compatibility(A,B)
    assert result['ok'] is False and result['status'] == 'blocked'
    assert 'PRIVATE' not in str(result) and 'charts' not in result
    with patch.object(module,'calculate_bazi_from_profile',return_value=chart({'year':'甲子','month':'乙丑','day':''})):
        assert module.build_compatibility(A,B)['ok'] is False


def test_real_two_chart_route_runs_node_once_per_person():
    with patch('hermes_ext.fortune_oracle.bazi_bridge.subprocess.run',wraps=subprocess.run) as node:
        result = prepare_reading('/궁합 1990-05-15 07:30 | 1988-03-02 22:10')
    assert result['ok']
    assert node.call_count == 2
    assert all(c['backend'] == 'lunar-javascript' for c in result['charts'])
    assert result['evidence']['comparison'] == 'cross_chart_only'
    assert '1990-05-15' not in str(result)


def test_own_profile_plus_explicit_partner_no_user_lookup():
    with patch.object(module,'calculate_bazi_from_profile',side_effect=[chart(CHART_A),chart(CHART_B)]):
        result = prepare_reading('/compatibility 1988-03-02 22:10',profile=A)
    assert result['ok']
    assert prepare_reading('/compatibility @someone',profile=A)['ok'] is False
    assert prepare_reading('/compatibility 1988-03-02 22:10')['ok'] is False
    assert prepare_reading('/compatibility 1990-05-15 | 1988-03-02 | 1999-01-01')['ok'] is False


@pytest.mark.parametrize('command,zones', [
    ('/compatibility 1990-05-15 07:30 America/New_York | 1988-03-02 22:10 Asia/Seoul',
     ['America/New_York', 'Asia/Seoul']),
    ('/compatibility 1990-05-15 America/New_York | 1988-03-02 Asia/Seoul',
     ['America/New_York', 'Asia/Seoul']),
])
def test_each_text_profile_preserves_its_birth_timezone(command, zones):
    with patch.object(module, 'calculate_bazi_from_profile', side_effect=[chart(CHART_A), chart(CHART_B)]) as calc:
        result = prepare_reading(command, language='en', reading_timezone='Pacific/Honolulu')
    assert result['ok']
    assert [call.args[0]['timezone'] for call in calc.call_args_list] == zones
    assert [item['birth_timezone'] for item in result['charts']] == zones
    assert all(item['timezone_source'] == 'explicit' for item in result['charts'])
    assert 'America/New_York' in result['text']
    assert '1990-05-15' not in str(result)


@pytest.mark.parametrize('zone', ['Invalid/Zone', '', None, 123])
def test_invalid_explicit_timezone_never_falls_back(zone):
    with patch.object(module, 'calculate_bazi_from_profile') as calc:
        assert not module.build_compatibility({**A, 'timezone': zone}, B)['ok']
    calc.assert_not_called()


def test_two_explicit_profiles_and_default_disclosure_do_not_mutate_inputs():
    a, b = deepcopy(A), {**B, 'timezone': 'America/Chicago'}
    originals = deepcopy((a, b))
    with patch.object(module, 'calculate_bazi_from_profile', side_effect=[chart(CHART_A), chart(CHART_B)]) as calc:
        result = prepare_reading('/compatibility', profile=a, partner_profile=b, language='en')
    assert result['ok'] and calc.call_count == 2
    assert (a, b) == originals
    assert result['charts'][0]['timezone_source'] == 'default'
    assert 'Asia/Seoul (default; not supplied)' in result['text']


@pytest.mark.parametrize('command', ['/compatibility 1988-03-02', '/tarot question', '/voice_fortune', '/voice_fortune tarot question'])
def test_partner_profile_rejects_conflicting_or_unrelated_inputs(command):
    with patch.object(module, 'calculate_bazi_from_profile') as calc:
        result = prepare_reading(command, profile=A, partner_profile=B)
    assert not result['ok']
    calc.assert_not_called()


def test_real_same_instant_in_two_birth_zones_has_same_solar_term_pillars():
    result = prepare_reading('/compatibility 2024-02-04 03:20 America/New_York | 2024-02-04 17:20 Asia/Seoul')
    assert result['ok']
    a, b = result['charts']
    assert a['pillars']['year'] == b['pillars']['year']
    assert a['pillars']['month'] == b['pillars']['month']


def test_cli_two_profile_files(tmp_path):
    import json
    import os
    import sys
    files = [tmp_path / 'a.json', tmp_path / 'b.json']
    for path, value in zip(files, ({**A, 'timezone': 'America/New_York'}, {**B, 'timezone': 'Asia/Seoul'})):
        path.write_text(json.dumps(value))
    command = [sys.executable, '-m', 'hermes_ext.fortune_oracle', 'compatibility',
               '--profile', str(files[0]), '--partner-profile', str(files[1]), '--lang', 'en', '--json']
    completed = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': 'plugins'})
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['ok']
    assert [c['birth_timezone'] for c in result['charts']] == ['America/New_York', 'Asia/Seoul']
    assert A['birth_date'] not in completed.stdout
    command[3] = 'today'
    completed = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': 'plugins'})
    assert completed.returncode == 2


def test_voice_compatibility_preserves_both_supplied_profiles_without_external_tts():
    with patch.object(module, 'calculate_bazi_from_profile', side_effect=[chart(CHART_A), chart(CHART_B)]) as calc, \
         patch('hermes_ext.fortune_oracle.speech.synthesize_reading', side_effect=lambda reading, **kwargs: reading) as speech:
        result = prepare_reading('/voice_fortune compatibility', profile=A,
                                 partner_profile={**B, 'timezone': 'America/Chicago'}, language='en')
    assert result['ok'] and calc.call_count == 2
    assert result['charts'][1]['birth_timezone'] == 'America/Chicago'
    speech.assert_called_once()
