#!/usr/bin/env python3
"""test_fortune_oracle_profile_key.py

Fortune Oracle Phase 15: profile_key.py 단위 테스트
"""

import sys
import os

# 플러그인 루트를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from plugins.hermes_ext.fortune_oracle.profile_key import (
    MULTI_USER_STATUS,
    ProfileKeyContext,
    migration_plan,
    resolve_profile_key,
    sanitize_user_id,
)


# ---------------------------------------------------------------------------
# resolve_profile_key 테스트
# ---------------------------------------------------------------------------

class TestResolveProfileKey:
    def test_no_context_returns_default_key(self):
        """context 없음 → 'telegram:default'"""
        result = resolve_profile_key()
        assert result == "telegram:default"

    def test_context_with_user_id(self):
        """context user_id='12345' → 'telegram:12345'"""
        ctx = ProfileKeyContext(user_id="12345", platform="telegram")
        result = resolve_profile_key(context=ctx)
        assert result == "telegram:12345"

    def test_platform_parameter_used_when_no_context(self):
        """context 없을 때 platform 파라미터 반영"""
        result = resolve_profile_key(platform="line")
        assert result == "line:default"

    def test_context_platform_overrides_parameter(self):
        """context.platform 이 platform 파라미터보다 우선"""
        ctx = ProfileKeyContext(user_id="abc", platform="line")
        result = resolve_profile_key(context=ctx, platform="telegram")
        assert result == "line:abc"

    def test_context_empty_user_id_returns_default(self):
        """context.user_id 빈 문자열 → fallback :default"""
        ctx = ProfileKeyContext(user_id="", platform="telegram")
        result = resolve_profile_key(context=ctx)
        assert result == "telegram:default"

    def test_context_user_id_is_default_literal(self):
        """context.user_id == 'default' → 'telegram:default'"""
        ctx = ProfileKeyContext(user_id="default", platform="telegram")
        result = resolve_profile_key(context=ctx)
        assert result == "telegram:default"

    def test_unsafe_user_id_is_sanitized(self):
        """공백·특수문자가 포함된 user_id는 sanitization됨"""
        ctx = ProfileKeyContext(user_id="user 123!", platform="telegram")
        result = resolve_profile_key(context=ctx)
        # 공백 → '_', '!' → '_'
        assert result == "telegram:user_123_"

    def test_platform_lowercased(self):
        """platform 대소문자 → 소문자 정규화"""
        ctx = ProfileKeyContext(user_id="99", platform="Telegram")
        result = resolve_profile_key(context=ctx)
        assert result == "telegram:99"


# ---------------------------------------------------------------------------
# sanitize_user_id 테스트
# ---------------------------------------------------------------------------

class TestSanitizeUserId:
    def test_normal_alphanumeric(self):
        assert sanitize_user_id("abc123") == "abc123"

    def test_underscore_preserved(self):
        assert sanitize_user_id("user_name") == "user_name"

    def test_space_replaced(self):
        assert sanitize_user_id("hello world") == "hello_world"

    def test_special_chars_replaced(self):
        result = sanitize_user_id("user@example.com")
        assert result == "user_example_com"

    def test_empty_string_returns_default(self):
        """빈 문자열 → 'default'"""
        assert sanitize_user_id("") == "default"

    def test_truncate_over_64_chars(self):
        """64자 초과 → 앞 64자로 잘라냄"""
        long_id = "a" * 100
        result = sanitize_user_id(long_id)
        assert len(result) == 64
        assert result == "a" * 64

    def test_exactly_64_chars_preserved(self):
        exact = "x" * 64
        assert sanitize_user_id(exact) == exact

    def test_65_chars_truncated(self):
        s = "b" * 65
        assert sanitize_user_id(s) == "b" * 64

    def test_all_special_chars_becomes_default(self):
        """모든 문자가 치환되어 결과가 '_' 만 남아도 'default' 아님 (언더스코어는 유효)"""
        result = sanitize_user_id("!!!")
        assert result == "___"

    def test_non_string_input_coerced(self):
        """숫자 등 비문자열 입력 → 문자열 변환 후 처리"""
        assert sanitize_user_id(12345) == "12345"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# migration_plan 테스트
# ---------------------------------------------------------------------------

class TestMigrationPlan:
    def test_returns_dict(self):
        plan = migration_plan()
        assert isinstance(plan, dict)

    def test_required_keys_present(self):
        plan = migration_plan()
        for key in ("current_key", "target_key_template", "strategy", "auto_destructive", "status"):
            assert key in plan, f"migration_plan에 '{key}' 키가 없음"

    def test_current_key_is_default(self):
        assert migration_plan()["current_key"] == "telegram:default"

    def test_auto_destructive_is_false(self):
        """자동 파괴적 마이그레이션 금지"""
        assert migration_plan()["auto_destructive"] is False

    def test_target_key_template_contains_placeholder(self):
        tmpl = migration_plan()["target_key_template"]
        assert "{sanitized_user_id}" in tmpl

    def test_status_is_pending(self):
        assert "PENDING" in migration_plan()["status"]


# ---------------------------------------------------------------------------
# 상수 테스트
# ---------------------------------------------------------------------------

class TestConstants:
    def test_multi_user_status_exists(self):
        """MULTI_USER_STATUS 상수 존재 확인"""
        assert MULTI_USER_STATUS
        assert isinstance(MULTI_USER_STATUS, str)

    def test_multi_user_status_contains_pending(self):
        assert "PENDING" in MULTI_USER_STATUS

    def test_multi_user_status_mentions_gateway(self):
        assert "gateway" in MULTI_USER_STATUS


# ---------------------------------------------------------------------------
# ProfileKeyContext dataclass 테스트
# ---------------------------------------------------------------------------

class TestProfileKeyContext:
    def test_default_values(self):
        ctx = ProfileKeyContext()
        assert ctx.user_id == "default"
        assert ctx.chat_id is None
        assert ctx.platform == "telegram"

    def test_custom_values(self):
        ctx = ProfileKeyContext(user_id="u1", chat_id="c1", platform="line")
        assert ctx.user_id == "u1"
        assert ctx.chat_id == "c1"
        assert ctx.platform == "line"


# ---------------------------------------------------------------------------
# store.py 회귀 테스트: make_key import 확인
# ---------------------------------------------------------------------------

class TestStoreRegression:
    def test_make_key_still_importable(self):
        """기존 make_key 함수 회귀 없음"""
        from plugins.hermes_ext.fortune_oracle.store import make_key
        result = make_key("telegram", "default")
        assert result == "telegram:default"

    def test_make_key_with_user(self):
        from plugins.hermes_ext.fortune_oracle.store import make_key
        assert make_key("telegram", "12345") == "telegram:12345"

    def test_make_key_raises_on_empty(self):
        from plugins.hermes_ext.fortune_oracle.store import make_key
        with pytest.raises(ValueError):
            make_key("", "abc")
        with pytest.raises(ValueError):
            make_key("telegram", "")
