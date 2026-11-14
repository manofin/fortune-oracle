# 구현 예정 방식: 안성법(安星法) 기준
"""Ziwei Doushu bridge skeleton (Phase 32).

Policy:
- stdout JSON only
- timeout mandatory
- dependency missing → fail-open (ok=False)
- never writes files, never calls external network
- raw birth_date/birth_time/name_hanja never exposed in prompts/logs
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# DEPRECATED: legacy bridge — kept for rollback (4단계)
LEGACY_BRIDGE_SCRIPT = Path(__file__).parent / "scripts" / "ziwei_doushu_bridge.mjs"

# ACTIVE: iztro adapter (4단계 전환)
BRIDGE_SCRIPT = Path(__file__).parent / "scripts" / "ziwei_iztro_adapter.mjs"
TIMEOUT_SEC = 8



def _enrich_ziwei_facts(facts: dict, birth_date: str = "", birth_time: str = "", gender: str = None) -> dict:
    """Enrich raw mjs output with consistent structures for all consumers.
    - ming_gong: main_stars, is_empty, borrowed_stars (from opposite +6)
    - sihua: converted to lu/quan/ke/ji
    - daxian + current_daxian + daxian_sihua (computed for current stem)
    This ensures /oracle, adapters, deep prompt etc. all see the same rich facts.
    """
    # ming_gong enrichment from stars
    ming = facts.setdefault("ming_gong", {})
    stars = facts.get("stars", {}) or {}
    ming_idx = ming.get("index")
    if ming_idx is not None:
        ming_idx_str = str(ming_idx)
        main_stars = stars.get(ming_idx_str, []) or []
        EARTHLY_BRANCHES = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
        branch_cn = EARTHLY_BRANCHES[ming_idx % 12] if ming_idx is not None else ""
        ming["main_stars"] = [{"star": s, "branch": branch_cn} for s in main_stars] if main_stars else []
        if not main_stars:
            ming["is_empty"] = True
            opp_idx = (ming_idx + 6) % 12 if ming_idx is not None else 0
            borrowed = stars.get(str(opp_idx), []) or []
            opp_branch = EARTHLY_BRANCHES[opp_idx % 12]
            ming["borrowed_stars"] = [{"star": s, "branch": opp_branch} for s in borrowed]
        else:
            ming["is_empty"] = False
            ming["borrowed_stars"] = []

    # sihua conversion (raw 祿 etc -> lu/quan/ke/ji for prompt skeleton)
    raw_sihua = facts.get("sihua", {})
    if raw_sihua and not any(k in raw_sihua for k in ("lu", "quan", "ke", "ji")):
        key_map = {"祿": "lu", "權": "quan", "科": "ke", "忌": "ji"}
        converted = {}
        for ch, eng in key_map.items():
            if ch in raw_sihua:
                converted[eng] = raw_sihua[ch]
        if converted:
            facts["sihua"] = converted

    # daxian enrichment (어댑터 단일 경로, 5단계-1 legacy fallback 제거)
    try:
        adapter_daxian = facts.get("daxian")
        adapter_decadal_sihua = facts.get("decadal_sihua", {})

        if adapter_daxian and len(adapter_daxian) > 0:
            facts["daxian"] = adapter_daxian

            # 현재 대한 계산 (나이 기준)
            birth_date_str = birth_date or facts.get("input", {}).get("birth_date", "")
            age = None
            if birth_date_str:
                parts = birth_date_str.split("-")
                if len(parts) >= 1:
                    birth_year = int(parts[0])
                    import datetime
                    current_year = datetime.datetime.now().year
                    age = current_year - birth_year

            if age is not None:
                for d in adapter_daxian:
                    range_vals = d.get("range")
                    if range_vals and isinstance(range_vals, list) and len(range_vals) >= 2:
                        start, end = range_vals[0], range_vals[1]
                        if age >= start and age <= end:
                            cd = {
                                "ages": f"{start}-{end}",
                                "ganzhi": d.get("ganzhi", ""),
                            }
                            facts["current_daxian"] = {
                                "ages": cd["ages"],
                                "ganzhi": cd["ganzhi"],
                                "range": cd["ages"],
                                "stem_branch": cd["ganzhi"],
                            }
                            # decadal_sihua에서 현재 대한의 사화 추출
                            idx_key = str(d.get("index", ""))
                            if idx_key in adapter_decadal_sihua:
                                cd["sihua"] = adapter_decadal_sihua[idx_key].get("sihua", {})
                                if cd["sihua"]:
                                    facts["daxian_sihua"] = cd["sihua"]
                            break
    except Exception:
        pass  # non-fatal

    return facts

# 실사용 모니터링 주석 (#6)
# - 甲·庚년생 등 사화 고친 부분 정확성 관찰 필요
# - 다양한 생년월일로 /ziwei_deep 호출 시 facts['ming_gong'], sihua, daxian_sihua 검증 권장
# - 로그나 간단한 stats 수집은 후속으로 추가 가능


def calculate_ziwei_chart(
    birth_date: str,
    birth_time: str,
    gender: str | None = None,
    longitude: float = 126.9780,
    calendar: str = "solar",
    is_leap_month: bool = False,
) -> dict[str, Any]:
    """Return Ziwei chart JSON or fail-open structure.

    Phase 3 (item 5): mjs not found / invalid output 시 stars={} 강제 fallback,
    모든 에러 경로에 stars/ming_gong/sihua 포함으로 adapters fail-open 안전.

    음력 입력 (calendar='lunar'): bridge.mjs에 is_leap_month 전달.
    윤달 플래그: isLeapMonth가 byLunar 4번째 인자로 전달됨.
    """
    if not BRIDGE_SCRIPT.exists():
        return {
            "ok": False,
            "error_code": "DEPENDENCY_MISSING",
            "message": "자미두수 브리지 스크립트를 찾을 수 없습니다.",
            "warnings": ["ziwei engine unavailable"],
            "stars": {},
            "ming_gong": {},
            "sihua": {},
        }

    input_data = {
        "birth_date": birth_date,
        "birth_time": birth_time,
        "gender": gender or "unknown",
        "longitude": longitude,
        "calendar": calendar,
        "isLeapMonth": is_leap_month,
    }

    try:
        proc = subprocess.run(
            ["node", str(BRIDGE_SCRIPT)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            shell=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or "bridge failed"
            # iztro 내부 에러 사용자에게 노출 방지
            if "missing birth_time" in stderr.lower():
                user_msg = "출생 시각을 입력해주세요."
            elif "invalid hour" in stderr.lower():
                user_msg = "입력하신 시각을 확인해주세요. 올바른 시간 형식(00:00~23:59)을 사용해주세요."
            elif "lunar" in stderr.lower() or "month" in stderr.lower() or "day" in stderr.lower():
                user_msg = "입력하신 음력 날짜를 확인해주세요. 존재하지 않는 날짜일 수 있습니다."
            elif "undefined" in stderr.lower() or "cannot read" in stderr.lower():
                user_msg = "계산 중 오류가 발생했습니다. 입력값을 확인해주세요."
            else:
                user_msg = stderr
            return {
                "ok": False,
                "error_code": "ENGINE_ERROR",
                "message": f"iztro adapter error: {user_msg}",
                "warnings": [f"계산 중 오류: {user_msg}"],
                "stars": {},
                "ming_gong": {},
                "sihua": {},
            }
        result = json.loads(proc.stdout)
        result.setdefault("ok", True)
        result.setdefault("engine", "ziwei-doushu-adapted")
        return _enrich_ziwei_facts(result, birth_date, birth_time, gender)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error_code": "TIMEOUT",
            "message": f"자미두수 계산 시간 초과 ({TIMEOUT_SEC}초) — 잠시 후 다시 시도해 주세요.",
            "warnings": [f"계산 시간 초과 ({TIMEOUT_SEC}초)"],
            "stars": {},
            "ming_gong": {},
            "sihua": {},
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "ok": False,
            "error_code": "INVALID_OUTPUT",
            "message": str(e),
            "warnings": ["ziwei output parse failed"],
            "stars": {},
            "ming_gong": {},
            "sihua": {},
        }
# --------------------------------------------------------------------------- 
# DaXian (대한) extras via iztro (길 C - verified only)
# Calls iztro_extras_adapter.mjs (thin, no change to core ziwei engine)
# ---------------------------------------------------------------------------

DAXIAN_SCRIPT = Path(__file__).parent / "scripts" / "iztro_extras_adapter.mjs"

def calculate_ziwei_daxian(
    birth_date: str,
    birth_time: str,
    gender: str | None = None,
) -> dict[str, Any]:
    """Return daxian list and current_daxian or fail-open structure.
    Uses the verified iztro_extras_adapter (DaXian only).
    """
    if not DAXIAN_SCRIPT.exists():
        return {
            "ok": False,
            "error_code": "DEPENDENCY_MISSING",
            "message": "iztro daxian adapter not found",
            "daxian": [],
        }

    input_data = {
        "birth_date": birth_date,
        "birth_time": birth_time,
        "gender": gender or "unknown",
    }

    try:
        proc = subprocess.run(
            ["node", str(DAXIAN_SCRIPT)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            shell=False,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error_code": "ENGINE_ERROR",
                "message": proc.stderr.strip() or "daxian bridge failed",
                "daxian": [],
            }
        result = json.loads(proc.stdout)
        result.setdefault("ok", True)
        return result
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error_code": "TIMEOUT",
            "message": f"DaXian calculation timeout ({TIMEOUT_SEC}s)",
            "daxian": [],
        }
    except (json.JSONDecodeError, Exception) as e:
        return {
            "ok": False,
            "error_code": "INVALID_OUTPUT",
            "message": str(e),
            "daxian": [],
        }
