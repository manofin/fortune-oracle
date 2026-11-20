"""Evidence-linked natal interpretation. Local engines; no LLM, network or storage.

The vocabulary below is a versioned, deliberately small interpretation policy,
not a scientific personality measurement. Agreement means that these rules
use the same reflection theme; it does not mean independent predictive proof.
Only computed cards contribute. Calendar periods and old confidence fields are
never mixed into this natal report.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
import re
from zoneinfo import ZoneInfo

from .oracle_input import from_profile
from .oracle_method_adapters import adapt_all
from .oracle_method_card import OracleMethodCard
from .oracle_renderer import is_calculated_card

METHODS = {"bazi": "사주", "ziwei": "자미두수", "western": "서양 점성술", "vedic": "베딕 점성술"}
THEMES = {"temperament": "기질", "relationships": "관계", "work": "일·학습", "resources": "자원 관리"}
RULE_VERSION = "natal-reflection-1"
METHOD_BACKENDS = {"bazi": "lunar-javascript", "ziwei": "ziwei-iztro-adapter",
                   "western": "skyfield-jpl-de440s", "vedic": "swisseph-moshier"}
BASIS = {
    "bazi": "절기 기준 년·월주와 현지 민간시 일·시주. 미상 시주는 제외하며 진태양시 보정은 적용하지 않습니다.",
    "ziwei": "iztro 양력→음력 변환과 현지 민간 날짜·시각. 진태양시 보정은 적용하지 않습니다.",
    "western": "DE440s 천체력의 지구 중심 겉보기 열대황도. IANA 출생시각을 UTC로 변환합니다.",
    "vedic": "Swiss Ephemeris Moshier의 항성황도·Lahiri 기준. IANA 출생시각을 UTC로 변환합니다.",
}
POLES = {
    "initiative": "표현과 새로운 시도", "structure": "일관성과 안정",
    "connection": "교류와 조율", "reflection": "내면 탐색과 숙고",
    "adaptation": "학습과 유연한 전환",
}
REFLECTIONS = {
    "temperament": "어떤 환경에서 내 방식이 편안하게 드러나는지 돌아보세요.",
    "relationships": "내가 원하는 소통 방식과 상대가 원하는 방식을 구체적으로 나눠 보세요.",
    "work": "작은 과제 하나에서 나에게 맞는 일·학습 방식을 시험해 보세요.",
    "resources": "시간과 에너지를 어디에 쓰는지 기록하고 우선순위를 점검해 보세요.",
}
STEMS = dict(zip("甲乙丙丁戊己庚辛壬癸", "목목화화토토금금수수"))
BRANCHES = dict(zip("子丑寅卯辰巳午未申酉戌亥", "수토목목토화화토금금토수"))
ELEMENT_POLES = {"목": "adaptation", "화": "initiative", "토": "structure", "금": "structure", "수": "reflection"}
WESTERN_SIGNS = ("양자리", "황소자리", "쌍둥이자리", "게자리", "사자자리", "처녀자리", "천칭자리", "전갈자리", "사수자리", "염소자리", "물병자리", "물고기자리")
RASHIS = ("Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena")
SIGN_POLES = ("initiative", "structure", "adaptation", "connection", "initiative", "structure", "connection", "reflection", "adaptation", "structure", "adaptation", "reflection")
PLANET_LABELS = {"Sun": "태양", "Moon": "달", "Venus": "금성", "Mercury": "수성", "Saturn": "토성"}
STAR_POLES = {
    "紫微": "initiative", "天機": "adaptation", "太陽": "connection", "武曲": "structure",
    "天同": "connection", "廉貞": "structure", "天府": "structure", "太陰": "reflection",
    "貪狼": "initiative", "巨門": "reflection", "天相": "connection", "天梁": "connection",
    "七殺": "initiative", "破軍": "adaptation", "文昌": "adaptation", "文曲": "reflection",
    "左輔": "connection", "右弼": "connection",
}
LIMITATIONS = [
    "이 리포트는 출생 성향을 살펴보는 간략한 전통 해석입니다. 오늘·이번 달의 운세나 사건 발생 시기를 계산하지 않습니다.",
    "계산된 간지·별 배치와 성향 해석은 구분됩니다. 해석 규칙은 서비스의 성찰용 분류이며 과학적 성격 진단이나 예측 확률이 아닙니다.",
    "여러 체계의 공통점은 해석 주제의 반복입니다. 독립적인 증거가 늘거나 예측 정확도가 높아졌다는 뜻이 아닙니다.",
    "체계별 황도·역법·해석 기준이 달라 강조점이 다를 수 있습니다. 서로 다른 관점을 하나의 점수로 합치지 않습니다.",
    "이 결과는 출생정보의 파생 데이터이며 익명화된 정보가 아닙니다. 의학·투자·법률 결정을 지시하지 않습니다.",
]


def _number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value < high


def _input(profile):
    """Validate without echoing raw input or consulting a saved profile store."""
    if not isinstance(profile, dict):
        raise ValueError("profile")
    birth_date = profile.get("birth_date")
    birth_time = profile.get("birth_time", "")
    zone = profile.get("timezone")
    if not isinstance(birth_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birth_date):
        raise ValueError("date")
    date.fromisoformat(birth_date)
    if not isinstance(birth_time, str) or (birth_time and not re.fullmatch(r"[0-9]{2}:[0-9]{2}", birth_time)):
        raise ValueError("time")
    if not isinstance(zone, str) or not zone:
        raise ValueError("zone")
    ZoneInfo(zone)
    if birth_time:
        from .birth_clock import resolve_wall_time
        # Python versions may normalize ISO 24:00 to the following day. A birth
        # clock must retain the supplied date and therefore rejects that spelling.
        wall = datetime(*map(int, birth_date.split("-")), *map(int, birth_time.split(":")))
        resolve_wall_time(wall, zone)
    gender = profile.get("gender", "unknown")
    if gender not in {"male", "female", "unknown", ""}:
        raise ValueError("gender")
    clean = {"birth_date": birth_date, "birth_time": birth_time, "timezone": zone, "gender": gender}
    lat, lon = profile.get("latitude"), profile.get("longitude")
    if lat is not None or lon is not None:
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
               or not -limit <= v <= limit for v, limit in ((lat, 90), (lon, 180))):
            raise ValueError("location")
        clean.update(latitude=lat, longitude=lon)
    return clean


class _Findings:
    def __init__(self):
        self.evidence = {}
        self.claims = {key: [] for key in THEMES}

    def add(self, method, theme, anchor, label, value, pole):
        evidence_id = f"{method}.{anchor}"
        self.evidence[evidence_id] = {"id": evidence_id, "method": method, "label": label, "value": value}
        self.claims[theme].append({
            "id": f"{method}.{anchor}.{theme}", "method": method, "time_scope": "natal",
            "rule_id": f"{RULE_VERSION}/{method}/{anchor}/{pole}/{theme}",
            "evidence_ids": [evidence_id], "axis": "approach", "pole": pole,
            "text": f"{METHODS[method]}의 {label} 계산값에 연결된 {THEMES[theme]}의 성찰 주제는 ‘{POLES[pole]}’입니다.",
        })


def _valid_pillar(value):
    return isinstance(value, str) and len(value) == 2 and value[0] in STEMS and value[1] in BRANCHES


def _resource_counts(pillars, elements):
    """Validate adapter counts against all eight known characters, without repair."""
    if not isinstance(elements, dict) or not elements:
        return None
    expected = {element: 0 for element in ELEMENT_POLES}
    for key in ("year", "month", "day", "time"):
        pillar = pillars.get(key)
        if not _valid_pillar(pillar):
            return None
        expected[STEMS[pillar[0]]] += 1
        expected[BRANCHES[pillar[1]]] += 1
    aliases = {key: element for element, char in zip("목화토금수", "木火土金水")
               for key in (element, f"{element}({char})")}
    counts = {element: 0 for element in ELEMENT_POLES}
    for key, value in elements.items():
        if key not in aliases or type(value) is not int or not 0 <= value <= 8:
            return None
        element = aliases[key]
        if value != expected[element]:
            return None
        counts[element] = value
    return counts if counts == expected else None


def _bazi(facts, out, *, time_known):
    pillars = facts.get("eight_char", {})
    if not isinstance(pillars, dict):
        return
    for theme, key, label, part, mapping in (
        ("temperament", "day", "일간 오행", 0, STEMS),
        ("relationships", "day", "일지 오행", 1, BRANCHES),
        ("work", "month", "월지 오행", 1, BRANCHES),
    ):
        pillar = pillars.get(key)
        if _valid_pillar(pillar):
            element = mapping[pillar[part]]
            out.add("bazi", theme, f"{key}_{part}", label, f"{pillar[part]} · {element}", ELEMENT_POLES[element])
    counts = _resource_counts(pillars, facts.get("elements")) if time_known else None
    if counts is not None:
        peak = max(counts.values())
        # Ties remain multiple perspectives; dict order must not select a false winner.
        for element, count in counts.items():
            if count == peak:
                out.add("bazi", "resources", f"elements_{element}", "팔자 오행 개수의 최다 항목",
                        " · ".join(f"{e} {n}개" for e, n in counts.items()), ELEMENT_POLES[element])


def _ziwei(facts, out):
    ming = facts.get("ming_gong", {})
    stars = facts.get("stars_full", facts.get("stars", {}))
    if isinstance(ming, dict) and isinstance(stars, dict):
        index = ming.get("index")
        entries = stars.get(str(index), []) if type(index) is int and 0 <= index < 12 else []
        if isinstance(entries, list):
            for star in entries:
                if star in STAR_POLES:
                    for theme in ("temperament", "relationships"):
                        out.add("ziwei", theme, f"ming_{star}", "명궁에 배치된 별",
                                star, STAR_POLES[star])
    sihua = facts.get("sihua", {})
    if isinstance(sihua, dict):
        for key, theme, label in (("權", "work", "화권의 별"), ("科", "work", "화과의 별"), ("祿", "resources", "화록의 별")):
            entry = sihua.get(key)
            star = entry.get("star") if isinstance(entry, dict) else None
            if star in STAR_POLES:
                out.add("ziwei", theme, f"sihua_{key}", label, star, STAR_POLES[star])


def _astrology(method, facts, out):
    rows = facts.get("planet_positions" if method == "western" else "graha_positions", [])
    if not isinstance(rows, list):
        return
    planets = {row.get("name"): row for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)}
    for theme, planet in (("temperament", "Sun" if method == "western" else "Moon"),
                          ("relationships", "Venus"), ("work", "Mercury"), ("resources", "Saturn")):
        row = planets.get(planet, {})
        if method == "western":
            longitude = row.get("longitude")
            if not _number(longitude, 0, 360):
                continue
            index, degree = int(longitude // 30), longitude % 30
            value = f"열대황도 {WESTERN_SIGNS[index]} {degree:.2f}°"
        else:
            rashi, degree = row.get("rashi"), row.get("degree")
            if rashi not in RASHIS or not _number(degree, 0, 30):
                continue
            index = RASHIS.index(rashi)
            value = f"항성황도 {rashi} {degree:.2f}°"
        out.add(method, theme, planet.lower(), f"{PLANET_LABELS[planet]}의 별자리", value, SIGN_POLES[index])


def _compare(claims):
    groups = defaultdict(list)
    for claim in claims:
        groups[claim["pole"]].append(claim)
    agreements = []
    for pole, group in groups.items():
        methods = [m for m in METHODS if any(c["method"] == m for c in group)]
        if len(methods) >= 2:
            agreements.append({"text": f"{'·'.join(METHODS[m] for m in methods)}에서 ‘{POLES[pole]}’ 주제가 반복됩니다.",
                               "methods": methods, "claim_ids": [c["id"] for c in group]})
    differences = []
    if len(groups) >= 2 and len({c["method"] for c in claims}) >= 2:
        labels = []
        for pole, group in groups.items():
            names = [METHODS[m] for m in METHODS if any(c["method"] == m for c in group)]
            labels.append(f"{'·'.join(names)}는 ‘{POLES[pole]}’")
        differences.append({"text": "강조점이 다릅니다: " + "; ".join(labels) + ". 어느 한쪽이 정답이라는 뜻은 아닙니다.",
                            "methods": [m for m in METHODS if any(c["method"] == m for c in claims)],
                            "claim_ids": [c["id"] for c in claims]})
    return agreements, differences


def _render(report):
    lines = [report["title"], "출생 성향 · 계산 근거가 연결된 성찰용 해석", "", *report["summary"], "", "계산 범위"]
    for method in report["methods"]:
        lines.append(f"{method['label']}: {method['reason']}")
        if method["used_in_reading"]:
            lines.append(method["calculation_basis"])
    for theme in report["themes"]:
        lines.extend(["", theme["title"], theme["summary"]])
        lines.extend(item["text"] for item in theme["agreements"] + theme["differences"]
                     if item["text"] != theme["summary"])
        lines.extend(claim["text"] for claim in theme["claims"])
        lines.append(theme["reflection"])
    lines.extend(["", "해석의 계산 근거"])
    for evidence in report["evidence"]:
        lines.append(f"[{evidence['id']}] {METHODS[evidence['method']]} · {evidence['label']}: {evidence['value']}")
    lines.extend(["", "읽기 전에 알아둘 점", *report["limitations"]])
    return "\n".join(lines)


def _input_exclusion(method, inp):
    if inp is None:
        return "유효한 출생일·시각 형식·시간대가 필요합니다. 원문 입력을 다시 확인해 주세요."
    if method in {"ziwei", "western", "vedic"} and not inp.has_birth_time:
        return "출생시각 미상으로 시간에 의존하는 계산을 제외했습니다."
    if method == "ziwei" and inp.gender not in {"male", "female"}:
        return "전통 계산에 사용할 성별이 지정되지 않아 제외했습니다."
    return None


def build_integrated_report(profile=None):
    """Return all four statuses and an evidence-linked natal report, without persistence."""
    valid = True
    try:
        clean = _input(profile)
        inp = from_profile(clean)
    except Exception:
        valid, clean, inp = False, {}, None
    # Keep eligibility tied to the validated caller input, even if an adapter
    # returns stale computed facts or mutates its own input object.
    exclusions = {method: _input_exclusion(method, inp) for method in METHODS}
    time_known = bool(inp and inp.has_birth_time)
    try:
        cards = adapt_all(inp, profile=clean) if valid else []
    except Exception:
        cards = []
    if not isinstance(cards, (list, tuple)):
        cards = []
    by_method = {c.method: c for c in cards if isinstance(c, OracleMethodCard)
                 and isinstance(c.method, str) and c.method in METHODS}
    findings = _Findings()
    methods = []
    for method, label in METHODS.items():
        card = by_method.get(method)
        staged = _Findings()
        try:
            calculated = bool(not exclusions[method] and card and isinstance(card.backend, str)
                              and card.backend == METHOD_BACKENDS[method] and is_calculated_card(card))
        except (TypeError, ValueError, AttributeError, KeyError):
            calculated = False
        if calculated:
            try:
                if method == "bazi":
                    _bazi(card.facts, staged, time_known=time_known)
                elif method == "ziwei":
                    _ziwei(card.facts, staged)
                else:
                    _astrology(method, card.facts, staged)
            except (TypeError, ValueError, KeyError, AttributeError):
                # Atomic per-method findings: do not retain a half-extracted chart.
                staged = _Findings()
        used = any(staged.claims.values())
        findings.evidence.update(staged.evidence)
        for theme in THEMES:
            findings.claims[theme].extend(staged.claims[theme])
        status = ("ready" if used and card.status == "runnable" and (method != "bazi" or time_known)
                  else "partial" if used else "unavailable")
        reason = "계산된 출생 자료를 해석에 사용했습니다."
        if exclusions[method]:
            reason = exclusions[method]
        elif card and card.calculation_mode == "approximate":
            reason = "근사 계산은 통합 해석의 근거에 포함하지 않습니다."
        elif not used:
            reason = "계산 엔진·자료를 사용할 수 없거나 현재 해석 규칙에 필요한 계산값이 부족합니다."
        elif status == "partial":
            reason = "계산 가능한 출생 자료만 사용했습니다. 시각·위치 또는 일부 계산 항목이 제한됩니다."
        engine_status = card.status if card and isinstance(card.status, str) and card.status in {"runnable", "partial", "blocked"} else "blocked"
        mode = card.calculation_mode if card and isinstance(card.calculation_mode, str) and card.calculation_mode in {"computed", "approximate"} else "unknown"
        backend = card.backend if card and isinstance(card.backend, str) and card.backend == METHOD_BACKENDS[method] else "unavailable"
        methods.append({"method": method, "label": label, "status": status, "used_in_reading": used,
                        "engine_status": engine_status, "calculation_mode": mode, "backend": backend,
                        "calculation_basis": BASIS[method] if used else "해석에 사용하지 않았습니다.",
                        "reason": reason})
    themes = []
    for theme_id, title in THEMES.items():
        claims = findings.claims[theme_id]
        agreements, differences = _compare(claims)
        summary = (agreements[0]["text"] if agreements else
                   "체계별 관점을 함께 살펴보세요." if len({c["method"] for c in claims}) > 1 else
                   "현재 한 체계의 근거만 있어 체계 간 공통점은 판단하지 않습니다." if claims else
                   "현재 계산 자료로 이 주제를 해석하지 않습니다.")
        themes.append({"id": theme_id, "title": title, "summary": summary, "agreements": agreements,
                       "differences": differences, "claims": claims, "reflection": REFLECTIONS[theme_id] if claims else ""})
    used_count = sum(m["used_in_reading"] for m in methods)
    summary = [f"네 체계 중 {used_count}개 체계의 계산 근거를 사용했습니다."]
    for theme in themes:
        if theme["agreements"]:
            summary.append(f"{theme['title']}: {theme['agreements'][0]['text']}")
        if len(summary) == 3:
            break
    if len(summary) == 1:
        summary.append("공통 해석을 억지로 만들지 않고, 확인된 관점과 제한사항을 함께 보여드립니다.")
    limitations = list(LIMITATIONS)
    if any(m["used_in_reading"] and m["method"] == "ziwei" for m in methods):
        limitations.append("자미두수는 입력한 현지 민간 날짜·시각을 iztro의 양력→음력 변환에 사용합니다. 진태양시 보정이나 다른 시간대로의 날짜 이동을 적용하지 않습니다.")
    report = {"ok": used_count > 0, "computed": used_count > 0, "kind": "integrated", "schema_version": 1,
              "rule_version": RULE_VERSION, "scope": "natal", "title": "네 관점으로 읽는 나의 성향",
              "summary": summary, "methods": methods, "themes": themes,
              "evidence": list(findings.evidence.values()), "limitations": limitations}
    report["text"] = _render(report)
    return report
