# ZD-3: ziwei deep narrative prompt builder (Phase 33)
#
# Safe design:
# - No calculation. Only prompt assembly from pre-verified facts.
# - No network access. No file writes.
# - Pure function: input chart_facts -> (system_prompt, user_prompt)
# - birth_date, birth_time, name_hanja never exposed in prompts
#
# This module builds the system + user prompts for LLM-based
# ziwei deep narrative generation (자허 톤 + 4계층 + 안전선).

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Hangul conversion maps (to prevent LLM hanja misreading)
# All star names and ganzhi in prompts are converted to pure Hangul.
# LLM is instructed to use only the given Hangul forms.
# ---------------------------------------------------------------------------

STAR_CN_TO_KR: dict[str, str] = {
    "紫微": "자미", "天機": "천기", "太陽": "태양", "武曲": "무곡",
    "天同": "천동", "廉貞": "염정", "天府": "천부", "太陰": "태음",
    "貪狼": "탐랑", "巨門": "거문", "天相": "천상", "天梁": "천량",
    "七殺": "칠살", "破軍": "파군",
    # 보조성 (문곡 등 — 사화에서 등장 가능)
    "文昌": "문창", "文曲": "문곡", "左輔": "좌보", "右弼": "우필",
    "地空": "지공", "地劫": "지겁", "綠存": "녹존", "擎羊": "경양",
    "陀羅": "타라", "天魁": "천괴", "天鉞": "천월", "火星": "화성", "鈴星": "영성",
}

# Also include aux stars for completeness in future
AUX_CN_TO_KR: dict[str, str] = {
    "左輔": "좌보", "右弼": "우필", "文昌": "문창", "文曲": "문곡",
    "地空": "지공", "地劫": "지겁", "綠存": "녹존", "擎羊": "경양",
    "陀羅": "타라", "天魁": "천괴", "天鉞": "천월", "火星": "화성", "鈴星": "영성",
}

GANZHI_CN_TO_KR: dict[str, str] = {
    # stems
    "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
    "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
    # branches
    "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진",
    "巳": "사", "午": "오", "未": "미", "申": "신", "酉": "유",
    "戌": "술", "亥": "해",
}

def to_kr_star(star_cn: str) -> str:
    return STAR_CN_TO_KR.get(star_cn, star_cn)

def to_kr_ganzhi(gz: str) -> str:
    if not gz:
        return gz
    result = ""
    for ch in gz:
        result += GANZHI_CN_TO_KR.get(ch, ch)
    return result

def convert_facts_to_kr_prompt(facts: dict) -> dict:
    """Return a copy of facts with all star names, ganzhi, and branches converted to Hangul for prompt."""
    f = json.loads(json.dumps(facts))  # deep copy
    # ming_gong
    ming = f.get("ming_gong", {})
    if "branch" in ming:
        ming["branch"] = to_kr_ganzhi(ming["branch"])  # e.g. 未 -> 미
    for key in ("main_stars", "borrowed_stars"):
        for entry in ming.get(key, []):
            if isinstance(entry, dict) and "star" in entry:
                entry["star"] = to_kr_star(entry["star"])
    # sihua
    sihua = f.get("sihua", {})
    for h in ("lu", "quan", "ke", "ji"):
        if h in sihua and "star" in sihua[h]:
            sihua[h]["star"] = to_kr_star(sihua[h]["star"])
    # daxian_sihua (same pattern: may carry dict {star: "..."} or bare string)
    daxian_sihua = f.get("daxian_sihua", {})
    for h in ("lu", "quan", "ke", "ji"):
        entry = daxian_sihua.get(h)
        if isinstance(entry, dict) and "star" in entry:
            entry["star"] = to_kr_star(entry["star"])
        elif isinstance(entry, str) and entry:
            daxian_sihua[h] = to_kr_star(entry)
    # sam bang
    f["sam_bang_lucky"] = [to_kr_star(s) for s in f.get("sam_bang_lucky", [])]
    f["sam_bang_kill"] = [to_kr_star(s) for s in f.get("sam_bang_kill", [])]
    # current_daxian
    dax = f.get("current_daxian", {})
    if "stem_branch" in dax:
        dax["stem_branch"] = to_kr_ganzhi(dax["stem_branch"])
    if "ganzhi" in dax:
        dax["ganzhi"] = to_kr_ganzhi(dax["ganzhi"])
    return f


# ---------------------------------------------------------------------------
# 14정성 사전 (확정본: 캐릭터 + 약점/다루기)
# LLM 프롬프트에 "해당 명반에 등장하는 별만 발췌"해서 넣음.
# ---------------------------------------------------------------------------

STAR_DICTIONARY: dict[str, dict[str, str]] = {
    "紫微": {
        "캐릭터": "내면의 제왕. 모든 결정을 자신에게 맡기고, 남의 의견을 참고하되 최종 판단은 스스로 내리는 기운.",
        "약점_다루기": "혼자 모든 걸 짊어지려 해요. 신뢰할 수 있는 사람을 찾고, 위임을 연습하는 것이 제왕의 지혜예요.",
    },
    "天機": {
        "캐릭터": "끊임없이 돌아가는 바퀴. 생각이 빠르고, 여러 가능성을 동시에 보는 기운. 기획과 분석의 별.",
        "약점_다루기": "생각이 너무 많아 결정을 미루거나 흔들려 해요. 가장 핵심 하나를 잡고 실행으로 옮기는 것이 중요해요.",
    },
    "太陽": {
        "캐릭터": "세상을 밝히는 빛. 개방적이고 포용적인 기운. 남을 비추며 자신의 존재를 확인하는 별.",
        "약점_다루기": "남에게만 빛을 비추고 자신의 그림자는 외면해요. 때로는 쉬어야 하는 것도 배워야 해요.",
    },
    "武曲": {
        "캐릭터": "차가운 쇳덩어리. 결단력과 실행력이 뛰어난 기운. 말보다 행동으로 증명하는 별.",
        "약점_다루기": "냉철함이 냉담해지기 쉬워요. 감정의 온도를 낮추지 않고도 결단할 수 있는 방법을 찾아야 해요.",
    },
    "天同": {
        "캐릭터": "평화의 수호자. 조화와 안정을 추구하는 기운. 갈등을 피하고Everyone을 위한 해법을 찾는 별.",
        "약점_다루기": "안정 추구가 안주되는 경향이 있어요. 편안함을 떠나 새로운 도전을 선택하는 용기가 필요해요.",
    },
    "廉貞": {
        "캐릭터": "원칙을 지키는 수호신. 자제력과 교섭력이 뛰어난 기운. 복잡한 관계에서도 경계를 지키는 별.",
        "약점_다루기": "원칙이 경직되기도 해요. 유연함과 원칙 사이에서 균형을 찾는 것이 핵심이에요.",
    },
    "天府": {
        "캐릭터": "안정의 금고. 관리 능력과 안정감이 뛰어난 기운. 물건을 쌓아두고 지키는 별.",
        "약점_다루기": "지키려는 마음이 변화에 대한 저항이 되기도 해요. 필요한 것을放手하는 지혜가 필요해요.",
    },
    "太陰": {
        "캐릭터": "내면의 달. 섬세하고 깊은 감성을 가진 기운. 겉으로 드러나지 않는 부분을 보는 별.",
        "약점_다루기": "감정이 너무 깊어 혼자 고민하기 쉬워요. 내면을 누군가와 나누는 것이 치유의 시작이에요.",
    },
    "貪狼": {
        "캐릭터": "호기심과 도전 정신의 화신. 무엇이든 경험해보고 싶은 기운. 한계를 넘어서는 별.",
        "약점_다루기": "모든 것을 경험하려는 욕심이 분산을 만들어요. 깊이 파는 것의 가치를 알아야 해요.",
    },
    "巨門": {
        "캐릭터": "분석력과 통찰력의 별. 겉으로 드러나지 않는 것을 보는 기운. 질문을 던지며 진실을 파고드는 별.",
        "약점_다루기": "분석이 비판으로 흐르기도 해요. 관찰과 판단 사이에서 선을 그어야 해요.",
    },
    "天相": {
        "캐릭터": "조정과 신뢰의 별. 타인과의 관계를 중시하는 기운. 신뢰를 바탕으로 조화를 만드는 별.",
        "약점_다루기": "남의 기대에 맞춰 자신은 뒤로 미루어요. 조정이 타협이 되지 않도록 자신의 목소리를 내야 해요.",
    },
    "天梁": {
        "캐릭터": "보호와 지혜의 별. 남을 지키려는 본능과 지혜를 가진 기운. 어려움 속에서 길을 찾는 별.",
        "약점_다루기": "보호하려는 마음이 간섭이 되기도 해요. 남이 스스로 성장할 수 있는 공간을 열어줘야 해요.",
    },
    "七殺": {
        "캐릭터": "독립과 돌파의 선봉. 혼자서 길을 여는 기운. 안전지대를 떠나는 용기를 가진 별.",
        "약점_다루기": "돌파가 무모해지기도 해요. 용기와 신중함이 함께할 때 진정한 돌파가 가능해요.",
    },
    "破軍": {
        "캐릭터": "낡은 것을 부수는 선봉. 변화와 혁신을 추구하는 기운. 낡은 틀을 깨는 별.",
        "약점_다루기": "부수는 것만 잘하고 만드는 것은 서툴러요. 파괴 이후의 재건을 함께 계획해야 해요.",
    },
}

# Also convert STAR_DICTIONARY keys for [A] section (after definition)
STAR_DICTIONARY_KR = {to_kr_star(k): v for k, v in STAR_DICTIONARY.items()}
ZIWEI_HEADERS = (
    "▸명궁과 주성",
    "▸사화의 흐름",
    "▸삼방사정의 회조",
    "▸새겨둘 점",
)


# ---------------------------------------------------------------------------
# 밝기 7단계 정의 (작가님 확정본)
# ---------------------------------------------------------------------------

BRIGHTNESS_DEFINITIONS: str = """
밝기 7단계 (발현 상태와 다루는 난이도):
  廟(묘, 100%): 별의 에너지가 가장 완벽하게 발현. 본연의 힘을 충분히 펼침.
  旺(왕, 85%): 거의 완벽에 가까운 발현. 별의 강점이 뚜렷하게 드러남.
  得(득, 75%): 안정적으로 발현. 별의 본질을 안정적으로 표현할 수 있음.
  利(리, 60%): 어느 정도 발현. 별의 일부 강점이 드러나지만 전부는 아님.
  平(평, 45%): 중간 발현. 별의 에너지가 흐릿하게 나타남.
  不(불, 25%): 약한 발현. 별의 에너지가 제한적이지만 완전히 꺼진 것은 아님.
  陷(함, 10%): 매우 약한 발현. 별의 에너지가 거의 발현되지 않음. 다루기 어려움.
"""

# ---------------------------------------------------------------------------
# 4계층 작성 문법 (작가님 확정본)
# ---------------------------------------------------------------------------

FOUR_LAYER_RULES: str = """
4계층 작성 문법 (명제를 뒤집지 않고 방향성으로):

1계층 — 뼈대 (▸명궁과 주성): 주성 캐릭터를 밝기 수준에서 서술.
  예시: "명궁 {지지}에 {주성}이 {밝기}에 있어요. {캐릭터 요약}."

2계층 — 색 (▸사화의 흐름): 사화(化祿/化權/化科/化忌)가 주성에 어떤 색을 더하는지.
  예시: "{사화별}이 {사화}에 있어요. {별}의 {사화_의미} 흐름이 읽혀요."

3계층 — 배경 (▸삼방사정의 회조): 삼방사정에서 길성·살성이 어떻게 보조하는지.
  예시: "삼방사정에 {길성}이 있어요. {보조_의미}. {살성}은 {기질_의미} 경향이 있어요."

4계층 — 조언 (▸새겨둘 점): 강점을 살리고 약점을 다루는 방향.
  예시: "{강점}을 잘 활용하면 {장점}. {약점_솔직_인정}. {다룰_방향}."

절대 규칙 (한자·밝기 오염 방지):
- 별 이름은 반드시 주어진 한글 표기(자미, 천기, 천상, 무곡 등)만 사용. 한자(紫微, 天機 등)를 절대 쓰지 말고, 음독(자희, 연진, 칭양 등)도 금지.
- 간지(대한 등)는 주어진 한글(경진, 병인 등)만 사용.
- 밝기는 facts에 명시된 별에만 언급. facts에 밝기가 없는 별에 밝기를 붙이지 마라.
- 4계층 헤더는 정확히 다음 4줄만 사용: "▸명궁과 주성", "▸사화의 흐름", "▸삼방사정의 회조", "▸새겨둘 점". "1계층 — 뼈대" 같은 다른 라벨 절대 사용 금지.
- facts에 current_daxian이 있으면 ▸새겨둘 점에서 **반드시 구체적으로 명시**하세요. 예: "지금 33-42세 경진 대한을 지나고 계세요." "현재 대한의 흐름"처럼 막연하게 쓰지 마세요. 나이 범위(ages)와 **한글 간지** (경진, 庚辰 절대 금지)를 정확히 사용하세요.
- facts에 daxian_sihua가 있으면 ▸사화의 흐름과 ▸새겨둘 점에서 **생년 사화와 대한 사화의 층위 브릿지**를 넣으세요. 구체적으로: "생년의 X 기운 위에, 지금 대한에선 Y" 식으로 두 층위를 연결하세요. 예: "생년의 화록 기운 위에, 지금 대한에선 화권이 더해져요." 같은 별이 두 사화에 다를 수 있습니다(예: 파군이 생년에는 화권, 대한에 화록). 같은 별이 겹칠 때는 이 차이 자체를 브릿지로 사용하세요 — "생년에는 ○로 읽혔던 파군이, 지금 대한에선 □로 바뀌어요."
- 유년(流年) 사화: facts에 liunian_sihua가 있으면 자연스럽게 ▸새겨둘 점이나 사화 흐름에 녹이세요. (iztro horoscope(year) 안정성 확인 후 본격 지원 예정)

품질 지시:
- 공궁일 때는 단순히 "차용하여 봅니다"가 아니라, 공궁의 철학(여백, 비어 있음이 가진 의미)을 풀어써요.
- 계층 간 브릿지 문장: 1계층→2계층, 2계층→3계층 사이에 두 계층을 연결하는 문장을 하나 넣어요.
- 사화를 나열하지 말고 통합해요. "천기가 화록이고 천량이 화권이고"가 아니라 "현실 감각 위에 기획 감각이 더해지니" 같은 통합 서술.
- 충돌의 방향성 통합: 주성 간 충돌(예: 무곡의 냉철함 vs 탐랑의 욕망)을 단순히 나열하지 말고, 그 충돌이 만들어내는 방향성을 써요.
- 문체: 항상 "이에요/해요" 친근체. "~합니다", "~해요" 혼용 금지. 받침 조사 정확히 (무곡과, 탐랑의 등). "~와" 대신 "~과" 사용.
"""

# ---------------------------------------------------------------------------
# 안전선 규칙
# ---------------------------------------------------------------------------

SAFETY_RULES: str = """
안전선 규칙 (반드시 준수):

1. 단정 금지 어휘: 반드시, 틀림없이, 거머쥔다, ~하게 된다, 액운, 대박,
   불행해, 사고가 난다, 병에 걸린 — 절대 사용하지 마세요.
2. 경향 톤: "~한 경향", "~흐름이 읽혀요", "~기운이에요"를 사용하세요.
3. 미래 사건 예측 금지: 시기는 테마/경향까지만 서술. "사고 난다", "병에 걸린다" 금지.
4. 계산 금지: 아래 '확정 사실'의 별 위치·밝기·사화·삼방을 절대 바꾸거나 추가하지 마세요.
   너는 계산하지 않습니다. 서술만 합니다.
   (예시 금지: "무곡와", "~합니다", "~해요" 대신 "무곡과", "~이에요/해요" 사용)
"""

# ---------------------------------------------------------------------------
# 자허(紫虛) 페르소나
# ---------------------------------------------------------------------------

ZAXU_PERSONA: str = """
너는 자허(紫虛) — 진희이 선인의 〈자미두수전서〉를 잇는 술사.
따뜻하되 예리함. 사용자를 "{이름}님"으로 부름.
문체: ···이에요/해요 (2인칭 친근체).
"""

# ---------------------------------------------------------------------------
# 시스템 프롬프트 조립
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """자허 톤 + 안전선 + 4계층 + 밝기 7단계를 포함하는 시스템 프롬프트."""
    return (
        ZAXU_PERSONA
        + "\n\n"
        + SAFETY_RULES
        + "\n\n"
        + BRIGHTNESS_DEFINITIONS
        + "\n\n"
        + FOUR_LAYER_RULES
        + "\n\n"
        + "이제 아래 [확정 사실]을 바탕으로 명궁 서사를 4계층으로 작성하세요.\n"
        + "사실만 사용하세요. 계산하지 마세요.\n"
    )

# ---------------------------------------------------------------------------
# 유저 프롬프트 조립 (chart_facts 기반)
# ---------------------------------------------------------------------------

def _filter_star_dict(chart_facts: dict) -> dict[str, dict[str, str]]:
    """명반에 등장하는 별만 발췌 (토큰 절약)."""
    relevant_stars = set()

    # 명궁 주성 + 차용성
    ming = chart_facts.get("ming_gong", {})
    for key in ("main_stars", "borrowed_stars"):
        for entry in ming.get(key, []):
            if isinstance(entry, dict):
                star = entry.get("star", "")
                if star:
                    relevant_stars.add(star)
            elif isinstance(entry, str) and entry:
                relevant_stars.add(entry)

    # 사화 붙은 별
    for hua_key in ("lu", "quan", "ke", "ji"):
        hua_data = chart_facts.get("sihua", {}).get(hua_key, {})
        star = hua_data.get("star", "")
        if star:
            relevant_stars.add(star)

    # 삼방 주요 별 (길성·살성)
    for star in chart_facts.get("sam_bang_lucky", []):
        relevant_stars.add(star)
    for star in chart_facts.get("sam_bang_kill", []):
        relevant_stars.add(star)

    filtered = {}
    for star in relevant_stars:
        if star in STAR_DICTIONARY:
            filtered[star] = STAR_DICTIONARY[star]

    return filtered

def _classify_star_role(chart_facts: dict, star: str) -> str:
    """별의 역할을 분류: [성격 뼈대] 또는 [사화 언급용].

    성격 뼈대 = 명궁 주성/차용성/삼방 주요 별 (성격 서술에 끌어들이면 됨)
    사화 언급용 = 삼방 밖 사화 붙은 별 (사화 흐름에만 언급, 성격 서술 금지)
    """
    ming = chart_facts.get("ming_gong", {})

    # 명궁 주성/차용성 체크
    for key in ("main_stars", "borrowed_stars"):
        for entry in ming.get(key, []):
            if isinstance(entry, dict) and entry.get("star") == star:
                return "성격 뼈대"
            elif isinstance(entry, str) and entry == star:
                return "성격 뼈대"

    # 삼방 주요 별 체크
    for s in chart_facts.get("sam_bang_lucky", []):
        if s == star:
            return "성격 뼈대"
    for s in chart_facts.get("sam_bang_kill", []):
        if s == star:
            return "성격 뼈대"

    # 나머지 (사화로만 등장)
    return "사화 언급용"



# ---------------------------------------------------------------------------
# 밝기 조회: 어댑터 brightness (iztro 단일 소스)
# ---------------------------------------------------------------------------

# Single source of truth for ALL brightness (주성 + 사화 별 + 대한사화 별):
# 어댑터가 iztro brightness를 직접 추출해 facts['brightness']에 제공.
# key = "idx_별명"(번체), value = brightness(한자: 庙/旺/得/利/平/不/陷)
# 예: "7_天相": "得" → "득"

BRIGHT_CN_TO_KR: dict[str, str] = {
    "庙": "묘", "旺": "왕", "得": "득", "利": "리",
    "平": "평", "不": "불", "陷": "함",
}

def _get_star_brightness_from_fixture(star: str, facts: dict) -> str:
    """Brightness from adapter facts['brightness'] — single source for ALL stars.

    Input: star name (KR or CN) + facts containing brightness dict.
    Output: Korean brightness string (e.g. "함", "묘") or "" if not found.

    Looks up star in:
    1. facts['sihua'] — sihua entries have palace_index → brightness key.
    2. facts['stars'] — indexed by palace index → find star in list.
    3. facts['ming_gong']['main_stars'] / ['borrowed_stars'] — may carry branch.
    4. facts['aux_stars'] — 보좌성.
    """
    brightness = facts.get("brightness", {})
    EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

    cn_to_kr = STAR_CN_TO_KR
    kr_to_cn = {v: k for k, v in cn_to_kr.items()}
    star_cn = kr_to_cn.get(star, star)

    # 1. Try facts['sihua'] — sihua entries have 'palace_index'
    sihua = facts.get("sihua", {})
    for hua_key in ("lu", "quan", "ke", "ji"):
        hua_data = sihua.get(hua_key, {})
        hua_star = hua_data.get("star", "")
        hua_star_cn = kr_to_cn.get(hua_star, hua_star)
        if hua_star_cn == star_cn:
            palace_idx = hua_data.get("palace_index")
            if palace_idx is not None:
                bkey = f"{palace_idx}_{star_cn}"
                b_cn = brightness.get(bkey)
                if b_cn:
                    return BRIGHT_CN_TO_KR.get(b_cn, b_cn)

    # 2. Try facts['stars'] — indexed by palace index
    stars_full = facts.get("stars") or {}
    for idx_str, star_list in stars_full.items():
        try:
            idx = int(idx_str)
        except (ValueError, TypeError):
            continue
        if isinstance(star_list, list):
            for s in star_list:
                s_cn = kr_to_cn.get(s, s)
                if s_cn == star_cn:
                    bkey = f"{idx}_{star_cn}"
                    b_cn = brightness.get(bkey)
                    if b_cn:
                        return BRIGHT_CN_TO_KR.get(b_cn, b_cn)

    # 3. Try facts['ming_gong']['main_stars'] or ['borrowed_stars'] — may have 'branch'
    ming = facts.get("ming_gong", {})
    for key in ("main_stars", "borrowed_stars"):
        for entry in ming.get(key, []):
            if isinstance(entry, dict):
                entry_star = entry.get("star", "")
                entry_star_cn = kr_to_cn.get(entry_star, entry_star)
                if entry_star_cn == star_cn:
                    branch = entry.get("branch", "")
                    if branch:
                        # Find idx from branch
                        try:
                            idx = EARTHLY_BRANCHES.index(branch)
                            bkey = f"{idx}_{star_cn}"
                            b_cn = brightness.get(bkey)
                            if b_cn:
                                return BRIGHT_CN_TO_KR.get(b_cn, b_cn)
                        except ValueError:
                            pass

    # 4. Fallback: try aux_stars (보좌성)
    aux_stars = facts.get("aux_stars", {})
    for aux_star_name, branch in aux_stars.items():
        aux_cn = kr_to_cn.get(aux_star_name, aux_star_name)
        if aux_cn == star_cn and branch:
            try:
                idx = EARTHLY_BRANCHES.index(branch)
                bkey = f"{idx}_{star_cn}"
                b_cn = brightness.get(bkey)
                if b_cn:
                    return BRIGHT_CN_TO_KR.get(b_cn, b_cn)
            except ValueError:
                pass

    # Not found
    return ""

# ---------------------------------------------------------------------------
# DEPRECATED: Old fixture-based chart identification (kept for comparison)
# ---------------------------------------------------------------------------
# _normalize_chart_key, _normalize_fixture_key are NO LONGER used for brightness.
# They remain here ONLY for reference. New code should NOT use them.
# They are replaced by adapter brightness (5-3B).
# ---------------------------------------------------------------------------


def build_ziwei_skeleton(facts: dict) -> str:
    """Build deterministic KR factual skeleton. LLM must not invent any of these tokens.
    Converts star names to Hangul via STAR_CN_TO_KR to prevent LLM hanja misreading.
    """
    facts = convert_facts_to_kr_prompt(facts)
    ming = facts.get("ming_gong", {})
    sihua = facts.get("sihua", {})
    daxian = facts.get("current_daxian", {})
    branch = ming.get("branch", "")

    # Main / borrowed stars with brightness (KR names only)
    lines = []
    if ming.get("is_empty"):
        borrowed = ming.get("borrowed_stars", [])
        if borrowed:
            parts = []
            for e in borrowed:
                if isinstance(e, dict):
                    star = e["star"]
                    br = e.get("brightness", "")
                    if not br and e.get("branch"):
                        br = _get_star_brightness_from_fixture(star, facts)
                    parts.append(f"{star}({br})" if br else star)
            bstr = " · ".join(parts)
            lines.append(f"명궁 {branch} (공궁 — 대조궁 차용: {bstr})")
    else:
        main = ming.get("main_stars", [])
        if main:
            parts = []
            for e in main:
                if isinstance(e, dict):
                    star = e["star"]
                    br = e.get("brightness", "")
                    if not br and e.get("branch"):
                        br = _get_star_brightness_from_fixture(star, facts)
                    parts.append(f"{star}({br})" if br else star)
            mstr = " · ".join(parts)
            lines.append(f"명궁 {branch}, 주성: {mstr}")

    # Sihua assignment (clean list, not prose) -- brightness from fixture 12궁 table
    sihua_lines = []
    for key, label in [("lu","화록"), ("quan","화권"), ("ke","화과"), ("ji","화기")]:
        s = sihua.get(key, {})
        star = s.get("star", "")
        if star:
            br = _get_star_brightness_from_fixture(star, facts)
            sihua_lines.append(f"{label}={star}" + (f"({br})" if br else ""))
    if sihua_lines:
        lines.append("사화 배정 (생년): " + " · ".join(sihua_lines))

    # Daxian sihua (if present) -- also from fixture brightness
    # daxian_sihua may carry dict values {"star": "..."} or bare string values
    daxian_sihua = facts.get("daxian_sihua", {})
    if daxian_sihua:
        daxian_lines = []
        _dax_label_map = {"lu": "화록", "quan": "화권", "ke": "화과", "ji": "화기"}
        for key, star_data in daxian_sihua.items():
            label = _dax_label_map.get(key, key)
            star = star_data.get("star", "") if isinstance(star_data, dict) else str(star_data) if star_data else ""
            if star:
                br = _get_star_brightness_from_fixture(star, facts)
                daxian_lines.append(f"{label}={star}" + (f"({br})" if br else ""))
        if daxian_lines:
            lines.append("사화 배정 (대한): " + " · ".join(daxian_lines))

    # Sam-bang
    lucky = facts.get("sam_bang_lucky", [])
    kill = facts.get("sam_bang_kill", [])
    if lucky or kill:
        sb = []
        if lucky: sb.append("길성:" + ",".join(lucky))
        if kill: sb.append("살성:" + ",".join(kill))
        lines.append("삼방: " + " ".join(sb))

    # Liunian (유년) sihua placeholder — pending iztro horoscope(year) stability check
    # When ready: facts["liunian_sihua"] = { "lu": "...", ... } for current year stem
    liunian = facts.get("liunian_sihua", {})
    if liunian:
        liu_lines = []
        for label, star in liunian.items():
            if star:
                br = _get_star_brightness_from_fixture(star, facts)
                liu_lines.append(f"{label}={star}" + (f"({br})" if br else ""))
        if liu_lines:
            lines.append("사화 배정 (유년): " + " · ".join(liu_lines))

    if daxian:
        rng = daxian.get('ages') or daxian.get('range', '')
        gzh = daxian.get('ganzhi') or daxian.get('stem_branch', '')
        if rng or gzh:
            lines.append(f"현재 대한: {rng} {gzh}")

    # 유년(流年) 사화 placeholder — iztro horoscope(year) 안정성 확인 후 본격 지원
    # (현재는 주석으로만 포함, facts에 liunian_sihua 추가 시 자동 렌더)
    lines.append("# 유년 사화: (추후 지원) 현재 연도 천간에 따른 사화 변화 추적 예정")

    skeleton = "\n".join(lines)
    return skeleton

# provider로 전송하는 이름은 항상 이 호칭으로 교체한다.
GENERIC_ADDRESS = "사용자"


def _scrub_name(text: str, original_name: str | None, replace_with: str = GENERIC_ADDRESS) -> str:
    """LLM 응답 안에 되받아 적힌 실명을 일반 호칭으로 되돌린다.

    원본 실명을 알고 있을 때만 의미가 있다. 비었거나 이미 일반 호칭이면
    원문을 그대로 반환한다.
    """
    if not text or not original_name:
        return text
    name = original_name.strip()
    if not name or name == replace_with:
        return text
    return text.replace(name, replace_with)


def _generic_address(name: str | None) -> str:
    """실명을 일반 호칭으로 치환한다(공백·None 포함).

    사주 간지 등 파생 데이터는 그대로 전송한다 — 출생 원문이 아니라
    계산 결과이므로, 익명화 처리 대상이 아니다.
    """
    return GENERIC_ADDRESS


def build_user_prompt(chart_facts: dict, name: str = "사용자") -> str:
    """확정 사실 + 발췌된 14정성 사전을 포함하는 유저 프롬프트.
    Facts are converted to pure Hangul before formatting to prevent hanja misreading.
    """
    chart_facts = convert_facts_to_kr_prompt(chart_facts)
    ming = chart_facts.get("ming_gong", {})
    sihua = chart_facts.get("sihua", {})
    current_daxian = chart_facts.get("current_daxian", {})

    # 명궁 정보
    branch = ming.get("branch", "알 수 없음")
    main_stars = ming.get("main_stars", [])
    borrowed_stars = ming.get("borrowed_stars", [])
    is_empty = ming.get("is_empty", False)

    # 밝기 매핑 (중국어 -> 한국어)
    brightness_map = {
        "庙": "묘", "旺": "왕", "利": "리", "平": "평", "陷": "함",
        "得": "득", "不": "불",
    }

    def _format_stars_with_brightness(stars_with_brightness: list[dict]) -> str:
        parts = []
        for entry in stars_with_brightness:
            star = entry.get("star", "")
            br = entry.get("brightness", "")
            kr_br = brightness_map.get(br, br) if br else ""
            if star:
                parts.append(f"{star}({kr_br})" if kr_br else star)
        return "·".join(parts) if parts else "없음"

    # 명궁 서술
    if is_empty and borrowed_stars:
        ming_desc = f"명궁 {branch} (공궁, 대조궁 차용: {_format_stars_with_brightness(borrowed_stars)})"
    elif main_stars:
        ming_desc = f"명궁 {branch}, 주성: {_format_stars_with_brightness(main_stars)}"
    else:
        ming_desc = f"명궁 {branch}"

    # 사화 서술
    sihua_desc = ""
    sihua_labels = {"lu": "화록", "quan": "화권", "ke": "화과", "ji": "화기"}
    for hua_key, label in sihua_labels.items():
        hua_data = sihua.get(hua_key, {})
        star = hua_data.get("star", "")
        br = hua_data.get("brightness", "")
        kr_br = brightness_map.get(br, br) if br else ""
        if star:
            sihua_desc += f"  {label} = {star} ({kr_br})\\n" if kr_br else f"  {label} = {star}\\n"

    # 삼방 서술
    lucky = chart_facts.get("sam_bang_lucky", [])
    kill = chart_facts.get("sam_bang_kill", [])
    sam_bang_desc = ""
    if lucky:
        sam_bang_desc += f"  길성: {', '.join(lucky)}\n"
    if kill:
        sam_bang_desc += f"  살성: {', '.join(kill)}\n"

    # 대한 서술
    daxian_desc = ""
    if current_daxian:
        range_info = current_daxian.get("range", "")
        stem_branch = current_daxian.get("stem_branch", "")
        daxian_desc = f"  현재 대한: {range_info} {stem_branch}"

    # 발췌된 14정성 사전 (역할 라벨 포함)
    filtered_dict = _filter_star_dict(chart_facts)
    star_dict_desc = ""
    if filtered_dict:
        star_dict_desc = "\n[A] 14정성 사전 (등장 별만 발췌):\n"
        for star, info in filtered_dict.items():
            role = _classify_star_role(chart_facts, star)
            star_dict_desc += f"  {star} [{role}]: {info['캐릭터']}\n"
            star_dict_desc += f"    → {info['약점_다루기']}\n"

    # 역할 라벨 설명
    role_instructions = (
        "\n[A] 사전의 역할 라벨:\n"
        "  [성격 뼈대]: 명궁 주성/차용성/삼방 별 — 성격 서술(명궁과 주성/새겨둘 점)에 자유롭게 끌어들이세요.\n"
        "  [사화 언급용]: 삼방 밖 사화 별 — 사화 흐름 한 문장에만 언급하세요. 성격 서술에 끌어들이지 마세요.\n"
    )

    # 자허 페르소나 (유저 프롬프트용)
    # 이름은 provider로 전송하지 않는다 — LLM 호출 경계에서 일반 호칭으로 고정.
    # 간지·띠·오행 등 파생 데이터는 현행 계약대로 포함한다(익명화 아님).
    name = _generic_address(name)
    zaxu_user = ZAXU_PERSONA.replace("{이름}", name).replace("사용자", name)

    skeleton = build_ziwei_skeleton(chart_facts)

    prompt = (
          f"{zaxu_user}\n\n"
          f"[확정 사실 골격 — 이 아래의 별·밝기·사화 배정·헤더는 Python이 facts에서 결정론적으로 생성한 정본입니다. 절대 변경·추가·재해석하지 마세요.]\n\n"
          f"{skeleton}\n\n"
          f"{star_dict_desc}\n"
          f"{role_instructions}\n"
          f"출력 형식 (엄격 준수):\n"
          f"아래 4개 헤더를 정확히 이 순서로 쓰고, 각 헤더 바로 아래에 **산문만** 작성하세요. 헤더 아래에 사실 토큰(별 이름, 밝기 값, 사화 배정, 새로운 헤더)을 절대 쓰지 마세요.\n\n"
          f"▸명궁과 주성\n"
          f"[이 섹션 산문만 — 주성의 기질과 밝기 수준을 자연스럽게 서술. 밝기 값(묘/왕/득 등)과 '밝기'라는 단어는 이 산문에 사용하지 마세요. 골격에 이미 있습니다.]\n\n"
          f"▸사화의 흐름\n"
          f"[이 섹션 산문만 — 골격에 주어진 사화 배정(화록=xxx 등)을 해석으로 풀어서. 사화 배정 자체를 다시 나열하거나 바꾸지 마세요.]\n\n"
          f"▸삼방사정의 회조\n"
          f"[이 섹션 산문만]\n\n"
          f"▸새겨둘 점\n"
          f"[이 섹션 산문만 — facts에 current_daxian이 있으면 자연스럽게 1문장 포함. 약점은 솔직히, 방향성은 건설적으로.]\n\n"
          f"{name}님의 명반입니다. 위 골격의 모든 사실 토큰은 변경 불가. 한자·음독·새 사실 토큰·밝기 값 명명 금지. 안전 고지는 산문 마지막에 1회만.\n"
      )

    return prompt

# ---------------------------------------------------------------------------
# 메인 빌더
# ---------------------------------------------------------------------------

def build_ziwei_deep_prompt(
    chart_facts: dict,
    name: str = "사용자",
) -> tuple[str, str]:
    """LLM 호출용 (system_prompt, user_prompt) 튜플 반환.

    Args:
        chart_facts: 명반 확정 사실 dict
        name: 사용자 이름

    Returns:
        (system_prompt, user_prompt)
    """
    system = build_system_prompt()
    user = build_user_prompt(chart_facts, name)
    return (system, user)

# 도입부 다양화 (#2): 실사용자 피드백 후 판단. 현재는 일관된 자허 톤 유지 (표현 다양성 vs 사실 일관성 트레이드오프)