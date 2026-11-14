#!/usr/bin/env python3
"""Phase 39 — Oracle Short (deterministic 2~3 sentence summary)
- deep provider 호출 완전 배제
- Phase 37/38 renderer 결과를 2~3문장으로 압축
- loading phrase + fallback phrase bank 사용
- user-safe parser (raw traceback, error leak 방지)
"""

import random
import re
from typing import Dict, List, Optional

# ====================== Phrase Bank (Phase 39) ======================

LOADING_PHRASES = [
    "태허가 잠시 침묵하며 명식을 살피고 있습니다...",
    "현재 흐름을 조용히 읽고 있습니다. 잠시만 기다려주세요.",
    "팔자와 천시를 대조하는 중입니다...",
    "간결한 흐름을 정리하고 있습니다.",
    "명식의 핵심만 추려내는 중입니다...",
]

FALLBACK_PHRASES = [
    "현재 등록된 명식의 흐름이 조용합니다. 큰 변화보다는 안정적인 일상이 이어질 가능성이 높습니다.",
    "지금은 스스로를 돌아보고 작은 선택을 신중히 하는 시기입니다. 서두르지 않는 것이 좋습니다.",
    "주변과의 조화가 중요한 때입니다. 듣는 것보다 공감하는 태도가 도움이 됩니다.",
    "내면의 균형을 다지는 시기입니다. 외부의 소음보다 자신의 목소리에 집중해보세요.",
    "천천히, 그러나 꾸준히 나아가는 것이 현재 가장 적합한 흐름입니다.",
]

# Safe parser
_RAW_FORBIDDEN = [
    r"Traceback", r"File \".*\", line", r"Exception:", r"Error:",
    r"OracleMethodCard\(", r"dataclass", r"\{.*:.*\}", r"\[.*\]",
    r"NoneType", r"object at 0x", r"<class "
]

def _is_raw_leak(text: str) -> bool:
    if not text or not isinstance(text, str):
        return True
    text = text.strip()
    if any(re.search(p, text, re.IGNORECASE) for p in _RAW_FORBIDDEN):
        return True
    if len(text) > 800 and ("{" in text or "[" in text):
        return True
    return False


def _safe_clip(text: str, max_len: int = 180) -> str:
    if _is_raw_leak(text):
        return random.choice(FALLBACK_PHRASES)
    if len(text) > max_len:
        return text[:max_len].rstrip() + "…"
    return text.strip()


def render_oracle_short(
    full_reading: str = "",
    profile: Optional[Dict] = None,
    use_loading: bool = False,
) -> str:
    """2~3문장으로 압축된 deterministic short fortune.
    
    deep provider 호출 없이, renderer 결과를 안전하게 요약.
    """
    if use_loading:
        return random.choice(LOADING_PHRASES)

    if not full_reading or _is_raw_leak(full_reading):
        return random.choice(FALLBACK_PHRASES)

    # 핵심 문장만 추출 (첫 3개 유의미 문장)
    sentences = re.split(r'[.!?。！？]', full_reading)
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 8 and not _is_raw_leak(s)]

    if not meaningful:
        return random.choice(FALLBACK_PHRASES)

    # 최대 3문장으로 압축
    summary = " ".join(meaningful[:3])
    summary = _safe_clip(summary, 240)

    # 항상 disclaimer 포함
    disclaimer = " (이 결과는 참고용이며, 오락과 자기성찰을 위한 것입니다.)"

    return summary + disclaimer


def get_loading_phrase() -> str:
    return random.choice(LOADING_PHRASES)


def get_fallback_phrase() -> str:
    return random.choice(FALLBACK_PHRASES)
