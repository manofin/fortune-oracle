"""Natal report boundaries, actual engine regressions and evidence contracts."""
from copy import deepcopy
import json
import math

import pytest

from hermes_ext.fortune_oracle import integrated_report as report
from hermes_ext.fortune_oracle.oracle_input import from_profile
from hermes_ext.fortune_oracle.oracle_method_card import OracleMethodCard
from hermes_ext.fortune_oracle.oracle_method_adapters import adapt_ziwei


PROFILE = {"birth_date": "1996-04-18", "birth_time": "09:30", "timezone": "Asia/Seoul", "gender": "female"}


def card(method, facts, mode="computed", status="runnable"):
    backends = {"bazi": "lunar-javascript", "ziwei": "ziwei-iztro-adapter", "western": "skyfield-jpl-de440s", "vedic": "swisseph-moshier"}
    return OracleMethodCard(method=method, status=status, backend=backends[method], calculation_mode=mode, facts=facts)


def four_cards():
    return [
        card("bazi", {"eight_char": {"year": "甲子", "month": "甲寅", "day": "甲寅", "time": "己巳"},
                      "elements": {"목(木)": 4, "화(火)": 1, "토(土)": 2, "수(水)": 1}}),
        card("ziwei", {"ming_gong": {"index": 0, "branch": "子"}, "stars": {"0": ["天機", "破軍"]},
                       "sihua": {"權": {"star": "天機"}, "科": {"star": "文昌"}, "祿": {"star": "天機"}}}),
        card("western", {"planet_positions": [{"name": n, "longitude": 65.0} for n in ("Sun", "Venus", "Mercury", "Saturn")]}),
        card("vedic", {"graha_positions": [{"name": n, "rashi": "Mithuna", "degree": 5.0} for n in ("Moon", "Venus", "Mercury", "Saturn")]}),
    ]


@pytest.mark.parametrize("bad", [None, {}, {**PROFILE, "birth_date": "2026-02-30"},
    {**PROFILE, "birth_date": "1996-4-18"}, {**PROFILE, "birth_time": "24:00"},
    {**PROFILE, "birth_time": "9:30"}, {**PROFILE, "birth_time": None},
    {**PROFILE, "timezone": "Invalid/Zone"}, {**PROFILE, "timezone": ""},
    {**PROFILE, "gender": []}, {**PROFILE, "latitude": 37.0},
    {**PROFILE, "latitude": float("nan"), "longitude": 127.0},
    {**PROFILE, "latitude": True, "longitude": 127.0},
    {**PROFILE, "latitude": 90.000000001, "longitude": 127.0},
    {**PROFILE, "birth_date": "2024-11-03", "birth_time": "01:30", "timezone": "America/New_York"},
    {**PROFILE, "birth_date": "2024-03-10", "birth_time": "02:30", "timezone": "America/New_York"},
])
def test_invalid_or_ambiguous_input_never_reaches_an_engine(monkeypatch, bad):
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: pytest.fail("Invalid input must stop before engine calls"))
    result = report.build_integrated_report(bad)
    assert not result["computed"] and not result["ok"]
    assert len(result["methods"]) == 4 and not result["evidence"]
    assert all(not t["claims"] and not t["reflection"] for t in result["themes"])
    assert "score" not in result


@pytest.mark.parametrize("coords", [(90.0, 180.0), (-90.0, -180.0), (0.0, 0.0)])
def test_inclusive_coordinate_boundaries_pass_without_guessing(monkeypatch, coords):
    seen = []
    monkeypatch.setattr(report, "adapt_all", lambda inp, **_kw: seen.append((inp.latitude, inp.longitude)) or [])
    report.build_integrated_report({**PROFILE, "latitude": coords[0], "longitude": coords[1]})
    assert seen == [coords]


def test_real_unknown_time_ziwei_regression_never_calls_bridge(monkeypatch):
    from hermes_ext.fortune_oracle import ziwei_bridge
    monkeypatch.setattr(ziwei_bridge, "calculate_ziwei_chart", lambda **_kw: pytest.fail("Must not calculate unknown hour as midnight"))
    inp = from_profile({**PROFILE, "birth_time": ""})
    assert not inp.sufficient_for_ziwei
    result = adapt_ziwei(inp)
    assert result.status == "blocked" and not result.facts


def test_explicit_midnight_is_valid_and_missing_location_is_not_seoul(monkeypatch):
    from hermes_ext.fortune_oracle import ziwei_bridge
    seen = []
    def calculate(**kwargs):
        seen.append(kwargs)
        return {"ok": True, "stars": {"0": ["天機"]}, "ming_gong": {"index": 0, "branch": "子"}, "sihua": {}}
    monkeypatch.setattr(ziwei_bridge, "calculate_ziwei_chart", calculate)
    monkeypatch.setattr(ziwei_bridge, "calculate_ziwei_daxian", lambda **_kw: {"ok": False})
    inp = from_profile({**PROFILE, "birth_time": "00:00"})
    assert inp.sufficient_for_ziwei
    result = adapt_ziwei(inp)
    assert seen[0]["birth_time"] == "00:00" and seen[0]["longitude"] is None
    assert result.status == "partial"
    assert result.facts["time_basis"]["true_solar_time"] is False


def test_unknown_gender_is_not_assigned_by_ziwei(monkeypatch):
    from hermes_ext.fortune_oracle import ziwei_bridge
    monkeypatch.setattr(ziwei_bridge, "calculate_ziwei_chart", lambda **_kw: pytest.fail("No guessed gender"))
    assert adapt_ziwei(from_profile({**PROFILE, "gender": "unknown"})).status == "blocked"


def test_real_iztro_minor_star_mutagen_survives_bridge():
    from hermes_ext.fortune_oracle.ziwei_bridge import calculate_ziwei_chart
    result = calculate_ziwei_chart("1990-01-01", "12:00", gender="male", longitude=None)
    assert result["ok"]
    assert set(result["sihua"]) == {"lu", "quan", "ke", "ji"}
    assert result["sihua"]["ji"]["star"] == "文曲"
    assert result["sihua"]["ji"]["palace_index"] == 10


def test_roundtrip_evidence_contract_and_no_private_input(monkeypatch):
    seen = []
    def engine(inp, profile):
        seen.append(profile)
        return four_cards()
    monkeypatch.setattr(report, "adapt_all", engine)
    private = {**PROFILE, "display_name": "SYNTHETIC_PRIVATE_NAME", "birth_place": "SYNTHETIC_PRIVATE_PLACE",
               "latitude": 37.5665, "longitude": 126.978}
    before = deepcopy(private)
    result = report.build_integrated_report(private)
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    assert json.loads(encoded) == result
    assert private == before
    assert "display_name" not in seen[0] and "birth_place" not in seen[0]
    for raw in (private["display_name"], private["birth_place"], private["birth_date"], private["birth_time"], "37.5665", "126.978"):
        assert raw not in encoded
    assert result["computed"] and result["scope"] == "natal" and result["schema_version"] == 1
    assert [m["method"] for m in result["methods"]] == list(report.METHODS)
    assert all(m["used_in_reading"] for m in result["methods"])
    evidence = {e["id"]: e for e in result["evidence"]}
    for theme in result["themes"]:
        ids = {c["id"] for c in theme["claims"]}
        for claim in theme["claims"]:
            assert claim["text"] in result["text"]
            assert claim["time_scope"] == "natal"
            assert claim["rule_id"].startswith(report.RULE_VERSION)
            assert claim["evidence_ids"] and all(evidence[i]["method"] == claim["method"] for i in claim["evidence_ids"])
        for comparison in theme["agreements"] + theme["differences"]:
            assert set(comparison["claim_ids"]) <= ids
            assert len(set(comparison["methods"])) >= 2
    assert all(e["value"] in result["text"] for e in evidence.values())
    assert "예측 정확도가 높아졌다는 뜻이 아닙니다" in result["text"]


def test_mixed_version_approximate_and_missing_provenance_are_excluded(monkeypatch):
    cards = four_cards()
    cards[2].backend = ""  # old card without computation provenance
    cards[3].calculation_mode = "approximate"
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: cards)
    result = report.build_integrated_report(PROFILE)
    assert [m["method"] for m in result["methods"] if m["used_in_reading"]] == ["bazi", "ziwei"]
    assert all(e["method"] not in {"western", "vedic"} for e in result["evidence"])
    assert "근사 계산은" in result["methods"][3]["reason"]
    assert all(len(c["methods"]) <= 2 for t in result["themes"] for c in t["agreements"])


@pytest.mark.parametrize("backend", ["builtin-vedic", "skyfield-jpl-de440s", "unrecognized-engine", [], None])
def test_stale_or_mismatched_vedic_backend_cannot_claim_verified_computation(monkeypatch, backend):
    cards = four_cards()
    cards[3].backend = backend
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: cards)
    result = report.build_integrated_report(PROFILE)
    vedic = result["methods"][3]
    assert not vedic["used_in_reading"] and vedic["backend"] == "unavailable"
    assert "Lahiri" not in vedic["calculation_basis"]
    assert not any(e["method"] == "vedic" for e in result["evidence"])


@pytest.mark.parametrize("attribute", ["method", "status", "calculation_mode"])
def test_malformed_metadata_isolated_from_other_methods(monkeypatch, attribute):
    cards = four_cards()
    setattr(cards[3], attribute, [])
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: cards)
    result = report.build_integrated_report(PROFILE)
    assert result["ok"]
    assert not result["methods"][3]["used_in_reading"]
    json.dumps(result, allow_nan=False)


def test_same_method_multiple_claims_are_not_multiple_supporting_systems(monkeypatch):
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: [four_cards()[1]])
    result = report.build_integrated_report(PROFILE)
    assert result["computed"]
    assert all(not t["agreements"] and not t["differences"] for t in result["themes"])


def test_different_perspectives_are_retained_without_forced_consensus(monkeypatch):
    cards = four_cards()
    for row in cards[2].facts["planet_positions"]:
        row["longitude"] = 35.0  # stability, other supplied cards emphasize adaptation
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: cards)
    result = report.build_integrated_report(PROFILE)
    theme = result["themes"][0]
    assert theme["agreements"] and theme["differences"]
    assert "western" not in theme["agreements"][0]["methods"]
    assert "western" in theme["differences"][0]["methods"]


@pytest.mark.parametrize("malformed", [None, [], {"stars": {"0": ["天機", []]}, "ming_gong": {"index": 0}},
    {"planet_positions": [{"name": "Sun", "longitude": math.nan}]}, {"eight_char": {"day": 4}}])
def test_malformed_method_facts_do_not_break_or_partially_pollute_report(monkeypatch, malformed):
    bad = card("ziwei", malformed)
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: [four_cards()[0], bad])
    result = report.build_integrated_report(PROFILE)
    assert result["ok"]
    assert not next(m for m in result["methods"] if m["method"] == "ziwei")["used_in_reading"]
    assert all(e["method"] == "bazi" for e in result["evidence"])


def test_engine_exception_cannot_leak_inputs_or_create_a_score(monkeypatch):
    def fail(*_a, **_kw):
        raise RuntimeError("SYNTHETIC_PRIVATE_NAME 1996-04-18 secret payload")
    monkeypatch.setattr(report, "adapt_all", fail)
    result = report.build_integrated_report(PROFILE)
    assert not result["ok"] and not result["evidence"]
    assert "PRIVATE" not in result["text"] and "secret payload" not in result["text"]


def test_natal_report_is_independent_of_current_dasha_and_arbitrary_confidence(monkeypatch):
    cards = four_cards()
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: cards)
    before = report.build_integrated_report(PROFILE)
    cards[1].facts["current_daxian"] = {"year": 3000, "label": "PRIVATE_PERIOD"}
    cards[3].facts["dasha"] = "PRIVATE_PERIOD"
    for c in cards:
        c.confidence = 0.9999
    assert report.build_integrated_report(PROFILE) == before


def test_bazi_unknown_time_keeps_only_calculated_natal_parts():
    result = report.build_integrated_report({**PROFILE, "birth_time": ""})
    assert result["ok"]
    used = [m for m in result["methods"] if m["used_in_reading"]]
    assert [m["method"] for m in used] == ["bazi"]
    assert used[0]["status"] == "partial"
    assert all(not t["agreements"] for t in result["themes"])


@pytest.mark.parametrize("day,element,pole,opening", [
    ("丁卯", "목", "adaptation", "의견이 다르다면,"),
    ("甲午", "화", "initiative", "마음을 전할 일이 있다면,"),
    ("甲辰", "토", "structure", "함께 약속을 정한다면,"),
    ("甲申", "금", "structure", "서로 원하는 것이 다르다면,"),
    ("甲子", "수", "reflection", "바로 답하기 어렵다면,"),
])
def test_relationship_practice_uses_the_calculated_day_branch_without_a_trait_claim(monkeypatch, day, element, pole, opening):
    bazi = four_cards()[0]
    bazi.facts["eight_char"]["day"] = day
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: [bazi])
    result = report.build_integrated_report(PROFILE)
    theme = next(item for item in result["themes"] if item["id"] == "relationships")
    assert len(theme["claims"]) == 1
    claim = theme["claims"][0]
    assert claim["text"].startswith(opening)
    assert f"계산된 일지 {day[1]}({element})" in claim["text"]
    assert "실제 관계나 성격을 확인한 결과는 아닙니다" in claim["text"]
    assert claim["pole"] == pole
    assert claim["rule_id"] == f"natal-reflection-1/bazi/day_1/{pole}/relationships"
    assert claim["evidence_ids"] == ["bazi.day_1"]
    evidence = next(item for item in result["evidence"] if item["id"] == "bazi.day_1")
    assert evidence["value"] == f"{day[1]} · {element}"
    if element == "목":
        assert "상대가 중요하게 보는 점을 하나 물어보세요" in claim["text"]
    assert result["text"].count(claim["text"]) == 1
    assert not theme["agreements"] and not theme["differences"]


@pytest.mark.parametrize("day", [None, "", "甲", "甲?", []])
def test_missing_day_branch_does_not_receive_a_relationship_practice(monkeypatch, day):
    bazi = four_cards()[0]
    bazi.facts["eight_char"]["day"] = day
    monkeypatch.setattr(report, "adapt_all", lambda *_a, **_kw: [bazi])
    result = report.build_integrated_report(PROFILE)
    theme = next(item for item in result["themes"] if item["id"] == "relationships")
    assert not theme["claims"] and not theme["reflection"]
    assert not any(item["id"] == "bazi.day_1" for item in result["evidence"])
    assert all(text not in result["text"] for text in report.BAZI_RELATIONSHIP_PRACTICE.values())
