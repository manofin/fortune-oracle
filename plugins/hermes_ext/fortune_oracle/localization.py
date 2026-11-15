"""Explicit Korean/English presentation and IANA reading time zones.

Reading time zone is independent from birth-location time zone. No guessing
from place names or server local time; unknown zones/languages are rejected.
"""
from datetime import datetime, timezone
from collections.abc import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ELEMENT_EN = {'목':'Wood','화':'Fire','토':'Earth','금':'Metal','수':'Water'}
ASPECT_EN = {'종합':'Overall','활동':'Activity','관계':'Relationships','재물':'Resources','건강':'Well-being'}
_STEMS = dict(zip('갑을병정무기경신임계', ('Jia','Yi','Bing','Ding','Wu','Ji','Geng','Xin','Ren','Gui')))
_STEMS.update(dict(zip('甲乙丙丁戊己庚辛壬癸',_STEMS.values())))
_BRANCHES = dict(zip('자축인묘진사오미신유술해',('Zi','Chou','Yin','Mao','Chen','Si','Wu','Wei','Shen','You','Xu','Hai')))
_BRANCHES.update(dict(zip('子丑寅卯辰巳午未申酉戌亥',_BRANCHES.values())))
DISCLAIMER_EN = 'For entertainment and self-reflection. Not medical, investment or legal advice.'
NOT_CALCULATED_KO = '계산 결과가 아님'
NOT_CALCULATED_EN = 'Not a calculated result'
_KEYWORDS = {'시작':'beginnings','성장':'growth','방향':'direction','계획':'planning','배움':'learning','연결':'connection',
    '속도':'pace','표현':'expression','관심':'attention','행동':'action','관계의 온도':'warmth',
    '안정':'stability','묵묵함':'steadiness','저축':'saving','안정감':'grounding','정돈':'order','마무리':'completion',
    '정리':'organization','결단':'decisiveness','기준':'standards','선별':'selection','단호함':'resolve','숫자':'numbers',
    '회복':'recovery','유연':'flexibility','이동':'movement','대처':'adaptation','균형':'balance'}
_RELATION_EN = {'same':'A useful theme is maintaining your own rhythm.',
    'output':'A useful theme is expressing ideas clearly.', 'input':'A useful theme is learning and organizing.',
    'pressure':'A useful theme is managing demands and leaving room to recover.',
    'wealth':'A useful theme is reviewing resources and responsibilities.',
    'unknown':'Use a small, practical step to reflect on the day.'}


def language_code(value=None):
    if value is None:
        return 'ko'
    if not isinstance(value,str):
        raise ValueError('Unsupported language; use ko or en.')
    code = value.strip().lower().replace('_','-').split('-')[0]
    if code not in {'ko','en'}:
        raise ValueError('Unsupported language; use ko or en.')
    return code


def reading_zone(profile=None, override=None):
    profile = profile if isinstance(profile,Mapping) else {}
    name = override if override is not None else profile.get('reading_timezone') or profile.get('timezone') or 'Asia/Seoul'
    if not isinstance(name,str):
        raise ValueError('Use a valid IANA time zone.')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError,ValueError):
        raise ValueError('Use a valid IANA time zone.') from None


def local_today(profile=None, *, reading_timezone=None, now=None):
    zone = reading_zone(profile,reading_timezone)
    instant = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(instant,datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('The clock must be a timezone-aware datetime.')
    return instant.astimezone(zone).date()


def pillar_label(pillar):
    return f'{_STEMS[pillar[0]]}-{_BRANCHES[pillar[1]]}' if len(pillar) == 2 else ''


def localize_daily(reading, language='ko'):
    code = language_code(language)
    result = {**reading,'language':code}
    if code == 'ko':
        return result
    # Sections currently carry Korean copy only; preserve the established English text.
    result.pop('sections', None)
    score = result['score']
    grade = 'Strong momentum' if score >= 78 else 'Supportive' if score >= 62 else 'Steady' if score >= 46 else 'Take care' if score >= 32 else 'Leave more room'
    keywords = [_KEYWORDS[k] for k in result['keywords']]
    lines = [f"{ASPECT_EN.get(result['aspect'],'Overall')} · {score:.0f}/100 — {grade}",
        f"Day pillar {pillar_label(result['day_pillar'])} ({ELEMENT_EN[result['day_element']]}) · {_RELATION_EN[result['relation']]}",
        'Reflection keywords: ' + ' · '.join(keywords) + '.']
    if result['dayun_pillar']:
        start,end = result['dayun_years']
        result['dayun_theme'] = f"{pillar_label(result['dayun_pillar'])} · calendar years {start}–{end}"
        lines.append(f"Solar-term-based ten-year cycle {pillar_label(result['dayun_pillar'])}, calendar years {start}–{end}. Interpretive adjustment: {result['dayun_adjustment']:+.0f} points.")
    else:
        lines.append('Ten-year cycle adjustment omitted: required inputs or an applicable cycle are unavailable.')
    lines.append('This score is an interpretive index, not a predicted probability.')
    basis = result.get('birth_time_basis', {})
    if basis:
        lines.append('Birth day/hour use local civil time; true solar time correction is not applied.')
        if basis.get('solar_terms') == 'civil_day_interval_confirmed':
            lines.append('Year/month are unchanged throughout the local birth date. Hour and ten-year cycle are omitted.')
        elif basis.get('solar_terms') != 'birth_instant_utc_plus_8':
            lines.append('Without a known birth time, year/month pillars near solar terms are uncertain.')
    result.update(grade=grade,keywords=keywords,lines=lines,disclaimer=DISCLAIMER_EN)
    return result
