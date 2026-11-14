#!/usr/bin/env python3
"""Fortune Oracle — Yongshen Johu (調候法) Wrapper (Gate 3.3).

한난조습(寒暖燥濕) 기준 조후 용신 별도 계산.
기존 yongshen.py의 seasonal boost (강도 점수 가중치)와 완전히 구분.
억부법 결과와 병렬 제시 (덮어쓰기 금지).

신규 파일: wrapper 계층 전용.
기존 calculate_yongshen, calculate_strength_score, seasonal boost 로직 절대 수정/재사용 금지.

조후 용신은 "계절 기후 균형" 관점에서 별도 후보를 산출한다.
억부(강약)와 함께 제시하여 사용자가 두 관점을 비교할 수 있게 한다.

금지:
- yongshen.py 함수/로직 수정 또는 직접 호출 (상수 import만 허용)
- 기존 Eopbu / YongshenResult 출력 변경
- 용신 단정, 건강/투자 지시
- raw repr 노출
- 외부 API

이 결과는 rule-based 참고이며, 기존 용신과 병렬로만 사용하십시오.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .yongshen import (
    _MONTH_BRANCH_SEASON,
    _SEASON_ELEMENT,
)

# ---------------------------------------------------------------------------#
# 한난조습(寒暖燥濕) 조후 매핑 (전통 기준 단순화 + 명확 구분)
# ---------------------------------------------------------------------------#

# 계절 → 조후 필요 기운 (한난조습 기준)
# 겨울(寒): 따뜻함 필요 → 火 위주
# 여름(熱): 시원함 필요 → 水 위주
# 봄(溫): 성장기, 습기 보충 → 水
# 가을(燥): 건조, 윤택 필요 → 水/木
_SEASON_JOHU: Dict[str, List[str]] = {
    "겨울": ["화", "목"],   # 寒 → 온기
    "여름": ["수", "금"],   # 熱 → 냉기
    "봄": ["수"],           # 온화하나 성장에 수분
    "가을": ["수", "목"],   # 燥 → 윤택
}

# 월지 → 더 세밀한 조후 힌트 (지장간 영향 최소 반영)
_MONTH_JOHU_HINT: Dict[str, str] = {
    "子": "한랭 극심 → 강한 온기 필요",
    "丑": "한기 + 토 → 온기 + 약간의 윤택",
    "寅": "초봄 → 성장 촉진을 위한 수분",
    "卯": "봄 → 수분 보충",
    "辰": "늦봄 토 → 습기 조절",
    "巳": "초여름 열 → 냉기",
    "午": "한여름 극열 → 강한 냉기",
    "未": "늦여름 → 냉기 + 윤택",
    "申": "가을 건조 시작 → 윤택",
    "酉": "가을 건조 → 윤택",
    "戌": "늦가을 토 → 온기 보완",
    "亥": "초겨울 한기 → 온기",
}

@dataclass
class JohuAnalysis:
    ok: bool = False
    month_branch: str = ""
    season: str = ""
    johu_favorable: List[str] = field(default_factory=list)
    johu_reasoning: List[str] = field(default_factory=list)
    confidence_label: str = "rule_based_low"
    disclaimer: str = "이 조후법 분석은 한난조습 기준 rule-based 참고이며, 억부법과 별개로 병렬 제시됩니다. 기존 용신 결과를 대체하지 않습니다."
    warnings: List[str] = field(default_factory=list)


def _get_season_and_hint(month_gz: str) -> tuple[str, str, str]:
    """월지에서 계절 + 조후 힌트 추출 (기존 seasonal boost와 무관한 별도 로직)."""
    if len(month_gz) < 2:
        return "", "", ""
    branch = month_gz[1]
    season = _MONTH_BRANCH_SEASON.get(branch, "")
    hint = _MONTH_JOHU_HINT.get(branch, "")
    return branch, season, hint


def build_johu_analysis(eight_char: Dict[str, str]) -> JohuAnalysis:
    """eight_char → JohuAnalysis (한난조습 조후 용신, 억부와 완전 병렬).

    기존 yongshen.py의 calculate_strength_score seasonal boost와
    전혀 다른 목적(기후 균형)으로 별도 계산.
    """
    if not eight_char:
        return JohuAnalysis(ok=False, warnings=["eight_char 없음"])

    month_gz = eight_char.get("month", "")
    branch, season, hint = _get_season_and_hint(month_gz)

    if not season:
        return JohuAnalysis(
            ok=True,
            warnings=["월지 정보 부족 — 조후 판단 보류"],
            confidence_label="rule_based_low",
        )

    # 조후 용신 후보 (한난조습 기준)
    favorable = _SEASON_JOHU.get(season, [])

    reasoning = [
        f"조후법: {season} ({branch}월) — {hint or '계절 기후 균형'}",
        f"한난조습 필요: {', '.join(favorable)}",
    ]

    # 간단한 confidence (계절이 명확할수록 medium)
    conf = "rule_based_medium" if season in ("겨울", "여름") else "rule_based_low"

    return JohuAnalysis(
        ok=True,
        month_branch=branch,
        season=season,
        johu_favorable=favorable,
        johu_reasoning=reasoning,
        confidence_label=conf,
    )


def build_johu_note(analysis: JohuAnalysis, max_lines: int = 4) -> str:
    """JohuAnalysis → compact note (억부와 병렬용, 기존 노트 영향 없음)."""
    if not analysis.ok or not analysis.season:
        return ""

    lines: List[str] = []
    lines.append(f"조후법: {analysis.season} ({analysis.month_branch}월) — {analysis.confidence_label}")

    for elem in analysis.johu_favorable[:2]:
        lines.append(f"  {elem} 기운으로 한난조습 균형")

    lines.append(analysis.disclaimer)

    body = "\n".join(f"- {l}" for l in lines[:max_lines])
    return f"\n[조후법 참고]\n{body}"


def build_show_profile_johu_note(eight_char: Optional[Dict[str, str]], max_lines: int = 2) -> str:
    """fail-open wrapper."""
    if not eight_char:
        return ""
    try:
        analysis = build_johu_analysis(eight_char)
        return build_johu_note(analysis, max_lines=max_lines)
    except Exception:
        return ""
