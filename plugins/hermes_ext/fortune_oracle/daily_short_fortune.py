#!/usr/bin/env python3
"""Gate 2 — Daily Short Fortune (dedupe + KST filtering, dry-run only).

이 모듈은 자동 발송 트리거를 포함하지 않습니다.
모든 기능은 dry-run 목적으로만 사용됩니다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
DEFAULT_SEND_HOUR = 7  # KST 07:00

# 저장소 루트의 store/ (plugins/hermes_ext/fortune_oracle 기준 세 단계 위)
DEDUPE_LOG_PATH = Path(__file__).resolve().parents[3] / "store" / "daily_fortune_dedupe.json"


def get_current_kst() -> datetime:
    """현재 KST 시각 반환."""
    return datetime.now(KST)


def time_matches(user_hhmm: str, now: datetime, tolerance_minutes: int = 30) -> bool:
    """
    사용자가 설정한 HH:MM 과 현재 KST 시각이 발송 윈도우 내인지 확인.
    기본: 설정 시각 ±30분 내.
    """
    try:
        h, m = map(int, user_hhmm.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        delta = abs((now - target).total_seconds() / 60)
        return delta <= tolerance_minutes
    except Exception:
        return False


def filter_by_kst_time(targets: List[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """KST 기준으로 현재 발송 대상만 필터링."""
    if now is None:
        now = get_current_kst()

    filtered = []
    for t in targets:
        user_time = t.get("time", "07:00")
        if time_matches(user_time, now):
            filtered.append(t)
    return filtered


def _load_dedupe_log() -> Dict[str, str]:
    """오늘 날짜 기준 dedupe 로그 로드."""
    if not DEDUPE_LOG_PATH.exists():
        return {}
    try:
        data = json.loads(DEDUPE_LOG_PATH.read_text(encoding="utf-8"))
        today = get_current_kst().date().isoformat()
        return {k: v for k, v in data.items() if k.startswith(today)}
    except Exception:
        return {}


def _save_dedupe_log(log: Dict[str, str]) -> None:
    try:
        DEDUPE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if DEDUPE_LOG_PATH.exists():
            existing = json.loads(DEDUPE_LOG_PATH.read_text(encoding="utf-8"))
        existing.update(log)
        DEDUPE_LOG_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def apply_dedupe(targets: List[Dict[str, Any]], dry_run: bool = True) -> List[Dict[str, Any]]:
    """
    동일 사용자 + 오늘 날짜 기준 dedupe.
    dry_run=True 면 실제 로그를 쓰지 않고 시뮬레이션만 함.
    """
    today = get_current_kst().date().isoformat()
    dedupe_log = _load_dedupe_log()

    result = []
    new_log_entries = {}

    for t in targets:
        key = f"{today}:{t.get('user_id')}"
        if key in dedupe_log:
            continue  # 이미 오늘 발송됨 (또는 dry-run 기록)

        result.append(t)
        new_log_entries[key] = "would_send" if dry_run else "sent"

    if not dry_run and new_log_entries:
        _save_dedupe_log(new_log_entries)

    return result


def get_recipients_for_dry_run(store, platform: str = "telegram") -> List[Dict[str, Any]]:
    """
    store에서 opt-in 대상 로드 → KST 필터 → dedupe 적용 (dry-run 전용).
    """
    raw_targets = store.collect_daily_push_targets(platform=platform)
    kst_filtered = filter_by_kst_time(raw_targets)
    deduped = apply_dedupe(kst_filtered, dry_run=True)
    return deduped


def get_recipients_with_profile_for_dry_run(store, platform: str = "telegram") -> List[Dict[str, Any]]:
    """
    store에서 opt-in 대상 로드 → KST 필터 → dedupe 적용.
    각 대상에 profile 정보를 함께 붙여서 반환 (dry-run 전용).
    """
    raw_targets = store.collect_daily_push_targets(platform=platform)
    kst_filtered = filter_by_kst_time(raw_targets)
    deduped = apply_dedupe(kst_filtered, dry_run=True)

    enriched = []
    for t in deduped:
        user_id = t.get("user_id")
        profile = None
        try:
            profile = store.get_profile(platform, user_id)
        except Exception:
            pass

        enriched.append({
            **t,
            "profile": profile,
        })
    return enriched
