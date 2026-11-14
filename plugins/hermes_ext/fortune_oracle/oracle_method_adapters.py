#!/usr/bin/env python3
"""Fortune Oracle — Oracle Method Adapters (Phase 37D).

기존 계산 엔진의 결과를 OracleMethodCard로 감싸는 adapter.
각 method별로 별개의 함수를 제공하며, 실패 시 blocked card를 반환.

기존 계산 엔진을 수정하지 않는다 — wrapping만 한다.
deep provider를 호출하지 않는다.

method 목록:
- bazi: BaziResult → OracleMethodCard
- western: WesternChart → OracleMethodCard (AstroMethodCard를 경유)
- vedic: VedicChart → OracleMethodCard (AstroMethodCard를 경유)
- ziwei: Ziwei bridge 결과 → OracleMethodCard (chart facts 없으면 blocked)
- qimen: QimenResult → OracleMethodCard (question-time oracle — birth-based default 제외)

금지:
- 기존 계산 엔진 수정
- deep provider 호출
- 외부 API 호출

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .oracle_input import UnifiedOracleInput
from .location_bridge import (
    apply_location_to_astro_input,
    build_location_context_for_command,
)
from .oracle_method_card import (
    ERR_CALCULATION_FAILED,
    ERR_DEPENDENCY_MISSING,
    ERR_INSUFFICIENT_BIRTH_DATA,
    OracleMethodCard,
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_RUNNABLE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bazi adapter
# ---------------------------------------------------------------------------

def adapt_bazi(inp: UnifiedOracleInput) -> OracleMethodCard:
    """Bazi adapter.

    profile birth data가 있으면 runnable 또는 partial.
    birth_date 없으면 blocked.
    """
    if not inp.sufficient_for_bazi:
        return OracleMethodCard.blocked(
            method="bazi",
            error_code=ERR_INSUFFICIENT_BIRTH_DATA,
            message="생년월일이 필요합니다.",
            blockers=["INSUFFICIENT_BIRTH_DATA: 생년월일 없음"],
        )

    try:
        bazi_input = inp.to_bazi_input()
        from .bazi_bridge import calculate_bazi
        bazi = calculate_bazi(bazi_input)
    except Exception as e:
        logger.warning("Bazi calculation failed: %s", e)
        return OracleMethodCard.blocked(
            method="bazi",
            error_code=ERR_CALCULATION_FAILED,
            message="팔자 계산에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        )

    if not bazi.ok:
        return OracleMethodCard.blocked(
            method="bazi",
            error_code=bazi.error_code or ERR_CALCULATION_FAILED,
            message=bazi.message,
            blockers=[f"{bazi.error_code}: {bazi.message}"],
        )

    if not bazi.eight_char or not bazi.eight_char.get("day"):
        return OracleMethodCard.blocked("bazi", ERR_CALCULATION_FAILED, "팔자 계산 결과가 부족합니다.")

    # facts 구성
    facts: Dict[str, Any] = {}
    if bazi.time_basis:
        facts['time_basis'] = dict(bazi.time_basis)

    if bazi.eight_char:
        facts["eight_char"] = dict(bazi.eight_char)
        if not inp.has_birth_time:
            facts["eight_char"].pop("time", None)
        elif bazi.elements:
            facts["elements"] = dict(bazi.elements)

    # status 결정
    precision_notes: List[str] = []
    if not inp.has_birth_time:
        status = STATUS_PARTIAL
        confidence = 0.5
        precision_notes.append("출생 시간 미등록 — 시주를 계산 근거에서 제외하고 년·월주의 하루 전체 일치 여부를 확인합니다.")
    else:
        status = STATUS_RUNNABLE
        confidence = 0.8

    card = OracleMethodCard(
        method="bazi",
        label_ko="팔자",
        status=status,
        facts=facts,
        backend=bazi.engine or "lunar-javascript",
        calculation_mode="computed",
        interpretation="팔자: " + " ".join(str(value) for value in facts["eight_char"].values()),
        confidence=confidence,
        warnings=bazi.warnings[:5],
        precision_notes=precision_notes + inp.precision_notes[:5],
    )

    card.add_evidence(f"계산된 일주: {facts['eight_char']['day']}")
    if bazi.time_basis:
        mode = bazi.time_basis.get('solar_terms')
        card.add_evidence("년·월주 절기: 출생 순간을 UTC+8 기준으로 변환 · 일·시주: 현지 민간시, 진태양시 보정 없음"
                          if mode == 'birth_instant_utc_plus_8' else
                          "년·월주: 현지 하루 전체에서 동일함을 확인 · 시주 미등록 · 진태양시 보정 없음"
                          if mode == 'civil_day_interval_confirmed' else
                          "절기 경계의 미확정 년·월주는 제외 · 시주 미등록 · 진태양시 보정 없음")

    # Phase 40B: 오행 강약 trace evidence
    try:
        from .bazi_element_strength import build_element_strength_trace
        if bazi.eight_char:
            trace = build_element_strength_trace(
                facts["eight_char"],
                day_master=getattr(bazi, "day_master", ""),
            )
            for ev in trace.format_evidence():
                card.add_evidence(ev)
    except Exception:
        pass

    return card

# ---------------------------------------------------------------------------
# Western adapter
# ---------------------------------------------------------------------------

def adapt_western(
    inp: UnifiedOracleInput,
    *,
    store: Optional[Dict[str, Any]] = None,
    platform: str = "telegram",
    user_id: str = "default",
    profile: Optional[Dict[str, Any]] = None,
) -> OracleMethodCard:
    """Western adapter.

    Phase 38 backend 결과를 card로 변환.
    D1: saved location settings를 우선 적용 (주입 경로 수정).
    """
    try:
        astro_inp = inp.to_astro_birth_input()

        # D1: Always try to enrich from saved location first (injection path fix)
        loc_ctx = build_location_context_for_command(
            store=store,
            platform=platform,
            user_id=user_id,
            profile=profile or inp.__dict__,
            has_birth_time=inp.has_birth_time,
        )
        apply_location_to_astro_input(astro_inp, loc_ctx)

        # Now check sufficiency *after* location enrichment
        if not astro_inp.sufficient_for_planets:
            return OracleMethodCard.blocked(
                method="western",
                error_code=ERR_INSUFFICIENT_BIRTH_DATA,
                message="출생일시와 타임존이 필요합니다.",
            )

        from .western_bridge import calculate_western_method_card
        astro_card = calculate_western_method_card(astro_inp)
        card = OracleMethodCard.from_astro_method_card(astro_card)
        card.precision_notes = inp.precision_notes[:5]
        provenance = card.facts.get("provenance", {})
        if provenance:
            card.add_evidence(f"천체력: {provenance['ephemeris']} · SHA256 {provenance['sha256']}")
            card.add_evidence("기준 좌표: 지구 중심 겉보기 열대황도(계산 날짜 기준), 출생지 IANA 시각을 UTC로 변환")
            card.add_evidence("역행: 전후 1시간 황경 차분 · 외행성은 계의 질량중심")
        return card
    except Exception as e:
        logger.warning("Western calculation failed: %s", e)
        return OracleMethodCard.blocked(
            method="western",
            error_code=ERR_CALCULATION_FAILED,
            message="서양 점성술 계산에 실패했습니다.",
        )

# ---------------------------------------------------------------------------
# Vedic adapter
# ---------------------------------------------------------------------------

def adapt_vedic(
    inp: UnifiedOracleInput,
    *,
    store: Optional[Dict[str, Any]] = None,
    platform: str = "telegram",
    user_id: str = "default",
    profile: Optional[Dict[str, Any]] = None,
) -> OracleMethodCard:
    """Vedic adapter.

    Phase 38 backend 결과를 card로 변환.
    D1: saved location settings를 우선 적용.
    """
    if not inp.sufficient_for_planets:
        return OracleMethodCard.blocked(
            method="vedic",
            error_code=ERR_INSUFFICIENT_BIRTH_DATA,
            message="출생일시와 타임존이 필요합니다.",
        )

    try:
        astro_inp = inp.to_astro_birth_input()
        # D1: Apply saved location settings
        loc_ctx = build_location_context_for_command(
            store=store,
            platform=platform,
            user_id=user_id,
            profile=profile or inp.__dict__,
            has_birth_time=inp.has_birth_time,
        )
        apply_location_to_astro_input(astro_inp, loc_ctx)
        from .vedic_bridge import calculate_vedic_method_card
        astro_card = calculate_vedic_method_card(astro_inp)
        card = OracleMethodCard.from_astro_method_card(astro_card)
        card.precision_notes = inp.precision_notes[:5]
        return card
    except Exception as e:
        logger.warning("Vedic calculation failed: %s", e)
        return OracleMethodCard.blocked(
            method="vedic",
            error_code=ERR_CALCULATION_FAILED,
            message="베딕 점성술 계산에 실패했습니다.",
        )

# ---------------------------------------------------------------------------
# Ziwei adapter
# ---------------------------------------------------------------------------

def adapt_ziwei(inp: UnifiedOracleInput) -> OracleMethodCard:
    """Ziwei adapter.

    chart facts가 없으면 partial 또는 blocked.
    별/궁/사화를 지어내지 않음.

    안정성 가드 (Phase 3):
    - stars가 None 또는 빈 dict일 때 partial 처리
    - ming_gong이 없을 때 fallback
    - sihua에서 화록/화기 중 하나가 없을 때 안전 처리
    - mjs timeout 초과 시 ok:false + 적절한 에러 메시지
    - bridge output에서 raw birth 정보 필터링
    """
    if not inp.sufficient_for_ziwei:
        return OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_INSUFFICIENT_BIRTH_DATA,
            message="자미두수에는 출생일·알고 있는 출생시각·시간대가 필요합니다. 미상 시각은 자정으로 대체하지 않습니다.",
        )

    if inp.gender not in {"male", "female"}:
        return OracleMethodCard.blocked(
            "ziwei", ERR_INSUFFICIENT_BIRTH_DATA,
            "자미두수의 전통 계산에 사용할 성별이 지정되지 않았습니다. 임의로 선택하지 않습니다.",
        )

    try:
        from .ziwei_bridge import calculate_ziwei_chart
        parsed = inp.parse_birth_datetime()
        if not parsed:
            return OracleMethodCard.blocked(
                method="ziwei",
                error_code=ERR_INSUFFICIENT_BIRTH_DATA,
                message="출생일시 파싱 실패",
            )

        date_str = f"{parsed['year']}-{parsed['month']:02d}-{parsed['day']:02d}"
        time_str = f"{parsed['hour']:02d}:{parsed['minute']:02d}"

        result = calculate_ziwei_chart(
            birth_date=date_str,
            birth_time=time_str,
            gender=inp.gender,
            # iztro uses the supplied local civil date/hour, not solar time.
            # Do not manufacture Seoul coordinates when location is unknown.
            longitude=inp.longitude,
        )
    except Exception as e:
        logger.warning("Ziwei calculation failed: %s", e)
        return OracleMethodCard.blocked(
            method="ziwei",
            error_code=ERR_CALCULATION_FAILED,
            message="자미두수 계산에 실패했습니다.",
        )

    if not result.get("ok"):
        error_code = result.get("error_code", ERR_CALCULATION_FAILED)
        message = result.get("message", "계산 실패")

        # 사용자 친화적 에러 메시지 (iztro 내부 에러 노출 방지)
        if error_code == "TIMEOUT":
            message = "자미두수 계산 시간 초과 — 잠시 후 다시 시도해 주세요."
        elif error_code == "ENGINE_ERROR":
            # iztro 내부 에러 메시지를 사용자에게 노출하지 않음
            msg_lower = message.lower()
            if "missing" in msg_lower or "시각" in msg_lower:
                message = "출생 시각을 입력해주세요. 자미두수 계산에는 시각이 필요합니다."
            elif "invalid hour" in msg_lower:
                message = "입력하신 시각을 확인해주세요. 올바른 시간 형식(00:00~23:59)을 사용해주세요."
            elif "lunar" in msg_lower or "month" in msg_lower or "day" in msg_lower:
                message = "입력하신 음력 날짜를 확인해주세요. 존재하지 않는 날짜일 수 있습니다."
            elif "push" in msg_lower or "undefined" in msg_lower or "cannot read" in msg_lower:
                message = "입력하신 시각을 확인해주세요. 올바른 시간 형식(00:00~23:59)을 사용해주세요."
            else:
                message = "자미두수 계산 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        return OracleMethodCard.blocked(
            method="ziwei",
            error_code=error_code,
            message=message,
        )

    # Phase 3 (item 2): bridge output에서 raw birth 정보 필터링 — 실제 사용
    filtered_result = dict(result)
    filtered_result.pop("input", None)

    # Step 1-4: mjs는 최상위에 stars/ming_gong/sihua를 노출
    # dict 보장 가드 재확인 (item 2)
    stars = filtered_result.get("stars") or {}
    if not isinstance(stars, dict):
        stars = {}
    ming_gong = filtered_result.get("ming_gong") or {}
    if not isinstance(ming_gong, dict):
        ming_gong = {}
    sihua = filtered_result.get("sihua") or {}
    if not isinstance(sihua, dict):
        sihua = {}
    # The bridge emits lu/quan/ke/ji; the interpreter consumes traditional names.
    # Normalize actual entries only, without inventing empty star placements.
    sihua = {canonical: dict(value) for canonical, aliases in (
        ("祿", ("祿", "禄", "lu")), ("權", ("權", "权", "quan")),
        ("科", ("科", "ke")), ("忌", ("忌", "ji")),
    ) for value in [next((sihua[key] for key in aliases if isinstance(sihua.get(key), dict)), {})]
        if value.get("star")}

    # Phase 3: stars가 None 또는 빈 dict일 때 partial 처리
    # (calc ok but data 부족 케이스에도 안성법 note 선택적 주입)
    if not stars or not any(stars.values()):
        return OracleMethodCard.blocked(
            "ziwei", ERR_CALCULATION_FAILED, "별/궁 계산 결과가 없어 해석하지 않습니다.",
        )
    complete = bool(ming_gong.get("branch") and ming_gong.get("index") is not None
                    and all(sihua.get(key) for key in ("祿", "權", "科", "忌")))

    # 갈래 1: 대한 (DaXian) from verified iztro extras (길 C)
    # ziwei_doushu_bridge.mjs untouched; extras called separately here
    # facts["daxian"] + facts["current_daxian"] for interpreter/renderer
        # Single source of truth for all brightness = iztro brightness via adapter facts['brightness'].
         # Queried via _get_star_brightness_from_fixture in ziwei_deep_prompt.py.
         # (which now reads adapter brightness directly — 5-3B).
         # facts may carry star names only. Any brightness in facts is ignored.
         # fixture는 deprecated (물리 삭제 전 비교용 유지).
         # facts may carry star names only. Any brightness in facts is ignored.
    daxian = []
    current_daxian = None
    try:
        from .ziwei_bridge import calculate_ziwei_daxian
        daxian_res = calculate_ziwei_daxian(
            birth_date=date_str,
            birth_time=time_str,
            gender=inp.gender,
        )
        if daxian_res.get("ok") and daxian_res.get("daxian"):
            daxian = daxian_res["daxian"]
            current_daxian = daxian_res.get("current_daxian")
    except Exception as e:
        logger.warning("Ziwei daxian extras non-fatal: %s", e)

    # facts 구성 — 실제 계산 결과만 사용 (filtered 기반)
    # Z5-1: 정통 mjs 출력(27성 + 오행국 + 명궁간지 + aux 13성) 전체 facts에 반영
    facts: Dict[str, Any] = {}
    facts["time_basis"] = {"day_hour": "local_civil_time", "true_solar_time": False,
                          "calendar": "solar_to_lunar_iztro", "timezone_conversion": False}
    if daxian:
        facts["daxian"] = daxian
        if current_daxian:
            facts["current_daxian"] = current_daxian

    if stars:
        # Phase 3: ming_gong palace의 stars는 반드시 포함 (핵심 요약/해석에 필요)
        ming_idx_str = str(ming_gong.get("index", ""))
        included: Dict[str, Any] = {}
        if ming_idx_str and ming_idx_str in stars:
            included[ming_idx_str] = stars[ming_idx_str]
        for k, v in stars.items():
            if k not in included and len(included) < 5:
                included[k] = v
        facts["stars"] = included
        # Z5: full stars도 별도 제공 (renderer/interpreter 확장 대비)
        facts["stars_full"] = stars
    if ming_gong:
        facts["ming_gong"] = ming_gong
    if sihua:
        facts["sihua"] = sihua

    # Z5-1: 정통 데이터 추가 (wuxing_ju, aux_stars 13성, tianfu, ziwei_info)
    wuxing_ju = filtered_result.get("wuxing_ju") or {}
    if wuxing_ju:
        facts["wuxing_ju"] = {
            "ju_number": wuxing_ju.get("ju_number"),
            "ju_name": wuxing_ju.get("ju_name"),
            "wuxing": wuxing_ju.get("wuxing"),
            "ming_gong_ganzhi": wuxing_ju.get("ming_gong_ganzhi"),
        }
    aux_stars = filtered_result.get("aux_stars") or {}
    if aux_stars:
        facts["aux_stars"] = aux_stars  # 13 보좌성 전체 (표시 범위는 Z5-2/Z5-3에서 결정)
    tianfu = filtered_result.get("tianfu_branch")
    if tianfu:
        facts["tianfu_branch"] = tianfu
    ziwei_info = filtered_result.get("ziwei_info") or {}
    if ziwei_info:
        facts["ziwei_info"] = {
            "branch": ziwei_info.get("branch"),
            "source": ziwei_info.get("source", "authentic"),
        }

    # 해석 텍스트 생성 (Z5-2에서 확장 예정, 현재 signature 유지)
    interpretation = ""
    try:
        from .ziwei_interpreter import generate_ziwei_note
        interpretation = generate_ziwei_note(
            facts.get("stars_full") or stars,
            ming_gong,
            sihua,
            wuxing_ju=facts.get("wuxing_ju"),
            aux_stars=facts.get("aux_stars"),
            ziwei_info=facts.get("ziwei_info"),
        )
    except Exception as interp_err:
        logger.warning("Ziwei interpretation failed: %s", interp_err)

    # Z5-1: precision_notes 업데이트 (간이 문구 제거, 정통 기반으로)
    precision_notes = [
        "자미두수의 성향 문구는 계산된 별 배치에 기초한 전통적 해석입니다. 오락과 자기성찰 용도이며 의학·투자·법률 결정을 지시하지 않습니다."
    ]

    return OracleMethodCard(
        method="ziwei",
        label_ko="자미두수",
        status=STATUS_RUNNABLE if complete else STATUS_PARTIAL,
        backend=filtered_result.get("engine", "ziwei-doushu-adapted"),
        calculation_mode="computed",
        facts=facts,
        interpretation=interpretation,
        confidence=0.7,
        warnings=filtered_result.get("warnings", [])[:5],
        precision_notes=precision_notes + ([] if complete else ["명궁 또는 사화 정보가 일부 누락되었습니다."]),
    )

# ---------------------------------------------------------------------------
# Qimen adapter
# ---------------------------------------------------------------------------

def adapt_qimen(
    inp: UnifiedOracleInput,
    question: str = "",
) -> OracleMethodCard:
    """Qimen adapter.

    question-time oracle이므로 birth-based final reading에는 기본 제외.
    사용자가 question_focus를 주거나 별도 흐름에서만 optional card.

    질문이 없으면 blocked.
    """
    if not question:
        return OracleMethodCard.blocked(
            method="qimen",
            error_code=ERR_INSUFFICIENT_BIRTH_DATA,
            message="기문둔갑은 질문 시각 기준입니다. 질문을 입력하세요.",
            blockers=["QIMEN_IS_QUESTION_TIME: 질문 필요"],
        )

    try:
        from datetime import datetime, timedelta, timezone
        from .qimen_bridge import calculate_qimen
        from .qimen_schema import QimenQuery
        from .qimen_interpreter import format_qimen_result
        now = datetime.now(timezone(timedelta(hours=9)))
        result = calculate_qimen(QimenQuery(now.year, now.month, now.day, now.hour, now.minute,
                                           question=question))
        if not result.ok or not result.chart or not result.chart.palaces:
            return OracleMethodCard.blocked(
                "qimen", result.error_code or ERR_CALCULATION_FAILED,
                "기문 계산을 사용할 수 없습니다. 계산 환경과 입력을 확인해 주세요.",
            )
        chart = result.chart
        text = format_qimen_result(result)
        return OracleMethodCard(
            method="qimen", label_ko="기문둔갑", status=STATUS_RUNNABLE,
            facts={"ganzhi": chart.ganzhi, "pai_ju": chart.pai_ju,
                   "question_time": now.isoformat(timespec='minutes'), "question_timezone":"Asia/Seoul",
                   "palaces": {name: {"door": palace.door, "star": palace.star}
                               for name, palace in chart.palaces.items()}},
            interpretation=text[:300], confidence=0.6,
            backend="kinqimen", calculation_mode="computed",
            evidence=[f"질문 시각(KST): {now:%Y-%m-%d %H:%M}", f"간지: {chart.ganzhi}"],
            warnings=["기문둔갑은 질문 시각 기준이며 출생정보와 무관합니다."] + result.warnings,
        )
    except Exception:
        return OracleMethodCard.blocked("qimen", ERR_CALCULATION_FAILED, "기문 계산에 실패했습니다.")

# ---------------------------------------------------------------------------
# Bulk adapter — all methods
# ---------------------------------------------------------------------------

def adapt_all(
    inp: UnifiedOracleInput,
    *,
    include_qimen: bool = False,
    question: str = "",
    store: Optional[Dict[str, Any]] = None,
    platform: str = "telegram",
    user_id: str = "default",
    profile: Optional[Dict[str, Any]] = None,
) -> List[OracleMethodCard]:
    """모든 method의 card를 한 번에 생성.

    실패한 method는 전체 renderer를 죽이지 않고 blocked card로 반환.

    Args:
        inp: UnifiedOracleInput
        include_qimen: birth-based renderer에 Qimen 포함 여부 (기본: False)
        question: Qimen 질문 텍스트 (include_qimen=True 시 사용)
        store: Persistent store dict (D1: for location settings)
        platform: Platform identifier (D1)
        user_id: User identifier (D1)
        profile: Profile dict (D1)

    Returns:
        OracleMethodCard 리스트
    """
    routes = [
        ("bazi", lambda: adapt_bazi(inp)),
        ("western", lambda: adapt_western(inp, store=store, platform=platform, user_id=user_id, profile=profile)),
        ("vedic", lambda: adapt_vedic(inp, store=store, platform=platform, user_id=user_id, profile=profile)),
        ("ziwei", lambda: adapt_ziwei(inp)),
    ]
    if include_qimen:
        routes.append(("qimen", lambda: adapt_qimen(inp, question=question)))
    cards = []
    for method, route in routes:
        try:
            cards.append(route())
        except Exception:
            cards.append(OracleMethodCard.blocked(method, ERR_CALCULATION_FAILED,
                                                  "계산 결과를 처리할 수 없습니다."))
    return cards
