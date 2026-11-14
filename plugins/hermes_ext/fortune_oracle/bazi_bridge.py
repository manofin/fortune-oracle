"""Fortune Oracle — Bazi Bridge (Phase 3)

Node CLI sandbox bridge를 통해 팔자/사주를 계산한다.
subprocess로 JSON만 주고받으며, 어떠한 경우에도 plugin 전체를 중단시키지 않는다.

금지:
- shell=True 사용 금지
- 외부 네트워크 호출 금지
- AI/LLM 호출 금지
- 파일 쓰기 금지

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parent / "scripts"
_BRIDGE_SCRIPT = _SCRIPTS_DIR / "life_kline_bazi_bridge.mjs"

# subprocess 타임아웃 (초)
_TIMEOUT_SEC = 5

# stdout 최대 크기 (8KB — JSON oversize 방어)
_MAX_STDOUT_BYTES = 8 * 1024


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BaziInput:
    """사주 계산 입력. birth_date는 필수."""
    birth_date: str                        # YYYY-MM-DD
    birth_time: Optional[str] = None       # HH:MM; no implicit known midnight
    birth_place: str = ""
    longitude: Optional[float] = None
    timezone: str = "Asia/Seoul"
    gender: str = "unknown"
    birth_time_known: Optional[bool] = None

    def __post_init__(self):
        supplied = bool(self.birth_time)
        if self.birth_time_known is None:
            self.birth_time_known = supplied
        elif not supplied:
            self.birth_time_known = False
        if not supplied:
            self.birth_time = '00:00'  # internal civil-date placeholder, never a known hour

    def validate(self) -> Optional[str]:
        """검증 실패 시 오류 메시지 반환, 성공 시 None."""
        import re
        if not self.birth_date:
            return "birth_date가 비어 있습니다."
        if not isinstance(self.birth_date, str) or not isinstance(self.birth_time, str):
            return '날짜와 시각은 문자열로 입력해 주세요.'
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", self.birth_date):
            return "birth_date 형식 오류: YYYY-MM-DD 형식이어야 합니다."
        if not re.match(r"^\d{1,2}:\d{2}$", self.birth_time):
            return "birth_time 형식 오류: HH:MM 형식이어야 합니다."
        parts = self.birth_time.split(":")
        if int(parts[0]) > 23 or int(parts[1]) > 59:
            return "birth_time 값 오류: 올바른 시각이 필요합니다."
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            from .birth_clock import resolve_wall_time, civil_day_utc_bounds
            wall = datetime.fromisoformat(self.birth_date).replace(hour=int(parts[0]), minute=int(parts[1]))
            if not 1800 <= wall.year <= 2100:
                raise ValueError
            ZoneInfo(self.timezone)
            if self.birth_time_known:
                resolve_wall_time(wall, self.timezone)
            else:
                civil_day_utc_bounds(wall.date(), self.timezone)
            if self.longitude is not None:
                import math
                if isinstance(self.longitude, bool) or not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
                    raise ValueError
        except (ValueError, TypeError, KeyError):
            return '유효한 날짜·IANA 시간대와 중복되지 않는 출생시각이 필요합니다.'
        return None


def _valid_result_schema(data):
    """Check provider types and facts before coercion or date adjustment."""
    if not isinstance(data, dict) or type(data.get("ok")) is not bool:
        return False
    if not data["ok"]:
        return True
    pillars, counts = data.get("eight_char"), data.get("elements")
    basis = data.get("time_basis", {})
    if not isinstance(basis, dict) or not isinstance(pillars, dict):
        return False
    uncertain = basis.get("uncertain_pillars", [])
    if not isinstance(uncertain, list) or any(k not in ("year", "month") for k in uncertain):
        return False
    if set(pillars) != {"year", "month", "day", "time"}:
        return False
    for key, value in pillars.items():
        if value == "" and (key == "time" or key in uncertain):
            continue
        if not isinstance(value, str) or len(value) != 2 or value[0] not in "甲乙丙丁戊己庚辛壬癸" or value[1] not in "子丑寅卯辰巳午未申酉戌亥":
            return False
    if (not isinstance(counts, dict) or not counts
            or any(k not in {"목(木)", "화(火)", "토(土)", "금(金)", "수(水)"} or type(v) is not int or v < 0 for k, v in counts.items())
            or sum(counts.values()) != sum(len(v) for v in pillars.values())):
        return False
    if type(data.get("solar_term_month_mode", False)) is not bool:
        return False
    if not isinstance(data.get("warnings", []), list) or any(not isinstance(v, str) for v in data.get("warnings", [])):
        return False
    dayun = data.get("dayun")
    if dayun is not None:
        if not isinstance(dayun, dict) or not isinstance(dayun.get("cycles"), list):
            return False
        try:
            from datetime import datetime, date
            date.fromisoformat(dayun["start_date"])
            if dayun.get("start_reference") is not None:
                datetime.fromisoformat(dayun["start_reference"])
            if dayun.get("direction") not in ("forward", "reverse"):
                return False
            for cycle in dayun["cycles"]:
                if not isinstance(cycle, dict) or type(cycle.get("start_year")) is not int or type(cycle.get("end_year")) is not int:
                    return False
                if cycle["start_year"] > cycle["end_year"] or not isinstance(cycle.get("pillar"), str) or len(cycle["pillar"]) != 2:
                    return False
        except (ValueError, TypeError, KeyError):
            return False
    return True


@dataclass
class BaziResult:
    """사주 계산 결과."""
    ok: bool
    engine: str = ""
    solar_term_month_mode: bool = False  # True = 절기 시각 기준 Exact 모드
    input: Optional[Dict[str, Any]] = None
    solar: Optional[Dict[str, Any]] = None
    lunar: Optional[Dict[str, Any]] = None
    eight_char: Optional[Dict[str, str]] = None
    elements: Optional[Dict[str, int]] = None
    zodiac: str = ""
    dayun: Optional[Dict[str, Any]] = None
    time_basis: Dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다."
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BaziResult":
        if not _valid_result_schema(d):
            return cls.error("ENGINE_ERROR", "bridge 결과 형식 오류")
        return cls(
            ok=d["ok"],
            engine=d.get("engine", ""),
            solar_term_month_mode=bool(d.get("solar_term_month_mode", False)),
            input=d.get("input"),
            solar=d.get("solar"),
            lunar=d.get("lunar"),
            eight_char=d.get("eight_char"),
            elements=d.get("elements"),
            zodiac=d.get("zodiac", ""),
            dayun=d.get("dayun"),
            time_basis=d.get("time_basis") or {},
            disclaimer=d.get("disclaimer", cls.__dataclass_fields__["disclaimer"].default),
            warnings=d.get("warnings", []),
            error_code=d.get("error_code", ""),
            message=d.get("message", ""),
        )

    @classmethod
    def error(cls, error_code: str, message: str, warnings: Optional[List[str]] = None) -> "BaziResult":
        return cls(ok=False, error_code=error_code, message=message, warnings=warnings or [])

    def format_summary(self) -> str:
        """팔자 요약 텍스트 (Telegram용)."""
        if not self.ok or not self.eight_char:
            return ""
        ec = self.eight_char
        zodiac_str = f"띠: {self.zodiac}" if self.zodiac else ""
        pillar_str = ' '.join(label + ec[key] for key, label in
                              (('year','년'), ('month','월'), ('day','일'), ('time','시')) if ec.get(key))
        elements_str = ""
        if self.elements:
            top = sorted(self.elements.items(), key=lambda x: -x[1])[:2]
            elements_str = " · ".join(f"{k} {v}개" for k, v in top)
        lines = [f"🔮 팔자: {pillar_str}"]
        if zodiac_str:
            lines.append(zodiac_str)
        if elements_str:
            lines.append(f"오행: {elements_str}")
        # 절기 기준 limitation 문구 — 기본 모드(일 기준)일 때만 표기
        if not self.solar_term_month_mode:
            lines.append("  ※ 월주는 절기 날짜 기준이며, 절기 당일 출생 시각에 따라 일부 차이가 있을 수 있습니다.")
        if self.time_basis:
            lines.append("  ※ 일·시주는 출생지 민간시 기준이며 진태양시 보정은 적용하지 않았습니다.")
            if self.time_basis.get('uncertain_pillars'):
                labels = {'year':'년주', 'month':'월주'}
                missing = '·'.join(labels[key] for key in self.time_basis['uncertain_pillars'] if key in labels)
                lines.append(f"  ※ 절기 경계 미확정: {missing} 제외, 시주·대운 미등록.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node 가용성 확인 (모듈 로드 시 1회)
# ---------------------------------------------------------------------------

def _find_node() -> Optional[str]:
    """node 실행 파일 경로 반환. 없으면 None."""
    import shutil
    return shutil.which("node")


_NODE_BIN: Optional[str] = _find_node()


# ---------------------------------------------------------------------------
# Core bridge function
# ---------------------------------------------------------------------------

def calculate_bazi(bazi_input: BaziInput) -> BaziResult:
    """팔자 계산 메인 함수. fail-open: 어떤 오류도 BaziResult로 래핑.

    Args:
        bazi_input: BaziInput 인스턴스.

    Returns:
        BaziResult. ok=False면 error_code/message 확인.
    """
    # 1. Python-side 입력 검증
    err = bazi_input.validate()
    if err:
        logger.debug("BaziInput validation failed: %s", err)
        return BaziResult.error("INVALID_INPUT", err)

    # 2. Node 존재 확인
    if not _NODE_BIN:
        logger.warning("node binary not found — bazi bridge unavailable")
        return BaziResult.error(
            "DEPENDENCY_MISSING",
            "Node.js가 설치되어 있지 않아 팔자 계산을 사용할 수 없습니다."
        )

    # 3. Bridge 스크립트 존재 확인
    if not _BRIDGE_SCRIPT.exists():
        logger.warning("bridge script not found: %s", _BRIDGE_SCRIPT)
        return BaziResult.error(
            "DEPENDENCY_MISSING",
            f"bridge 스크립트를 찾을 수 없습니다: {_BRIDGE_SCRIPT}"
        )

    # 4. 입력 JSON 직렬화 (민감 필드 최소화 — birth_date/time만 필수)
    input_dict: Dict[str, Any] = {
        "birth_date": bazi_input.birth_date,
        "birth_time": bazi_input.birth_time,
        "birth_place": bazi_input.birth_place,
        "timezone": bazi_input.timezone,
        "gender": bazi_input.gender,
        "birth_time_known": bazi_input.birth_time_known,
    }
    if bazi_input.longitude is not None:
        input_dict["longitude"] = bazi_input.longitude
    if bazi_input.birth_time_known:
        from datetime import datetime, timedelta, timezone
        from .birth_clock import resolve_wall_time
        h, m = map(int, bazi_input.birth_time.split(':'))
        wall = datetime.fromisoformat(bazi_input.birth_date).replace(hour=h, minute=m)
        reference = resolve_wall_time(wall, bazi_input.timezone).astimezone(timezone(timedelta(hours=8)))
        input_dict['term_reference'] = {key: getattr(reference, key) for key in
                                        ('year', 'month', 'day', 'hour', 'minute', 'second')}
    else:
        from datetime import date, timedelta, timezone
        from .birth_clock import civil_day_utc_bounds
        bounds = civil_day_utc_bounds(date.fromisoformat(bazi_input.birth_date), bazi_input.timezone)
        input_dict['term_interval'] = [
            {key: getattr(moment.astimezone(timezone(timedelta(hours=8))), key)
             for key in ('year', 'month', 'day', 'hour', 'minute', 'second')}
            for moment in bounds]
    input_json = json.dumps(input_dict, ensure_ascii=False)

    # 5. subprocess 실행 (shell=False, command list)
    cmd = [_NODE_BIN, str(_BRIDGE_SCRIPT)]
    # 최소 env: PATH만 유지, 민감한 환경변수 제거
    # FORTUNE_BAZI_SOLAR_TERM_MONTH=1 이면 절기 시각 기준 Exact 모드 활성화
    safe_env: Dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin")}
    _solar_term_flag = os.environ.get("FORTUNE_BAZI_SOLAR_TERM_MONTH", "")
    if _solar_term_flag == "1":
        safe_env["FORTUNE_BAZI_SOLAR_TERM_MONTH"] = "1"

    try:
        proc = subprocess.run(
            cmd,
            input=input_json,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SEC,
            cwd=str(_SCRIPTS_DIR),
            env=safe_env,
        )
    except subprocess.TimeoutExpired:
        logger.warning("bazi bridge timeout (%ds)", _TIMEOUT_SEC)
        return BaziResult.error("TIMEOUT", f"팔자 계산 타임아웃 ({_TIMEOUT_SEC}초)")
    except FileNotFoundError:
        logger.warning("node not found at %s", _NODE_BIN)
        return BaziResult.error("DEPENDENCY_MISSING", "Node.js 실행 파일을 찾을 수 없습니다.")
    except OSError as e:
        logger.warning("bazi bridge OSError: %s", e)
        return BaziResult.error("ENGINE_ERROR", f"시스템 오류: {e}")

    # 6. stderr — debug용으로만 보관
    if proc.stderr:
        logger.debug("bazi bridge returned diagnostic output (%d characters)", len(proc.stderr))

    # 7. stdout 크기 제한 확인
    stdout = proc.stdout
    if len(stdout.encode()) > _MAX_STDOUT_BYTES:
        logger.warning("bazi bridge stdout too large: %d bytes", len(stdout.encode()))
        return BaziResult.error("ENGINE_ERROR", "bridge 출력이 너무 큽니다.")

    # 8. JSON 파싱
    stdout = stdout.strip()
    if not stdout:
        logger.warning("bazi bridge empty stdout (rc=%d)", proc.returncode)
        return BaziResult.error("ENGINE_ERROR", "bridge가 빈 응답을 반환했습니다.")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.warning("bazi bridge JSON parse failed; provider output was not logged")
        return BaziResult.error("ENGINE_ERROR", "bridge JSON 파싱 실패")

    # 9. BaziResult 생성
    result = BaziResult.from_dict(data)
    if result.ok and result.dayun and result.dayun.get('start_reference'):
        from datetime import datetime, timedelta, timezone
        from zoneinfo import ZoneInfo
        start = datetime.fromisoformat(result.dayun.pop('start_reference')).replace(tzinfo=timezone(timedelta(hours=8)))
        local_start = start.astimezone(ZoneInfo(bazi_input.timezone))
        result.dayun['start_date'] = local_start.date().isoformat()
        year_shift = local_start.year - start.year
        for cycle in result.dayun['cycles']:
            cycle['start_year'] += year_shift
            cycle['end_year'] += year_shift
    return result


def calculate_bazi_from_profile(profile: Dict[str, Any]) -> BaziResult:
    """profile dict에서 BaziInput을 구성해 calculate_bazi 호출.

    profile 키: birth_date, birth_time, birth_place, longitude, timezone, gender
    """
    if not profile or not profile.get("birth_date"):
        return BaziResult.error("INVALID_INPUT", "프로필에 생년월일(birth_date)이 없습니다.")

    bazi_input = BaziInput(
        birth_date=str(profile.get("birth_date", "")),
        birth_time=str(profile.get("birth_time") or "00:00"),
        birth_place=str(profile.get("birth_place", "")),
        longitude=profile.get("longitude"),
        timezone=str(profile.get("timezone", "Asia/Seoul")),
        gender=str(profile.get("gender", "unknown")),
        birth_time_known=bool(profile.get("birth_time")),
    )
    return calculate_bazi(bazi_input)


def bridge_available() -> bool:
    """Node + bridge 스크립트 모두 사용 가능한지 확인."""
    return bool(_NODE_BIN) and _BRIDGE_SCRIPT.exists()

def bazi_result_to_legacy_dict(result: "BaziResult") -> dict:
    """BaziResult를 _handle_show_profile이 기대하는 레거시 dict 형식으로 변환.

    - eight_char의 "time" 키를 "hour"로 매핑 (시주)
    - 각 간지를 heavenly_stem / earthly_branch로 분리
    - .get() 호출이 가능한 순수 dict 반환
    """
    if not result or not result.ok:
        return {"ok": False, "pillars": {}}

    ec = result.eight_char or {}
    pillars = {}
    # eight_char의 time → pillars의 hour로 매핑 (중요)
    for ec_key, pillar_key in [
        ("year", "year"),
        ("month", "month"),
        ("day", "day"),
        ("time", "hour"),   # ← 시주 키 매핑
    ]:
        gz = ec.get(ec_key, "")
        if len(gz) == 2:
            pillars[pillar_key] = {
                "heavenly_stem": gz[0],
                "earthly_branch": gz[1],
            }
        else:
            pillars[pillar_key] = {"heavenly_stem": "?", "earthly_branch": "?"}

    legacy = {
        "ok": True,
        "pillars": pillars,
        "elements": result.elements or {},
    }
    return legacy
