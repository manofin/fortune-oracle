"""Fortune Oracle — Astro Input (Phase 38B).

출생정보 입력 스키마와 유효성 검증.
Western/Vedic 양쪽에서 공유하는 단일 입력 모델.

금지:
- 외부 네트워크 호출 금지
- AI/LLM 호출 금지
- 파일 쓰기 금지

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_CALENDAR = "gregorian"

# 위치/시간대가 충분한지 판단하는 임계값
LAT_LON_REQUIRED = True  # ASC/MC/house에 필요
TIMEZONE_REQUIRED = True  # 행성 계산에 필요


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AstroBirthInput:
    """점성술 출생정보 입력.

    Western/Vedic 양쪽에서 공유.
    필드별 충분성으로 planets-only / houses / dasha 가능 여부를 구분.
    """
    name: str = ""
    gender: str = ""                    # optional: male | female | unknown
    birth_datetime: str = ""            # YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD
    calendar_type: str = DEFAULT_CALENDAR  # gregorian | julian
    timezone: str = DEFAULT_TIMEZONE
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    birthplace_text: str = ""           # 사용자 제공 출생지 텍스트 (geocoding 금지)
    question_focus: str = ""            # 질문/관심사 (optional)
    precision_notes: List[str] = field(default_factory=list)

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
    def has_timezone(self) -> bool:
        """타임존이 설정되어 있는지."""
        return bool(self.timezone.strip())

    @property
    def has_birth_time(self) -> bool:
        """具体时间이 있는지 (HH:MM)."""
        if not self.birth_datetime:
            return False
        return "T" in self.birth_datetime or " " in self.birth_datetime

    @property
    def sufficient_for_planets(self) -> bool:
        """행성 위치 계산에 충분한지 (datetime + timezone)."""
        return bool(self.birth_datetime.strip()) and self.has_timezone

    @property
    def sufficient_for_houses(self) -> bool:
        """house/Asc/MC 계산에 충분한지 (datetime + timezone + location)."""
        return (
            self.sufficient_for_planets
            and self.has_location
            and self.has_birth_time
        )

    @property
    def sufficient_for_vedic_nakshatra(self) -> bool:
        """Vedic nakshatra 계산에 충분한지 (행성 위치 가능해야 함)."""
        return self.sufficient_for_planets

    @property
    def sufficient_for_dasha(self) -> bool:
        """Vimshottari dasha 계산에 충분한지 (달 경도 필요)."""
        return self.sufficient_for_planets

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

    def validate(self) -> Optional[str]:
        """검증 실패 시 오류 메시지 반환, 성공 시 None."""
        if not self.birth_datetime.strip():
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

        def _note(text: str) -> None:
            if text not in self.precision_notes:
                self.precision_notes.append(text)

        if self.has_location:
            if not self.has_birth_time:
                _note("위치는 제공되었으나 출생 시간이 없어 Ascendant/house를 계산할 수 없습니다.")
            if not self.has_timezone:
                _note("위치는 제공되었으나 타임존이 없어 정확한 계산을 할 수 없습니다.")
        elif self.has_timezone and self.has_birth_time:
            _note("위치가 없어 Ascendant/MC/house를 계산할 수 없습니다. 행성 위치만 계산됩니다.")

        return None

    def get_precision_summary(self) -> Dict[str, str]:
        """입력 충분성 요약."""
        summary: Dict[str, str] = {}
        summary["planets"] = "sufficient" if self.sufficient_for_planets else "blocked"
        summary["houses"] = "sufficient" if self.sufficient_for_houses else "blocked"
        summary["nakshatra"] = "sufficient" if self.sufficient_for_vedic_nakshatra else "blocked"
        summary["dasha"] = "sufficient" if self.sufficient_for_dasha else "blocked"
        if not self.has_location and self.has_timezone and self.has_birth_time:
            summary["location_warning"] = "위도/경도 부족 — Asc/MC/house 불가"
        if self.has_location and not self.has_birth_time:
            summary["time_warning"] = "출생 시간 부족 — Asc/MC/house 불가"
        return summary
