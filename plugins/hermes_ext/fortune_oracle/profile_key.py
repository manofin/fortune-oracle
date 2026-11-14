#!/usr/bin/env python3
"""profile_key.py: per-user profile key resolution for Fortune Oracle.

Phase 15 구현. gateway context가 전달되지 않는 현재 배포 환경에서는
per-user isolation이 불가하여 fallback key 'telegram:default' 를 사용한다.
live per-user isolation은 gateway context 연동 완료 후 전환 예정.

정책:
- birth_date / birth_time / name_hanja 미노출
- gateway/run.py, gateway/platforms/*, config.yaml 수정 금지
- Hermes core runtime 수정 금지
- 외부 네트워크/AI API 호출 금지
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# PENDING 상태 상수
# ---------------------------------------------------------------------------

MULTI_USER_STATUS = (
    "PENDING: gateway context 미전달로 per-user isolation 불가"
)

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

_MAX_USER_ID_LEN = 64
_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9_]")


# ---------------------------------------------------------------------------
# ProfileKeyContext dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProfileKeyContext:
    """Gateway 또는 플랫폼 핸들러에서 전달받는 컨텍스트.

    user_id: 플랫폼별 사용자 식별자 (예: Telegram user_id 정수 → 문자열)
    chat_id: 채팅방/채널 식별자 (옵션)
    platform: 플랫폼 이름 (기본 'telegram')
    """

    user_id: str = "default"
    chat_id: Optional[str] = None
    platform: str = "telegram"


# ---------------------------------------------------------------------------
# 핵심 함수
# ---------------------------------------------------------------------------

def sanitize_user_id(user_id: str) -> str:
    """user_id를 안전한 형태로 정규화한다.

    - 영숫자(a-z A-Z 0-9)와 밑줄(_)만 허용; 나머지 문자는 '_' 로 치환
    - 64자 초과 시 앞 64자로 잘라냄
    - 결과가 빈 문자열이면 'default' 반환
    """
    if not isinstance(user_id, str):
        user_id = str(user_id)
    sanitized = _SAFE_PATTERN.sub("_", user_id)
    sanitized = sanitized[:_MAX_USER_ID_LEN]
    return sanitized if sanitized else "default"


def resolve_profile_key(
    context: Optional[ProfileKeyContext] = None,
    platform: str = "telegram",
) -> str:
    """플랫폼:user_id 형태의 프로필 키를 반환한다.

    context가 None이거나 user_id가 비어 있으면 fallback 키를 반환한다.
    fallback 키: '<platform>:default'

    Args:
        context: ProfileKeyContext 인스턴스 또는 None
        platform: 플랫폼 이름 (context.platform 이 우선됨)

    Returns:
        'platform:user_id' 형태의 문자열
    """
    if context is None:
        return f"{platform}:default"

    resolved_platform = (context.platform or platform).strip().lower() or platform
    raw_uid = (context.user_id or "").strip()

    if not raw_uid or raw_uid == "default":
        return f"{resolved_platform}:default"

    safe_uid = sanitize_user_id(raw_uid)
    return f"{resolved_platform}:{safe_uid}"


def migration_plan() -> dict:
    """현재 키 전략에서 per-user 키로의 마이그레이션 계획을 반환한다.

    Returns:
        migration plan dict:
          current_key        : 현재 사용 중인 fallback 키
          target_key_template: per-user 전환 목표 키 패턴
          strategy           : 마이그레이션 방식 설명
          auto_destructive   : 자동으로 기존 데이터를 삭제/덮어쓰는지 여부
          status             : 현재 구현 상태
    """
    return {
        "current_key": "telegram:default",
        "target_key_template": "telegram:{sanitized_user_id}",
        "strategy": (
            "gateway context 연동 후 resolve_profile_key(context)를 호출하면 "
            "자동으로 per-user 키가 생성된다. "
            "기존 'telegram:default' 데이터는 수동 확인 후 사용자별로 복사/이동하며, "
            "자동 일괄 삭제는 수행하지 않는다."
        ),
        "auto_destructive": False,
        "status": MULTI_USER_STATUS,
    }
