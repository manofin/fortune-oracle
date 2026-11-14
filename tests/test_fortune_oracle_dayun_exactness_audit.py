from _fo_paths import hermes_path, repo_path
import sys
sys.path.insert(0, repo_path('plugins'))

from hermes_ext.fortune_oracle.dayun_exactness_audit import audit_dayun_exactness, dayun_limitations_text
from hermes_ext.fortune_oracle.dayun import calculate_dayun_skeleton
from hermes_ext.fortune_oracle.dayun_interpreter import build_show_profile_dayun_note

EC_YANG = {'year': '甲子', 'month': '乙丑', 'day': '丙寅', 'time': '丁卯'}
EC_YIN = {'year': '乙丑', 'month': '丙寅', 'day': '丁卯', 'time': '戊辰'}


def test_gender_direction_rules_and_unknown_fail_open():
    assert calculate_dayun_skeleton(EC_YANG, gender='male').direction == 'forward'
    assert calculate_dayun_skeleton(EC_YANG, gender='female').direction == 'reverse'
    assert calculate_dayun_skeleton(EC_YIN, gender='male').direction == 'reverse'
    unknown = calculate_dayun_skeleton(EC_YANG, gender='unknown')
    assert unknown.direction == 'unknown'
    assert unknown.cycles == []


def test_start_age_approx_current_cycle_and_limitations():
    audit = audit_dayun_exactness(EC_YANG, gender='male', birth_year=1986, current_age=40)
    assert audit['start_age_precision'] == 'approx'
    assert audit['current_cycle'] is not None
    text = dayun_limitations_text()
    assert 'true solar time: unsupported' in text
    assert 'longitude correction: unsupported' in text
    assert 'Asia/Seoul' in text


def test_show_profile_dayun_note_compact_and_safe():
    note = build_show_profile_dayun_note(EC_YANG, gender='male', birth_year=1986, max_lines=2)
    assert '대운' in note
    assert len([line for line in note.splitlines() if line.strip()]) <= 3
