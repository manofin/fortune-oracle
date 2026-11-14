"""Fortune Oracle — Bazi Template Analyzer (Phase 4)

deterministic template 기반 해석. AI/LLM을 호출하지 않는다.
외부 네트워크 금지.

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .bazi_bridge import BaziResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 오행 특성 템플릿
# ---------------------------------------------------------------------------

_ELEMENT_TRAITS = {
    "목(木)": {
        "quality": "성장·창조·추진력",
        "strength": "새로운 시작, 아이디어 발굴, 지속적 성장 지향",
        "caution": "과도한 확장이나 급진적 변화에 주의",
    },
    "화(火)": {
        "quality": "열정·표현·사교성",
        "strength": "감정 표현, 대인 관계, 창의적 열정",
        "caution": "충동적 결정이나 감정 소모에 주의",
    },
    "토(土)": {
        "quality": "안정·신뢰·조화",
        "strength": "중심 잡기, 신뢰 구축, 실용적 문제 해결",
        "caution": "과도한 안정 추구나 변화 저항에 주의",
    },
    "금(金)": {
        "quality": "결단·원칙·명확성",
        "strength": "원칙 준수, 목표 달성, 명확한 판단",
        "caution": "지나친 완벽주의나 경직성에 주의",
    },
    "수(水)": {
        "quality": "지혜·유연성·깊이",
        "strength": "상황 적응, 깊은 사고, 통찰력",
        "caution": "과도한 내성이나 우유부단함에 주의",
    },
}

_ZODIAC_TRAITS = {
    "쥐띠": "영리하고 적응력이 뛰어난 기질",
    "소띠": "성실하고 꾸준한 기질",
    "호랑이띠": "용감하고 카리스마 있는 기질",
    "토끼띠": "온화하고 섬세한 기질",
    "용띠": "활력 넘치고 이상적인 기질",
    "뱀띠": "직관적이고 신중한 기질",
    "말띠": "자유롭고 활동적인 기질",
    "양띠": "예술적이고 부드러운 기질",
    "원숭이띠": "재치 있고 다재다능한 기질",
    "닭띠": "꼼꼼하고 솔직한 기질",
    "개띠": "충실하고 정직한 기질",
    "돼지띠": "풍요롭고 너그러운 기질",
}

_DISCLAIMER = "이 분석은 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다."

_REFLECTION_QUESTIONS = [
    "나의 강점을 최근 어떤 방식으로 활용하고 있나요?",
    "주의할 흐름 중 현재 나에게 해당하는 것이 있다면 어떻게 대응하고 싶나요?",
    "오늘 하루, 어떤 에너지를 가장 잘 쓰고 싶나요?",
]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class TemplateSection:
    title: str
    summary: str
    confidence: str = "template"
    disclaimer: str = ""


@dataclass
class TemplateAnalysisResult:
    ok: bool
    sections: List[TemplateSection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    message: str = ""

    def to_telegram_summary(self, max_chars: int = 800) -> str:
        """Telegram용 요약 텍스트. max_chars 이하로 제한."""
        if not self.ok or not self.sections:
            return f"⚠️ 템플릿 분석 불가: {self.message}"
        lines: List[str] = []
        for sec in self.sections:
            if sec.title == "자기성찰 질문":
                continue  # 요약에서는 생략
            lines.append(f"**{sec.title}**\n{sec.summary}")
        lines.append(f"\n_{_DISCLAIMER}_")
        text = "\n\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars - 3] + "..."
        return text


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

def analyze_bazi_template(
    bazi_result: BaziResult,
    *,
    kline_summary: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> TemplateAnalysisResult:
    """BaziResult를 받아 deterministic template 분석 결과를 반환.

    Args:
        bazi_result: bazi_bridge.calculate_bazi()의 반환값.
        kline_summary: 운세 K선 요약 텍스트 (선택).
        profile: 사용자 프로필 dict (선택 — 민감 필드 제외).

    Returns:
        TemplateAnalysisResult. ok=False면 fallback 사용.
    """
    warnings: List[str] = []

    # bazi_result 실패 시 fallback
    if not bazi_result.ok:
        return TemplateAnalysisResult(
            ok=False,
            error_code=bazi_result.error_code,
            message=f"팔자 계산 데이터가 없어 기본 분석을 사용합니다. ({bazi_result.message})",
            sections=_fallback_sections(),
            warnings=[bazi_result.message],
        )

    sections: List[TemplateSection] = []

    # --- 1. 기본 기질 ---
    zodiac_trait = _ZODIAC_TRAITS.get(bazi_result.zodiac, "독특한 기질")
    eight_char = bazi_result.eight_char or {}
    pillar_str = (
        f"년{eight_char.get('year','')} 월{eight_char.get('month','')} "
        f"일{eight_char.get('day','')} 시{eight_char.get('time','')}"
    )
    sections.append(TemplateSection(
        title="기본 기질",
        summary=(
            f"{bazi_result.zodiac}: {zodiac_trait}.\n"
            f"팔자 구성: {pillar_str}"
        ),
    ))

    # --- 2. 강점 (오행 상위 2개 기준) ---
    elements = bazi_result.elements or {}
    if elements:
        top_elements = sorted(elements.items(), key=lambda x: -x[1])[:2]
        strength_parts = []
        for elem_kr, count in top_elements:
            trait = _ELEMENT_TRAITS.get(elem_kr, {})
            if trait:
                strength_parts.append(f"{elem_kr}({count}개): {trait['strength']}")
        if strength_parts:
            sections.append(TemplateSection(
                title="강점",
                summary="\n".join(strength_parts),
            ))
    else:
        warnings.append("오행 데이터 없음 — 강점 섹션 생략")

    # --- 3. 주의할 흐름 (오행 하위 또는 부재 기준) ---
    if elements:
        all_elem_keys = list(_ELEMENT_TRAITS.keys())
        missing_or_low = [k for k in all_elem_keys if elements.get(k, 0) == 0]
        if missing_or_low:
            caution_parts = []
            for elem_kr in missing_or_low[:2]:
                trait = _ELEMENT_TRAITS.get(elem_kr, {})
                if trait:
                    caution_parts.append(f"{elem_kr}: {trait['caution']}")
            if caution_parts:
                sections.append(TemplateSection(
                    title="주의할 흐름",
                    summary="\n".join(caution_parts),
                ))
        else:
            # 균형 잡힌 경우
            bottom = sorted(elements.items(), key=lambda x: x[1])[:1]
            caution_parts = []
            for elem_kr, _ in bottom:
                trait = _ELEMENT_TRAITS.get(elem_kr, {})
                if trait:
                    caution_parts.append(trait["caution"])
            sections.append(TemplateSection(
                title="주의할 흐름",
                summary="\n".join(caution_parts) if caution_parts else "전체적으로 균형 잡힌 오행 구성입니다.",
            ))

    # --- 4. 이번 달 운세 K선 연결 (kline_summary 있을 때만) ---
    if kline_summary:
        sections.append(TemplateSection(
            title="이번 달 운세 K선과의 연결",
            summary=f"팔자 기질과 이번 달 운세를 함께 살펴보세요:\n{kline_summary[:200]}",
        ))

    # --- 5. 올해 흐름 (간단한 오행 순환 기반) ---
    try:
        import datetime
        current_year = datetime.date.today().year
        # 년도 오행 간단 근사 (60갑자 주기)
        year_gan_idx = (current_year - 4) % 10
        year_gan = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"][year_gan_idx]
        year_elem_map = {
            "甲":"목(木)","乙":"목(木)","丙":"화(火)","丁":"화(火)",
            "戊":"토(土)","己":"토(土)","庚":"금(金)","辛":"금(金)",
            "壬":"수(水)","癸":"수(水)",
        }
        year_elem = year_elem_map.get(year_gan, "")
        if year_elem:
            trait = _ELEMENT_TRAITS.get(year_elem, {})
            year_quality = trait.get("quality", "")
            sections.append(TemplateSection(
                title="올해 흐름",
                summary=f"{current_year}년({year_gan}년)은 {year_elem} 기운의 해입니다. 핵심 키워드: {year_quality}.",
            ))
    except Exception as e:
        warnings.append(f"올해 흐름 계산 실패: {e}")

    # --- 6. 자기성찰 질문 ---
    sections.append(TemplateSection(
        title="자기성찰 질문",
        summary="\n".join(f"• {q}" for q in _REFLECTION_QUESTIONS),
    ))

    # --- 7. 고지 ---
    sections.append(TemplateSection(
        title="안내",
        summary=_DISCLAIMER,
        confidence="disclaimer",
        disclaimer=_DISCLAIMER,
    ))

    return TemplateAnalysisResult(ok=True, sections=sections, warnings=warnings)


def _fallback_sections() -> List[TemplateSection]:
    """bazi 계산 실패 시 기본 섹션."""
    return [
        TemplateSection(
            title="기본 안내",
            summary="사주 정보를 등록하시면 더 상세한 분석을 제공해 드릴 수 있습니다.",
        ),
        TemplateSection(
            title="자기성찰 질문",
            summary="\n".join(f"• {q}" for q in _REFLECTION_QUESTIONS),
        ),
        TemplateSection(
            title="안내",
            summary=_DISCLAIMER,
            confidence="disclaimer",
            disclaimer=_DISCLAIMER,
        ),
    ]
