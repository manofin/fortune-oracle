"""Computed adapter facts still need validated anchors and actual input eligibility."""
from copy import deepcopy
import json

import pytest

from hermes_ext.fortune_oracle import integrated_report as report
from hermes_ext.fortune_oracle.oracle_input import from_profile
from hermes_ext.fortune_oracle.oracle_method_adapters import adapt_bazi
from hermes_ext.fortune_oracle.oracle_method_card import OracleMethodCard


PROFILE = {"birth_date": "1996-04-18", "birth_time": "09:30", "timezone": "Asia/Seoul", "gender": "female"}
PRIVATE_MARKER = "SYNTHETIC_ADAPTER_PRIVATE_METADATA"
BACKENDS = {"bazi": "lunar-javascript", "ziwei": "ziwei-iztro-adapter",
            "western": "skyfield-jpl-de440s", "vedic": "swisseph-moshier"}
COUNTS = {"목": 5, "화": 1, "토": 1, "금": 0, "수": 1}


def card(method, facts):
    return OracleMethodCard(method=method, status="runnable", calculation_mode="computed",
                            backend=BACKENDS[method], facts=facts, interpretation=PRIVATE_MARKER)


def bazi_facts():
    return {"eight_char": {"year": "甲子", "month": "甲寅", "day": "甲寅", "time": "己巳"},
            "elements": COUNTS.copy(), "arbitrary_metadata": PRIVATE_MARKER}


def complete_cards():
    return [card("bazi", bazi_facts()),
            card("ziwei", {"ming_gong": {"index": 0}, "stars": {"0": ["天機"]},
                           "sihua": {"權": {"star": "文昌"}}}),
            card("western", {"planet_positions": [{"name": "Sun", "longitude": 65.0}]}),
            card("vedic", {"graha_positions": [{"name": "Moon", "rashi": "Mithuna", "degree": 5.0}]})]


def build(monkeypatch, cards, profile=None):
    monkeypatch.setattr(report, "adapt_all", lambda *_args, **_kwargs: cards)
    return report.build_integrated_report(PROFILE if profile is None else profile)


def claims(result, method=None, theme=None):
    return [claim for section in result["themes"] if theme is None or section["id"] == theme
            for claim in section["claims"] if method is None or claim["method"] == method]


def method(result, name):
    return next(row for row in result["methods"] if row["method"] == name)


def assert_links_and_usage(result):
    evidence = {row["id"]: row for row in result["evidence"]}
    all_claims = claims(result)
    assert result["computed"] == result["ok"] == bool(all_claims)
    assert set(evidence) == {key for claim in all_claims for key in claim["evidence_ids"]}
    for name in BACKENDS:
        used = bool(claims(result, name))
        row = method(result, name)
        assert row["used_in_reading"] == used
        assert (row["status"] in {"ready", "partial"}) == used
        assert bool([item for item in evidence.values() if item["method"] == name]) == used
        if not used:
            assert row["calculation_basis"] == "해석에 사용하지 않았습니다."
    for section in result["themes"]:
        ids = {claim["id"] for claim in section["claims"]}
        for item in section["agreements"] + section["differences"]:
            assert set(item["claim_ids"]) <= ids
    assert PRIVATE_MARKER not in json.dumps(result, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("elements", [
    {element: 8 for element in COUNTS},
    {"목": 4, "화": 1, "토": 2, "금": 0, "수": 1},  # Total 8 still contradicts its pillars.
    {**COUNTS, "목(木)": 4},
    {**COUNTS, "목": True}, {**COUNTS, "목": 5.0}, {**COUNTS, "목": "5"},
    {**COUNTS, "목": -1}, {**COUNTS, "목": 9}, {**COUNTS, "목": None},
    {**COUNTS, "unrecognized": 8}, {"목": 5}, {}, None, [],
])
def test_contradictory_or_malformed_counts_cannot_be_repaired_into_resource_claims(monkeypatch, elements):
    facts = bazi_facts()
    facts["elements"] = elements
    before = deepcopy(facts)
    result = build(monkeypatch, [card("bazi", facts)])
    assert not claims(result, "bazi", "resources")
    assert not any(item["id"].startswith("bazi.elements_") for item in result["evidence"])
    assert {claim["id"] for claim in claims(result)} == {
        "bazi.day_0.temperament", "bazi.day_1.relationships", "bazi.month_1.work"}
    assert facts == before
    assert_links_and_usage(result)


@pytest.mark.parametrize("elements", [
    COUNTS,
    {"목(木)": 5, "화(火)": 1, "토(土)": 1, "수(水)": 1},
    {"목": 5, "화(火)": 1, "토": 1, "수(水)": 1},
    {**COUNTS, "목(木)": 5},
])
def test_consistent_counts_accept_supported_aliases_and_omitted_zeroes(monkeypatch, elements):
    facts = bazi_facts()
    facts["elements"] = deepcopy(elements)
    result = build(monkeypatch, [card("bazi", facts)])
    assert [claim["id"] for claim in claims(result, "bazi", "resources")] == ["bazi.elements_목.resources"]
    evidence = next(item for item in result["evidence"] if item["id"] == "bazi.elements_목")
    assert evidence["value"] == "목 5개 · 화 1개 · 토 1개 · 금 0개 · 수 1개"
    assert_links_and_usage(result)


@pytest.mark.parametrize("key", ["day", "month"])
@pytest.mark.parametrize("pillar", ["?寅", "甲?", "子甲", "甲寅多", "甲", "", None, 4, False, [], {}])
def test_bazi_anchor_requires_both_recognized_characters(monkeypatch, key, pillar):
    facts = bazi_facts()
    facts["eight_char"][key] = pillar
    before = deepcopy(facts)
    result = build(monkeypatch, [card("bazi", facts)])
    # The existing computed-card gate requires a valid day before any Bazi
    # extraction. A bad month must still preserve the independently valid day.
    expected = set() if key == "day" else {"bazi.day_0.temperament", "bazi.day_1.relationships"}
    assert {claim["id"] for claim in claims(result)} == expected
    assert facts == before
    assert_links_and_usage(result)


@pytest.mark.parametrize("key", ["year", "time"])
@pytest.mark.parametrize("pillar", ["?寅", "甲?", "", None])
def test_resource_counts_require_all_four_complete_pillars(monkeypatch, key, pillar):
    facts = bazi_facts()
    facts["eight_char"][key] = pillar
    result = build(monkeypatch, [card("bazi", facts)])
    assert len(claims(result, "bazi")) == 3
    assert not claims(result, "bazi", "resources")
    assert_links_and_usage(result)


def test_partial_day_facts_remain_usable_without_fabricating_month_or_resources(monkeypatch):
    result = build(monkeypatch, [card("bazi", {"eight_char": {"day": "甲寅"}, "elements": COUNTS.copy()})])
    assert {claim["id"] for claim in claims(result)} == {"bazi.day_0.temperament", "bazi.day_1.relationships"}
    assert_links_and_usage(result)


def test_consistent_peak_ties_retain_all_original_resource_perspectives(monkeypatch):
    facts = {"eight_char": {"year": "甲子", "month": "丙寅", "day": "戊午", "time": "庚申"},
             "elements": {"목": 2, "화": 2, "토": 1, "금": 2, "수": 1}}
    result = build(monkeypatch, [card("bazi", facts)])
    assert {claim["id"] for claim in claims(result, "bazi", "resources")} == {
        "bazi.elements_목.resources", "bazi.elements_화.resources", "bazi.elements_금.resources"}
    assert_links_and_usage(result)


@pytest.mark.parametrize("star_field", ["stars", "stars_full"])
@pytest.mark.parametrize("index", [-1, 12, 99, True, False, 0.0, 11.0, "0", "11", None, [], {}])
def test_ziwei_cannot_use_noninteger_or_out_of_range_palace(monkeypatch, star_field, index):
    facts = {"ming_gong": {"index": index}, "stars": {"0": ["天機"]},
             star_field: {str(index): ["天機"]}, "metadata": PRIVATE_MARKER}
    before = deepcopy(facts)
    result = build(monkeypatch, [card("ziwei", facts)])
    assert not claims(result) and not result["evidence"]
    assert method(result, "ziwei")["status"] == "unavailable"
    assert facts == before
    assert_links_and_usage(result)


@pytest.mark.parametrize("index", [0, 11])
def test_ziwei_accepts_both_real_palace_boundaries(monkeypatch, index):
    facts = {"ming_gong": {"index": index}, "stars": {str(index): ["天機"]},
             "stars_full": {str(index): ["天機"]}}
    result = build(monkeypatch, [card("ziwei", facts)])
    assert {claim["id"] for claim in claims(result)} == {
        "ziwei.ming_天機.temperament", "ziwei.ming_天機.relationships"}
    assert method(result, "ziwei")["status"] == "ready"
    assert_links_and_usage(result)


@pytest.mark.parametrize("ming", [None, [], {}, {"index": None}])
def test_missing_or_malformed_palace_cannot_be_looked_up_by_stringified_none(monkeypatch, ming):
    result = build(monkeypatch, [card("ziwei", {"ming_gong": ming, "stars": {"None": ["天機"]}})])
    assert not claims(result) and not result["evidence"]
    assert_links_and_usage(result)


def test_bad_life_palace_does_not_discard_independent_valid_sihua(monkeypatch):
    facts = {"ming_gong": {"index": 99}, "stars": {"99": ["天機"]},
             "sihua": {"權": {"star": "文昌"}}}
    result = build(monkeypatch, [card("ziwei", facts)])
    assert [claim["id"] for claim in claims(result)] == ["ziwei.sihua_權.work"]
    assert [item["id"] for item in result["evidence"]] == ["ziwei.sihua_權"]
    assert_links_and_usage(result)


def test_unknown_time_blocks_stale_cards_before_extract_and_keeps_bazi_partial(monkeypatch):
    cards = complete_cards()
    before = deepcopy(cards)
    original_gate = report.is_calculated_card
    def input_eligible_gate(item):
        assert item.method == "bazi", "Excluded methods must stop before inspecting adapter facts"
        return original_gate(item)
    monkeypatch.setattr(report, "is_calculated_card", input_eligible_gate)
    monkeypatch.setattr(report, "_ziwei", lambda *_args: pytest.fail("Unknown time must stop before Ziwei extraction"))
    monkeypatch.setattr(report, "_astrology", lambda *_args: pytest.fail("Unknown time must stop before astrology extraction"))
    result = build(monkeypatch, cards, {**PROFILE, "birth_time": ""})
    assert {claim["method"] for claim in claims(result)} == {"bazi"}
    assert not claims(result, "bazi", "resources")
    assert method(result, "bazi")["status"] == "partial"
    assert "계산 가능한" in method(result, "bazi")["reason"]
    for name in ("ziwei", "western", "vedic"):
        row = method(result, name)
        assert row["status"] == "unavailable" and not row["used_in_reading"]
        assert "출생시각 미상" in row["reason"]
    assert cards == before
    assert_links_and_usage(result)


@pytest.mark.parametrize("name", ["ziwei", "western", "vedic"])
def test_excluded_stale_card_alone_cannot_make_report_computed(monkeypatch, name):
    stale = next(item for item in complete_cards() if item.method == name)
    result = build(monkeypatch, [stale], {**PROFILE, "birth_time": ""})
    assert not result["computed"] and not result["ok"]
    assert not result["evidence"] and not claims(result)
    assert all(not section["reflection"] for section in result["themes"])
    assert_links_and_usage(result)


@pytest.mark.parametrize("gender", ["unknown", "", None])
def test_unknown_or_absent_gender_excludes_only_ziwei_stale_claims(monkeypatch, gender):
    profile = PROFILE.copy()
    if gender is None:
        profile.pop("gender")
    else:
        profile["gender"] = gender
    before = deepcopy(profile)
    result = build(monkeypatch, complete_cards(), profile)
    assert not claims(result, "ziwei")
    assert method(result, "ziwei")["status"] == "unavailable"
    assert "성별이 지정되지 않아" in method(result, "ziwei")["reason"]
    assert all(method(result, name)["used_in_reading"] for name in ("bazi", "western", "vedic"))
    assert profile == before
    assert_links_and_usage(result)


@pytest.mark.parametrize("gender", ["male", "female"])
def test_explicit_midnight_and_known_gender_keep_healthy_claims(monkeypatch, gender):
    result = build(monkeypatch, complete_cards(), {**PROFILE, "birth_time": "00:00", "gender": gender})
    assert all(row["status"] == "ready" and row["used_in_reading"] for row in result["methods"])
    assert claims(result, "bazi", "resources")
    assert_links_and_usage(result)


def test_eligibility_remains_tied_to_original_validated_input_when_adapter_mutates_its_copy(monkeypatch):
    profile = {**PROFILE, "birth_time": "", "gender": "unknown", "display_name": PRIVATE_MARKER}
    before = deepcopy(profile)
    cards = complete_cards()
    def stale_adapter(inp, profile):
        inp.birth_datetime = "1996-04-18T09:30"
        inp.gender = "female"
        profile.update(birth_time="09:30", gender="female")
        return cards
    monkeypatch.setattr(report, "adapt_all", stale_adapter)
    result = report.build_integrated_report(profile)
    assert {claim["method"] for claim in claims(result)} == {"bazi"}
    assert not claims(result, "bazi", "resources")
    assert method(result, "bazi")["status"] == "partial"
    assert profile == before
    assert_links_and_usage(result)


def test_actual_bazi_adapter_retains_consistent_resource_evidence(monkeypatch):
    calculated = adapt_bazi(from_profile(PROFILE))
    assert calculated.calculation_mode == "computed" and calculated.status == "runnable"
    before = deepcopy(calculated)
    result = build(monkeypatch, [calculated])
    assert claims(result, "bazi", "resources")
    assert method(result, "bazi")["status"] == "ready"
    assert calculated == before
    assert_links_and_usage(result)
