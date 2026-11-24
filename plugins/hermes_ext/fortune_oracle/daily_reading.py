"""Localized daily/tomorrow/week response using the user's current time zone."""
from datetime import timedelta
from collections.abc import Mapping

from .localization import language_code, local_today, reading_zone, localize_daily, DISCLAIMER_EN
from .localization import NOT_CALCULATED_KO, NOT_CALCULATED_EN
from .daily_fortune_engine import build_personalized_daily, build_personalized_series, render_daily_channel_text


def prepare_daily_reading(profile=None, *, day='today', language=None, reading_timezone=None, now=None, compact=False):
    profile = dict(profile) if isinstance(profile,Mapping) else {}
    try:
        code = language_code(language if language is not None else profile.get('language'))
    except ValueError:
        return {'ok':False,'computed':False,'error':'unsupported_language',
                'text':f'{NOT_CALCULATED_KO} / {NOT_CALCULATED_EN}\nUnsupported language; use ko or en. / 한국어(ko) 또는 영어(en)를 선택해 주세요.'}
    def failure(error, message):
        notice = NOT_CALCULATED_EN if code == 'en' else NOT_CALCULATED_KO
        return {'ok':False,'computed':False,'error':error,'language':code,'text':f'{notice}\n{message}'}
    unavailable = 'Calculation failed. Please check your birth information and time zone, or try again later.' if code == 'en' else '개인화 계산 불가 — 출생정보·시간대를 확인하거나 잠시 후 다시 시도해 주세요.'
    try:
        zone = reading_zone(profile,reading_timezone)
        today = local_today(profile,reading_timezone=reading_timezone,now=now)
        if day not in {'today','tomorrow','week'}:
            raise ValueError('Unsupported period')
    except ValueError:
        return failure('invalid_time_context', 'Use a valid IANA reading time zone and period.' if code == 'en' else '올바른 IANA 시간대와 기간을 선택해 주세요.')
    if not profile.get('birth_date'):
        return failure('calculation_unavailable',
                       'Birth information is missing. Register it with /register_birth.' if code == 'en' else
                       '출생정보가 없습니다. /register_birth 로 등록해 주세요.')
    basis = ('Interpretation based on calculated birth-chart and daily pillars; scores and advice are heuristic, not probabilities.'
             if code == 'en' else '계산된 사주·일진을 바탕으로 한 해석입니다.')
    target = today + timedelta(days=1 if day == 'tomorrow' else 0)
    if day == 'week':
        dates = [target+timedelta(days=i) for i in range(7)]
        try:
            readings = build_personalized_series(profile,dates)
        except Exception:
            return failure('calculation_unavailable', unavailable)
        if not readings:
            return failure('calculation_unavailable', unavailable)
        readings = [localize_daily(r,code) for r in readings]
        title = 'Seven-day reflection' if code == 'en' else '7일 운세'
        lines = [basis, f'{title} · {target.isoformat()} · {zone.key}']
        lines.extend(f"{r['date']} · {r['score']:.0f}/100 · {r['grade']}" for r in readings)
        lines.append(DISCLAIMER_EN if code == 'en' else readings[0]['disclaimer'])
        return {'ok':True,'computed':True,'kind':'week','language':code,'reading_timezone':zone.key,
                'readings':readings,'text':'\n'.join(lines)}
    try:
        result = build_personalized_daily(profile,target_date=target,language=code)
    except Exception:
        return failure('calculation_unavailable', unavailable)
    if not result:
        return failure('calculation_unavailable', unavailable)
    text = (render_daily_channel_text(result, reading_timezone=zone.key) if compact else
            '\n'.join([basis, f"{result['date']} · {zone.key}",*result['lines'],result['disclaimer']]))
    return {'ok':True,'computed':True,'kind':'daily','language':code,'reading_timezone':zone.key,
            'date':result['date'],'reading':result,'text':text}


def prepare_kline_reading(profile=None, *, command='month_kline', args='', language=None,
                          reading_timezone=None, now=None):
    """Calendar-aware text/card route. One chart calculation per requested period."""
    import re
    from .kline import build_monthly_kline, build_yearly_kline, summarize_kline
    profile = dict(profile) if isinstance(profile,Mapping) else {}
    try:
        code = language_code(language if language is not None else profile.get('language'))
        zone = reading_zone(profile,reading_timezone)
        today = local_today(profile,reading_timezone=reading_timezone,now=now)
        profile.update(language=code,reading_timezone=zone.key)
        period = 'year' if command in {'life_kline','year_kline'} else 'month'
        value = args.strip()
        if command == 'kline_card' and value in {'year','month'}:
            period,value = value,''
        elif command == 'kline_card' and value.startswith(('year ','month ')):
            period,value = value.split(maxsplit=1)
        year,month = today.year,today.month
        if value:
            if period == 'year' and re.fullmatch(r'\d{4}',value):
                year = int(value)
            elif period == 'month' and re.fullmatch(r'\d{4}-\d{2}',value):
                year,month = map(int,value.split('-'))
            else:
                raise ValueError('Invalid period')
        from datetime import date
        date(year,month,1)
    except ValueError:
        return {'ok':False,'error':'invalid_input','text':
            'Use a valid IANA zone and YYYY-MM (monthly) or YYYY (annual).' if language == 'en' or profile.get('language') == 'en' else
            '올바른 IANA 시간대와 월간 YYYY-MM 또는 연간 YYYY를 입력해 주세요.'}
    if command == 'kline_card':
        from .core import render_kline_card
        result = render_kline_card(profile=profile,period=period,year=year,month=month)
        if not result.startswith('MEDIA:'):
            return {'ok':False,'error':'renderer_unavailable','language':code,'text':result}
        return {'ok':True,'kind':'kline_card','language':code,'reading_timezone':zone.key,
                'media_response':result,'text':'\n'.join(result.splitlines()[1:])}
    candles = build_yearly_kline(profile,year) if period == 'year' else build_monthly_kline(profile,year,month)
    title = (f'{year} Annual K-line' if period == 'year' else f'{year}-{month:02d} K-line') if code == 'en' else (
             f'{year}년 인생 K선' if period == 'year' else f'{year}년 {month}월 운세 K선')
    text = summarize_kline(candles,title=title,platform='line',unit='개월' if period == 'year' else '일',language=code)
    return {'ok':bool(candles),'kind':'kline','language':code,'reading_timezone':zone.key,
            'error':None if candles else 'calculation_unavailable',
            'candles':[{'date':c.date.isoformat(),'open':c.open,'close':c.close,'high':c.high,'low':c.low} for c in candles],
            'text':text}
