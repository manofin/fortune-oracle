# ZD-3 + ZD-5: ziwei deep LLM caller + safety + critique + backoff
from __future__ import annotations
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from .ziwei_deep_critic import critique_draft, parse_critique
from .deep_transport import deep_enabled, bounded_timeout, read_json_response

logger = logging.getLogger(__name__)

LLM_MODEL = "local-writer"
LLM_API_KEY = os.environ.get("FORTUNE_DEEP_API_KEY", "")
LLM_TIMEOUT_SEC = 30
LLM_MAX_TOKENS = 2000

def _resolve_llm_base_url() -> Optional[str]:
    """운영 지정 endpoint. 코드 기본값 없이 환경변수에서만 읽는다."""
    raw = os.environ.get("FORTUNE_DEEP_BASE_URL", "")
    url = raw.strip() if raw else ""
    if not url:
        logger.warning(
            "FORTUNE_DEEP_BASE_URL 미설정 — ziwei deep LLM 호출을 차단합니다"
            "(하드코딩 fallback 없음)."
        )
    return url or None


def call_llm_with_backoff(system_prompt, user_prompt, temperature=0.7, max_tokens=LLM_MAX_TOKENS, timeout=LLM_TIMEOUT_SEC, max_attempts=1, initial_delay=0.0):
    # 주소 미지정이면 backoff 루프에 진입하지 않는다: 요청 0회, 대기 0회.
    if not deep_enabled() or _resolve_llm_base_url() is None:
        return None
    max_attempts = min(2, max(1, int(max_attempts)))
    delay = min(1.0, max(0.0, float(initial_delay)))
    for attempt in range(max_attempts):
        result = call_llm(system_prompt, user_prompt, temperature, max_tokens, timeout)
        if result is not None:
            if attempt > 0:
                logger.info(f"Backoff success on attempt {attempt+1}")
            return result
        if attempt < max_attempts-1:
            logger.warning(f"LLM attempt {attempt+1} failed, sleep {delay}s")
            time.sleep(delay)
    logger.error(f"LLM failed after {max_attempts} backoff attempts")
    return None

def call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=LLM_MAX_TOKENS, timeout=LLM_TIMEOUT_SEC):
    if not deep_enabled():
        return None
    base_url = _resolve_llm_base_url()
    if base_url is None:
        return None
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/chat/completions", data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=bounded_timeout(timeout)) as resp:
            body = read_json_response(resp)
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content if isinstance(content, str) and content else None
    except Exception as exc:
        logger.error("LLM call failed (%s)", type(exc).__name__)
        return None

GANZHI_STEM = {"甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무", "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계"}
GANZHI_BRANCH = {"子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진", "巳": "사", "午": "오", "未": "미", "신": "신", "酉": "유", "戌": "술", "亥": "해"}

def _convert_ganzhi_to_hangul(text):
    if not text: return text
    def replace_pair(m):
        return GANZHI_STEM.get(m.group(1), m.group(1)) + GANZHI_BRANCH.get(m.group(2), m.group(2))
    text = re.sub(r"([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])", replace_pair, text)
    for han, kr in {**GANZHI_STEM, **GANZHI_BRANCH}.items():
        text = text.replace(han, kr)
    return text

DEFINITIVE_PATTERNS = [r"반드시", r"틀림없이", r"거머쥐", r"확실히.{0,5}된다?", r"액운", r"대박", r"불행해", r"사고가.{0,5}난다?", r"병에.{0,5}걸린", r"죽는다?", r"파산", r"망한다?", r"재앙", r"흉하다", r"필연적", r"결정적"]
STAR_PATTERN_EITHER = r"((?:자미|천기|태양|무곡|천동|염정|천부|태음|탐랑|거문|천상|천량|칠살|파군|紫微|天機|太陽|武曲|天同|廉貞|天府|太陰|貪狼|巨門|天相|天梁|七殺|破軍))"
COMPILED_DEF_PATTERNS = [re.compile(p) for p in DEFINITIVE_PATTERNS]
STAR_KR_MAP = {"자미": "紫微", "천기": "天機", "태양": "太陽", "무곡": "武曲", "천동": "天同", "염정": "廉貞", "천부": "天府", "태음": "太陰", "탐랑": "貪狼", "거문": "巨門", "천상": "天相", "천량": "天梁", "칠살": "七殺", "파군": "破軍"}
SIHUA_LABEL_MAP = {"禄": "록", "权": "권", "科": "과", "忌": "기"}
_BRIGHTNESS_KR = ("묘", "왕", "득", "리", "평", "불", "함")
_SIHUA_KR = ("화록", "화권", "화과", "화기")
ZIWEI_HEADERS = ("▸명궁과 주성", "▸사화의 흐름", "▸삼방사정의 회조", "▸새겨둘 점")

def _nearest_star(text, lo, hi, stars, window=14):
    left, right = text[max(0, lo - window):lo], text[hi:hi + window]
    best, best_d = None, window + 1
    for s in stars:
        if len(s) < 2: continue
        li = left.rfind(s)
        if li != -1 and (d := len(left) - li - len(s)) < best_d: best, best_d = s, d
        ri = right.find(s)
        if ri != -1 and ri < best_d: best, best_d = s, ri
    return best

def validate_ziwei_prose(prose, facts):
    star_brightness = {}
    for entry in facts.get("ming_gong", {}).get("main_stars", []):
        if isinstance(entry, dict): star_brightness[entry.get("star", "")] = entry.get("brightness", "")
    for entry in facts.get("ming_gong", {}).get("borrowed_stars", []):
        if isinstance(entry, dict): star_brightness[entry.get("star", "")] = entry.get("brightness", "")
    sihua_raw = facts.get("sihua", {})
    sihua_map = {}
    for k, lbl in {"lu": "화록", "quan": "화권", "ke": "화과", "ji": "화기"}.items():
        star = sihua_raw.get(k, {}).get("star", "")
        if star: sihua_map[lbl] = star
    valid_pairs = {(star, label) for label, star in sihua_map.items()}
    # 대한사화(합집합) — 같은 별이 두 세트에서 다른 사화를 가질 수 있음 (예: 파군은 생년=화권, 대한=화록)
    daxian_sihua_raw = facts.get("daxian_sihua", {})
    for k, lbl in {"lu": "화록", "quan": "화권", "ke": "화과", "ji": "화기"}.items():
        star_data = daxian_sihua_raw.get(k)
        star = star_data.get("star", "") if isinstance(star_data, dict) else str(star_data) if star_data else ""
        if star: valid_pairs.add((star, lbl))
    stars = sorted(star_brightness.keys(), key=len, reverse=True)
    issues = []
    if "밝기" in prose: issues.append("본문에 '밝기' 등장")
    for m in re.finditer(r"\(\s*[" + "".join(_BRIGHTNESS_KR) + r"]\s*\)", prose):
        issues.append(f"본문에 밝기 괄호 {m.group(0)}")
    cjk = sorted(set(re.findall(r"[\u4e00-\u9fff]+", prose)))
    if cjk: issues.append(f"한자 오염: {', '.join(cjk)}")
    for m in re.finditer(r"([가-힣]{1,4})\(([가-힣]{1,4})\)", prose):
        if m.group(1) == m.group(2): issues.append(f"중복 괄호 {m.group(0)}")
    for label in _SIHUA_KR:
        for m in re.finditer(re.escape(label), prose):
            star = _nearest_star(prose, m.start(), m.end(), stars)
            if star and (star, label) not in valid_pairs:
                issues.append(f"사화 불일치: {star} {label}")
    last = -1
    for h in ZIWEI_HEADERS:
        i = prose.find(h)
        if i == -1: issues.append(f"헤더 누락: {h}")
        elif i < last: issues.append(f"헤더 순서 오류: {h}")
        else: last = i
    return issues

def safety_check(text, chart_facts):
    issues = []
    for pattern in COMPILED_DEF_PATTERNS:
        match = pattern.search(text)
        if match: issues.append(f"단정 어휘: '{match.group()}'")
    prose_issues = validate_ziwei_prose(text, chart_facts)
    issues.extend(prose_issues)
    return (len(issues) == 0, issues)

def generate_deep_narrative(chart_facts, name="사용자", temperature=0.7, max_retries=1):
    return _generate_safe_draft(chart_facts, name, temperature, max_retries)

def generate_deep_narrative_with_critique(chart_facts, name="사용자", temperature=0.7, max_retries=1, use_critic: bool = False):
    """1-pass stable path by default (use_critic=False).
    When use_critic=True, attempts critic + rewrite (experimental).
    All critic/rewrite code is preserved behind the flag for future use.
    """
    # Always produce safe 1-pass draft first
    draft_result = _generate_safe_draft(chart_facts, name, temperature, max_retries)
    if not draft_result.get("ok") or not draft_result.get("text"):
        draft_result["used_critique"] = False
        return draft_result

    if not use_critic:
        # Explicit off: never call critic or rewrite. Return 1-pass result.
        draft_result["used_critique"] = False
        return draft_result

    # Experimental 3-pass path (critic + rewrite) - only when explicitly enabled
    draft_text = draft_result["text"]
    crit_result = critique_draft(draft_text, chart_facts, name, temperature=0.4)
    if not crit_result.get("ok") or not crit_result.get("critique"):
        draft_result["critique"] = None
        draft_result["critique_issues"] = crit_result.get("issues", ["critic unavailable"])
        draft_result["used_critique"] = False
        return draft_result
    critique_text = crit_result["critique"]
    from .ziwei_deep_prompt import build_ziwei_deep_prompt, _scrub_name
    system, base_user = build_ziwei_deep_prompt(chart_facts, name)
    # critique 응답(LLM 출력)에 실명이 되받아 들어와도 rewrite payload 로 넘기지 않는다.
    critique_text = _scrub_name(critique_text, name)
    rewrite_user = base_user + "\n\n[자허 비평가 피드백]\n" + critique_text + "\n\n규칙: 군더더기는 덜어내되, 자허 목소리·청월당급 문학성·정통 뉘앙스·안전 가드레일은 절대 건드리지 마세요. 4계층 헤더 그대로, 사실 토큰 변경 금지."
    rewrite_text = call_llm_with_backoff(system, rewrite_user, temperature=temperature)
    if rewrite_text:
        rewrite_text = re.sub(r'<think>.*?</think>', '', rewrite_text, flags=re.DOTALL | re.IGNORECASE).strip()
        rewrite_text = _convert_ganzhi_to_hangul(rewrite_text)
        ok, issues = safety_check(rewrite_text, chart_facts)
        if ok:
            return {"ok": True, "text": rewrite_text, "issues": [], "retries": draft_result.get("retries", 0), "temperature": temperature, "critique": critique_text, "used_critique": True}
        draft_result["critique"] = critique_text
        draft_result["used_critique"] = False
        draft_result["fallback_reason"] = "rewrite_safety_fail"
        return draft_result
    draft_result["critique"] = critique_text
    draft_result["used_critique"] = False
    draft_result["fallback_reason"] = "rewrite_call_fail"
    return draft_result

def _generate_safe_draft(chart_facts, name="사용자", temperature=0.7, max_retries=1):
    from .ziwei_deep_prompt import build_ziwei_deep_prompt, _scrub_name
    system, base_user = build_ziwei_deep_prompt(chart_facts, name)
    user = base_user
    text = None
    issues = []
    # One initial draft plus at most one semantic retry, with no nested transport retry.
    retries = min(1, max(0, int(max_retries)))
    for attempt in range(1 + retries):
        text = call_llm_with_backoff(system, user, temperature=temperature, max_attempts=1)
        if text:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            text = _convert_ganzhi_to_hangul(text)
        if text is None:
            return {"ok": False, "text": None, "issues": ["LLM 호출 실패"], "retries": attempt, "temperature": temperature}
        ok, issues = safety_check(text, chart_facts)
        if ok:
            return {"ok": True, "text": text, "issues": [], "retries": attempt, "temperature": temperature}
        # Validation may quote a model response; scrub the known name again before a retry.
        note = _scrub_name("\n".join(str(issue) for issue in issues), name)
        user = base_user + "\n\n위반된 규칙 (피해야 할 항목):\n" + note
    return {"ok": False, "text": None, "issues": issues, "retries": retries, "temperature": temperature}
