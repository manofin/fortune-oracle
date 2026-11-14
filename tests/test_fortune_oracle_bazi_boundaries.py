"""
Phase 20: Bazi Boundary Accuracy Suite 테스트
사주 경계 조건 및 정밀도 관련 단위 테스트
"""
from _fo_paths import hermes_path, repo_path
import sys
import types
import importlib
import pytest

# ── 테스트 대상 모듈 직접 import ─────────────────────────────────────────
sys.path.insert(0, repo_path('plugins/hermes_ext'))

import fortune_oracle.bazi_boundary as bb
import fortune_oracle.bazi_boundary_interpreter as bbi


# ── 1. validate_birth_datetime 유효 케이스 ──────────────────────────────

def test_validate_birth_datetime_valid_basic():
    ok, msg = bb.validate_birth_datetime(1990, 5, 15, 12, 30)
    assert ok is True

def test_validate_birth_datetime_valid_boundary_year_min():
    ok, _ = bb.validate_birth_datetime(1800, 1, 1, 0, 0)
    assert ok is True

def test_validate_birth_datetime_valid_boundary_year_max():
    ok, _ = bb.validate_birth_datetime(2100, 12, 31, 23, 59)
    assert ok is True


# ── 2. validate_birth_datetime 무효 케이스 ─────────────────────────────

def test_validate_birth_datetime_invalid_year_low():
    ok, msg = bb.validate_birth_datetime(1799, 6, 1, 12, 0)
    assert ok is False
    assert '연도' in msg

def test_validate_birth_datetime_invalid_year_high():
    ok, msg = bb.validate_birth_datetime(2101, 1, 1, 0, 0)
    assert ok is False
    assert '연도' in msg

def test_validate_birth_datetime_invalid_month_low():
    ok, msg = bb.validate_birth_datetime(2000, 0, 1, 0, 0)
    assert ok is False
    assert '월' in msg

def test_validate_birth_datetime_invalid_month_high():
    ok, msg = bb.validate_birth_datetime(2000, 13, 1, 0, 0)
    assert ok is False
    assert '월' in msg

def test_validate_birth_datetime_invalid_day_low():
    ok, msg = bb.validate_birth_datetime(2000, 1, 0, 0, 0)
    assert ok is False
    assert '일' in msg

def test_validate_birth_datetime_invalid_day_high():
    ok, msg = bb.validate_birth_datetime(2000, 1, 32, 0, 0)
    assert ok is False
    assert '일' in msg

def test_validate_birth_datetime_invalid_hour():
    ok, msg = bb.validate_birth_datetime(2000, 1, 1, 24, 0)
    assert ok is False
    assert '시' in msg

def test_validate_birth_datetime_invalid_minute():
    ok, msg = bb.validate_birth_datetime(2000, 1, 1, 12, 60)
    assert ok is False
    assert '분' in msg


# ── 3. classify_hour_branch ────────────────────────────────────────────

def test_classify_hour_branch_hour0():
    result = bb.classify_hour_branch(0)
    assert result['branch'] == '子'
    assert result['warning'] is None

def test_classify_hour_branch_hour23():
    result = bb.classify_hour_branch(23)
    assert result['branch'] == '子'
    assert result['warning'] is not None
    assert '야자시' in result['warning']

def test_classify_hour_branch_hour12():
    result = bb.classify_hour_branch(12)
    assert result['branch'] == '午'

def test_classify_hour_branch_hour1():
    result = bb.classify_hour_branch(1)
    assert result['branch'] == '丑'

def test_classify_hour_branch_hour3():
    result = bb.classify_hour_branch(3)
    assert result['branch'] == '寅'

def test_classify_hour_branch_hour11():
    result = bb.classify_hour_branch(11)
    assert result['branch'] == '午'

def test_classify_hour_branch_hour21():
    result = bb.classify_hour_branch(21)
    assert result['branch'] == '亥'


# ── 4. BOUNDARY_FIXTURES 구조 확인 ────────────────────────────────────

def test_boundary_fixtures_is_list():
    assert isinstance(bb.BOUNDARY_FIXTURES, list)
    assert len(bb.BOUNDARY_FIXTURES) >= 4

def test_boundary_fixtures_has_ipchun_before():
    ids = [f['id'] for f in bb.BOUNDARY_FIXTURES]
    assert 'ipchun_before' in ids

def test_boundary_fixtures_has_ipchun_after():
    ids = [f['id'] for f in bb.BOUNDARY_FIXTURES]
    assert 'ipchun_after' in ids

def test_boundary_fixtures_has_solar_term_day():
    ids = [f['id'] for f in bb.BOUNDARY_FIXTURES]
    assert 'solar_term_day' in ids

def test_boundary_fixtures_has_jasi_boundary():
    ids = [f['id'] for f in bb.BOUNDARY_FIXTURES]
    assert 'jasi_boundary' in ids

def test_boundary_fixtures_each_has_label_and_note():
    for fixture in bb.BOUNDARY_FIXTURES:
        assert 'label' in fixture, f"fixture {fixture} missing 'label'"
        assert 'note' in fixture, f"fixture {fixture} missing 'note'"


# ── 5. 상수 존재 확인 ──────────────────────────────────────────────────

def test_ipchun_boundary_note_exists():
    assert hasattr(bb, 'IPCHUN_BOUNDARY_NOTE')
    assert len(bb.IPCHUN_BOUNDARY_NOTE) > 0

def test_jasi_boundary_note_exists():
    assert hasattr(bb, 'JASI_BOUNDARY_NOTE')
    assert '야자시' in bb.JASI_BOUNDARY_NOTE or '子시' in bb.JASI_BOUNDARY_NOTE

def test_true_solar_time_note_exists():
    assert hasattr(bb, 'TRUE_SOLAR_TIME_NOTE')
    assert '진태양시' in bb.TRUE_SOLAR_TIME_NOTE or 'longitude' in bb.TRUE_SOLAR_TIME_NOTE

def test_supported_date_range():
    assert bb.SUPPORTED_DATE_RANGE == (1800, 2100)


# ── 6. bazi_boundary_interpreter ──────────────────────────────────────

def test_format_boundary_limitations_returns_str():
    text = bbi.format_boundary_limitations()
    assert isinstance(text, str)
    assert len(text) > 0

def test_format_boundary_limitations_no_fear():
    text = bbi.format_boundary_limitations()
    fear_words = ['위험', '틀릴', '오류', '잘못', '공포', '심각한 오류']
    for word in fear_words:
        assert word not in text, f"공포 조장 단어 발견: {word}"

def test_format_boundary_limitations_contains_key_info():
    text = bbi.format_boundary_limitations()
    assert '입춘' in text or 'IPCHUN' in text or '연주' in text
    assert '진태양시' in text or 'longitude' in text

def test_get_precision_note_exact_true():
    note = bbi.get_precision_note(True)
    assert '정밀' in note

def test_get_precision_note_exact_false():
    note = bbi.get_precision_note(False)
    assert 'approximate' in note or '기본값' in note


# ── 7. 외부 네트워크 없음 확인 ────────────────────────────────────────

def test_no_requests_import():
    import ast, pathlib
    for filepath in [
        repo_path('plugins/hermes_ext/fortune_oracle/bazi_boundary.py'),
        repo_path('plugins/hermes_ext/fortune_oracle/bazi_boundary_interpreter.py'),
    ]:
        source = pathlib.Path(filepath).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, 'names', [])]
                module = getattr(node, 'module', '') or ''
                for name in names:
                    assert name not in ('requests', 'httpx', 'urllib3'), \
                        f"외부 네트워크 라이브러리 발견: {name} in {filepath}"
                assert module not in ('requests', 'httpx', 'urllib3'), \
                    f"외부 네트워크 라이브러리 발견: {module} in {filepath}"


# ── 8. 기존 /show_profile 회귀 없음 ──────────────────────────────────

def test_no_show_profile_regression():
    """bazi_boundary 모듈이 gateway나 show_profile 관련 코드를 건드리지 않음."""
    import pathlib
    for filepath in [
        repo_path('plugins/hermes_ext/fortune_oracle/bazi_boundary.py'),
        repo_path('plugins/hermes_ext/fortune_oracle/bazi_boundary_interpreter.py'),
    ]:
        source = pathlib.Path(filepath).read_text()
        assert 'show_profile' not in source
        assert 'gateway' not in source.lower() or 'gateway' not in source
