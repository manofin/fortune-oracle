from _fo_paths import hermes_path, repo_path
from pathlib import Path

DOCS = Path(repo_path('docs'))


def _read(name):
    return (DOCS / name).read_text(encoding='utf-8')


def test_phase30_product_spec_contains_required_commands_and_limits():
    text = _read('FORTUNE_ORACLE_PRODUCT_SPEC.md')
    for cmd in [
        '/today_fortune', '/tomorrow_fortune', '/month_kline', '/life_kline',
        '/kline_card', '/kline_card year', '/register_birth', '/show_profile',
        '/delete_profile', '/profile_status', '/deep_fortune', '/deep_fortune full',
        '/deep_fortune qna', '/voice_fortune', '/도움말',
    ]:
        assert cmd in text
    assert 'FORTUNE_DEEP_ANALYSIS' in text
    assert 'LINE' in text and 'deferred' in text
    assert 'Multi-turn registration unsupported' in text or 'multi-turn 등록은 지원하지 않습니다' in text
    assert 'telegram:<user_id>' in text
    assert '식별자가 없으면 다른 저장 프로필을 자동 선택하지 않는다' in text


def test_phase30_commands_and_live_smoke_docs_exist():
    commands = _read('FORTUNE_ORACLE_COMMANDS_AND_FLAGS.md')
    smoke = _read('FORTUNE_ORACLE_LIVE_SMOKE_CHECKLIST.md')
    assert 'FORTUNE_DEEP_ANALYSIS' in commands
    assert 'config.yaml' in commands and 'No config.yaml auto modification' in commands
    assert '/delete_profile' in smoke and 'explicit user approval' in smoke
    assert 'LINE remains deferred' in smoke or 'LINE' in smoke
