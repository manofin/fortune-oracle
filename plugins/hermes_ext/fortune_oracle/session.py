#!/usr/bin/env python3
"""Stage-gated precise fortune analysis sessions."""

from __future__ import annotations

from dataclasses import dataclass

CONTINUE_WORDS = {"다음", "예"}


@dataclass
class StageResult:
    stage: int
    text: str
    waiting_for_confirmation: bool = True
    final: bool = False


class AnalysisSession:
    """One-stage-at-a-time precise analysis state machine.

    The session advances only when the user says exactly "다음" or "예" after
    whitespace trimming. Any other input repeats the confirmation gate.
    """

    def __init__(self) -> None:
        self.kind = "precise"
        self.stage = 0
        self.max_stage = 5

    def start(self, kind: str = "precise") -> StageResult:
        self.kind = kind
        self.stage = 1
        return self._render()

    def next(self, user_text: str) -> StageResult:
        if user_text.strip() not in CONTINUE_WORDS:
            return StageResult(
                self.stage or 1,
                "정밀 분석은 한 단계씩만 진행합니다. 다음 단계를 진행할까요?",
                True,
                False,
            )
        if self.stage <= 0:
            self.stage = 1
        else:
            self.stage = min(self.stage + 1, self.max_stage)
        return self._render()

    def _render(self) -> StageResult:
        titles = {
            1: "STAGE 1 태허: 전체 기운 요약",
            2: "STAGE 2 관음: 관계와 마음의 흐름",
            3: "STAGE 3 티코: 실행과 일정 조정",
            4: "STAGE 4 자허: 통합 조언과 주의점",
            5: "FINAL 태허: 정밀 분석 요약",
        }
        body = [
            titles[self.stage],
            "출생정보 원문은 반복 출력하지 않고 해석에 필요한 맥락만 사용합니다.",
            "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
        ]
        final = self.stage >= self.max_stage
        if final:
            body.append("정밀 분석을 종료합니다.")
            return StageResult(self.stage, "\n".join(body), False, True)
        body.append("다음 단계를 진행할까요?")
        return StageResult(self.stage, "\n".join(body), True, False)
