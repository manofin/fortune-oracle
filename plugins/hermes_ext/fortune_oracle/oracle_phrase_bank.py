"""Fortune Oracle Phase 31 — safe Korean oracle phrase bank.

This module contains original Fortune Oracle phrases only. It does not import
external chatbot corpora, scraped text, or ML dependencies.
"""

from __future__ import annotations

import hashlib
from typing import Final

DISCLAIMER: Final[str] = "이 결과는 오락과 자기성찰용 참고입니다. 의학, 투자, 법률 결정을 지시하지 않습니다."

ARCHETYPE_LABELS: Final[dict[str, str]] = {
    "career": "일과 역할",
    "creation": "창작과 표현",
    "relationship": "관계와 거리",
    "timing": "시기와 속도",
    "self_reflection": "자기성찰",
    "unknown": "흐름 점검",
}

FALLBACK_PHRASES: Final[dict[str, tuple[str, ...]]] = {
    "career": (
        "지금은 결과를 단정하기보다 역할의 경계와 책임의 무게를 다시 재는 시기입니다.",
        "일의 흐름은 속도보다 정렬을 먼저 요구합니다. 맡은 일과 내려놓을 일을 구분해 보세요.",
        "직장과 역할의 문제는 한 번의 선택보다 반복되는 기준에서 방향이 드러납니다.",
    ),
    "creation": (
        "창작은 도피라기보다 오래 쌓인 열기를 다른 통로로 옮기는 방식에 가깝습니다.",
        "표현의 기운은 완벽한 확신보다 작은 지속에서 먼저 살아납니다.",
        "지금의 창작 흐름은 결과를 증명하기보다 목소리의 방향을 확인하는 데 초점이 있습니다.",
    ),
    "relationship": (
        "관계의 흐름은 가까워질지 멀어질지보다 어떤 거리를 지켜야 편안한지 묻고 있습니다.",
        "상대의 마음을 단정하기보다 내가 반복해서 넘겨준 경계를 먼저 살피는 편이 안전합니다.",
        "관계에서는 빠른 결론보다 말하지 못한 기준을 차분히 정리하는 시간이 필요합니다.",
    ),
    "timing": (
        "시기는 문이 저절로 열리는 순간보다 준비한 손이 문고리에 닿는 순간에 가까워집니다.",
        "지금은 전부를 걸기보다 작은 시험으로 흐름의 반응을 보는 편이 어울립니다.",
        "급하게 확정하기보다 한 단계 낮은 강도로 시작하면 흐름을 더 잘 읽을 수 있습니다.",
    ),
    "self_reflection": (
        "이 질문은 바깥의 허락보다 안쪽의 기준을 다시 세우라는 신호에 가깝습니다.",
        "지금 필요한 것은 정답을 맞히는 일이 아니라 내가 반복해서 피한 감정을 확인하는 일입니다.",
        "흐름은 사용자를 몰아붙이지 않습니다. 다만 외면한 선택지를 다시 책상 위에 올려놓습니다.",
    ),
    "unknown": (
        "질문이 흐릿할수록 답은 넓어집니다. 지금은 하나의 장면으로 질문을 좁히는 편이 좋습니다.",
        "운의 흐름은 단정 대신 점검을 권합니다. 가장 신경 쓰이는 한 가지를 먼저 적어 보세요.",
        "지금의 물음은 방향보다 초점이 먼저 필요합니다. 무엇을 잃고 싶지 않은지부터 확인해 보세요.",
    ),
    "provider_failure": (
        "provider 응답이 안정적이지 않아 기본 oracle 문장으로 전환했습니다.",
        "외부 해석을 기다리기보다 현재 확인된 흐름만으로 차분히 답합니다.",
    ),
    "disabled": (
        "심층 provider는 현재 비활성화되어 있습니다. 확인된 팔자·K선 맥락과 phrase bank만 사용합니다.",
    ),
    "no_profile": (
        "등록된 사주 정보가 없어 일반 oracle 문장으로만 답합니다. 개인화가 필요하면 먼저 사주를 등록해 주세요.",
    ),
    "ambiguous": (
        "질문이 아직 넓습니다. 일, 창작, 관계, 시기, 자기성찰 중 하나로 좁히면 답이 더 선명해집니다.",
    ),
}

TODAY_PHRASES: Final[dict[str, tuple[str, ...]]] = {
    "career": (
        "무거운 일은 한 번에 들지 말고, 손잡이를 먼저 찾는 날입니다.",
        "자리가 흔들릴 때는 의자보다 앉은 자세를 먼저 살피는 때입니다.",
    ),
    "creation": (
        "문이 열리지 않을 때는, 문고리를 바꾸는 것이 아니라 들어갈 방을 바꾸는 때입니다.",
        "아직 작품이 작아 보여도, 불씨는 크기보다 꺼지지 않는지가 먼저입니다.",
    ),
    "relationship": (
        "가까움은 거리를 없애는 일이 아니라, 안전한 거리를 함께 찾는 일입니다.",
        "말하지 않은 마음은 사라지지 않고 방향만 잃습니다.",
    ),
    "timing": (
        "때를 기다린다는 것은 멈춤이 아니라, 다음 발을 어디에 둘지 보는 일입니다.",
        "작게 시작한 흐름이 큰 결정을 대신 검증해 줍니다.",
    ),
    "self_reflection": (
        "답이 늦는 날에는 질문이 깊어지고 있는지도 살펴야 합니다.",
        "돌아보는 사람은 뒤처진 사람이 아니라 방향을 잃지 않으려는 사람입니다.",
    ),
    "unknown": (
        "안개가 짙을수록 멀리 보기보다 발밑을 확인하는 편이 안전합니다.",
        "흐릿한 질문은 나쁜 질문이 아니라 아직 몸을 찾는 질문입니다.",
    ),
}

_ALLOWED_ARCHETYPES: Final[set[str]] = set(ARCHETYPE_LABELS)


def _stable_index(archetype: str, seed_text: str, size: int) -> int:
    if size <= 0:
        return 0
    key = f"{archetype}\n{seed_text}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest[:12], 16) % size


def normalize_archetype(archetype: str | None) -> str:
    value = str(archetype or "").strip()
    return value if value in _ALLOWED_ARCHETYPES else "unknown"


def select_phrase(archetype: str | None, *, seed_text: str = "", bank: str = "fallback") -> str:
    """Select a deterministic safe phrase for an archetype."""
    normalized = normalize_archetype(archetype)
    source = TODAY_PHRASES if bank == "today" else FALLBACK_PHRASES
    phrases = source.get(normalized) or source["unknown"]
    return phrases[_stable_index(normalized, seed_text, len(phrases))]


def select_status_phrase(status: str, *, seed_text: str = "") -> str:
    phrases = FALLBACK_PHRASES.get(status) or FALLBACK_PHRASES["unknown"]
    return phrases[_stable_index(status, seed_text, len(phrases))]
