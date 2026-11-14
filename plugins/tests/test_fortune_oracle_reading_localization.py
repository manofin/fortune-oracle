from copy import deepcopy
from itertools import product
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle.divination import build_tarot_reading, build_iching_reading
from hermes_ext.fortune_oracle.reading_localization import localize_reading,TAROT_EN,HEXAGRAM_EN
from hermes_ext.fortune_oracle.platforms.telegram import prepare_reading


def english(text):
    assert not re.search('[가-힣]',text)


def test_every_card_has_english_name_and_both_orientations_without_redraw():
    assert len(TAROT_EN) == 78
    assert len({c[0] for c in TAROT_EN}) == 78
    assert TAROT_EN[8][0] == 'Strength' and TAROT_EN[11][0] == 'Justice'
    for index in range(78):
        ko = build_tarot_reading('질문',draws=[(index,False),((index+1)%78,True),((index+2)%78,False)])
        original = deepcopy(ko)
        with patch('hermes_ext.fortune_oracle.divination.SystemRandom',side_effect=AssertionError('must not draw')):
            en = localize_reading(ko,'en')
        assert ko == original
        assert [(c['id'],c['reversed']) for c in en['cards']] == [(c['id'],c['reversed']) for c in ko['cards']]
        assert en['evidence'] == ko['evidence']
        english(en['text'])
        assert all(c['interpretation'] for c in en['cards'])


def test_every_hexagram_preserves_lines_numbers_and_changing_evidence():
    assert len(HEXAGRAM_EN) == len({h[0] for h in HEXAGRAM_EN}) == 64
    for values in product((6,9),repeat=6):
        ko = build_iching_reading('질문',lines=list(values))
        original = deepcopy(ko)
        en = localize_reading(ko,'en')
        assert ko == original
        for key in ('lines','coins','changing_lines','evidence'):
            assert en[key] == ko[key]
        assert en['hexagram']['number'] == ko['hexagram']['number']
        assert en['transformed']['number'] == ko['transformed']['number']
        assert en['transformed']['lines'] == ko['transformed']['lines']
        english(en['text'])
    fixed = prepare_reading('/iching question | 7 8 7 8 7 8',language='en')
    assert fixed['hexagram']['name'] == 'After Completion'
    assert 'No changing lines' in fixed['text']


def test_english_compatibility_preserves_two_real_charts_and_cross_evidence():
    from hermes_ext.fortune_oracle import bazi_bridge
    command = '/compatibility 1990-05-15 07:30 | 1988-03-02 22:10'
    with patch.object(bazi_bridge.subprocess,'run',wraps=subprocess.run) as node:
        ko = prepare_reading(command)
        en = prepare_reading(command,language='en')
    assert node.call_count == 4  # Two independent user requests, exactly two charts each.
    for key in ('charts','cross_relations','day_master_relation','evidence','status'):
        assert ko[key] == en[key]
    english(en['text'])
    assert 'success probability' in en['text']
    assert '1990-05-15' not in en['text'] and '07:30' not in en['text']
    partial = prepare_reading('/compatibility 1990-05-15 | 1988-03-02',language='en')
    assert partial['status'] == 'partial' and 'hour pillar' in partial['text']


@pytest.mark.parametrize('command', ['/tarot','/iching','/compatibility', '/unknown'])
def test_english_input_errors_are_safe_and_do_not_claim_results(command):
    result = prepare_reading(command,language='en')
    assert not result['ok']
    english(result['text'])
    assert 'cards' not in result and 'charts' not in result


def test_english_voice_routes_completed_draw_once(tmp_path):
    calls = []
    def tts(**kwargs):
        calls.append(kwargs)
        return {'success':False}
    result = prepare_reading('/voice_fortune tarot question | 0 8r 21',language='en',tts=tts,output_root=tmp_path)
    assert not result['ok'] and result['error'] == 'tts_unavailable'
    assert result['reading']['language'] == 'en'
    assert [c['id'] for c in result['reading']['cards']] == [0,8,21]
    assert len(calls) == 1 and calls[0]['text'] == result['text_fallback']
    english(calls[0]['text'])


@pytest.mark.parametrize('command,input_text', [('tarot','question | 0 8r 21'),
    ('iching','question | 7 8 7 8 7 8'),
    ('compatibility','1990-05-15 07:30 | 1988-03-02 22:10')])
def test_public_cli_english_readings(command,input_text):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable,'-m','hermes_ext.fortune_oracle',command,input_text,'--lang','en','--json'],
        env={**os.environ,'PYTHONPATH':str(root/'plugins')},cwd=root,capture_output=True,text=True)
    assert result.returncode == 0 and not result.stderr
    reading = json.loads(result.stdout)
    assert reading['ok'] and reading['language'] == 'en'
    english(reading['text'])


def test_english_kline_candles_keep_ohlc_and_localize_text():
    from hermes_ext.fortune_oracle import kline
    profile = {'birth_date':'1990-05-15','birth_time':'07:30','gender':'male'}
    ko = kline.build_monthly_kline(profile,2026,10)
    en = kline.build_monthly_kline({**profile,'language':'en'},2026,10)
    assert [(c.date,c.open,c.close,c.high,c.low) for c in ko] == [(c.date,c.open,c.close,c.high,c.low) for c in en]
    assert all(not re.search('[가-힣]',c.label+c.dayun_theme) for c in en)
    text = kline.render_month_kline({**profile,'language':'en'},year=2026,month=10)
    english(text)
    assert 'Oct 2026' in text and 'interpretive index' in text
    assert '31 days' in text
    annual = kline.render_life_kline({**profile,'language':'en'},year=2026)
    english(annual)
    assert '12 months' in annual
    assert 'no K-line' in kline.render_month_kline({'language':'en'})


def test_english_png_has_translated_labels_caption_and_verified_image(tmp_path):
    from hermes_ext.fortune_oracle import chart_renderer,core
    from matplotlib.text import Text
    from PIL import Image
    profile = {'birth_date':'1990-05-15','birth_time':'07:30','gender':'male','language':'en'}
    captured = []
    original = Text.set_text
    def capture(self,text):
        if text:
            captured.append(str(text))
        return original(self,text)
    with patch.object(Text,'set_text',capture):
        path = chart_renderer.render_month_card_png(profile,year=2026,month=10,output_path=tmp_path/'english.png')
    english('\n'.join(captured))
    assert any('Average' in t for t in captured)
    assert any('calendar years' in t for t in captured)
    image = Image.open(path).convert('RGB')
    assert image.width > 800 and image.height > 400
    assert any(low != high for low,high in image.getextrema())
    # Caption is checked with the real renderer, not a hand-built mock response.
    response = core.render_kline_card(profile=profile,year=2026,month=10)
    english(response)
    assert response.startswith('MEDIA:') and '2026-10 K-line card' in response
    Path(response.splitlines()[0][6:]).unlink()
    english(core.render_kline_card(profile={'language':'en'}))


def test_english_help_and_voice_invalid_command_are_localized():
    help_result = prepare_reading('/help',language='en')
    assert help_result['ok'] and '/tarot question' in help_result['text']
    english(help_result['text'])
    failed = prepare_reading('/voice_fortune unknown',language='en')
    assert not failed['ok']
    english(failed['text_fallback'])


def test_kline_command_route_honors_calendar_and_calls_chart_once():
    from datetime import datetime,timezone
    from hermes_ext.fortune_oracle import bazi_bridge
    profile = {'birth_date':'1990-05-15','birth_time':'07:30','gender':'male'}
    now = datetime(2026,1,1,1,tzinfo=timezone.utc)
    with patch.object(bazi_bridge.subprocess,'run',wraps=subprocess.run) as node:
        result = prepare_reading('/month_kline',profile=profile,language='en',
                                reading_timezone='America/Los_Angeles',now=now)
    assert node.call_count == 1 and result['ok']
    assert result['candles'][0]['date'] == '2025-12-01'
    assert result['candles'][-1]['date'] == '2025-12-31'
    english(result['text'])
    assert prepare_reading('/month_kline 2026-13',profile=profile,language='en')['ok'] is False
    assert prepare_reading('/year_kline 2026',profile=profile,language='en')['ok'] is True
