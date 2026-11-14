"""Locale parity and current-location date boundaries, with real Bazi calls."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle.localization import language_code, local_today, reading_zone
from hermes_ext.fortune_oracle.daily_reading import prepare_daily_reading
from hermes_ext.fortune_oracle.daily_fortune_engine import build_personalized_daily
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading

PROFILE = {'birth_date':'1990-05-15','birth_time':'07:30','gender':'male','timezone':'Asia/Seoul',
           'birth_place':'PRIVATE PLACE','name_hanja':'PRIVATE NAME'}
NOW = datetime(2026,1,1,1,0,tzinfo=timezone.utc)


@pytest.mark.parametrize('zone,expected', [('Asia/Seoul',date(2026,1,1)),
    ('America/Los_Angeles',date(2025,12,31)),('Pacific/Honolulu',date(2025,12,31)),
    ('Pacific/Auckland',date(2026,1,1)),('UTC',date(2026,1,1))])
def test_local_date_uses_zone_not_server_or_birth_zone(zone,expected):
    profile = {**PROFILE,'reading_timezone':zone}
    assert local_today(profile,now=NOW) == expected
    assert profile['timezone'] == 'Asia/Seoul'


def test_dst_changes_local_date_and_aware_clock_is_required():
    # 07:30 UTC is 23:30 the previous day in LA winter, but 00:30 in summer.
    assert local_today(reading_timezone='America/Los_Angeles',now=datetime(2026,1,15,7,30,tzinfo=timezone.utc)) == date(2026,1,14)
    assert local_today(reading_timezone='America/Los_Angeles',now=datetime(2026,7,15,7,30,tzinfo=timezone.utc)) == date(2026,7,15)
    with pytest.raises(ValueError):
        local_today(now=datetime(2026,1,1))


@pytest.mark.parametrize('tag,expected',[('en-US','en'),('EN_us','en'),('ko-KR','ko'),(None,'ko')])
def test_supported_language_tags(tag,expected):
    assert language_code(tag) == expected


@pytest.mark.parametrize('zone',['Wrong/Zone','',123,'../private'])
def test_invalid_explicit_timezone_is_rejected(zone):
    with pytest.raises(ValueError):
        reading_zone(PROFILE,override=zone)
    result = prepare_daily_reading(PROFILE,language='en',reading_timezone=zone,now=NOW)
    assert not result['ok'] and result['error'] == 'invalid_time_context'


def test_english_preserves_scores_pillars_and_evidence_all_aspects():
    for aspect in ('종합','활동','관계','재물','건강'):
        ko = build_personalized_daily(PROFILE,target_date=date(2026,10,3),aspect=aspect,language='ko')
        en = build_personalized_daily(PROFILE,target_date=date(2026,10,3),aspect=aspect,language='en')
        for key in ('score','aspect_scores','date','day_pillar','day_master','dayun_pillar','dayun_adjustment','dayun_years'):
            assert en[key] == ko[key]
        text = '\n'.join(en['lines']+[en['disclaimer']])
        assert 'interpretive index' in text
        assert not re.search('[가-힣]',text)
        for private in ('1990-05-15','07:30','PRIVATE PLACE','PRIVATE NAME'):
            assert private not in text


def test_today_and_tomorrow_use_current_zone_without_profile_mutation():
    profile = {**PROFILE,'language':'en','reading_timezone':'America/Los_Angeles'}
    original = deepcopy(profile)
    today = prepare_reading('/today',profile=profile,now=NOW)
    tomorrow = prepare_reading('/tomorrow',profile=profile,now=NOW)
    assert today['date'] == '2025-12-31' and tomorrow['date'] == '2026-01-01'
    assert today['language'] == 'en' and tomorrow['language'] == 'en'
    assert profile == original
    assert 'Overall' in today['text'] and not re.search('[가-힣]',today['text'])


def test_week_is_seven_actual_dates_and_one_node_call():
    from hermes_ext.fortune_oracle import bazi_bridge
    with patch.object(bazi_bridge.subprocess,'run',wraps=subprocess.run) as node:
        result = prepare_reading('/week',profile=PROFILE,language='en',reading_timezone='America/Los_Angeles',now=NOW)
    assert result['ok'] and node.call_count == 1
    assert len(result['readings']) == 7
    assert result['readings'][0]['date'] == '2025-12-31'
    assert result['readings'][-1]['date'] == '2026-01-06'
    assert all(r['language'] == 'en' for r in result['readings'])
    assert not re.search('[가-힣]',result['text'])


def test_english_missing_profile_is_actionable_and_never_fabricates_reading():
    result = prepare_reading('/today',language='en')
    assert not result['ok'] and 'Birth information' in result['text']
    assert 'reading' not in result
    assert prepare_reading('/today',language='zh')['error'] == 'unsupported_language'
    tarot = prepare_reading('/tarot question | 0 8r 21',language='en')
    assert tarot['ok'] and 'Three-card spread' in tarot['text']


def test_default_engine_and_kline_use_profile_calendar_date():
    from hermes_ext.fortune_oracle import localization, kline
    profile = {**PROFILE,'reading_timezone':'America/Los_Angeles'}
    with patch.object(localization,'local_today',return_value=date(2025,12,31)):
        daily = build_personalized_daily(profile)
        candle = kline.build_daily_candle(profile)
        month = kline.build_monthly_kline(profile)
    assert daily['date'] == '2025-12-31'
    assert candle.date == date(2025,12,31) and candle.close == daily['score']
    assert month[0].date == date(2025,12,1) and month[-1].date == date(2025,12,31)


def test_english_core_facade_and_cli_use_real_localized_reading(tmp_path):
    from hermes_ext.fortune_oracle import core
    text = core.render_daily_fortune(profile={**PROFILE,'language':'en'})
    assert 'Overall' in text and not re.search('[가-힣]',text)
    path = tmp_path/'profile.json'
    path.write_text(json.dumps(PROFILE))
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable,'-m','hermes_ext.fortune_oracle','today',
        '--profile',str(path),'--lang','en','--reading-timezone','America/Los_Angeles','--json'],
        env={**os.environ,'PYTHONPATH':str(root/'plugins')},cwd=root,capture_output=True,text=True)
    assert result.returncode == 0 and not result.stderr
    reading = json.loads(result.stdout)
    assert reading['language'] == 'en' and reading['reading_timezone'] == 'America/Los_Angeles'
    assert not re.search('[가-힣]',reading['text'])


def test_english_voice_uses_localized_calculation_and_preserves_text_on_tts_failure(tmp_path):
    calls = []
    def failed_tts(**kwargs):
        calls.append(kwargs)
        return {'success':False}
    result = prepare_reading('/voice_fortune',profile=PROFILE,language='en',
        reading_timezone='America/Los_Angeles',now=NOW,tts=failed_tts,output_root=tmp_path)
    assert not result['ok'] and result['error'] == 'tts_unavailable'
    assert result['reading']['date'] == '2025-12-31'
    assert len(calls) == 1 and calls[0]['text'] == result['text_fallback']
    assert 'Overall' in calls[0]['text'] and not re.search('[가-힣]',calls[0]['text'])
    assert '1990-05-15' not in calls[0]['text']
    assert list(tmp_path.iterdir()) == []
