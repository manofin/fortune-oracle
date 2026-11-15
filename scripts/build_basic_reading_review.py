#!/usr/bin/env python3
"""Build reproducible, synthetic before/after reading samples for human review.

Run from a checkout containing the public baseline commit and Node dependencies.
No customer data, store, model provider, or network is used.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BASE = "2f10b1ee25127f8930082b5b8afd9e34b7603eac"
ENGINE = "plugins/hermes_ext/fortune_oracle/daily_fortune_engine.py"
# Invented adult inputs, unrelated to customers or the operator.
PROFILES = [
    {"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male", "timezone": "Asia/Seoul"},
    {"birth_date": "1988-03-02", "birth_time_known": False, "gender": "unknown", "timezone": "Asia/Seoul"},
]
TARGETS = [date(2026, 10, 3), date(2026, 10, 4)]


def output_text(reading):
    return "\n".join([*reading["lines"], reading["disclaimer"]])


def build(output):
    sys.path.insert(0, str(ROOT / "plugins"))
    from hermes_ext.fortune_oracle import bazi_bridge, daily_fortune_engine as current

    # Fixed public baseline: never read an operator's private Git history.
    source = subprocess.run(
        ["git", "show", f"{BASE}:{ENGINE}"], cwd=ROOT,
        text=True, capture_output=True, check=True,
    ).stdout
    baseline = ModuleType("hermes_ext.fortune_oracle._review_baseline")
    exec(compile(source, f"public-baseline:{ENGINE}", "exec"), baseline.__dict__)
    samples, comparisons = [], 0
    for index, (profile, target) in enumerate(zip(PROFILES, TARGETS), 1):
        chart = bazi_bridge.calculate_bazi_from_profile(profile)
        if not chart.ok:
            raise RuntimeError(f"Synthetic sample {index}: chart unavailable")
        # Check every non-prose field, including all score components, over a month.
        for offset in range(30):
            day = target + timedelta(days=offset)
            for aspect in current.ASPECT_TITLE:
                before = baseline._daily_from_chart(profile, chart, day, aspect)
                after = current._daily_from_chart(profile, chart, day, aspect)
                facts = lambda value: {k: v for k, v in value.items() if k not in {"lines", "disclaimer"}}
                if facts(before) != facts(after):
                    raise AssertionError(f"Non-prose fields changed: sample {index}, {day}, {aspect}")
                comparisons += 1
        before = baseline._daily_from_chart(profile, chart, target, "종합")
        after = current._daily_from_chart(profile, chart, target, "종합")
        samples.append({"id": index, "synthetic_input": profile, "date": target.isoformat(),
                        "before": before, "after": after,
                        "channel_text": current.render_daily_channel_text(after)})

    # Controlled charts test all relation themes; they are not real birth charts.
    matrix = []
    for stem in "甲丙戊庚壬":
        chart = SimpleNamespace(ok=True, eight_char={"year": "庚午", "month": "戊寅", "day": stem + "子"},
                                elements={"목": 3, "화": 2, "토": 1, "금": 0, "수": 2},
                                dayun=None, time_basis={})
        reading = current._daily_from_chart(PROFILES[0], chart, TARGETS[0], "종합")
        matrix.append({"stem": stem, "relation": reading["relation"], "score": reading["score"],
                       "theme": reading["lines"][1], "action": reading["lines"][2],
                       "caution": reading["lines"][3]})

    output.mkdir(parents=True, exist_ok=True)
    data = {"baseline": BASE, "synthetic_only": True, "non_prose_comparisons": comparisons,
            "samples": samples, "relation_matrix": matrix}
    (output / "basic-reading-samples.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 기본 풀이 전후 샘플", "", "이 자료는 전부 가상 성인 입력입니다. 고민·외부 모델·고객 자료를 사용하지 않았습니다.", "",
             f"기준: 공개 `main` 커밋 `{BASE}`. 변경 후는 이 문서와 함께 검토하는 변경분입니다.", "",
             "재생성: `python scripts/build_basic_reading_review.py` (기본 Node 의존성 필요).",
             f"자동 비교: 가상 프로필 2개 × 30일 × 5영역 = **{comparisons}건**, 문구 외 모든 반환 필드 동일.", "",
             "점수 유지 확인은 문장의 효용이나 점술의 예측 타당성을 검증한 결과가 아닙니다.", ""]
    for sample in samples:
        lines.extend([f"## 가상 사례 {sample['id']}", "", f"입력: `{json.dumps(sample['synthetic_input'], ensure_ascii=False)}`",
                      f"풀이 날짜: {sample['date']}", ""])
        for key, label in (("before", "변경 전"), ("after", "변경 후")):
            lines.extend([f"### {label}", "", "```text", output_text(sample[key]), "```", ""])
        lines.extend(["### 메시지·직접 음성용 요약 (보완본)", "",
                      "웹의 상세 풀이와 별도 표시입니다. Telegram과 시간대를 지정한 음성 경로에는 풀이 시간대도 표시합니다.", "",
                      "```text", sample["channel_text"], "```", ""])
    lines.extend(["## 관계별 문구 확인용 합성 차트", "", "아래 차트는 분기를 확인하기 위한 가공 입력이며 실제 출생 계산 사례가 아닙니다.", "",
                  "| 관계 | 이날의 해석 | 해볼 일 | 주의할 점 |", "| --- | --- | --- | --- |"])
    lines.extend(f"| {r['relation']} | {r['theme']} | {r['action']} | {r['caution']} |" for r in matrix)
    lines.extend(["", "## 가림 평가 운영자용 대응표", "", "평가자에게는 아래 대응표와 전후 문서를 주지 않고 `basic-reading-blind.md`만 전달합니다.",
                  "첫 사례는 변경 후→전, 둘째는 전→후로 순서를 상쇄했습니다. 소규모 준비 자료이며 무작위 사용자 실험을 실행한 결과가 아닙니다.", "",
                  "| 평가 표기 | 대응 |", "| --- | --- |", "| 1-X | 사례 1 변경 후 |", "| 1-Y | 사례 1 변경 전 |",
                  "| 2-X | 사례 2 변경 전 |", "| 2-Y | 사례 2 변경 후 |", ""])
    (output / "basic-reading-samples.md").write_text("\n".join(lines))

    blind = ["# 기본 풀이 읽기 평가용", "", "가상 사례별 두 글을 읽고 각각 평가합니다. 버전의 출처나 변경 순서는 공개하지 않습니다.",
             "개인적으로 느껴지는 정도와 근거의 납득도는 별개로 점수를 매깁니다. 1=전혀 그렇지 않음, 5=매우 그러함.",
             "실제 자신에 대한 적중도를 묻는 평가가 아닙니다. 근거가 납득된다는 응답도 예측의 타당성을 입증하지 않습니다. 서로 상의하기 전에 응답을 기록합니다.", "",
             "각 글: 고민 입력 없이 읽을 가치가 있음 __/5 · 이해하기 쉬움 __/5 · 행동의 실행 가능성 __/5 · 개인적으로 느껴짐 __/5 · 근거 납득도 __/5",
             "해볼 일 하나를 본인 말로 적어주세요: ____________________",
             "단정으로 느껴진 문장 / 부담스러운 행동 / 실제로 도움이 된 문장: ____________________", "",
             "각 쌍: 더 유용한 글 X / Y / 차이 없음 / 판단 어려움 · 이유: ____________________", ""]
    for sample, order in zip(samples, [("after", "before"), ("before", "after")]):
        for label, key in zip("XY", order):
            blind.extend([f"## {sample['id']}-{label}", "", "```text", output_text(sample[key]), "```", ""])
            blind.extend(["읽을 가치 __/5 · 이해하기 쉬움 __/5 · 행동 실행 가능성 __/5 · 개인적으로 느껴짐 __/5 · 근거 납득도 __/5",
                          "해볼 일 하나를 본인 말로: ____________________",
                          "도움이 된 문장 / 부담스럽거나 단정적인 문장: ____________________", ""])
    (output / "basic-reading-blind.md").write_text("\n".join(blind))
    print(f"Wrote 2 synthetic comparisons and 5 relation themes; {comparisons} non-prose comparisons passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reviews")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="fortune-reading-samples-") as temporary:
        for key in list(os.environ):
            if key.startswith(("FORTUNE_", "HERMES_SESSION_", "OPENAI_")) or any(
                word in key for word in ("TOKEN", "API_KEY", "SECRET")
            ):
                os.environ.pop(key)
        os.environ.update(HERMES_HOME=temporary, FORTUNE_ORACLE_STORE=str(Path(temporary) / "store.json"),
                          FORTUNE_DEEP_ANALYSIS="0", PYTHONDONTWRITEBYTECODE="1")
        build(args.output)


if __name__ == "__main__":
    main()
