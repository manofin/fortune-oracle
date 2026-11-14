"""Two explicitly supplied profiles → real Bazi charts → cross-chart evidence.

No user-ID lookup or persistence. No synthetic compatibility score or outcome
prediction. Unknown birth time excludes the assumed hour pillar everywhere.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
from typing import Mapping

from .bazi_bridge import calculate_bazi_from_profile
from .bazi_relations import LIU_HE, LIU_CHONG
from .daily_fortune_engine import _stem_element, _branch_element, _element_day_relation

_PILLARS = {'year':'년주', 'month':'월주', 'day':'일주', 'time':'시주'}
_RELATIONS = {'same':'같은 오행', 'output':'A의 오행이 B의 오행을 생함',
              'input':'B의 오행이 A의 오행을 생함', 'wealth':'A의 오행이 B의 오행을 극함',
              'pressure':'B의 오행이 A의 오행을 극함'}
_UNAVAILABLE = {'ok': False, 'status':'blocked', 'error':'calculation_unavailable',
                'text':'두 사람의 출생정보를 확인해 주세요. 계산이 완료되지 않아 궁합을 표시할 수 없습니다.'}


def _valid_profile(profile) -> bool:
    if not isinstance(profile, Mapping) or not isinstance(profile.get('birth_date'),str):
        return False
    try:
        birth = date.fromisoformat(profile['birth_date'])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',profile['birth_date']) or not 1800 <= birth.year <= 2100:
            return False
        time = profile.get('birth_time')
        if time:
            if not isinstance(time,str) or not re.fullmatch(r'\d{1,2}:\d{2}',time):
                return False
            h,m = map(int,time.split(':'))
            if not 0 <= h <= 23 or not 0 <= m <= 59:
                return False
        zone = profile.get('timezone', 'Asia/Seoul')
        if not isinstance(zone, str):
            return False
        ZoneInfo(zone)
        return True
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return False


def build_compatibility(profile_a, profile_b) -> dict:
    """Each person's chart is calculated once; only cross-chart pairs are compared."""
    if not _valid_profile(profile_a) or not _valid_profile(profile_b):
        return dict(_UNAVAILABLE)
    charts = []
    try:
        for profile in (profile_a,profile_b):
            calculation_input = dict(profile)
            if not calculation_input.get('birth_time'):
                calculation_input.pop('birth_time', None)
            result = calculate_bazi_from_profile(calculation_input)
            if not result.ok or not result.eight_char:
                return dict(_UNAVAILABLE)
            uncertain = set((getattr(result, 'time_basis', {}) or {}).get('uncertain_pillars', []))
            if not uncertain <= {'year', 'month'} or not result.eight_char.get('day'):
                return dict(_UNAVAILABLE)
            pillars = {k:result.eight_char[k] for k in ('year','month','day') if k not in uncertain}
            if profile.get('birth_time'):
                pillars['time'] = result.eight_char['time']
            for pillar in pillars.values():
                if len(pillar) != 2 or not _stem_element(pillar[0]) or not _branch_element(pillar[1]):
                    return dict(_UNAVAILABLE)
            elements = {e:0 for e in ('목','화','토','금','수')}
            for pillar in pillars.values():
                elements[_stem_element(pillar[0])] += 1
                elements[_branch_element(pillar[1])] += 1
            charts.append({'pillars':pillars, 'elements':elements,
                           'day_master':pillars['day'][0], 'backend':result.engine,
                           'uncertain_pillars':sorted(uncertain),
                           'birth_time_known':bool(profile.get('birth_time')),
                           'birth_timezone':profile.get('timezone', 'Asia/Seoul'),
                           'timezone_source':'explicit' if 'timezone' in profile else 'default'})
    except Exception:
        return dict(_UNAVAILABLE)

    first,second = charts
    a_el,b_el = _stem_element(first['day_master']),_stem_element(second['day_master'])
    relation = _element_day_relation(a_el,b_el)
    matches = []
    for a_key,a_pillar in first['pillars'].items():
        for b_key,b_pillar in second['pillars'].items():
            pair = frozenset((a_pillar[1],b_pillar[1]))
            for table,label in ((LIU_HE,'육합'),(LIU_CHONG,'육충')):
                if pair in table:
                    matches.append({'a_pillar':a_key,'b_pillar':b_key,
                                    'branches':[a_pillar[1],b_pillar[1]],'relation':label})
    partial = not all(c['birth_time_known'] for c in charts) or any(c['uncertain_pillars'] for c in charts)
    text = ['두 사람 비교 · 사주 계산 근거',
            f'일간: A {first["day_master"]}({a_el}) · B {second["day_master"]}({b_el})',
            '오행 관계: ' + _RELATIONS[relation] + '. 좋은 관계·나쁜 관계의 판정이 아닙니다.']
    for label,chart in zip(('A','B'),charts):
        text.append(label + ' 출생 시간대: ' + chart['birth_timezone']
                    + (' (미입력 기본값)' if chart['timezone_source'] == 'default' else ''))
        text.append(label + ' 오행 분포: ' + ' · '.join(f'{e} {n}' for e,n in chart['elements'].items()))
    text.append('양쪽 지지 비교 (같은 사람 안의 합·충은 제외):')
    if not matches:
        text.append('육합·육충 일치 없음. 이것만으로 관계의 질을 판단할 수 없습니다.')
    for match in matches:
        text.append(f'A {_PILLARS[match["a_pillar"]]} {match["branches"][0]} ↔ '
                    f'B {_PILLARS[match["b_pillar"]]} {match["branches"][1]}: {match["relation"]}')
    if any(m['relation'] == '육충' for m in matches):
        text.append('성찰 질문: 생활 속 속도·경계·결정 방식이 다른 부분을 어떻게 조율할까요?')
    else:
        text.append('성찰 질문: 함께 유지하고 싶은 습관과 서로에게 필요한 도움은 무엇인가요?')
    if partial:
        text.append('출생시각 미등록: 해당 사람의 시주와 시주 오행은 제외한 부분 비교입니다.')
    for label, chart in zip(('A', 'B'), charts):
        if chart['uncertain_pillars']:
            text.append(label + ' 절기 경계 미확정: ' + '·'.join(_PILLARS[key] for key in chart['uncertain_pillars'])
                        + '와 해당 오행·지지 비교를 제외했습니다.')
    text.extend(['근거: 각 프로필 사주 계산 1회 · 일간 오행 관계와 양쪽 지지의 육합·육충 표 대조.',
                 '오락과 자기성찰용입니다. 결혼·이별 여부나 관계 성공 확률을 예측하지 않습니다.'])
    return {'ok':True,'status':'partial' if partial else 'runnable', 'charts':charts,
            'day_master_relation':relation,'cross_relations':matches,
            'evidence':{'calculation':'two_bazi_charts','comparison':'cross_chart_only',
                        'tables':['bazi_relations.LIU_HE','bazi_relations.LIU_CHONG']},
            'text':'\n'.join(text)}
