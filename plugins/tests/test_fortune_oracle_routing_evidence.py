"""Calculation failures and approximations must remain visible through final rendering."""
from unittest.mock import patch
import pytest

from hermes_ext.fortune_oracle import oracle_method_adapters as adapters
from hermes_ext.fortune_oracle.oracle_input import UnifiedOracleInput
from hermes_ext.fortune_oracle.oracle_method_card import OracleMethodCard
from hermes_ext.fortune_oracle.oracle_renderer import render_final_reading
from hermes_ext.fortune_oracle.qimen_schema import QimenResult, QimenChart, QimenPalace
from hermes_ext.fortune_oracle.bazi_bridge import BaziResult

INPUT = UnifiedOracleInput(birth_datetime="1990-05-15T07:30", gender="male",
                           latitude=37.5665, longitude=126.978, timezone="Asia/Seoul")


def test_qimen_dependency_failure_is_blocked_not_reading():
    with patch("hermes_ext.fortune_oracle.qimen_bridge.calculate_qimen",
               return_value=QimenResult.error("DEPENDENCY_MISSING", "private-path")):
        card = adapters.adapt_qimen(INPUT, question="진로")
    assert card.status == "blocked" and not card.facts and not card.interpretation
    text = render_final_reading([card], include_qimen=True)
    assert "계산할 수 없습니다" in text and "private-path" not in text


def test_qimen_calculated_facts_and_explicit_routing():
    result = QimenResult(ok=True, chart=QimenChart(ganzhi="甲子", pai_ju="陽一局",
                         palaces={"坎": QimenPalace(palace_name="坎", door="休", star="蓬")}))
    with patch("hermes_ext.fortune_oracle.qimen_bridge.calculate_qimen", return_value=result):
        card = adapters.adapt_qimen(INPUT, question="진로")
    assert card.status == "runnable" and card.facts["palaces"]["坎"]["door"] == "休"
    assert "甲子" in render_final_reading([card], include_qimen=True)
    assert "kinqimen" in render_final_reading([card], include_qimen=True)
    assert "기문둔갑" not in render_final_reading([card])


def test_missing_bazi_facts_blocked():
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi", return_value=BaziResult(ok=True)):
        assert adapters.adapt_bazi(INPUT).status == "blocked"


def test_birth_time_unknown_does_not_publish_assumed_time_pillar():
    chart = BaziResult(ok=True, eight_char={"year":"庚午", "month":"辛巳", "day":"庚辰", "time":"假時"})
    with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi", return_value=chart):
        card = adapters.adapt_bazi(UnifiedOracleInput(birth_datetime="1990-05-15"))
    assert card.status == "partial" and "time" not in card.facts["eight_char"]
    assert "假時" not in render_final_reading([card])


def test_ziwei_missing_stars_blocked():
    with patch("hermes_ext.fortune_oracle.ziwei_bridge.calculate_ziwei_chart",
               return_value={"ok": True, "stars": {}}):
        card = adapters.adapt_ziwei(INPUT)
    assert card.status == "blocked" and not card.facts


def test_ziwei_normalizes_real_sihua_and_preserves_missing_data():
    result = {"ok": True, "stars": {"0": ["太陽"]}, "ming_gong": {"branch": "子", "index": 0},
              "sihua": {"lu": {"star": "太陽", "palace_index": 0}}}
    with patch("hermes_ext.fortune_oracle.ziwei_bridge.calculate_ziwei_chart", return_value=result), \
         patch("hermes_ext.fortune_oracle.ziwei_bridge.calculate_ziwei_daxian", return_value={"ok": False}):
        card = adapters.adapt_ziwei(INPUT)
    assert card.status == "partial"
    assert card.facts["sihua"] == {"祿": {"star": "太陽", "palace_index": 0}}
    assert result["sihua"] == {"lu": {"star": "太陽", "palace_index": 0}}
    assert "化祿" in card.interpretation


def test_package_presence_is_not_backend_usage():
    from hermes_ext.fortune_oracle import western_bridge
    with patch.dict("os.environ", {"FORTUNE_EPHEMERIS_PATH": "/missing/de440s.bsp"}):
        assert western_bridge.backend_info() == {"backend": "skyfield-jpl-de440s", "status": "unavailable"}


def test_astrology_calculation_sources_survive_adapter_and_renderer():
    cards = [adapters.adapt_western(INPUT), adapters.adapt_vedic(INPUT)]
    assert cards[0].calculation_mode == "computed" and cards[0].backend == "skyfield-jpl-de440s"
    assert cards[1].calculation_mode == "computed" and cards[1].backend == "swisseph-moshier"
    assert "dasha" not in cards[1].facts
    text = render_final_reading(cards)
    assert "skyfield-jpl-de440s" in text and "swisseph-moshier" in text
    assert "builtin-vedic" not in text


def test_empty_success_does_not_create_interpretation_or_mutate_card():
    card = OracleMethodCard.runnable("bazi", {"eight_char": {}}, interpretation="지어낸 풀이")
    text = render_final_reading([card])
    assert "지어낸 풀이" not in text and "계산할 수 없습니다" in text
    assert card.status == "runnable"


def test_adapter_failure_does_not_abort_other_methods():
    with patch.object(adapters, "adapt_bazi", side_effect=ValueError("private data")):
        cards = adapters.adapt_all(INPUT)
    assert len(cards) == 4 and cards[0].status == "blocked"
    assert any(c.facts for c in cards[1:])
    assert "private data" not in render_final_reading(cards)


def test_approximate_values_cannot_enter_core_temperament_or_long_term_flow():
    from copy import deepcopy
    real = OracleMethodCard(method='bazi', status='runnable', backend='lunar-javascript',
                            calculation_mode='computed', facts={'eight_char':{'day':'庚辰'}})
    approximate = OracleMethodCard(method='vedic', status='partial', backend='builtin-vedic',
                                   calculation_mode='approximate', facts={'grahas':['APPROX_PLANET'],
                                       'nakshatra':'APPROX_NAKSHATRA', 'dasha':'APPROX_DASHA'},
                                   interpretation='APPROX_TEMPERAMENT')
    before = deepcopy([real, approximate])
    text = render_final_reading([real, approximate], detailed=True)
    combined, reference = text.split('⚠️ 10. 한계/참고')
    assert '일庚辰' in combined
    assert 'APPROX_' not in combined and 'APPROX_TEMPERAMENT' not in text
    assert 'APPROX_PLANET' in reference and 'APPROX_DASHA' in reference
    assert '향후 5년의 흐름은 계산하지 않았습니다' in combined
    assert [real, approximate] == before


@pytest.mark.parametrize('method,facts', [
    ('bazi', {'time_basis':{'solar_terms':'birth_instant_utc_plus_8'}}),
    ('bazi', {'eight_char':None}),
    ('western', {'provenance':{'ephemeris':'DE440s'}, 'planet_positions':[]}),
    ('western', {'planet_positions':[{'name':'Sun','longitude':float('nan')}]}),
    ('western', {'planet_positions':[{'name':'Sun','longitude':360}]}),
    ('ziwei', {'stars':{}, 'backend':'iztro'}),
    ('qimen', {'palaces':{'0':{'index':0}}}),
])
def test_computed_flag_and_backend_alone_do_not_prove_calculation(method,facts):
    from hermes_ext.fortune_oracle.oracle_renderer import is_calculated_card
    card = OracleMethodCard(method=method,status='runnable',backend='claimed-backend',
                            calculation_mode='computed',facts=facts,interpretation='FAKE_INTERPRETATION')
    assert not is_calculated_card(card)
    for lang in ('ko','en'):
        text = render_final_reading([card],language=lang,include_qimen=True)
        assert 'FAKE_INTERPRETATION' not in text
    assert card.status == 'runnable'  # no caller mutation


def test_unattributed_or_approximate_only_route_is_not_a_successful_combined_reading():
    from hermes_ext.fortune_oracle import combined_reading
    card = OracleMethodCard(method='vedic',status='partial',backend='builtin-vedic',calculation_mode='approximate',
                            facts={'graha_positions':[{'name':'Sun','rashi':'Mesha','degree':2.0}]})
    with patch.object(combined_reading,'adapt_all',return_value=[card]):
        result = combined_reading.prepare_combined_reading({},language='en')
    assert result['ok'] is False and result['methods'][0]['used_in_reading'] is False
    assert 'Reference only' in result['text'] and 'No calculated reading' in result['text']


def test_question_chart_evidence_reports_request_time_in_english():
    result = QimenResult(ok=True,chart=QimenChart(ganzhi='甲子',pai_ju='陽一局',
                         palaces={'坎':QimenPalace(palace_name='坎',door='休',star='蓬')}))
    with patch('hermes_ext.fortune_oracle.qimen_bridge.calculate_qimen',return_value=result):
        card = adapters.adapt_qimen(INPUT,question='PRIVATE_QUESTION')
    text = render_final_reading([card],include_qimen=True,language='en')
    assert card.facts['question_time'] in text and 'Asia/Seoul' in text
    assert 'PRIVATE_QUESTION' not in text and '1990-05-15' not in text
