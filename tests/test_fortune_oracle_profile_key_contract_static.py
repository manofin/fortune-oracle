from _fo_paths import hermes_path, repo_path
from pathlib import Path

DOC = Path(repo_path('docs/FORTUNE_ORACLE_PHASE22_GATEWAY_USER_CONTEXT_CONTRACT.md')).read_text(encoding='utf-8')
MIGRATION = Path(repo_path('docs/FORTUNE_ORACLE_PROFILE_KEY_MIGRATION_PLAN.md')).read_text(encoding='utf-8')


def test_gateway_contract_design_documents_future_context_without_core_edit():
    for token in ['PluginContext', 'platform', 'user_id', 'chat_id', 'session_id', 'message_id']:
        assert token in DOC
    assert 'fn(args: str)' in DOC
    assert 'fn(args, context)' in DOC
    assert 'No gateway/run.py edits' in DOC
    assert 'No gateway/platforms/* edits' in DOC


def test_profile_key_migration_plan_is_non_destructive_and_pending():
    assert 'telegram:default' in MIGRATION
    assert 'telegram:<user_id>' in MIGRATION
    assert 'Dry-run' in MIGRATION
    assert 'explicit user approval' in MIGRATION
    assert 'PENDING' in MIGRATION
