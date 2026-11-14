from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path('plugins'))

from hermes_ext.fortune_oracle.yongshen import calculate_yongshen
from hermes_ext.fortune_oracle.yongshen_calibration import (
    calibrate_yongshen_result,
    contains_unsafe_yongshen_phrase,
    yongshen_deep_context_summary,
)
from hermes_ext.fortune_oracle.yongshen_interpreter import build_show_profile_yongshen_note

EC = {'year': '甲子', 'month': '乙丑', 'day': '丙寅', 'time': '丁卯'}


def test_confidence_boundaries_no_rule_based_high():
    result = calculate_yongshen(EC)
    assert result.confidence in {'rule_based_low', 'rule_based_medium'}
    calibrated = calibrate_yongshen_result(EC)
    assert calibrated['confidence'] in {'rule_based_low', 'rule_based_medium'}
    assert calibrated['confidence'] != 'rule_based_high'


def test_reasoning_contains_model_basis_and_is_deterministic():
    a = calibrate_yongshen_result(EC)
    b = calibrate_yongshen_result(EC)
    assert a == b
    reasoning = ' '.join(a['reasoning'])
    assert '일간' in reasoning
    assert '월지 계절' in reasoning
    assert '지장간' in reasoning
    summary = yongshen_deep_context_summary(EC)
    assert 'confidence=' in summary
    assert 'strength=' in summary


def test_no_unsafe_phrase_and_show_profile_compact():
    text = str(calibrate_yongshen_result(EC)) + '\n' + build_show_profile_yongshen_note(EC, max_lines=2)
    assert not contains_unsafe_yongshen_phrase(text)
    assert 'rule-based' in text or '참고' in text
