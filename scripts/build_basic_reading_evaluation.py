#!/usr/bin/env python3
"""Generate separate participant handouts and an operator-only manifest.

Reads synthetic review samples already generated from this checkout. Does not
recruit participants, collect responses or approve the start of an evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = "basic-reading-evaluation-v2-draft"
PRODUCT_CANDIDATE = "78893ff877b8e2c5ed480e43c3fb40d1a411ebe8"
UI_CONTEXT = "이 화면은 가상 인물의 2026년 11월 24일 풀이에서 ‘기대되는 만남’을 선택한 결과입니다."
SOURCES = ["plugins/hermes_ext/fortune_oracle/" + path for path in (
    "daily_fortune_engine.py", "bazi_bridge.py", "localization.py", "scripts/life_kline_bazi_bridge.mjs")]
UI_SOURCES = ["web/fortune_web/static/" + path for path in ("index.html", "app.js", "style.css")]
OPERATOR = "docs/reviews/basic-reading-evaluation-operator.md"
MAPPING = {"a": (0, "after", "1-X"), "b": (0, "before", "1-Y"),
           "c": (1, "before", "2-X"), "d": (1, "after", "2-Y")}
CONDITIONS = {
    "C1": [(1, ["a", "b"]), (2, ["d", "c"])],
    "C2": [(1, ["b", "a"]), (2, ["c", "d"])],
    "C3": [(2, ["d", "c"]), (1, ["a", "b"])],
    "C4": [(2, ["c", "d"]), (1, ["b", "a"])],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reading_text(reading):
    return "\n".join([*reading["lines"], reading["disclaimer"]])


def build(reviews):
    source_file = reviews / "basic-reading-samples.json"
    source = json.loads(source_file.read_text())
    expected = {path: digest(ROOT / path) for path in SOURCES}
    product_sources = {**expected, **{path: digest(ROOT / path) for path in UI_SOURCES},
                       "web/fortune_web/service.py": digest(ROOT / "web/fortune_web/service.py")}
    for path, current_hash in product_sources.items():
        frozen = subprocess.run(["git", "show", f"{PRODUCT_CANDIDATE}:{path}"], cwd=ROOT,
                                capture_output=True, check=True).stdout
        assert hashlib.sha256(frozen).hexdigest() == current_hash, "Product differs from the frozen candidate; review and pin a new version first"
    assert UI_CONTEXT in (ROOT / OPERATOR).read_text(), "Operator and participant context wording must match"
    assert source["source_sha256"] == expected, "Regenerate basic-reading-samples before preparing handouts"
    assert source["synthetic_only"] is True and len(source["samples"]) == 2
    output = reviews / "evaluation"
    participant = output / "participant"
    participant.mkdir(parents=True, exist_ok=True)
    documents = {
        "instructions.md": """# 읽기 평가 안내

가상 사례 두 개에 대해 글을 두 편씩 읽습니다. 자신의 운세나 적중 여부를 평가하는 과제가 아닙니다. 실제 출생정보나 개인적인 고민을 적을 필요는 없습니다.

운영자가 제시하는 순서대로 한 편을 읽고 개별 응답을 마친 다음, 다음 글을 읽어 주세요. 각 사례의 두 글을 모두 평가한 뒤 비교 의견을 받습니다. 답하는 동안 해당 원문을 다시 볼 수 있습니다. 다른 참가자와 상의하기 전에 자신의 답을 적어 주세요.

문구 평가가 끝나면 화면을 만들 때 선택한 조건을 안내받고, 별도 화면 자료에서 내용을 찾는 과제를 진행합니다. 마지막에 추가 확인 자료를 보여드립니다. 정답을 추측하기보다 읽고 이해한 그대로 답해 주세요.

1~5점 척도는 1 전혀 그렇지 않음, 2 그렇지 않음, 3 보통, 4 그렇다, 5 매우 그렇다입니다. 판단하기 어려우면 숫자를 고르지 말고 ‘판단 어려움’이라고 적어 주세요.
""",
        "response-sheet.md": """# 글 한 편의 응답

참가자 번호: ____ / 사례 번호: ____ / 첫 번째 글·두 번째 글: ____

각 항목을 1~5점으로 평가해 주세요. 판단하기 어려우면 ‘판단 어려움’이라고 적어 주세요.

| 항목 | 응답 |
| --- | --- |
| 고민을 입력하지 않아도 읽을 가치가 있다 | ____ |
| 이해하기 쉽다 | ____ |
| 제안된 행동을 실행할 수 있다 | ____ |
| 개인적으로 느껴진다 | ____ |
| 해석의 근거가 납득된다 | ____ |

1. 이 풀이를 읽고 무엇을 해볼 수 있나요? 제안된 행동을 찾지 못했다면 ‘없음’이라고 적어 주세요.

   답: ____________________

2. 어떤 정보가 어떤 해석으로 이어졌다고 이해했나요? 연결을 찾지 못했다면 그대로 적어 주세요.

   답: ____________________

3. 도움이 되거나 되지 않은 부분과 그 이유를 적어 주세요. 없다면 ‘없음’이라고 적어 주세요.

   답: ____________________

4. 부담스럽거나 단정적으로 느껴진 문장이 있다면 적어 주세요. 없다면 ‘없음’이라고 적어 주세요.

   답: ____________________
""",
        "comparison-sheet.md": """# 두 글을 모두 평가한 뒤의 응답

참가자 번호: ____ / 사례 번호: ____

더 유용하게 읽힌 글: 첫 번째 글 / 두 번째 글 / 차이 없음 / 판단 어려움

이유: ____________________
""",
        "observation-sheet.md": """# 화면 읽기와 추가 확인

참가자 번호: ____

운영자가 ‘화면의 선택 조건’ 안내와 화면을 보여드린 뒤 진행합니다.

1. 화면에서 해볼 일 하나와 주의할 점을 찾아 본인 말로 설명해 주세요.

   답: ____________________

2. 해석의 근거와 한계를 찾아 설명해 주세요. 찾지 못했다면 그대로 말씀해 주세요.

   답: ____________________

화면 과제를 마친 뒤 별도로 묻습니다.

3. 이 화면의 기본 해석과 행동·주의는 각각 어떤 정보에 바탕을 둔다고 이해했나요?

   답: ____________________

운영자가 추가 확인 자료를 보여드린 뒤 묻습니다.

4. 이 글에서는 출생시각을 사용했나요? 어떤 항목이 계산됐고, 어떤 항목이 제외됐다고 이해했나요? 판단하기 어렵다면 그대로 적어 주세요.

   답: ____________________
""",
    }
    documents["ui-context.md"] = f"# 화면의 선택 조건\n\n{UI_CONTEXT}\n"
    for letter, (index, version, internal) in MAPPING.items():
        text = reading_text(source["samples"][index][version])
        documents[f"reading-{letter}.md"] = f"# 읽기 자료\n\n```text\n{text}\n```\n"
    text = reading_text(source["samples"][1]["after"])
    documents["scope-check.md"] = f"# 추가 확인 자료\n\n```text\n{text}\n```\n"
    for name, text in documents.items():
        (participant / name).write_text(text.rstrip() + "\n")

    captures = ["ui-collapsed.png", "ui-expanded.png"]
    for name in captures:
        assert (participant / name).is_file(), "Run the current browser check and copy the UI captures first"
    browser_file = reviews / "basic-reading-evaluation-browser.json"
    browser = json.loads(browser_file.read_text())
    assert all(digest(ROOT / path) == checksum for path, checksum in browser["source_sha256"].items()), "UI captures are from another source revision"
    files = {f"participant/{name}": digest(participant / name) for name in sorted([*documents, *captures])}
    materials_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    mappings = {f"participant/reading-{letter}.md": {"case": index + 1, "version": version, "internal_id": internal}
                for letter, (index, version, internal) in MAPPING.items()}
    assignments = [{"participant_id": f"P{index + 1:02}", "condition": f"C{index % 4 + 1}",
                    "sequence": [{"case": case, "files": [f"participant/reading-{letter}.md" for letter in letters]}
                                 for case, letters in CONDITIONS[f"C{index % 4 + 1}"]]}
                   for index in range(5)]
    manifest = {"audience": "operator_only_do_not_give_to_participants", "procedure_revision": REVISION,
                "collection_status": "not_started", "responses_received": 0, "material_approval": "pending",
                "candidate_commit": PRODUCT_CANDIDATE,
                "candidate_commit_rule": "Keep this product candidate fixed. Record the separate reviewed materials commit, procedure revision and manifest hash for every session; a materials-only PR head does not replace the product candidate.",
                "candidate_source_sha256": product_sources,
                "source_samples_sha256": digest(source_file), "operator_protocol_sha256": digest(ROOT / OPERATOR),
                "materials_id": materials_id, "participant_file_sha256": files,
                "mapping": mappings, "assignments": assignments,
                "extra_participant_rule": "Repeat C1,C2,C3,C4 in participant ID order; never reassign using observed scores.",
                "ui_fixture": {"synthetic_input": source["samples"][0]["synthetic_input"],
                               "date": "2026-11-24", "scenario": "meeting", "initial_details_open": False,
                               "scenario_label": "기대되는 만남",
                               "context_file": "participant/ui-context.md",
                               "context_text": UI_CONTEXT,
                               "context_timing": "Once, after text responses are locked and before presenting the initial UI screen; identical in every display mode",
                               "context_interpretation_limit": "Measures source understanding with input context supplied, not recognition of the selected situation from the cropped card alone",
                               "collapsed_capture": "participant/ui-collapsed.png",
                               "expanded_capture": "participant/ui-expanded.png",
                               "capture_viewport": {"width": 390, "height": 844},
                               "browser_record_sha256": digest(browser_file),
                               "require_same_candidate_as_text": True,
                               "capture_mode_is_not_interactive_or_physical_device_validation": True},
                "scope_check": {"file": "participant/scope-check.md", "case": 2, "version": "after",
                                "present_only_after_primary_responses_are_locked": True}}
    (output / "operator-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    # Verify one-to-one source preservation and deterministic order before publishing.
    assert len(set(files.values())) == len(files), "Unexpected duplicate participant files"
    for letter, (index, version, _) in MAPPING.items():
        assert reading_text(source["samples"][index][version]) in (participant / f"reading-{letter}.md").read_text()
    for assignment in assignments:
        assert sorted(path for case in assignment["sequence"] for path in case["files"]) == sorted(mappings)
    print(f"Prepared {len(documents)} participant documents and {len(captures)} UI captures, 5 assignments and operator-only manifest. Collection remains blocked pending review.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, default=ROOT / "docs/reviews")
    build(parser.parse_args().reviews)
