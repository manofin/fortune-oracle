"""Validate actual provider output without another live inference call."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from hermes_ext.fortune_oracle import deep_review as review


def result(payload, context=None):
    provider = Mock(return_value=json.dumps(payload,ensure_ascii=False))
    response = review.analyze_deep_review(context or {},provider=provider,enabled=True)
    provider.assert_called_once()
    return response


def safe_payload():
    return {'sections':[{'title':'해석','summary':'해석(경험적 참고): 현재의 선택을 돌아보세요.'}]}


@pytest.mark.parametrize('payload', [
    {'sections':[{'title':'반드시 성공합니다','summary':'인과적 단정은 아닙니다.'}]},
    {'sections':[{'summary':'반드시 성공합니다만 인과적 단정은 아닙니다.'}]},
    {'title':'반드시 투자하세요','style':'taheo_qna','sections':[{'heading':'해석','body':'일상을 돌아보세요.'}]},
])
def test_rendered_claims_cannot_hide_in_titles_or_disclaimers(payload):
    assert result(payload)['source']=='template'


@pytest.mark.parametrize('value',[None,{},[],False,42])
@pytest.mark.parametrize('field',['summary','title','reflection_question'])
def test_nontext_section_fields_fail_without_exception_or_coercion(field,value):
    data=safe_payload(); data['sections'][0][field]=value
    assert result(data)['source']=='template'


@pytest.mark.parametrize('field',['title','reflection_question','final_advice','style','disclaimer'])
def test_nontext_top_level_fields_fail_closed(field):
    data=safe_payload(); data[field]={'untrusted':'private detail'}
    assert result(data)['source']=='template'


@pytest.mark.parametrize('sections',[[],[{}],[{'summary':'  '}],[{'title':'해석'}],[{'body':'다른 형식의 본문'}]])
def test_short_reply_requires_visible_nonblank_body(sections):
    assert result({'sections':sections},{'style':'short'})['source']=='template'


def test_requested_qna_style_requires_qna_body():
    assert result(safe_payload(),{'style':'taheo_qna'})['source']=='template'
    accepted=result({'sections':[{'heading':'질문','body':'해석(경험적 참고): 선택을 돌아보세요.'}]},{'style':'taheo_qna'})
    assert accepted['source']=='deep_provider' and accepted['style']=='taheo_qna'


@pytest.mark.parametrize('warnings',[None,'not a list',[{}],[42]])
def test_malformed_warning_metadata_is_rejected(warnings):
    data=safe_payload();data['warnings']=warnings
    assert result(data)['source']=='template'


@pytest.mark.parametrize('claim',['통계적 경향','통계적 패턴'])
def test_unsupported_statistical_claim_is_independently_rejected(claim):
    data=safe_payload();data['sections'][0]['summary']='이는 '+claim+'입니다.'
    assert result(data)['source']=='template'


def test_harmless_interpretation_with_product_disclaimer_remains_accepted():
    data=safe_payload();data['disclaimer']='의학, 투자, 법률 결정을 지시하지 않습니다.'
    assert result(data)['source']=='deep_provider'


CASES=json.loads((Path(__file__).parent/'fixtures/deep_mac_recorded_responses.json').read_text())
@pytest.mark.parametrize('case',CASES,ids=lambda c:'mac-attempt-'+str(c['attempt']))
def test_recorded_live_outputs_remain_suppressed_offline(case):
    # Historical real responses only. No provider, socket or live data source.
    assert result(json.loads(case['raw_response']))['source']=='template'


def test_statistical_claim_does_not_depend_on_unrelated_certainty_word():
    raw=next(c['raw_response'] for c in CASES if c['attempt']==4)
    assert result(json.loads(raw.replace('반드시 ','')))['source']=='template'
