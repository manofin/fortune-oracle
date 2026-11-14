"""Physical solar-term instant versus explicit local civil day/hour convention."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from hermes_ext.fortune_oracle import bazi_bridge as bridge, ephemeris

LUNAR = Path(bridge.__file__).parent / 'scripts/node_modules/lunar-javascript'


def profile(wall, zone):
    return {'birth_date': wall[:10], 'birth_time': wall[11:], 'timezone': zone, 'gender': 'male'}


@pytest.mark.parametrize('wall,zone', [
    ('2024-03-10T02:30', 'America/New_York'), ('2024-11-03T01:30', 'America/New_York'),
    ('2024-02-30T12:00', 'UTC'), ('2024-01-01T12:00', 'Unknown/Private'),
    ('2011-12-30T12:00', 'Pacific/Apia'), ('2024-01-01T24:00', 'UTC'),
])
def test_invalid_birth_clock_blocks_before_node(wall, zone):
    with patch.object(bridge.subprocess, 'run') as node:
        result = bridge.calculate_bazi_from_profile(profile(wall, zone))
    assert not result.ok and result.error_code == 'INVALID_INPUT'
    node.assert_not_called()


def test_solar_term_year_month_same_instant_on_three_continents():
    before = [('2024-02-04T08:20', 'UTC'), ('2024-02-04T17:20', 'Asia/Seoul'),
              ('2024-02-04T03:20', 'America/New_York')]
    after = [('2024-02-04T08:35', 'UTC'), ('2024-02-04T17:35', 'Asia/Seoul'),
             ('2024-02-04T03:35', 'America/New_York')]
    for inputs, expected in ((before, ('癸卯', '乙丑')), (after, ('甲辰', '丙寅'))):
        charts = [bridge.calculate_bazi_from_profile(profile(wall, zone)) for wall, zone in inputs]
        assert all(chart.ok and chart.solar_term_month_mode for chart in charts)
        assert {(chart.eight_char['year'], chart.eight_char['month']) for chart in charts} == {expected}
        assert all(chart.time_basis['true_solar_time'] is False for chart in charts)
        assert len({chart.eight_char['time'] for chart in charts}) > 1  # civil clocks differ


def test_same_instant_does_not_replace_local_civil_birth_day():
    utc = bridge.calculate_bazi_from_profile(profile('2024-01-01T01:00', 'UTC'))
    ny = bridge.calculate_bazi_from_profile(profile('2023-12-31T20:00', 'America/New_York'))
    assert utc.ok and ny.ok
    assert utc.eight_char['year'] == ny.eight_char['year']
    assert utc.eight_char['month'] == ny.eight_char['month']
    assert utc.eight_char['day'] != ny.eight_char['day']
    assert ny.time_basis['day_hour'] == 'local_civil_time'


def test_unknown_birth_time_is_uncertain_and_no_dayun_is_invented():
    result = bridge.calculate_bazi_from_profile({'birth_date':'2024-02-04', 'timezone':'America/New_York', 'gender':'male'})
    assert result.ok and result.dayun is None
    assert result.time_basis['solar_terms'] == 'date_only_uncertain'
    assert any('미확정' in warning for warning in result.warnings)


@pytest.mark.parametrize('missing', [None, ''])
def test_explicit_missing_time_is_not_converted_to_known_midnight(missing):
    result = bridge.calculate_bazi_from_profile({'birth_date':'2024-02-04', 'birth_time':missing,
                                                 'timezone':'America/New_York', 'gender':'male'})
    assert result.ok and result.dayun is None
    assert result.time_basis['solar_terms'] == 'date_only_uncertain'
    from hermes_ext.fortune_oracle.oracle_input import from_profile
    inp = from_profile({'birth_date':'2024-02-04', 'birth_time':missing, 'timezone':'America/New_York'})
    assert inp.to_bazi_input().birth_time_known is False


def test_provider_diagnostics_and_invalid_json_are_not_logged(caplog):
    from types import SimpleNamespace
    with patch.object(bridge.subprocess, 'run', return_value=SimpleNamespace(
            stdout='PRIVATE_BIRTH_DATE not json', stderr='PRIVATE_BIRTH_TIME', returncode=1)), \
         caplog.at_level('DEBUG', logger=bridge.__name__):
        result = bridge.calculate_bazi_from_profile(profile('2024-01-01T12:00','UTC'))
    assert not result.ok
    assert 'PRIVATE' not in caplog.text and 'PRIVATE' not in result.message


def test_dst_offset_used_for_library_reference():
    chart = bridge.calculate_bazi_from_profile(profile('2024-07-01T08:00', 'America/New_York'))
    script = '''const {Solar}=require(process.argv[1]);
const l=Solar.fromYmdHms(2024,7,1,20,0,0).getLunar();
console.log(JSON.stringify([l.getYearInGanZhiExact(), l.getMonthInGanZhiExact()]));'''
    expected = json.loads(subprocess.check_output(['node','-e',script,str(LUNAR)], text=True))
    assert chart.ok and [chart.eight_char['year'], chart.eight_char['month']] == expected


def test_solar_term_table_cross_checked_against_jpl_longitude():
    try:
        ephemeris.resources()
    except ephemeris.EphemerisUnavailable:
        pytest.skip('Pinned local JPL kernel required for independent longitude check')
    script = '''const {Solar}=require(process.argv[1]);
console.log(Solar.fromYmd(2024,2,4).getLunar().getJieQiTable()['立春'].toYmdHms());'''
    wall = subprocess.check_output(['node','-e',script,str(LUNAR)], text=True).strip()
    moment = datetime.fromisoformat(wall).replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
    # Independent JPL apparent longitude at the library's Li Chun timestamp.
    planets, _ = ephemeris.positions(moment)
    sun = next(p for p in planets if p['name'] == 'Sun')['longitude']
    assert abs((sun - 315 + 180) % 360 - 180) < 0.002  # ~3 minutes of solar motion


def test_dayun_start_is_local_date_of_the_same_reference_instant():
    script = '''const {Solar}=require(process.argv[1]);
const y=Solar.fromYmdHms(1990,5,15,6,30,0).getLunar().getEightChar().getYun(1,2);
console.log(y.getStartSolar().toYmdHms());'''
    start = datetime.fromisoformat(subprocess.check_output(['node','-e',script,str(LUNAR)], text=True).strip())
    expected = start.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    result = bridge.calculate_bazi_from_profile(profile('1990-05-15T07:30', 'Asia/Seoul'))
    assert result.dayun['start_date'] == expected


def test_reading_evidence_has_clock_convention_without_birth_values():
    from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading
    reading = prepare_reading('/deep_fortune', profile={**profile('2024-02-04T03:20','America/New_York'), 'language':'en'})
    assert reading['ok']
    assert "solar-term table's UTC+8" in reading['text'] and 'true solar time' in reading['text']
    assert '2024-02-04' not in reading['text'] and '03:20' not in reading['text']


def test_unknown_clock_after_lichun_before_lunar_new_year_uses_solar_year():
    result = bridge.calculate_bazi_from_profile({'birth_date':'2024-02-07','timezone':'America/New_York'})
    assert result.ok and result.solar_term_month_mode
    assert result.eight_char['year'] == '甲辰' and result.eight_char['month'] == '丙寅'
    assert result.eight_char['time'] == '' and result.dayun is None
    assert sum(result.elements.values()) == 6  # three actual pillars, no assumed hour
    assert result.time_basis['solar_terms'] == 'civil_day_interval_confirmed'


def test_direct_bridge_input_distinguishes_missing_time_from_explicit_midnight():
    unknown = bridge.BaziInput(birth_date='2024-02-07', timezone='America/New_York', gender='male')
    midnight = bridge.BaziInput(birth_date='2024-02-07', birth_time='00:00', timezone='America/New_York', gender='male')
    assert unknown.birth_time_known is False and midnight.birth_time_known is True
    missing = bridge.calculate_bazi(unknown)
    known = bridge.calculate_bazi(midnight)
    assert missing.ok and known.ok
    assert missing.eight_char['time'] == '' and missing.dayun is None
    assert known.eight_char['time'] and known.dayun


def test_unknown_clock_on_solar_term_day_does_not_choose_a_pillar_or_score():
    from hermes_ext.fortune_oracle.daily_fortune_engine import build_personalized_daily
    from hermes_ext.fortune_oracle.kline import build_daily_candle, build_monthly_kline, build_yearly_kline
    from hermes_ext.fortune_oracle.core import get_daily_candle_score
    unknown = {'birth_date':'2024-02-04','timezone':'America/New_York'}
    chart = bridge.calculate_bazi_from_profile(unknown)
    assert chart.ok and chart.eight_char['day']
    assert chart.eight_char['year'] == chart.eight_char['month'] == chart.eight_char['time'] == ''
    assert sum(chart.elements.values()) == 2
    assert chart.time_basis['uncertain_pillars'] == ['year','month']
    assert chart.time_basis['pillar_candidates']['year'] == ['癸卯','甲辰']
    assert build_personalized_daily(unknown) is None
    assert build_daily_candle(unknown) is None and get_daily_candle_score(unknown) is None
    assert build_monthly_kline(unknown,2024,2) == [] and build_yearly_kline(unknown,2024) == []


def test_only_uncertain_month_is_omitted_at_a_non_lichun_jie():
    # Jing Zhe occurs on March 5 in Seoul in 2024.
    result = bridge.calculate_bazi_from_profile({'birth_date':'2024-03-05','timezone':'Asia/Seoul'})
    assert result.ok and result.eight_char['year'] == '甲辰'
    assert result.eight_char['month'] == ''
    assert result.time_basis['uncertain_pillars'] == ['month']


def test_midnight_gap_does_not_invent_or_block_an_otherwise_valid_date():
    from hermes_ext.fortune_oracle.birth_clock import civil_day_utc_bounds
    from datetime import date
    first, last = civil_day_utc_bounds(date(2018,11,4), 'America/Sao_Paulo')
    assert first.astimezone(ZoneInfo('America/Sao_Paulo')).hour == 1
    assert last.astimezone(ZoneInfo('America/Sao_Paulo')).hour == 23
    chart = bridge.calculate_bazi_from_profile({'birth_date':'2018-11-04','timezone':'America/Sao_Paulo'})
    assert chart.ok and chart.time_basis['solar_terms'] == 'civil_day_interval_confirmed'


def test_whole_date_skipped_is_blocked_even_without_birth_time():
    with patch.object(bridge.subprocess, 'run') as node:
        result = bridge.calculate_bazi_from_profile({'birth_date':'2011-12-30','timezone':'Pacific/Apia'})
    assert not result.ok and result.error_code == 'INVALID_INPUT'
    node.assert_not_called()


def test_combined_and_compatibility_publish_only_confirmed_pillars():
    from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading
    from hermes_ext.fortune_oracle.compatibility import build_compatibility
    unknown = {'birth_date':'2024-02-04','timezone':'America/New_York','language':'en'}
    result = prepare_reading('/deep_fortune',profile=unknown)
    assert result['ok']
    assert 'Unresolved year/month' in result['text'] and 'Day pillar:' in result['text']
    assert 'Year pillar:' not in result['text'] and 'Hour pillar:' not in result['text']
    other = profile('1990-05-15T07:30','Asia/Seoul')
    comparison = build_compatibility(unknown, other)
    assert comparison['ok'] and comparison['status'] == 'partial'
    assert set(comparison['charts'][0]['pillars']) == {'day'}
    assert sum(comparison['charts'][0]['elements'].values()) == 2
    assert all(pair['a_pillar'] == 'day' for pair in comparison['cross_relations'])


def test_legacy_daily_fallback_is_explicitly_not_a_calculated_reading():
    from hermes_ext.fortune_oracle.core import render_daily_fortune
    text = render_daily_fortune(profile={'birth_date':'2024-02-04','timezone':'America/New_York'})
    assert '개인화 계산 불가' in text and '계산 결과가 아닌 일반 성찰' in text
    assert '2024-02-04' not in text
