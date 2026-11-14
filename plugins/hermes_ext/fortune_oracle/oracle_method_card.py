#!/usr/bin/env python3
"""Fortune Oracle — Oracle Method Card (Phase 37C).

모든 method(Bazi, Western, Vedic, Ziwei, Qimen)의 표준 상태 카드.
runnable / partial / blocked 삼분법.

기존 AstroMethodCard와의 관계:
- AstroMethodCard는 Phase 38 Western/Vedic 전용.
- OracleMethodCard는 Phase 37 통합 렌더링용.
- 기존 AstroMethodCard를 OracleMethodCard로 변환 가능.

금지:
- raw dataclass repr 노출
- 외부 API 호출
- AI/LLM 호출

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "이 결과는 자기성찰과 선택지 점검용 참고이며 확정적 판단이 아닙니다. "
    "의학, 투자, 법률 결정을 지시하지 않습니다."
)

# status 값
STATUS_RUNNABLE = "runnable"
STATUS_PARTIAL = "partial"
STATUS_BLOCKED = "blocked"

# error code
ERR_DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
ERR_CALCULATION_FAILED = "CALCULATION_FAILED"
ERR_INSUFFICIENT_BIRTH_DATA = "INSUFFICIENT_BIRTH_DATA"

# method별 한국어 라벨
METHOD_LABEL_KO: Dict[str, str] = {
    "bazi": "팔자",
    "western": "서양 점성술",
    "vedic": "베딕 점성술",
    "ziwei": "자미두수",
    "qimen": "기문둔갑",
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OracleMethodCard:
    """통합 method card.

    모든 method가 동일한 구조를 공유.
    backend가 없거나 데이터가 부족해도 blocked 상태로 반환되며
    plugin 전체를 중단시키지 않음.
    """
    method: str = ""
    label_ko: str = ""
    status: str = STATUS_BLOCKED
    facts: Dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    confidence: float = 0.0
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    precision_notes: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    backend: str = ""
    calculation_mode: str = "unknown"  # computed / approximate / unknown

    @classmethod
    def blocked(
        cls,
        method: str,
        error_code: str,
        message: str,
        blockers: Optional[List[str]] = None,
    ) -> "OracleMethodCard":
        """blocked 상태의 method card 생성."""
        label = METHOD_LABEL_KO.get(method, method)
        return cls(
            method=method,
            label_ko=label,
            status=STATUS_BLOCKED,
            blockers=blockers or [f"{error_code}: {message}"],
            confidence=0.0,
        )

    @classmethod
    def partial(
        cls,
        method: str,
        facts: Dict[str, Any],
        interpretation: str = "",
        warnings: Optional[List[str]] = None,
        precision_notes: Optional[List[str]] = None,
        confidence: float = 0.5,
    ) -> "OracleMethodCard":
        """partial 상태의 method card 생성."""
        label = METHOD_LABEL_KO.get(method, method)
        return cls(
            method=method,
            label_ko=label,
            status=STATUS_PARTIAL,
            facts=facts,
            interpretation=interpretation,
            confidence=confidence,
            warnings=warnings or [],
            precision_notes=precision_notes or [],
        )

    @classmethod
    def runnable(
        cls,
        method: str,
        facts: Dict[str, Any],
        interpretation: str = "",
        confidence: float = 0.8,
        warnings: Optional[List[str]] = None,
        precision_notes: Optional[List[str]] = None,
    ) -> "OracleMethodCard":
        """runnable 상태의 method card 생성."""
        label = METHOD_LABEL_KO.get(method, method)
        return cls(
            method=method,
            label_ko=label,
            status=STATUS_RUNNABLE,
            facts=facts,
            interpretation=interpretation,
            confidence=confidence,
            warnings=warnings or [],
            precision_notes=precision_notes or [],
        )

    def is_ok(self) -> bool:
        """runnable 또는 partial이면 True."""
        return self.status in (STATUS_RUNNABLE, STATUS_PARTIAL)

    def add_warning(self, msg: str) -> None:
        """경고 추가."""
        if msg and msg not in self.warnings:
            self.warnings.append(msg)

    def add_evidence(self, msg: str) -> None:
        """근거 추가."""
        if msg and msg not in self.evidence:
            self.evidence.append(msg)

    def add_precision_note(self, msg: str) -> None:
        """정밀도 참고 추가."""
        if msg and msg not in self.precision_notes:
            self.precision_notes.append(msg)

    # ------------------------------------------------------------------
    # Formatting — compact Korean output
    # ------------------------------------------------------------------

    def format_card(self, max_facts: int = 5) -> str:
        """compact Korean card 포맷."""
        lines: List[str] = []
        label = self.label_ko or self.method

        status_icon = {
            STATUS_RUNNABLE: "✅",
            STATUS_PARTIAL: "⚠️",
            STATUS_BLOCKED: "❌",
        }.get(self.status, "❓")

        lines.append(f"{status_icon} {label} ({self.status})")

        if self.status == STATUS_BLOCKED:
            for b in self.blockers[:3]:
                lines.append(f"  차단: {b}")
            return "\n".join(lines)

        # facts (제한)
        for key, value in list(self.facts.items())[:max_facts]:
            if isinstance(value, list):
                lines.append(f"  {key}: {', '.join(str(v) for v in value[:3])}")
            else:
                lines.append(f"  {key}: {value}")

        if self.interpretation:
            lines.append(f"  해석: {self.interpretation[:120]}")

        if self.warnings:
            for w in self.warnings[:2]:
                lines.append(f"  ⚠ {w}")

        if self.precision_notes:
            for p in self.precision_notes[:2]:
                lines.append(f"  ℹ {p}")

        return "\n".join(lines)

    def format_blocked_summary(self) -> str:
        """blocked method의 요약 (renderer용)."""
        label = self.label_ko or self.method
        reasons = "; ".join(self.blockers[:2]) if self.blockers else "이유 미상"
        return f"{label}: blocked — {reasons}"

    # ------------------------------------------------------------------
    # Conversion from AstroMethodCard
    # ------------------------------------------------------------------

    @classmethod
    def from_astro_method_card(cls, card) -> "OracleMethodCard":
        """기존 AstroMethodCard를 OracleMethodCard로 변환."""
        label = METHOD_LABEL_KO.get(card.method, card.method)
        return cls(
            method=card.method,
            label_ko=label if label else card.method,
            status=card.status,
            facts=card.facts,
            interpretation=card.interpretation,
            confidence=card.confidence,
            blockers=card.blockers,
            warnings=card.warnings,
            disclaimer=card.disclaimer or DISCLAIMER,
            backend=getattr(card, "backend", ""),
            calculation_mode=getattr(card, "calculation_mode", "unknown"),
        )
