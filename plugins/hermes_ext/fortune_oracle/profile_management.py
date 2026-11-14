#!/usr/bin/env python3
"""Fortune Oracle profile management UX helpers.

Provides masked profile status display and deletion confirmation messages.
Sensitive fields (birth_date, birth_time, birth_place, name_hanja) are NEVER
exposed as raw values — they are always shown as '***' or presence flags.

Multi-turn / conversational flows are NOT supported.
"""

from __future__ import annotations

from typing import Optional


def get_profile_status(profile: Optional[dict]) -> dict:
    """Return a safe, masked status dict from a raw profile dict.

    No sensitive field values are ever returned — only presence flags and
    masked placeholders ('***').
    """
    if not profile:
        return {
            "registered": False,
            "display_name": "없음",
            "birth_info_present": False,
            "gender_present": False,
            "birth_place_present": False,
            "timezone": "Asia/Seoul",
            "birth_date": "",
            "birth_time": "",
            "name_hanja": "",
            "life_context_present": False,
        }

    birth_date_present = bool(profile.get("birth_date"))
    birth_time_present = bool(profile.get("birth_time"))
    name_hanja_present = bool(profile.get("name_hanja"))

    try:
        from hermes_ext.fortune_oracle.life_context import has_life_context
        life_context_present = has_life_context(profile)
    except Exception:
        life_context_present = False

    return {
        "registered": True,
        "display_name": profile.get("display_name") or "없음",
        "birth_info_present": birth_date_present,
        "gender_present": bool(profile.get("gender")),
        "birth_place_present": bool(profile.get("birth_place")),
        "timezone": profile.get("timezone") or "Asia/Seoul",
        # Sensitive fields: masked, never raw
        "birth_date": "***" if birth_date_present else "",
        "birth_time": "***" if birth_time_present else "",
        "name_hanja": "***" if name_hanja_present else "",
        "life_context_present": life_context_present,
    }


def format_profile_status(status: dict) -> str:
    """Format profile status as Telegram-friendly text.

    Sensitive field values are masked; only presence/absence is indicated.
    """
    if not status.get("registered"):
        return (
            "프로필이 등록되지 않았습니다.\n\n"
            "/register_birth 명령으로 생년월일 정보를 등록할 수 있습니다."
        )

    lines = ["프로필 상태"]
    lines.append("")
    lines.append(f"이름(표시): {status['display_name']}")
    lines.append(f"생년월일: {'등록됨 (***)' if status['birth_info_present'] else '미등록'}")
    lines.append(f"출생 시간: {'등록됨 (***)' if status['birth_time'] else '미등록'}")
    lines.append(f"성별: {'등록됨' if status['gender_present'] else '미등록'}")
    lines.append(f"출생지: {'등록됨' if status['birth_place_present'] else '미등록'}")
    lines.append(f"한자 이름: {'등록됨 (***)' if status['name_hanja'] else '미등록'}")
    lines.append(f"현실 맥락: {'등록됨 (내용 비공개)' if status.get('life_context_present') else '미등록'}")
    lines.append(f"타임존: {status['timezone']}")
    lines.append("")
    lines.append("정보를 변경하려면 /register_birth 명령으로 재등록할 수 있습니다.")

    return "\n".join(lines)


def format_delete_confirm(display_name: Optional[str]) -> str:
    """Return a deletion confirmation message.

    Only the display_name (if any) is shown. No birth info is included.
    """
    scope = "등록된 출생정보·이름·저장된 위치·매일 운세 수신 설정을 삭제했습니다."
    if display_name:
        return f"'{display_name}' 프로필이 삭제되었습니다.\n{scope}"
    return f"프로필이 삭제되었습니다.\n{scope}"


def get_help_additions() -> list[str]:
    """Return list of new commands added by this module."""
    return ["/profile_status - 프로필 등록 여부 및 항목 확인 (민감정보 비공개)"]
