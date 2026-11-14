"""Fortune Oracle — Astro Method Card (Phase 38B).

점성술 계산 결과의 표준화 wrapper.
method, status, facts, interpretation, confidence, blockers, warnings, disclaimer을 포함.

기존 QimenResult 패턴과 동일한 fail-open 구조.

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

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AstroMethodCard:
    """점성술 계산의 표준 method card.

    Western/Vedic 모두 동일한 구조.
    backend가 없거나 데이터가 부족해도 ok=False로 반환되며 plugin 전체를 중단시키지 않음.
    """
    method: str = ""                     # "western" | "vedic"
    status: str = STATUS_BLOCKED         # runnable | partial | blocked
    facts: Dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    confidence: float = 0.0
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
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
    ) -> "AstroMethodCard":
        """blocked 상태의 method card 생성."""
        return cls(
            method=method,
            status=STATUS_BLOCKED,
            blockers=blockers or [f"{error_code}: {message}"],
            confidence=0.0,
        )

    @classmethod
    def partial(
        cls,
        method: str,
        facts: Dict[str, Any],
        interpretation: str,
        warnings: Optional[List[str]] = None,
        confidence: float = 0.5,
    ) -> "AstroMethodCard":
        """partial 상태의 method card 생성."""
        return cls(
            method=method,
            status=STATUS_PARTIAL,
            facts=facts,
            interpretation=interpretation,
            confidence=confidence,
            warnings=warnings or [],
        )

    @classmethod
    def runnable(
        cls,
        method: str,
        facts: Dict[str, Any],
        interpretation: str,
        confidence: float = 0.8,
        warnings: Optional[List[str]] = None,
    ) -> "AstroMethodCard":
        """runnable 상태의 method card 생성."""
        return cls(
            method=method,
            status=STATUS_RUNNABLE,
            facts=facts,
            interpretation=interpretation,
            confidence=confidence,
            warnings=warnings or [],
        )

    def is_ok(self) -> bool:
        """runnable 또는 partial이면 True."""
        return self.status in (STATUS_RUNNABLE, STATUS_PARTIAL)

    def add_warning(self, msg: str) -> None:
        """경고 추가."""
        if msg and msg not in self.warnings:
            self.warnings.append(msg)
