"""Fortune Oracle -- Korean birth input parser.

한국어 자연어 날짜/시간/이름 파싱.
외부 NLP/AI 호출 없음. 순수 regex/dict 기반.

예:
  parse_birth_input("1990년 5월 17일 오후 12시 30분, 홍길동 (洪吉童)")
  -> {"birth_date": "1990-05-17", "birth_time": "12:30",
      "display_name": "홍길동", "name_hanja": "洪吉童", "ok": True}
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Zero-width / invisible character 제거
# ---------------------------------------------------------------------------

_ZW_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")


def _clean(text: str) -> str:
    """zero-width 문자 및 불필요한 공백 정규화."""
    text = _ZW_CHARS.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------------------------------------------------------------------------
# 날짜 패턴
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
)

# ---------------------------------------------------------------------------
# 시간 패턴 -- 오전/오후 + 시 + 분
# ---------------------------------------------------------------------------

_TIME_PATTERN = re.compile(
    r"(오전|오후|am|pm|AM|PM)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?"
)


def _parse_int(s: str) -> Optional[int]:
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None


def _apply_ampm(hour: int, ampm: str) -> int:
    ampm = (ampm or "").strip()
    if ampm in ("오전", "am", "AM"):
        return 0 if hour == 12 else hour
    if ampm in ("오후", "pm", "PM"):
        return 12 if hour == 12 else hour + 12
    return hour


# ---------------------------------------------------------------------------
# 이름 파싱 -- 한글 이름 + 선택적 한자 괄호
# ---------------------------------------------------------------------------

# 한자 유니코드 범위
_HANJA_BLOCK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+")

# 쉼표 뒤 이름: "홍길동 (洪吉童)" 또는 "홍길동"
_NAME_AFTER_COMMA = re.compile(
    r"[,，]\s*"
    r"([\uac00-\ud7a3a-zA-Z][\uac00-\ud7a3a-zA-Z0-9 ·]{0,19}?)"
    r"(?:\s*[\(\（]([^\)\）]{1,20})[\)\）])?"
    r"\s*$"
)

# 쉼표 없이 날짜/시간 이후 이름
_NAME_NO_COMMA = re.compile(
    r"(?:분|시)\s+"
    r"([\uac00-\ud7a3]{2,6})"
    r"(?:\s*[\(\（]([^\)\）]{1,20})[\)\）])?"
    r"\s*$"
)

# ---------------------------------------------------------------------------
# gender 파싱 -- 쉼표 뒤 이름 다음에 gender 토큰
# ---------------------------------------------------------------------------

# 쉼표 + gender 토큰 (이름 뒤 두 번째 쉼표 또는 명시적 gender=xxx)
_GENDER_EXPLICIT = re.compile(
    r"gender\s*=\s*([a-zA-Z가-힣]+)",
    re.IGNORECASE,
)

_GENDER_INLINE_TOKENS = re.compile(
    r"(?:[,，]\s*|(?<=\s))\b(남성|여성|남자|여자|남|여|male|female|m|f)\b\s*$",
    re.IGNORECASE,
)

_GENDER_MAP = {
    "male": "male", "m": "male",
    "남": "male", "남성": "male", "남자": "male",
    "female": "female", "f": "female",
    "여": "female", "여성": "female", "여자": "female",
}


def _parse_gender(text: str) -> str:
    """텍스트에서 gender 추출. 없으면 'unknown'."""
    # 명시적 gender=xxx 우선
    m = _GENDER_EXPLICIT.search(text)
    if m:
        raw = m.group(1).strip().lower()
        return _GENDER_MAP.get(raw, "unknown")
    # 마지막 쉼표 뒤 gender 토큰
    m2 = _GENDER_INLINE_TOKENS.search(text)
    if m2:
        raw = m2.group(1).strip().lower()
        return _GENDER_MAP.get(raw, "unknown")
    return "unknown"


_TIMEZONE_ALIASES = {
    "서울": "Asia/Seoul",
    "seoul": "Asia/Seoul",
    "부산": "Asia/Seoul",
    "한국": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "kst": "Asia/Seoul",
}


def parse_birth_input(text: str) -> Dict[str, Any]:
    """한국어 생년월일시+이름 문자열을 파싱한다.

    Returns:
        dict:
          ok: bool
          birth_date: "YYYY-MM-DD"
          birth_time: "HH:MM"  (시각 미상은 빈 문자열, 임의 시각을 채우지 않음)
          display_name: str    (없으면 "")
          name_hanja: str      (없으면 "")
          timezone, gender, birth_place, warnings, error
    """
    text = _clean(text)
    warnings: list[str] = []

    # --- 날짜 ---
    date_m = _DATE_PATTERN.search(text)
    if not date_m:
        return {
            "ok": False,
            "error": "날짜를 인식하지 못했습니다. 'YYYY년 MM월 DD일' 형식으로 입력해 주세요.",
            "warnings": warnings,
        }
    year = _parse_int(date_m.group(1))
    month = _parse_int(date_m.group(2))
    day = _parse_int(date_m.group(3))

    if year is None or month is None or day is None:
        return {"ok": False, "error": "날짜 숫자를 읽지 못했습니다.", "warnings": warnings}
    if not (1800 <= year <= 2100):
        return {"ok": False, "error": f"지원하지 않는 연도입니다: {year}.", "warnings": warnings}
    if not (1 <= month <= 12):
        return {"ok": False, "error": f"월 값이 잘못됐습니다: {month}", "warnings": warnings}
    if not (1 <= day <= 31):
        return {"ok": False, "error": f"일 값이 잘못됐습니다: {day}", "warnings": warnings}

    try:
        birth_date = date(year, month, day).isoformat()
    except ValueError:
        return {"ok": False, "error": "실제 달력에 없는 날짜입니다. 생년월일을 확인해 주세요.", "warnings": warnings}

    # --- 시간 ---
    after_date = text[date_m.end():]
    time_m = _TIME_PATTERN.search(after_date)
    birth_time = ""
    if time_m:
        ampm = time_m.group(1) or ""
        hour_raw = _parse_int(time_m.group(2))
        minute_raw = _parse_int(time_m.group(3)) if time_m.group(3) else 0
        if hour_raw is None or not (0 <= hour_raw <= 23) or (ampm and not 1 <= hour_raw <= 12):
            return {"ok": False, "error": "시간 값이 잘못됐습니다. 0~23시 또는 오전/오후 1~12시로 입력해 주세요.", "warnings": warnings}
        if minute_raw is None or not 0 <= minute_raw <= 59:
            return {"ok": False, "error": "분 값이 잘못됐습니다. 0~59분으로 입력해 주세요.", "warnings": warnings}
        hour = _apply_ampm(hour_raw, ampm)
        birth_time = f"{hour:02d}:{minute_raw:02d}"
    else:
        warnings.append("출생시각 미상으로 저장합니다. 시주와 대운은 계산하지 않습니다.")

    # --- 이름 ---
    # trailing gender 토큰이 이름으로 오인되지 않도록 이름 파싱용 문자열에서만 제거한다.
    name_text = _GENDER_INLINE_TOKENS.sub("", text).strip()
    name_text = _GENDER_EXPLICIT.sub("", name_text).strip()
    display_name = ""
    name_hanja = ""

    # 방법 1: 쉼표 뒤
    name_m = _NAME_AFTER_COMMA.search(name_text)
    if name_m:
        candidate = (name_m.group(1) or "").strip()
        hanja_candidate = (name_m.group(2) or "").strip()
        if candidate and not re.match(r"^[\d\s]+$", candidate):
            display_name = candidate[:20]
        if hanja_candidate and _HANJA_BLOCK.search(hanja_candidate):
            name_hanja = hanja_candidate[:20]

    # 방법 2: 쉼표 없이 시간 뒤
    if not display_name:
        name_m2 = _NAME_NO_COMMA.search(name_text)
        if name_m2:
            candidate = (name_m2.group(1) or "").strip()
            hanja_candidate = (name_m2.group(2) or "").strip()
            if candidate:
                display_name = candidate[:20]
            if hanja_candidate and _HANJA_BLOCK.search(hanja_candidate):
                name_hanja = hanja_candidate[:20]

    # 방법 3: 시간 이후 남은 한글만 추출
    if not display_name:
        after_time = name_text[date_m.end():]
        if time_m:
            name_time_m = _TIME_PATTERN.search(after_time)
            after_time = after_time[name_time_m.end():] if name_time_m else after_time
        after_time = after_time.strip()
        hangul_only = re.sub(r"[^\uac00-\ud7a3]", "", after_time)
        if 2 <= len(hangul_only) <= 6:
            display_name = hangul_only

    # --- 장소/시간대 ---
    timezone = "Asia/Seoul"
    for alias, tz in _TIMEZONE_ALIASES.items():
        if alias.lower() in text.lower():
            timezone = tz
            break

    # --- gender ---
    gender = _parse_gender(text)

    return {
        "ok": True,
        "birth_date": birth_date,
        "birth_time": birth_time,
        "display_name": display_name,
        "name_hanja": name_hanja,
        "timezone": timezone,
        "gender": gender,
        "birth_place": "Seoul",
        "warnings": warnings,
    }
