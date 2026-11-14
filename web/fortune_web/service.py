"""Explicit profile input; reuse the existing engines without gateway globals."""
from datetime import date, timedelta
import math
import re

from hermes_ext.fortune_oracle.bazi_bridge import BaziInput, calculate_bazi_from_profile
from hermes_ext.fortune_oracle.daily_reading import prepare_daily_reading, prepare_kline_reading
from hermes_ext.fortune_oracle.daily_fortune_engine import build_personalized_daily
from hermes_ext.fortune_oracle.compatibility import build_compatibility
from hermes_ext.fortune_oracle.localization import local_today, reading_zone


ZONE_LABELS = {"Asia/Seoul": "한국 시간", "Asia/Tokyo": "일본 시간",
               "America/New_York": "미국 동부 시간", "America/Los_Angeles": "미국 서부 시간",
               "Europe/London": "영국 시간"}
ZONE_VALUES = {label: zone for zone, label in ZONE_LABELS.items()}

FIELDS = {"birth_date", "birth_time", "display_name", "timezone", "gender"}
LOCATION_FIELDS = {"birthplace_text", "latitude", "longitude"}
SCENARIOS = {
    "general": "그날 내가 직접 선택할 수 있는 작은 일은 무엇일까요?",
    "exam": "결과를 예상하기보다, 복습과 휴식에 필요한 시간을 하나씩 정해 보세요.",
    "meeting": "상대의 마음을 단정하기보다, 나누고 싶은 이야기와 듣고 싶은 이야기를 떠올려 보세요.",
}


class InvalidProfile(ValueError):
    pass


def validate_birth(payload, *, allow_location=False):
    accepted = FIELDS | LOCATION_FIELDS if allow_location is True else FIELDS
    if not isinstance(payload, dict) or set(payload) - accepted:
        raise InvalidProfile("출생정보 입력 항목을 확인해 주세요.")
    if any(not isinstance(value, str) for key, value in payload.items()
           if key not in {"latitude", "longitude"}):
        raise InvalidProfile("입력값의 형식을 확인해 주세요.")
    try:
        for value in payload.values():
            if isinstance(value, str):
                value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidProfile("입력값의 문자를 확인해 주세요.") from None
    clock = payload.get("birth_time", "").strip()
    if clock and not re.fullmatch(r"[0-9]{2}:[0-9]{2}", clock):
        raise InvalidProfile("출생시각은 숫자 HH:MM 형식으로 입력해 주세요.")
    profile = {field: payload.get(field, "").strip() for field in FIELDS}
    if (len(profile["display_name"]) > 30 or len(profile["timezone"]) > 64
            or len(profile["birth_date"]) != 10 or len(profile["birth_time"]) not in (0, 5)):
        raise InvalidProfile("날짜·시각·별명의 길이를 확인해 주세요.")
    if any(ord(ch) < 32 for ch in profile["display_name"]):
        raise InvalidProfile("별명에는 줄바꿈이나 제어 문자를 사용할 수 없습니다.")
    profile["timezone"] = ZONE_VALUES.get(profile["timezone"], profile["timezone"]) or "Asia/Seoul"
    profile["gender"] = profile["gender"] or "unknown"
    if profile["gender"] not in ("male", "female", "unknown"):
        raise InvalidProfile("성별 항목을 다시 선택해 주세요.")
    error = BaziInput(birth_date=profile["birth_date"], birth_time=profile["birth_time"],
                      timezone=profile["timezone"], gender=profile["gender"]).validate()
    if error:
        raise InvalidProfile("실제 달력에 있는 날짜·올바른 출생시각과 시간대를 입력해 주세요.")
    if date.fromisoformat(profile["birth_date"]) > date.today():
        raise InvalidProfile("출생일은 오늘 이전 날짜로 입력해 주세요.")
    place = payload.get("birthplace_text", "").strip()
    if len(place) > 80 or any(ord(ch) < 32 for ch in place):
        raise InvalidProfile("출생지는 줄바꿈 없이 80자 이내로 입력해 주세요.")
    lat, lon = payload.get("latitude"), payload.get("longitude")
    if (lat is None) != (lon is None):
        raise InvalidProfile("위도와 경도를 함께 입력하거나 둘 다 비워 주세요.")
    if lat is not None:
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not -limit <= v <= limit or not math.isfinite(v)
               for v, limit in ((lat, 90), (lon, 180))):
            raise InvalidProfile("위도는 -90~90, 경도는 -180~180 범위의 숫자로 입력해 주세요.")
        profile.update(latitude=float(lat), longitude=float(lon))
    if place:
        profile["birthplace_text"] = place
    profile.update(language="ko", birth_year=int(profile["birth_date"][:4]))
    return profile


def integrated(profile):
    """Natal report: no date forecasts, remote model, or additional persistence."""
    from hermes_ext.fortune_oracle.integrated_report import build_integrated_report
    return build_integrated_report(profile)


def daily(profile, day, now=None):
    result = prepare_daily_reading(profile, day=day, now=now)
    # The library's missing-profile hint mentions a Telegram command.
    if not profile:
        result["text"] = "계산 결과가 아님\n출생정보를 먼저 등록해 주세요."
    return result


def chart(profile):
    result = calculate_bazi_from_profile(profile)
    if result.ok is not True or not result.eight_char or not result.elements:
        return {"ok": False, "computed": False, "text": "계산 결과가 아님\n팔자 계산을 완료하지 못했습니다. 출생정보를 확인해 주세요."}
    return {"ok": True, "computed": True, "pillars": result.eight_char,
            "elements": result.elements, "warnings": result.warnings,
            "text": "간지는 출생정보로 계산했습니다. 성향과 조언은 전통적 해석입니다."}


def kline(profile, now=None):
    result = prepare_kline_reading(profile, now=now)
    if not result["ok"]:
        result["text"] = "계산 결과가 아님\n월간 흐름을 계산하지 못했습니다. 출생정보를 확인해 주세요."
    return result


def reading_window(profile=None, now=None):
    today = local_today(profile, now=now)
    return {"min": today.isoformat(), "max": (today + timedelta(days=365)).isoformat(),
            "timezone": reading_zone(profile).key}


def dated_reading(profile, payload, now=None):
    if (not isinstance(payload, dict) or set(payload) - {"date", "scenario"}
            or not isinstance(payload.get("date"), str)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", payload["date"])
            or not isinstance(payload.get("scenario", "general"), str)
            or payload.get("scenario", "general") not in SCENARIOS):
        raise InvalidProfile("날짜와 상황을 다시 선택해 주세요.")
    try:
        target = date.fromisoformat(payload["date"])
    except ValueError:
        raise InvalidProfile("실제 달력에 있는 날짜를 입력해 주세요.") from None
    today = local_today(profile, now=now)
    if not today <= target <= today + timedelta(days=365):
        raise InvalidProfile("내 시간대의 오늘부터 365일 이내 날짜를 선택해 주세요.")
    try:
        reading = build_personalized_daily(profile, target_date=target, language="ko")
    except Exception:
        reading = None
    if not reading:
        return {"ok": False, "computed": False, "error": "calculation_unavailable",
                "text": "계산 결과가 아님\n선택한 날의 풀이를 계산하지 못했습니다. 출생정보를 확인해 주세요."}
    scenario = payload.get("scenario", "general")
    reflection = SCENARIOS[scenario]
    text = "\n".join([
        "계산된 사주·일진을 바탕으로 한 해석입니다. 점수와 조언은 경험적 해석이며 예측 확률이 아닙니다.",
        f"{target.isoformat()} · {reading_zone(profile).key}", *reading["lines"],
        "상황별 성찰 질문 (별도 점수·성공 확률 아님): " + reflection, reading["disclaimer"],
    ])
    return {"ok": True, "computed": True, "kind": "dated", "date": target.isoformat(),
            "reading_timezone": reading_zone(profile).key, "reading": reading,
            "scenario": scenario, "reflection": reflection, "text": text}


def compatibility(profile, payload):
    if not isinstance(payload, dict) or set(payload) != {"partner"}:
        raise InvalidProfile("비교할 상대의 출생정보만 입력해 주세요.")
    # A nickname is unnecessary for comparison and is not accepted at this boundary.
    partner = payload["partner"]
    if not isinstance(partner, dict) or set(partner) - (FIELDS - {"display_name"}):
        raise InvalidProfile("상대 이름이나 사용자 ID는 받지 않습니다. 출생정보만 입력해 주세요.")
    partner = validate_birth(partner)
    try:
        result = build_compatibility(profile, partner)
    except Exception:
        result = {"ok": False}
    if not result.get("ok"):
        return {"ok": False, "computed": False, "error": "calculation_unavailable",
                "text": "계산 결과가 아님\n두 사람의 비교를 완료하지 못했습니다. 출생정보를 확인해 주세요."}
    # Translate presentation only; structured calculation time zones stay canonical.
    text = result["text"]
    for zone, label in ZONE_LABELS.items():
        text = text.replace("출생 시간대: " + zone + "\n", "출생 시간대: " + label + "\n")
    return {**result, "text": text, "computed": True, "kind": "compatibility"}
