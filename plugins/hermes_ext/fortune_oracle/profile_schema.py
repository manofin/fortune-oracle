"""Fortune Oracle -- Profile Schema (Phase 16).

Profile 필드 정의, 검증, 민감정보 마스킹, gender 정규화.
"""
from __future__ import annotations

from typing import Dict, Any, Tuple, List

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

DEFAULT_TIMEZONE = "Asia/Seoul"

PROFILE_FIELDS: Dict[str, Dict[str, Any]] = {
    "display_name": {
        "required": True,
        "sensitive": False,
        "type": "str",
        "description": "표시 이름 (한글/영문)",
    },
    "birth_date": {
        "required": True,
        "sensitive": True,
        "type": "str",
        "description": "생년월일 (YYYY-MM-DD)",
    },
    "birth_time": {
        "required": True,
        "sensitive": True,
        "type": "str",
        "description": "출생 시간 (HH:MM)",
    },
    "name_hanja": {
        "required": False,
        "sensitive": True,
        "type": "str",
        "description": "한자 이름 (선택)",
    },
    "gender": {
        "required": False,
        "sensitive": False,
        "type": "str",
        "description": "성별: male | female | unknown (선택)",
    },
    "birth_place": {
        "required": False,
        "sensitive": False,
        "type": "str",
        "description": "출생지 (선택)",
    },
    "timezone": {
        "required": False,
        "sensitive": False,
        "type": "str",
        "description": "타임존 (선택, 기본 Asia/Seoul)",
    },
    "longitude": {
        "required": False,
        "sensitive": False,
        "type": "float",
        "description": "경도 (선택, 정밀 절기 계산용)",
    },
    "life_context": {
        "required": False,
        "sensitive": False,
        "type": "dict",
        "description": "사용자가 명시 제공한 현실 맥락 (occupation/creative/recent/project)",
    },
}

GENDER_ALIASES: Dict[str, str] = {
    "male": "male",
    "m": "male",
    "남": "male",
    "남성": "male",
    "남자": "male",
    "female": "female",
    "f": "female",
    "여": "female",
    "여성": "female",
    "여자": "female",
}

# ---------------------------------------------------------------------------
# 함수
# ---------------------------------------------------------------------------


def validate_profile(profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """프로필 필수 필드 검증.

    Returns:
        (ok: bool, missing_required: list[str])
    """
    missing = [
        field_name
        for field_name, meta in PROFILE_FIELDS.items()
        if meta["required"] and not profile.get(field_name)
    ]
    return (len(missing) == 0, missing)


def mask_sensitive(profile: Dict[str, Any]) -> Dict[str, Any]:
    """민감 필드를 '***'로 마스킹한 새 dict 반환."""
    result = dict(profile)
    for field_name, meta in PROFILE_FIELDS.items():
        if meta["sensitive"] and field_name in result:
            result[field_name] = "***"
    return result


def normalize_gender(raw: str) -> str:
    """gender 문자열 정규화.

    Returns:
        'male' | 'female' | 'unknown'
    """
    if not raw:
        return "unknown"
    normalized = GENDER_ALIASES.get(raw.strip().lower(), None)
    return normalized if normalized else "unknown"
