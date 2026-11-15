#!/usr/bin/env python3
"""Compare the frozen public candidate with current time-scope wording.

Uses separate Python processes and the actual Node bridge for both revisions.
Only invented adult profiles are used; no store, network or model is required.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "103cea02a1af3968f1507331f69a2598b5b39c96"
SOURCES = ["plugins/hermes_ext/fortune_oracle/" + path for path in (
    "daily_fortune_engine.py", "bazi_bridge.py", "localization.py", "scripts/life_kline_bazi_bridge.mjs")]
PROFILES = [
    {"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male", "timezone": "Asia/Seoul"},
    {"birth_date": "1988-03-02", "birth_time_known": False, "gender": "unknown", "timezone": "Asia/Seoul"},
    {"birth_date": "1988-03-02", "birth_time_known": False, "timezone": "America/New_York"},
    {"birth_date": "2000-02-04", "birth_time_known": False, "timezone": "Asia/Seoul"},
    {"birth_date": "2000-03-05", "birth_time_known": False, "timezone": "Asia/Seoul"},
]
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def worker(root, output):
    sys.path[:0] = [str(root / "plugins"), str(root / "web")]
    from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as engine, localization
    from fortune_web import service

    charts, readings, payloads = [], [], []
    for index, profile in enumerate(PROFILES):
        chart = bazi_bridge.calculate_bazi_from_profile(profile)
        assert chart.ok, index
        daily = engine.build_personalized_daily(profile, target_date=date(2026, 11, 24))
        charts.append({"id": index, "chart": asdict(chart), "summary": chart.format_summary(),
                       "daily_available": daily is not None})
        if index > 1:
            continue
        for offset in range(30):
            target = date(2026, 10, 3) + timedelta(days=offset)
            for aspect in engine.ASPECT_TITLE:
                reading = engine._daily_from_chart(profile, chart, target, aspect)
                texts = {language: engine.render_daily_channel_text(localization.localize_daily(reading, language),
                                                                   reading_timezone="Asia/Seoul")
                         for language in ("ko", "en")}
                readings.append({"id": index, "date": str(target), "aspect": aspect,
                                 "reading": reading, "channel_texts": texts})
        for language in ("ko", "en"):
            for view in ("today", "tomorrow", "week"):
                payload = service.daily(dict(profile, language=language), view, now=NOW)
                assert payload["ok"]
                payloads.append({"id": index, "language": language, "view": view, "payload": payload})
        for scenario in ("general", "exam", "meeting"):
            payload = service.dated_reading(profile, {"date": "2026-11-24", "scenario": scenario}, now=NOW)
            assert payload["ok"]
            payloads.append({"id": index, "language": "ko", "view": "dday", "scenario": scenario, "payload": payload})
    output.write_text(json.dumps({"charts": charts, "readings": readings, "payloads": payloads}, ensure_ascii=False))


def facts(value):
    if isinstance(value, dict):
        return {key: facts(item) for key, item in value.items()
                if key not in {"lines", "disclaimer", "sections", "text", "warnings"}}
    if isinstance(value, list):
        return [facts(item) for item in value]
    return value


def compare(output):
    with tempfile.TemporaryDirectory(prefix="fortune-scope-compare-") as tmp:
        temporary = Path(tmp)
        baseline = temporary / "baseline"
        baseline.mkdir()
        archive = subprocess.run(["git", "archive", BASE, "plugins/hermes_ext/fortune_oracle", "web/fortune_web"],
                                 cwd=ROOT, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            files.extractall(baseline, filter="data")
        dependency = Path("plugins/hermes_ext/fortune_oracle/scripts/node_modules")
        assert (ROOT / dependency).is_dir(), "Install the locked Node dependencies first"
        (baseline / dependency).symlink_to(ROOT / dependency, target_is_directory=True)
        results = []
        for label, source in (("before", baseline), ("after", ROOT)):
            path = temporary / f"{label}.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker-root", str(source),
                            "--worker-output", str(path)], check=True, cwd=temporary)
            results.append(json.loads(path.read_text()))
        before, after = results

    assert len(before["charts"]) == len(after["charts"]) == 5
    scope = []
    for old, new in zip(before["charts"], after["charts"]):
        assert facts(old["chart"]) == facts(new["chart"]), ("chart", old["id"])
        assert old["daily_available"] == new["daily_available"]
        pillars = [key for key, value in new["chart"]["eight_char"].items() if value]
        if old["id"] == 0:
            assert old == new, "Known-time chart or summary changed"
        scope.append({"sample": old["id"], "computed_pillars": pillars,
                      "element_count": sum(new["chart"]["elements"].values()),
                      "dayun_present": bool(new["chart"]["dayun"]),
                      "daily_available": new["daily_available"],
                      "summary_before": old["summary"], "summary_after": new["summary"],
                      "warnings_before": old["chart"]["warnings"], "warnings_after": new["chart"]["warnings"]})
    assert [item["element_count"] for item in scope] == [8, 6, 6, 2, 4]
    assert [item["daily_available"] for item in scope] == [True, True, True, False, False]
    assert all(not item["dayun_present"] for item in scope[1:])
    assert len(before["readings"]) == len(after["readings"]) == 300
    changed_readings, channel_changes = 0, {"ko": 0, "en": 0}
    for old, new in zip(before["readings"], after["readings"]):
        assert facts(old["reading"]) == facts(new["reading"])
        assert old["reading"]["disclaimer"] == new["reading"]["disclaimer"]
        for key in ("theme", "action", "caution"):
            assert old["reading"]["sections"][key] == new["reading"]["sections"][key]
        if old["id"] == 0:
            assert old == new, "Known-time reading or channel changed"
        changed_readings += old["reading"] != new["reading"]
        for language in channel_changes:
            channel_changes[language] += old["channel_texts"][language] != new["channel_texts"][language]
    assert len(before["payloads"]) == len(after["payloads"]) == 18
    api = []
    for old, new in zip(before["payloads"], after["payloads"]):
        assert facts(old["payload"]) == facts(new["payload"])
        if old["id"] == 0:
            assert old == new, "Known-time API changed"
        api.append({**{key: value for key, value in old.items() if key != "payload"},
                    "text_changed": old["payload"]["text"] != new["payload"]["text"]})
    data = {"baseline": BASE, "synthetic_only": True, "after_code_sha256": {
                path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES},
            "chart_facts_equal": 5, "chart_cases": scope,
            "reading_facts_equal": 300, "changed_reading_copy": changed_readings,
            "unchanged_theme_action_caution_and_disclaimer": 300,
            "channel_text_comparisons": 600, "changed_channel_texts": channel_changes,
            "api_facts_equal": 18, "api_cases": api,
            "note": "Only display wording is excluded from facts; known-time results are compared in full. No human evaluation."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: data[key] for key in ("chart_facts_equal", "reading_facts_equal", "changed_reading_copy",
                                               "channel_text_comparisons", "changed_channel_texts", "api_facts_equal")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reviews/basic-reading-time-scope.json")
    parser.add_argument("--worker-root", type=Path)
    parser.add_argument("--worker-output", type=Path)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    for key in list(os.environ):
        if key.startswith(("FORTUNE_", "HERMES_SESSION_", "OPENAI_")) or any(word in key for word in ("TOKEN", "API_KEY", "SECRET")):
            os.environ.pop(key)
    with tempfile.TemporaryDirectory(prefix="fortune-scope-store-") as temporary:
        os.environ.update(HERMES_HOME=temporary, FORTUNE_ORACLE_STORE=str(Path(temporary) / "store.json"),
                          FORTUNE_DEEP_ANALYSIS="0", PYTHONDONTWRITEBYTECODE="1")
        if args.worker_root:
            worker(args.worker_root, args.worker_output)
        else:
            compare(args.output)


if __name__ == "__main__":
    main()
