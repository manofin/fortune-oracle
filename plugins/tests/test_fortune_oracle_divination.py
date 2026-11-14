"""Draw integrity, known hexagrams, replay, privacy and actual public routes."""
import itertools
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle.divination import (
    TAROT_DECK, build_tarot_reading, build_iching_reading, hexagram_number,
)
from hermes_ext.fortune_oracle.platforms.telegram import prepare_divination, parse_command


def test_complete_deck_and_draw_without_replacement():
    assert len(TAROT_DECK) == len({row[0] for row in TAROT_DECK}) == 78
    assert TAROT_DECK[8][0] == '힘'
    assert TAROT_DECK[11][0] == '정의'
    for seed in range(100):
        reading = build_tarot_reading('다음 행동은?', rng=random.Random(seed))
        assert len({c['id'] for c in reading['cards']}) == 3
        assert [c['position'] for c in reading['cards']] == ['현재 상황','살펴볼 과제','다음 작은 행동']
    for index in range(78):
        reading = build_tarot_reading('질문', draws=[(index,False),((index+1)%78,True),((index+2)%78,False)])
        assert reading['cards'][0]['name'] == TAROT_DECK[index][0]
        assert reading['cards'][0]['interpretation']


def test_tarot_replay_and_reversed_interpretation():
    reading = build_tarot_reading('비밀 질문', draws=[(0,False),(8,True),(21,False)])
    assert reading == build_tarot_reading('다른 질문', draws=[(0,False),(8,True),(21,False)])
    assert reading['cards'][1]['reversed'] is True
    assert '주의할 패턴' in reading['cards'][1]['interpretation']
    normal = build_tarot_reading('질문', draws=[(0,False),(8,False),(21,False)])
    assert reading['cards'][1]['interpretation'] != normal['cards'][1]['interpretation']
    assert '비밀 질문' not in json.dumps(reading, ensure_ascii=False)


@pytest.mark.parametrize('draws', [[], [(1,False)]*3, [(78,False),(1,False),(2,False)],
    [(True,False),(1,False),(2,False)], [(0,1),(1,False),(2,False)], [None,None,None]])
def test_invalid_tarot_draw_is_rejected(draws):
    with pytest.raises(ValueError):
        build_tarot_reading('질문', draws=draws)


@pytest.mark.parametrize('lines,number', [([7]*6,1),([8]*6,2),
    ([7,8,8,8,7,8],3),([7,8,7,8,7,8],63),([8,7,8,7,8,7],64)])
def test_known_hexagrams_bottom_first(lines,number):
    assert hexagram_number(lines) == number


def test_all_64_hexagrams_are_reachable_and_distinct():
    numbers = [hexagram_number(list(bits)) for bits in itertools.product((7,8),repeat=6)]
    assert set(numbers) == set(range(1,65))
    for bits in itertools.product((7,8),repeat=6):
        result = build_iching_reading('질문',lines=list(bits))
        assert result['changing_lines'] == []
        assert result['hexagram']['number'] == result['transformed']['number']
        assert result['hexagram']['theme']


def test_changing_yin_and_yang_transform_and_display_order():
    reading = build_iching_reading('질문',lines=[6,9,8,7,8,7])
    assert reading['changing_lines'] == [1,2]
    assert reading['transformed']['lines'] == [7,8,8,7,8,7]
    text = reading['text']
    assert text.index('6효') < text.index('1효')
    assert '효사를 계산하거나 인용한 결과는 아닙니다' in text
    assert build_iching_reading('질문',lines=[6]*6)['transformed']['number'] == 1
    assert build_iching_reading('질문',lines=[9]*6)['transformed']['number'] == 2


def test_three_coin_distribution_is_one_three_three_one_not_uniform_totals():
    totals = Counter()
    class Coins:
        def __init__(self, triple):
            self.values = iter(triple * 6)
        def choice(self, options):
            assert options == (2,3)
            return next(self.values)
    for triple in itertools.product((2,3),repeat=3):
        reading = build_iching_reading('질문',rng=Coins(triple))
        assert reading['coins'] == [list(triple)] * 6
        assert reading['lines'] == [sum(triple)] * 6
        totals[reading['lines'][0]] += 1
    assert totals == {6:1,7:3,8:3,9:1}


@pytest.mark.parametrize('lines', [[7]*5,[7]*7,[5]*6,[True]*6,'777777'])
def test_invalid_iching_lines_rejected(lines):
    with pytest.raises(ValueError):
        build_iching_reading('질문',lines=lines)


@pytest.mark.parametrize('builder', [build_tarot_reading,build_iching_reading])
@pytest.mark.parametrize('question', ['', '  ', 'x'*501, None])
def test_question_required_and_bounded(builder,question):
    with pytest.raises(ValueError):
        builder(question)


def test_default_randomness_uses_system_source_and_explicit_replay_skips_it():
    fake = random.Random(42)
    with patch('hermes_ext.fortune_oracle.divination.SystemRandom', return_value=fake) as system:
        build_tarot_reading('질문')
        build_iching_reading('질문')
        assert system.call_count == 2
    with patch('hermes_ext.fortune_oracle.divination.SystemRandom', side_effect=AssertionError):
        assert build_tarot_reading('질문',draws=[(0,False),(1,False),(2,True)])['ok']
        assert build_iching_reading('질문',lines=[7]*6)['ok']


def test_telegram_routes_question_to_draw_to_text_with_aliases_and_replay():
    reading = prepare_divination('/타로@mybot\t중요한 선택 | 0 8r 21')
    assert reading['ok'] and reading['kind'] == 'tarot'
    assert reading['cards'][1]['reversed'] is True
    assert '타로 · 3장' in reading['text']
    cast = prepare_divination('/주역 중요한 선택 | 7 8 7 8 7 8')
    assert cast['hexagram']['number'] == 63
    assert cast['coins'] is None
    assert '중요한 선택' not in cast['text']
    assert parse_command('/iching 질문')['command'] == 'iching'


@pytest.mark.parametrize('text', ['/tarot','/iching','/tarot 질문 | 1 1 2',
    '/tarot 질문 | 78 0 1','/iching 질문 | 7 7 7','/iching 질문 | a b c d e f'])
def test_route_invalid_input_does_not_draw_fake_result(text):
    result = prepare_divination(text)
    assert result['ok'] is False
    assert result['error'] == 'invalid_input'
    assert 'cards' not in result and 'hexagram' not in result


@pytest.mark.parametrize('exception', [RuntimeError, ValueError])
def test_draw_failure_does_not_leak_exception_or_question(exception):
    class Broken:
        def sample(self,*args):
            raise exception('PRIVATE token')
    result = prepare_divination('/tarot PRIVATE question',rng=Broken())
    assert result['ok'] is False and result['error'] == 'draw_unavailable'
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('reading,input_text,expected_kind', [
    ('iching','질문 | 7 8 7 8 7 8','iching'),
    ('tarot','질문 | 0 8r 21','tarot'),
    ('compatibility','1990-05-15 07:30 | 1988-03-02 22:10',None),
])
def test_cli_replay_is_a_real_public_execution_path(reading,input_text,expected_kind):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ,'PYTHONPATH':str(root/'plugins')}
    command = [sys.executable,'-m','hermes_ext.fortune_oracle']
    result = subprocess.run(command+[reading,input_text,'--json'],
        cwd=root,env=env,capture_output=True,text=True)
    assert result.returncode == 0
    assert not result.stderr
    data = json.loads(result.stdout)
    assert data['ok'] is True
    if expected_kind:
        assert data['kind'] == expected_kind
    if reading == 'iching':
        assert data['hexagram']['number'] == 63
    elif reading == 'tarot':
        assert [c['id'] for c in data['cards']] == [0,8,21]
    else:
        assert len(data['charts']) == 2
    failed = subprocess.run(command+['tarot'],cwd=root,env=env,capture_output=True,text=True)
    assert failed.returncode == 1
    assert '질문을' in failed.stdout
