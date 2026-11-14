from dataclasses import replace
from datetime import date
import pytest
from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as engine

@pytest.mark.parametrize('birth,time,zeros,expected', [
    ('1990-01-01','12:00',1,['금','토']),
    ('1990-05-15','07:30',2,['목','수']),
    ('1995-08-19','07:45',0,['토','화']),
])
def test_real_node_sparse_complete(monkeypatch, birth, time, zeros, expected):
    profile = dict(birth_date=birth, birth_time=time, timezone='Asia/Seoul', gender='male')
    result = bazi_bridge.calculate_bazi_from_profile(profile)
    assert result.ok, result
    counts = {engine._element_key(k): v for k,v in result.elements.items()}
    assert 5-len(counts) == zeros
    complete = replace(result, elements={e: counts.get(e,0) for e in '목화토금수'})
    target = date(2026,11,9)
    sparse_reading = engine._daily_from_chart(profile,result,target,'종합')
    full_reading = engine._daily_from_chart(profile,complete,target,'종합')
    print(birth, time, sparse_reading['score'], full_reading['score'])
    assert sparse_reading == full_reading
    assert sorted(full_reading['favorable_elements']) == expected
    monkeypatch.setattr(bazi_bridge,'calculate_bazi_from_profile',lambda p: result)
    monkeypatch.setattr(engine,'_profile_today',lambda p: target)
    assert engine.build_personalized_daily(profile) == engine.build_personalized_daily(profile,target_date=target)
    assert engine.build_personalized_series(profile,[target])[0]['score'] == full_reading['score']

from test_fortune_oracle_web import app, session
from datetime import datetime, timezone

@pytest.mark.parametrize('birth,time', [('1990-01-01','12:00'), ('1990-05-15','07:30'), ('1995-08-19','07:45')])
def test_http_parity(app, birth, time):
    app.config['NOW'] = datetime(2026,11,9,1,tzinfo=timezone.utc)
    client = app.test_client()
    headers = session(client)
    assert client.put('/api/profile',json=dict(birth_date=birth,birth_time=time,timezone='Asia/Seoul',gender='male'),headers=headers).status_code == 200
    today = client.get('/api/readings/today').json['reading']['score']
    assert client.post('/api/readings/date',json={'date':'2026-11-09'},headers=headers).json['reading']['score'] == today
    assert client.get('/api/readings/week').json['readings'][0]['score'] == today
    candles = client.get('/api/kline').json['candles']
    assert next(c['close'] for c in candles if c['date']=='2026-11-09') == today

@pytest.mark.parametrize('counts', [None, {}, {'목':0}, {'목':-1}, {'목':'1'}, {'unknown':8}])
def test_invalid_counts_fail_closed(monkeypatch, counts):
    from types import SimpleNamespace
    result = SimpleNamespace(ok=True,eight_char={'year':'己巳','month':'丙子','day':'丙寅'},elements=counts)
    monkeypatch.setattr(bazi_bridge,'calculate_bazi_from_profile',lambda p:result)
    assert engine.build_personalized_daily({'birth_date':'1990-01-01'}) is None
    assert engine.build_personalized_series({'birth_date':'1990-01-01'},[date(2026,11,9)]) is None
