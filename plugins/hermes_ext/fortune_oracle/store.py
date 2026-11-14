#!/usr/bin/env python3
"""FortuneStore: platform-aware profile and daily-push storage."""

from __future__ import annotations

import json
import os
import fcntl
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .privacy import redact_for_disk


def make_key(platform: str, user_id: str) -> str:
    """Create a stable composite key for platform + user_id."""
    platform_text = str(platform).strip().lower()
    user_text = str(user_id).strip()
    if not platform_text or not user_text:
        raise ValueError("platform and user_id are required")
    if ":" in platform_text:
        raise ValueError("platform must not contain ':'")
    return f"{platform_text}:{user_text}"


def _split_key(key: str) -> Tuple[str, str]:
    if ":" not in key:
        return "line", key
    return key.split(":", 1)[0], key.split(":", 1)[1]


def _profile_args(args: Tuple[Any, ...]) -> Tuple[str, str, Mapping[str, Any]]:
    if len(args) == 2:
        user_id, profile = args
        return "line", str(user_id), profile
    if len(args) == 3:
        platform, user_id, profile = args
        return str(platform), str(user_id), profile
    raise TypeError("expected (user_id, profile) or (platform, user_id, profile)")


def _user_args(args: Tuple[Any, ...]) -> Tuple[str, str]:
    if len(args) == 1:
        return "line", str(args[0])
    if len(args) == 2:
        return str(args[0]), str(args[1])
    raise TypeError("expected (user_id) or (platform, user_id)")


def _push_args(args: Tuple[Any, ...]) -> Tuple[str, str, str]:
    if len(args) == 2:
        user_id, time_hhmm = args
        return "line", str(user_id), str(time_hhmm)
    if len(args) == 3:
        platform, user_id, time_hhmm = args
        return str(platform), str(user_id), str(time_hhmm)
    raise TypeError("expected (user_id, time) or (platform, user_id, time)")


class FortuneStore:
    """Small JSON store for profile and daily-push opt-in state.

    Current keys are platform:user_id. Legacy LINE-only calls are still accepted
    as (user_id, ...) and transparently map to platform="line" so existing LINE
    behavior and tests remain intact.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def locked(self):
        """Serialize mutations and delivery across gateway/worker processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @contextmanager
    def transaction(self):
        with self.locked():
            data = self._load()
            yield data
            self._save(data)

    def _load(self) -> Dict[str, Any]:
        # A missing or zero-byte file is a fresh store; non-empty invalid JSON still raises.
        if not self.path.exists() or self.path.stat().st_size == 0:
            return {"profiles": {}, "daily_push": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("profiles", {})
        data.setdefault("daily_push", {})
        return data

    def _save(self, data: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(redact_for_disk(data), fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self.path)
        directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def save_profile(self, *args: Any) -> None:
        platform, user_id, profile = _profile_args(args)
        key = make_key(platform, user_id)
        with self.transaction() as data:
            data["profiles"][key] = dict(profile)

    def get_profile(self, *args: Any) -> Optional[Dict[str, Any]]:
        platform, user_id = _user_args(args)
        data = self._load().get("profiles", {})
        return data.get(make_key(platform, user_id)) or (data.get(user_id) if platform == "line" else None)

    def delete_profile(self, *args: Any) -> None:
        from .location_settings import build_location_profile_key, clear_location_settings

        platform, user_id = _user_args(args)
        key = make_key(platform, user_id)
        location_key = build_location_profile_key(*_split_key(key))
        with self.transaction() as data:
            data.get("profiles", {}).pop(key, None)
            data.get("daily_push", {}).pop(key, None)
            # Cover both current hashed location keys and legacy raw-ID keys.
            for owned_key in {key, location_key}:
                clear_location_settings(data, owned_key, dry_run=False)
            if platform == "line":
                data.get("profiles", {}).pop(user_id, None)
                data.get("daily_push", {}).pop(user_id, None)
            # The minimal delivery claim has no birth/location data. Keep it
            # until the worker expires it, so deletion cannot reset dedupe.

    def set_daily_push(self, *args: Any, target: str, now: Optional[datetime] = None) -> None:
        platform, user_id, time_hhmm = _push_args(args)
        if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", time_hhmm):
            raise ValueError("time must be HH:MM")
        hour = int(time_hhmm.split(":", 1)[0])
        if hour > 23:
            raise ValueError("time must be HH:MM")
        key = make_key(platform, user_id)
        consent = now or datetime.now(ZoneInfo("Asia/Seoul"))
        if consent.tzinfo is None:
            raise ValueError("consent time must include timezone")
        consent = consent.astimezone(ZoneInfo("Asia/Seoul"))
        with self.transaction() as data:
            data["daily_push"][key] = {
                "platform": platform.lower(),
                "user_id": user_id,
                "time": time_hhmm,
                "target": str(target),
                "opt_in": True,
                "consented_at": consent.isoformat(),
                "start_date": (consent.date() + timedelta(days=1)).isoformat(),
            }

    def get_daily_push(self, *args: Any) -> Optional[Dict[str, Any]]:
        platform, user_id = _user_args(args)
        data = self._load().get("daily_push", {})
        return data.get(make_key(platform, user_id)) or (data.get(user_id) if platform == "line" else None)

    def disable_daily_push(self, *args: Any) -> None:
        platform, user_id = _user_args(args)
        key = make_key(platform, user_id)
        with self.transaction() as data:
            data.get("daily_push", {}).pop(key, None)
            if platform == "line":
                data.get("daily_push", {}).pop(user_id, None)

    def daily_push_entries(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._load().get("daily_push", {}))

    def collect_daily_push_targets(self, *, platform: Optional[str] = None) -> List[Dict[str, str]]:
        targets: List[Dict[str, str]] = []
        platform_filter = platform.lower() if platform else None
        for composite_key, entry in sorted(self.daily_push_entries().items()):
            if entry.get("opt_in") is not True:
                continue
            entry_platform = str(entry.get("platform") or _split_key(composite_key)[0]).lower()
            user_id = str(entry.get("user_id") or _split_key(composite_key)[1])
            if platform_filter and entry_platform != platform_filter:
                continue
            target = str(entry.get("target") or user_id)
            time_hhmm = str(entry.get("time", ""))
            if target and time_hhmm:
                item = {"user_id": user_id, "time": time_hhmm, "target": target}
                if platform is not None:
                    item["platform"] = entry_platform
                targets.append(item)
        return targets
