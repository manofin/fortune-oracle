#!/usr/bin/env python3
"""Fortune Oracle — Unified Oracle Renderer (Phase 37E).

Yuan-style final reading을 한국어 11-section 구조로 구현.
blocked method가 있어도 renderer가 죽지 않음.
모든 method가 blocked이면 "입력 부족 안내"를 출력.

기존 oracle_renderer.py의 render_oracle_reading() 함수를 유지 (backward compat).

Qimen은 question-time oracle이므로 birth-based /oracle에는 기본 포함하지 않음.

금지:
- dataclass repr 노출
- traceback 노출
- raw dict/list dump 노출
- provider internal source dump
- "반드시", "확실히", "투자해야 한다", "치료해야 한다" 등 확정 문구
- 결혼/이혼/질병/사망 단정
- 법률적 판단
- 의료/법률/투자 확정 조언

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .oracle_method_card import (
    DISCLAIMER,
    OracleMethodCard,
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_RUNNABLE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# sanitize guard
# ---------------------------------------------------------------------------

_RAW_FORBIDDEN_PATTERNS = [
    r"OracleMethodCard\(",
    r"AstroMethodCard\(",
    r"dataclass",
    r"default_factory",
    r"ok=True",
    r"ok=False",
    r"Traceback",
    r"File\s+['\"][^\']+['\"]\s*, line \d+",
    r"^\s*<[^>]+>$",  # <class '...'>
]

_RAW_FORBIDDEN_COMPILED = [re.compile(p) for p in _RAW_FORBIDDEN_PATTERNS]

# 확정 예언 금지 패턴
_DETERMINISTIC_PATTERNS = [
    r"반드시",
    r"확실히",
    r"투자해야 한다",
    r"치료해야 한다",
    r"결혼해야",
    r"이혼해야",
    r"사망",
    r"법적으로",
]

_DETERMINISTIC_COMPILED = [re.compile(p) for p in _DETERMINISTIC_PATTERNS]

def _is_raw_dump(text: str) -> bool:
    """raw dump 감지."""
    if not text:
        return False
    if any(p.search(text) for p in _RAW_FORBIDDEN_COMPILED):
        return True
    stripped = text.strip()
    # Python/JSON dict·list raw dump
    if (stripped.startswith("{") and stripped.endswith("}")) or \
       (stripped.startswith("[") and stripped.endswith("]")):
        return True
    return False

def _sanitize(text: str) -> str:
    """sanitize guard: raw dump → 대체 텍스트."""
    if _is_raw_dump(text):
        return "해석 정보를 처리하는 중입니다."
    return text

def _clip(text: str, max_chars: int = 240) -> str:
    """텍스트 길이 제한 + sanitize."""
    if not text:
        return ""
    text = _sanitize(text)
    return text if len(text) <= max_chars else text[:max_chars - 1].rstrip() + "…"

def _sanitize_guard(text: str) -> str:
    """금지 패턴 제거 (raw repr, traceback, deterministic claims)."""
    for pattern in _RAW_FORBIDDEN_COMPILED:
        text = pattern.sub("[필터됨]", text)
    return text

def _check_deterministic(text: str) -> List[str]:
    """확정 예언 금지 패턴 감지."""
    violations = []
    for pattern in _DETERMINISTIC_COMPILED:
        m = pattern.search(text)
        if m:
            violations.append(f"금지 표현 감지: '{m.group()}'")
    return violations

# ---------------------------------------------------------------------------
# 11-section final reading renderer
# ---------------------------------------------------------------------------

def _has_facts(value) -> bool:
    """Empty containers and metadata alone cannot support an interpretation."""
    if isinstance(value, dict):
        return any(_has_facts(v) for k, v in value.items()
                   if k not in {"backend", "status", "calculation_mode"})
    if isinstance(value, (list, tuple)):
        return any(_has_facts(v) for v in value)
    return value is not None and value != "" and value is not False


def is_calculated_card(card) -> bool:
    """Only attributed, computed facts can enter the combined interpretation."""
    return (card.is_ok() and card.calculation_mode == 'computed' and bool(card.backend)
            and _has_calculated_facts(card))


def _has_calculated_facts(card) -> bool:
    """Provenance, backend names and success flags are not chart values."""
    facts = card.facts
    if not isinstance(facts, dict):
        return False
    if card.method == 'bazi':
        from .daily_fortune_engine import _stem_element, _branch_element
        pillars = facts.get('eight_char', {})
        day = pillars.get('day', '') if isinstance(pillars, dict) else ''
        return isinstance(day, str) and len(day) == 2 and bool(_stem_element(day[0]) and _branch_element(day[1]))
    if card.method in {'western', 'vedic'}:
        rows = facts.get('planet_positions' if card.method == 'western' else 'graha_positions', [])
        if not isinstance(rows, list):
            return False
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str) or row.get('name') not in {
                    'Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto','Rahu','Ketu'}:
                continue
            value = row.get('longitude' if card.method == 'western' else 'degree')
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                if 0 <= value < (360 if card.method == 'western' else 30):
                    return True
        return False
    if card.method == 'ziwei':
        stars = facts.get('stars', {})
        return isinstance(stars, dict) and any(isinstance(value, list) and any(isinstance(star, str) and star for star in value)
                                              for value in stars.values())
    if card.method == 'qimen':
        palaces = facts.get('palaces', {})
        return isinstance(palaces, dict) and any(isinstance(value, dict) and any(isinstance(value.get(key), str) and value.get(key)
                                                                               for key in ('door','star'))
                                                for value in palaces.values())
    return False


def render_final_reading(
    cards: List[OracleMethodCard],
    *,
    include_qimen: bool = False,
    detailed: bool = False,
    language: str = "ko",
) -> str:
    """통합 final reading 렌더링.

    11-section 한국어 구조:
    1. 자료 확인
    2. 실행 가능 메서드
    3. 핵심 요약
    4. 성향/기질
    5. 일/역할
    6. 재물/자원관리
    7. 관계
    8. 5년 흐름
    9. 현실 조언
    10. 한계/참고
    11. Disclaimer

    Args:
        cards: OracleMethodCard 리스트
        include_qimen: Qimen 포함 여부
        detailed: 상세 모드 (/fortune_full)

    Returns:
        sanitize된 Telegram용 한국어 텍스트
    """
    lines: List[str] = []
    max_section_len = 6 if detailed else 3  # 각 섹션당 최대 줄 수

    # Do not infer success from a formatted fallback message or mutate caller cards.
    cards = [c for c in cards if include_qimen or c.method != "qimen"]
    cards = [replace(c, status=STATUS_BLOCKED, interpretation="", confidence=0.0,
                     blockers=["계산 결과가 없어 해석에서 제외했습니다."])
             if c.is_ok() and (not _has_facts(c.facts) or
                              c.calculation_mode == 'computed' and not _has_calculated_facts(c)) else c for c in cards]

    from .localization import language_code
    if language_code(language) == "en":
        from .oracle_renderer_en import render_english_reading
        return render_english_reading(cards, detailed=detailed)

    # 상태 분류
    runnable_cards = [c for c in cards if c.status == STATUS_RUNNABLE]
    partial_cards = [c for c in cards if c.status == STATUS_PARTIAL]
    blocked_cards = [c for c in cards if c.status == STATUS_BLOCKED]
    calculated_cards = [c for c in cards if is_calculated_card(c)]
    reference_cards = [c for c in runnable_cards + partial_cards if not is_calculated_card(c)]

    # 모든 method가 blocked인 경우
    if not runnable_cards and not partial_cards:
        return _render_all_blocked(blocked_cards)

    # 1. 자료 확인
    lines.append("📋 1. 자료 확인")
    for c in cards:
        status_ko = {"runnable": "✅", "partial": "⚠️", "blocked": "❌"}.get(c.status, "❓")
        lines.append(f"  {status_ko} {c.label_ko or c.method}: {c.status}")
    lines.append("")

    # 2. 실행 가능 메서드
    lines.append("🔮 2. 실행 가능 메서드")
    for c in runnable_cards:
        suffix = "" if is_calculated_card(c) else " (종합 해석 제외: 계산 출처 미확인)"
        lines.append(f"  ✅ {c.label_ko or c.method}{suffix}")
    for c in partial_cards:
        detail = "근사 계산" if c.calculation_mode == "approximate" else "일부 제한"
        suffix = " · 종합 해석 제외" if not is_calculated_card(c) else ""
        lines.append(f"  ⚠️ {c.label_ko or c.method} ({detail}{suffix})")
    for c in blocked_cards:
        blockers_str = "; ".join(c.blockers[:2]) if c.blockers else "이유 미상"
        lines.append(f"  ❌ {c.label_ko or c.method} (차단: {blockers_str})")
    lines.append("")

    # 3. 핵심 요약
    lines.append("📌 3. 핵심 요약")
    # 자미두수가 runnable이면 1줄 더 확보 (명궁 + 주성 표시용)
    core_max = max_section_len + 1 if any(
        c.method == "ziwei" and c.status in (STATUS_RUNNABLE, STATUS_PARTIAL)
        for c in cards
    ) else max_section_len
    core_parts = _extract_core_summary(calculated_cards, max_lines=core_max)
    if core_parts:
        for cp in core_parts:
            lines.append(f"  {cp}")
    else:
        lines.append("  핵심 요약 정보 부족 — 출생정보를 더 제공해 주세요.")
    lines.append("")

    # 4. 성향/기질
    lines.append("🎭 4. 성향/기질")
    # 자미두수가 runnable이면 1줄 더 확보
    temp_max = max_section_len + 1 if any(
        c.method == "ziwei" and c.status in (STATUS_RUNNABLE, STATUS_PARTIAL)
        for c in cards
    ) else max_section_len
    temp_parts = _extract_temperament(calculated_cards, max_lines=temp_max)
    if temp_parts:
        for tp in temp_parts:
            lines.append(f"  {tp}")
    else:
        lines.append("  성향 정보 부족 — 출생정보를 더 제공해 주세요.")
    lines.append("")

    # 5. 일/역할
    lines.append("💼 5. 일/역할")
    career_parts = _extract_career(calculated_cards, max_lines=max_section_len)
    if career_parts:
        for cp in career_parts:
            lines.append(f"  {cp}")
    else:
        lines.append("  상세 분석은 개별 명령(/western, /vedic)에서 확인하세요.")
    lines.append("")

    # 6. 재물/자원관리
    lines.append("💰 6. 재물/자원관리")
    wealth_parts = _extract_wealth(calculated_cards, max_lines=max_section_len)
    if wealth_parts:
        for wp in wealth_parts:
            lines.append(f"  {wp}")
    else:
        lines.append("  재물 흐름을 판단할 계산 근거가 없습니다.")
    lines.append("")

    # 7. 관계
    lines.append("💑 7. 관계")
    relation_parts = _extract_relations(calculated_cards, max_lines=max_section_len)
    if relation_parts:
        for rp in relation_parts:
            lines.append(f"  {rp}")
    else:
        lines.append("  상세 분석은 개별 명령에서 확인하세요.")
    lines.append("")

    # 8. 5년 흐름 (theme window — 확정 예언 아님)
    lines.append("📅 8. 장기 흐름 (참고 테마)")
    flow_parts = _extract_5year_flow(calculated_cards, max_lines=max_section_len)
    if flow_parts:
        for fp in flow_parts:
            lines.append(f"  {fp}")
    else:
        lines.append("  향후 5년의 흐름은 계산하지 않았습니다.")
    lines.append("  ※ 이는 확정된 흐름이 아니라 참고용 테마입니다.")
    lines.append("")

    # 9. 현실 조언
    lines.append("💡 9. 현실 조언")
    lines.append("  이 판독은 자기성찰의 도구입니다.")
    lines.append("  현실의 선택은 사용자의 판단에 맡깁니다.")
    if detailed:
        lines.append("  여러 메서드의 공통점을 참고하되, 단정된 운명으로 여기지 마세요.")
    lines.append("")

    # 10. 한계/참고
    lines.append("⚠️ 10. 한계/참고")
    for c in reference_cards:
        lines.append(f"  참고 전용: {c.label_ko or c.method} — 근사 값 또는 계산 출처 미확인으로 종합 해석에서 제외했습니다.")
        # Reference chart facts stay inspectable without becoming temperament or forecasts.
        for part in _extract_core_summary([c], max_lines=1):
            lines.append(f"  참고 값: {part}")
        if c.method == 'vedic':
            for key, label in (('nakshatra', '근사 나크샤트라'), ('dasha', '근사 대운')):
                if isinstance(c.facts.get(key), str):
                    lines.append(f"  {label}: {_clip(c.facts[key], 100)} (장기 흐름 예측에 사용하지 않음)")
    for c in runnable_cards + partial_cards:
        mode = "계산 결과" if is_calculated_card(c) else (
            "근사 계산 (참고 전용)" if c.calculation_mode == 'approximate' else "계산 출처 미확인 (해석 제외)")
        lines.append(f"  계산 근거: {c.label_ko or c.method} · {c.backend or '제공된 결과'} · {mode}")
        for evidence in c.evidence[:2]:
            lines.append(f"  {_clip(evidence, 120)}")
    all_warnings: List[str] = []
    for c in cards:
        all_warnings.extend(c.warnings)
    all_precision: List[str] = []
    for c in cards:
        all_precision.extend(c.precision_notes)

    # 중복 제거 (동일 경고가 western/vedic/location 등 여러 경로에서 주입되는 경우)
    all_warnings = list(dict.fromkeys(all_warnings))
    all_precision = list(dict.fromkeys(all_precision))

    for w in all_warnings[:5]:
        lines.append(f"  ℹ️ {w}")
    for p in all_precision[:3]:
        lines.append(f"  ℹ️ {p}")
    lines.append("  이 판독은 간략한 참고이며 전문적 운세 분석을 대체하지 않습니다.")
    lines.append("")

    # 11. Disclaimer
    lines.append("📜 11. Disclaimer")
    lines.append(DISCLAIMER)

    result = "\n".join(lines)
    result = _sanitize_guard(result)

    # deterministic claim 감지
    violations = _check_deterministic(result)
    if violations:
        logger.warning("Phase 37E deterministic violation: %s", violations)

    return _sanitize(result)

# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _extract_core_summary(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """핵심 요약 추출."""
    parts: List[str] = []
    for c in cards:
        if c.method == "bazi" and c.facts.get("eight_char"):
            ec = c.facts["eight_char"]
            pillar = " ".join(f"{label}{ec[key]}" for key, label in (("year", "년"), ("month", "월"), ("day", "일"), ("time", "시")) if ec.get(key))
            parts.append(f"팔자: {pillar}")
        elif c.method == "qimen" and c.facts.get("palaces"):
            parts.append(f"기문: 간지 {c.facts.get('ganzhi', '')} · 배국 {c.facts.get('pai_ju', '')}")
        elif c.method == "western" and c.facts.get("planets"):
            planets = c.facts["planets"][:3]
            parts.append(f"서양: {', '.join(str(p) for p in planets)}")
        elif c.method == "vedic" and c.facts.get("grahas"):
            grahas = c.facts["grahas"][:3]
            parts.append(f"베딕: {', '.join(str(g) for g in grahas)}")
        elif c.method == "ziwei":
            # Z5-3: 명궁 + 오행국 + 주성 (간결)
            ziwei_summary_parts = []
            ming_gong = c.facts.get("ming_gong") or {}
            wuxing = c.facts.get("wuxing_ju") or {}
            stars = c.facts.get("stars") or {}
            if ming_gong.get("branch"):
                ziwei_summary_parts.append(f"명궁({ming_gong['branch']})")
            # 명궁 주성
            ming_index = ming_gong.get("index")
            if ming_index is not None and isinstance(stars, dict) and str(ming_index) in stars:
                ming_stars = stars[str(ming_index)]
                if ming_stars:
                    ziwei_summary_parts.append(f"주성({ming_stars[0]})")
            if ziwei_summary_parts:
                parts.append(f"자미두수: {', '.join(ziwei_summary_parts)}")
        if len(parts) >= max_lines:
            break
    return [_clip(p, 120) for p in parts]

def _extract_temperament(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """성향/기질 추출."""
    parts: List[str] = []

    # 자미두수 해석을 cards 순서와 무관하게 먼저 처리 (명궁 + 주성 + 사화 기반)
    for c in cards:
        if c.method == "ziwei" and c.interpretation:
            ziwei_lines = c.interpretation.strip().split("\n")
            for zl in ziwei_lines[:max_lines]:
                zl = zl.strip()
                if zl and not zl.startswith("🔮"):
                    parts.append(zl)
                elif zl and zl.startswith("🔮"):
                    parts.append(zl.replace("🔮 자미두수: ", "자미두수: "))
                if len(parts) >= max_lines:
                    break
            if len(parts) >= max_lines:
                break

    # 그 외 method의 해석 + planets + nakshatra
    # Phase 3 (item 4): bazi "🔮 팔자:" + multi-line + "※ 월주는..." leak 방지.
    # bazi pillar는 3번 핵심 요약에 이미 있으므로 temperament에서는 중복/노이즈 제거.
    # 모든 non-ziwei interp는 1줄로 제한 + prefix/※ note 정리 (표시만, 계산 로직 무관).
    if len(parts) < max_lines:
        for c in cards:
            if c.method == "ziwei":
                continue  # 이미 처리됨
            if c.interpretation:
                interp = c.interpretation.replace("🔮 ", "").strip()
                if "※" in interp:
                    interp = interp.split("※")[0].strip()
                first = interp.split("\n")[0].strip() if interp else ""
                if first:
                    # bazi: 3번에 이미 팔자 요약이 들어가므로 여기서는 pillar 라인 스킵 (leak + 중복 방지)
                    if c.method == "bazi" and (first.startswith("팔자:") or ("년" in first[:10] and "월" in first)):
                        first = ""
                    if first:
                        parts.append(_clip(first, 80))
            if c.method == "western" and c.facts.get("planets"):
                planets = c.facts["planets"][:2]
                for p in planets:
                    parts.append(str(p))
            if c.method == "vedic" and c.facts.get("nakshatra"):
                nak = c.facts["nakshatra"]
                parts.append(f"달 나크샤트라: {nak}")
            if len(parts) >= max_lines:
                break

    return [_clip(p, 80) for p in parts]

def _extract_career(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """일/역할 추출."""
    parts: List[str] = []
    for c in cards:
        if c.method == "western":
            if "midheaven" in c.facts:
                parts.append(f"MC: {c.facts['midheaven']}")
            if "ascendant" in c.facts:
                parts.append(f"ASC: {c.facts['ascendant']}")
        if len(parts) >= max_lines:
            break
    return [_clip(p, 80) for p in parts]

def _extract_wealth(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """재물/자원관리 추출."""
    parts: List[str] = []
    for c in cards:
        if c.method == "bazi" and c.facts.get("elements"):
            distribution = " · ".join(f"{key} {value}" for key, value in c.facts["elements"].items())
            parts.append(f"계산된 오행 분포: {distribution}. 재물 예측은 계산하지 않았습니다.")
        if len(parts) >= max_lines:
            break
    return [_clip(p, 80) for p in parts]

def _extract_relations(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """관계 추출."""
    parts: List[str] = []
    for c in cards:
        if c.method == "western" and c.facts.get("aspects"):
            aspects = c.facts["aspects"][:2]
            for a in aspects:
                parts.append(str(a))
        if len(parts) >= max_lines:
            break
    return [_clip(p, 80) for p in parts]

def _extract_5year_flow(cards: List[OracleMethodCard], max_lines: int = 3) -> List[str]:
    """5년 흐름 추출 (theme window — 확정 예언 아님)."""
    parts: List[str] = []
    for c in cards:
        if c.method == "vedic" and c.facts.get("dasha"):
            dasha = c.facts["dasha"]
            parts.append(f"베딕 대운 테마: {dasha}")

        if len(parts) >= max_lines:
            break
    return [_clip(p, 80) for p in parts]

# ---------------------------------------------------------------------------
# All blocked fallback
# ---------------------------------------------------------------------------

def _render_all_blocked(blocked_cards: List[OracleMethodCard]) -> str:
    """모든 method가 blocked인 경우 — 입력 부족 안내."""
    lines: List[str] = []
    lines.append("🔮 종합 운세")
    lines.append("")
    lines.append("현재 입력 정보로 운세를 계산할 수 없습니다.")
    lines.append("")
    lines.append("차단된 메서드:")
    for c in blocked_cards:
        blockers_str = "; ".join(c.blockers[:2]) if c.blockers else "이유 미상"
        lines.append(f"  ❌ {c.label_ko or c.method}: {blockers_str}")
    lines.append("")
    lines.append("출생정보를 등록하면 종합 운세를 확인할 수 있습니다.")
    lines.append("  /register_birth 1990년 5월 17일 오후 12시 30분, 홍길동")
    lines.append("  /사주등록 1990년 5월 17일 오후 12시 30분, 홍길동")
    lines.append("")
    lines.append(DISCLAIMER)
    return _sanitize("\n".join(lines))

# ---------------------------------------------------------------------------
# Backward compatibility — 기존 render_oracle_reading()
# ---------------------------------------------------------------------------

def render_oracle_reading(
    western_card=None,
    vedic_card=None,
    bazi_summary=None,
) -> str:
    """기존 render_oracle_reading() — backward compatibility."""
    cards: List[OracleMethodCard] = []

    if western_card:
        cards.append(OracleMethodCard.from_astro_method_card(western_card))
    if vedic_card:
        cards.append(OracleMethodCard.from_astro_method_card(vedic_card))
    if bazi_summary:
        cards.append(OracleMethodCard.partial(
            method="bazi",
            facts={"summary": bazi_summary},
            interpretation=bazi_summary[:200],
        ))

    return render_final_reading(cards, detailed=False)


# ---------------------------------------------------------------------------
# Astro summary (D1) — /astro command
# ---------------------------------------------------------------------------

def render_astro_summary(
    *,
    birth_date: str = "",
    birth_time: str = "",
    timezone: str = "Asia/Seoul",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    profile: Optional[Dict[str, Any]] = None,
    store: Optional[Dict[str, Any]] = None,
    platform: str = "telegram",
    user_id: str = "default",
) -> str:
    """통합 점성술 요약 — Western + Vedic method card + location basis.

    D1: location context를 사용하여 saved location을 우선 적용.
    """
    from .astro_input import AstroBirthInput
    from .western_bridge import calculate_western_chart
    from .vedic_bridge import calculate_vedic_chart
    from .location_bridge import (
        build_location_context_for_command,
        apply_location_to_astro_input,
        format_location_basis,
    )
    from .location_settings import (
        LocationSettings,
        LocationPrecision,
        LocationSource,
        AstroLocationContext,
    )

    # Build birth datetime
    birth_datetime = ""
    if birth_date and birth_time:
        birth_datetime = f"{birth_date}T{birth_time}"
    elif birth_date:
        birth_datetime = birth_date

    # D1: Build location context from saved settings first
    loc_ctx = build_location_context_for_command(
        store=store,
        platform=platform,
        user_id=user_id,
        profile=profile,
        has_birth_time=bool(birth_time),
    )

    # If direct lat/lon provided but loc_ctx is empty, build from direct params
    if (latitude is not None or longitude is not None) and loc_ctx.source == LocationSource.UNSET:
        # Build a context from direct parameters
        direct_settings = LocationSettings(
            label=(profile or {}).get("birth_place", "") if profile else "",
            timezone=timezone,
            latitude=latitude,
            longitude=longitude,
            precision=LocationPrecision.COORDINATE if (latitude is not None and longitude is not None) else LocationPrecision.CITY,
            source=LocationSource.COMMAND,
        )
        from .location_settings import _build_redacted_summary
        has_tz = bool(timezone)
        has_coords = latitude is not None and longitude is not None
        warnings: list = []
        if has_coords:
            precision_note = "좌표 제공됨"
        elif has_tz:
            precision_note = "타임존만 제공됨 — Ascendant/house 생략"
            warnings.append("위치가 없어 Ascendant/MC/house를 계산할 수 없습니다.")
        else:
            precision_note = "위치 정보 부족"
            warnings.append("위치 설정이 없어 Ascendant/house 등은 생략됩니다.")
        redacted = _build_redacted_summary(direct_settings)
        loc_ctx = AstroLocationContext(
            label=direct_settings.label,
            timezone=direct_settings.timezone,
            latitude=direct_settings.latitude,
            longitude=direct_settings.longitude,
            precision=direct_settings.precision,
            source=direct_settings.source,
            is_complete_for_houses=has_tz and has_coords and bool(birth_time),
            warnings=warnings,
            redacted_summary=redacted,
        )
    elif loc_ctx.source != LocationSource.UNSET and (
        (latitude is None and loc_ctx.latitude is not None) or
        (longitude is None and loc_ctx.longitude is not None)
    ):
        # Saved location has coordinates; use them
        pass  # loc_ctx already has them

    astro_inp = AstroBirthInput(
        name=(profile or {}).get("display_name", "") if profile else "",
        gender=(profile or {}).get("gender", "unknown") if profile else "unknown",
        birth_datetime=birth_datetime,
        timezone=loc_ctx.timezone or timezone,
        latitude=loc_ctx.latitude if loc_ctx.latitude is not None else latitude,
        longitude=loc_ctx.longitude if loc_ctx.longitude is not None else longitude,
        birthplace_text=loc_ctx.label or ((profile or {}).get("birth_place", "") if profile else ""),
    )

    apply_location_to_astro_input(astro_inp, loc_ctx)

    lines: List[str] = []
    lines.append("🔮 통합 점성술 요약")
    lines.append("")

    # Location basis (D1: redacted)
    lines.append(format_location_basis(loc_ctx))
    lines.append("")

    # Western
    lines.append("━━━ 서양 점성술 (Tropical) ━━━")
    w_chart = calculate_western_chart(astro_inp)
    if not w_chart.ok:
        lines.append("  ❌ 계산 불가: " + "; ".join(w_chart.blockers))
    else:
        status_ko = {"runnable": "✅", "partial": "⚠️", "blocked": "❌"}.get(w_chart.status, "❓")
        lines.append(f"  {status_ko} 상태: {w_chart.status}")
        if w_chart.ascendant:
            lines.append(f"  ASC: {w_chart.ascendant.format_kr()}")
        if w_chart.midheaven:
            lines.append(f"  MC: {w_chart.midheaven.format_kr()}")
        lines.append(f"  태양: {w_chart.planets[0].format_kr()}" if w_chart.planets else "  행성 정보 없음")
        lines.append(f"  달: {w_chart.planets[1].format_kr()}" if len(w_chart.planets) > 1 else "")
        if w_chart.warnings:
            lines.append(f"  ⚠️ {'; '.join(w_chart.warnings[:2])}")
    lines.append("")

    # Vedic
    lines.append("━━━ 베딕 점성술 (Sidereal · 내장 근사 · 종합 해석 제외) ━━━")
    v_chart = calculate_vedic_chart(astro_inp)
    if not v_chart.ok:
        lines.append("  ❌ 계산 불가: " + "; ".join(v_chart.blockers))
    else:
        status_ko = {"runnable": "✅", "partial": "⚠️", "blocked": "❌"}.get(v_chart.status, "❓")
        lines.append(f"  {status_ko} 상태: {v_chart.status}")
        if v_chart.moon_nakshatra:
            lines.append(f"  달 나크샤트라: {v_chart.moon_nakshatra.format_kr()}")
        if v_chart.current_vimshottari_dasha:
            lines.append(f"  현재 대운: {v_chart.current_vimshottari_dasha.format_kr()}")
        if v_chart.grahas:
            lines.append(f"  태양: {v_chart.grahas[0].format_kr()}" if v_chart.grahas else "")
        if v_chart.warnings:
            lines.append(f"  ⚠️ {'; '.join(v_chart.warnings[:2])}")
    lines.append("")

    lines.append(DISCLAIMER)
    result = "\n".join(lines)
    result = _sanitize_guard(result)
    return _sanitize(result)
