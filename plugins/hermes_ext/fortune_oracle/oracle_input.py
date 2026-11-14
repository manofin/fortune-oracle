#!/usr/bin/env python3
"""Fortune Oracle — Unified Oracle Input (Phase 37B).

모든 method가 공유하는 출생정보 입력 스키마.
기존 AstroBirthInput과 별개로 동작하며 Phase 37 전용 unified input을 제공한다.

기존 AstroBirthInput과의 관계:
- AstroBirthInput은 Phase 38 Western/Vedic 전용.
- UnifiedOracleInput은 Phase 37 통합 렌더링용.
- profile dict → UnifiedOracleInput 변환 helper 제공.

금지:
- 외부 네트워크 호출 금지
- AI/LLM 호출 금지
- 파일 쓰기 금지

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_CALENDAR = "solar"
GENDER_MAP = {
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
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class UnifiedOracleInput:
    """통합 운세 입력 스키마.

    모든 method(Bazi, Western, Vedic, Ziwei, Qimen)가 공유.
    부족한 입력은 crash가 아니라 precision_notes에 기록됨.
    """
    name: str = ""
    gender: str = "unknown"                  # male | female | unknown
    birth_datetime: str = ""                 # YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD
    calendar_type: str = DEFAULT_CALENDAR    # solar | lunar | unknown
    timezone: str = DEFAULT_TIMEZONE
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    birthplace_text: str = ""
    question_focus: str = ""
    precision_notes: List[str] = field(default_factory=list)
    source: str = "fallback"                 # profile | command | fallback

    # ------------------------------------------------------------------
    # Sufficiency checks
    # ------------------------------------------------------------------

    @property
    def has_birth_date(self) -> bool:
        """생년월일이 있는지."""
        return bool(self.birth_datetime.strip())

    @property
    def has_birth_time(self) -> bool:
        """具体时间이 있는지 (HH:MM)."""
        if not self.has_birth_date:
            return False
        dt = self.birth_datetime.strip()
        return "T" in dt or " " in dt

    @property
    def has_timezone(self) -> bool:
        """타임존이 설정되어 있는지."""
        return bool(self.timezone.strip())

    @property
    def has_location(self) -> bool:
        """위치(위도/경도)가 충분한지."""
        return (
            self.latitude is not None
            and self.longitude is not None
            and -90 <= self.latitude <= 90
            and -180 <= self.longitude <= 180
        )

    @property
    def sufficient_for_bazi(self) -> bool:
        """Bazi 계산에 충분한지 (birth_date만 있으면 됨)."""
        return self.has_birth_date

    @property
    def sufficient_for_planets(self) -> bool:
        """행성 계산에 충분한지 (datetime + timezone)."""
        return self.has_birth_date and self.has_timezone

    @property
    def sufficient_for_houses(self) -> bool:
        """house/Asc/MC 계산에 충분한지 (datetime + timezone + location + time)."""
        return (
            self.sufficient_for_planets
            and self.has_location
            and self.has_birth_time
        )

    @property
    def sufficient_for_ziwei(self) -> bool:
        """A recorded birth time is required; a date-only placeholder is not midnight."""
        return self.sufficient_for_planets and self.has_birth_time

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_birth_datetime(self) -> Optional[Dict[str, int]]:
        """birth_datetime 파싱. 성공 시 {year, month, day, hour, minute} 반환."""
        dt_str = self.birth_datetime.strip()
        if not dt_str:
            return None

        # YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD HH:MM
        m = re.match(
            r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})$",
            dt_str,
        )
        if m:
            return {
                "year": int(m.group(1)),
                "month": int(m.group(2)),
                "day": int(m.group(3)),
                "hour": int(m.group(4)),
                "minute": int(m.group(5)),
            }

        # YYYY-MM-DD only
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", dt_str)
        if m:
            return {
                "year": int(m.group(1)),
                "month": int(m.group(2)),
                "day": int(m.group(3)),
                "hour": 0,
                "minute": 0,
            }

        return None

    # ------------------------------------------------------------------
    # Validation — 부족함을 crash가 아닌 precision_notes로 기록
    # ------------------------------------------------------------------

    def validate(self) -> Optional[str]:
        """검증 실패 시 치명적 오류 메시지 반환, 성공 시 None.

        부족함은 precision_notes에 기록하고 None을 반환.
        """
        if not self.has_birth_date:
            return "출생일시가 필요합니다."

        parsed = self.parse_birth_datetime()
        if parsed is None:
            return f"출생일시 형식 오류: '{self.birth_datetime}'. YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM 형식이어야 합니다."

        if parsed["year"] < 1900 or parsed["year"] > 2100:
            return f"년도는 1900~2100 사이여야 합니다: {parsed['year']}"
        if parsed["month"] < 1 or parsed["month"] > 12:
            return f"월은 1~12 사이여야 합니다: {parsed['month']}"
        if parsed["day"] < 1 or parsed["day"] > 31:
            return f"일은 1~31 사이여야 합니다: {parsed['day']}"

        # 부족함 → precision_notes
        if not self.has_birth_time:
            self.precision_notes.append(
                "출생 시간이 없어 Ascendant/house/자미두수 정밀 계산을 할 수 없습니다."
            )
        if not self.has_timezone:
            self.precision_notes.append(
                "타임존이 없어 정확한 계산을 할 수 없습니다. 기본값 Asia/Seoul을 사용합니다."
            )
        if not self.has_location:
            self.precision_notes.append(
                "위치가 없어 Ascendant/MC/house를 계산할 수 없습니다."
            )
        if self.calendar_type == "unknown":
            self.precision_notes.append(
                "양력/음력 불명확 — 기본값 양력(solar)을 사용합니다."
            )

        return None

    def get_precision_summary(self) -> Dict[str, str]:
        """입력 충분성 요약."""
        summary: Dict[str, str] = {}
        summary["bazi"] = "sufficient" if self.sufficient_for_bazi else "blocked"
        summary["planets"] = "sufficient" if self.sufficient_for_planets else "blocked"
        summary["houses"] = "sufficient" if self.sufficient_for_houses else "blocked"
        summary["ziwei"] = "sufficient" if self.sufficient_for_ziwei else "blocked"
        if self.precision_notes:
            summary["notes"] = "; ".join(self.precision_notes[:3])
        return summary

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def to_astro_birth_input(self) -> Any:
        """AstroBirthInput으로 변환 (Western/Vedic용)."""
        from .astro_input import AstroBirthInput
        return AstroBirthInput(
            name=self.name,
            gender=self.gender,
            birth_datetime=self.birth_datetime,
            calendar_type=self.calendar_type if self.calendar_type in ("gregorian", "julian") else "gregorian",
            timezone=self.timezone,
            latitude=self.latitude,
            longitude=self.longitude,
            birthplace_text=self.birthplace_text,
            question_focus=self.question_focus,
            precision_notes=list(self.precision_notes),
        )

    def to_bazi_input(self) -> Any:
        """BaziInput으로 변환."""
        from .bazi_bridge import BaziInput
        parsed = self.parse_birth_datetime()
        date_str = ""
        time_str = "00:00"
        if parsed:
            date_str = f"{parsed['year']}-{parsed['month']:02d}-{parsed['day']:02d}"
            time_str = f"{parsed['hour']:02d}:{parsed['minute']:02d}"
        return BaziInput(
            birth_date=date_str,
            birth_time=time_str,
            birth_place=self.birthplace_text,
            longitude=self.longitude,
            timezone=self.timezone,
            gender=self.gender,
            birth_time_known=self.has_birth_time,
        )


def normalize_gender(raw: str) -> str:
    """gender 정규화."""
    if not raw:
        return "unknown"
    return GENDER_MAP.get(raw.strip().lower(), "unknown")


def from_profile(profile: Dict[str, Any]) -> UnifiedOracleInput:
    """기존 profile dict에서 UnifiedOracleInput 생성."""
    birth_date = profile.get("birth_date", "")
    birth_time = profile.get("birth_time", "")

    # datetime 조합
    birth_datetime = ""
    if birth_date and birth_time:
        birth_datetime = f"{birth_date}T{birth_time}"
    elif birth_date:
        birth_datetime = birth_date

    return UnifiedOracleInput(
        name=profile.get("display_name", profile.get("name", "")),
        gender=normalize_gender(profile.get("gender", "")),
        birth_datetime=birth_datetime,
        calendar_type="solar",  # 기존 profile은 solar 기준
        timezone=profile.get("timezone", DEFAULT_TIMEZONE),
        latitude=profile.get("latitude"),
        longitude=profile.get("longitude"),
        birthplace_text=profile.get("birth_place", ""),
        source="profile",
    )


def from_command_text(args: str, profile: Optional[Dict[str, Any]] = None) -> UnifiedOracleInput:
    """명령 텍스트에서 UnifiedOracleInput 생성.

    profile이 있으면 기본값으로 사용하고, args가 있으면 덮어씀.

    args 형식:
    - "1990-05-17T12:30 Asia/Seoul 37.5665 126.9780"
    - "1990-05-17T12:30"
    - "1990-05-17"
    """
    inp = from_profile(profile) if profile else UnifiedOracleInput(source="fallback")

    args = (args or "").strip()
    if not args:
        return inp

    # args 파싱: "YYYY-MM-DDTHH:MM [timezone] [lat] [lon]"
    parts = args.split()
    if parts:
        inp.birth_datetime = parts[0]
        inp.source = "command"
    if len(parts) > 1:
        inp.timezone = parts[1]
    if len(parts) > 2:
        try:
            inp.latitude = float(parts[2])
        except ValueError:
            pass
    if len(parts) > 3:
        try:
            inp.longitude = float(parts[3])
        except ValueError:
            pass

    return inp
