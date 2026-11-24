"""Synthetic pillar fixtures only; no birth records or external services."""

from copy import deepcopy
from itertools import combinations
import json

import pytest

from hermes_ext.fortune_oracle.natal_markers import evaluate_natal_markers


POSITIONS = ("year", "month", "day", "time")
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


def chart(*branches):
    """Valid individual sexagenary pillars; not asserted to be a birth chart."""
    return {position: ("甲" if BRANCHES.index(branch) % 2 == 0 else "乙") + branch
            for position, branch in zip(POSITIONS, branches)}


def rules(result):
    return {rule["id"]: rule for rule in result["rules"]}


def negative_chart():
    return chart("寅", "辰", "戌", "寅")


def test_complete_negative_has_versioned_json_contract_without_invented_rules():
    result = evaluate_natal_markers(negative_chart())
    assert set(result) == {"schema_version", "rule_version", "coverage", "rules"}
    assert result["schema_version"] == 1
    assert result["rule_version"] == "natal-markers-v1"
    assert result["coverage"] == {
        "expected_positions": list(POSITIONS), "available_positions": list(POSITIONS),
        "missing_positions": [], "invalid_positions": [], "complete": True,
    }
    assert [rule["id"] for rule in result["rules"]] == [
        "wonjin_all_pairs", "dohwa_year_triad", "dohwa_day_triad", "dohwa_broad_branches",
    ]
    assert all(rule["status"] == "not_detected" and rule["evidence"] == []
               for rule in result["rules"])
    assert json.loads(json.dumps(result)) == result
    assert set(result["rules"][0]) == {"id", "status", "evidence"}
    assert set(result["rules"][1]) == {
        "id", "status", "evidence", "reference_position", "reference_branch", "target_branch",
    }


@pytest.mark.parametrize("pair", ["子未", "丑午", "寅酉", "卯申", "辰亥", "巳戌"])
@pytest.mark.parametrize("reverse", [False, True])
def test_all_six_wonjin_pairs_match_in_both_orders_and_keep_every_position(pair, reverse):
    left, right = pair[::-1] if reverse else pair
    result = rules(evaluate_natal_markers(chart(left, left, left, right)))["wonjin_all_pairs"]
    assert result == {
        "id": "wonjin_all_pairs", "status": "detected",
        "evidence": [{"positions": [position, "time"], "branches": [left, right]}
                     for position in ("year", "month", "day")],
    }


def test_wonjin_preserves_four_distinct_pairs_for_repeated_branches():
    result = rules(evaluate_natal_markers(chart("子", "未", "子", "未")))["wonjin_all_pairs"]
    assert result["evidence"] == [
        {"positions": ["year", "month"], "branches": ["子", "未"]},
        {"positions": ["year", "time"], "branches": ["子", "未"]},
        {"positions": ["month", "day"], "branches": ["未", "子"]},
        {"positions": ["day", "time"], "branches": ["子", "未"]},
    ]


@pytest.mark.parametrize("pair_positions", list(combinations(POSITIONS, 2)))
def test_wonjin_checks_every_unordered_position_pair_including_nonadjacent(pair_positions):
    source = chart("子", "子", "子", "子")
    source[pair_positions[1]] = "乙未"
    evidence = rules(evaluate_natal_markers(source))["wonjin_all_pairs"]["evidence"]
    assert {"positions": list(pair_positions), "branches": ["子", "未"]} in evidence
    assert len(evidence) == 3
    assert all(len(set(item["positions"])) == 2 for item in evidence)


def test_repeated_identical_branch_is_not_a_wonjin_pair():
    result = rules(evaluate_natal_markers(chart("子", "子", "子", "子")))
    assert result["wonjin_all_pairs"]["status"] == "not_detected"
    assert result["dohwa_broad_branches"]["evidence"] == [
        {"position": position, "branch": "子"} for position in POSITIONS]


@pytest.mark.parametrize("group,target", [("寅午戌", "卯"), ("巳酉丑", "午"),
                                         ("申子辰", "酉"), ("亥卯未", "子")])
@pytest.mark.parametrize("reference", ["year", "day"])
def test_triad_reference_tables_and_all_repeated_matching_positions(group, target, reference):
    for branch in group:
        result = rules(evaluate_natal_markers(chart(branch, target, branch, target)))
        assert result[f"dohwa_{reference}_triad"] == {
            "id": f"dohwa_{reference}_triad", "status": "detected",
            "reference_position": reference, "reference_branch": branch,
            "target_branch": target,
            "evidence": [{"position": "month", "branch": target},
                         {"position": "time", "branch": target}],
        }


def test_year_and_day_reference_checks_stay_separate():
    result = rules(evaluate_natal_markers(chart("寅", "卯", "亥", "子")))
    assert result["dohwa_year_triad"]["reference_branch"] == "寅"
    assert result["dohwa_year_triad"]["evidence"] == [{"position": "month", "branch": "卯"}]
    assert result["dohwa_day_triad"]["reference_branch"] == "亥"
    assert result["dohwa_day_triad"]["evidence"] == [{"position": "time", "branch": "子"}]


def test_triad_can_match_the_other_reference_position():
    result = rules(evaluate_natal_markers(chart("寅", "辰", "卯", "子")))
    assert result["dohwa_year_triad"]["evidence"] == [{"position": "day", "branch": "卯"}]
    result = rules(evaluate_natal_markers(chart("卯", "辰", "寅", "子")))
    assert result["dohwa_day_triad"]["evidence"] == [{"position": "year", "branch": "卯"}]


def test_broad_convention_is_not_presented_as_a_triad_match():
    result = rules(evaluate_natal_markers(chart("寅", "午", "戌", "申")))
    assert result["dohwa_year_triad"]["status"] == "not_detected"
    assert result["dohwa_day_triad"]["status"] == "not_detected"
    assert result["dohwa_broad_branches"] == {
        "id": "dohwa_broad_branches", "status": "detected",
        "evidence": [{"position": "month", "branch": "午"}],
    }


def test_broad_rule_preserves_all_four_eligible_branches_in_position_order():
    result = rules(evaluate_natal_markers(chart("子", "午", "卯", "酉")))
    assert result["dohwa_broad_branches"]["evidence"] == [
        {"position": position, "branch": branch}
        for position, branch in zip(POSITIONS, "子午卯酉")]


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("missing", [None, "", "absent"])
def test_any_missing_pillar_prevents_a_definitive_negative(position, missing):
    source = negative_chart()
    if missing == "absent":
        del source[position]
    else:
        source[position] = missing
    result = evaluate_natal_markers(source)
    assert result["coverage"]["missing_positions"] == [position]
    assert result["coverage"]["invalid_positions"] == []
    assert not result["coverage"]["complete"]
    assert all(rule["status"] == "insufficient_input" for rule in result["rules"])


@pytest.mark.parametrize("malformed", [True, 0, 1.5, [], {}, ["甲寅", "乙卯"],
                                       "甲", "寅", "甲丑", "甲寅/乙卯", " 甲寅", "甲寅 ",
                                       "boundary", "<script>卯</script>"])
def test_malformed_values_are_not_salvaged_into_valid_branch_evidence(malformed):
    source = negative_chart()
    source["month"] = malformed
    result = evaluate_natal_markers(source)
    assert result["coverage"]["invalid_positions"] == ["month"]
    assert result["coverage"]["missing_positions"] == []
    assert result["coverage"]["available_positions"] == ["year", "day", "time"]
    assert all(rule["status"] == "insufficient_input" for rule in result["rules"])


@pytest.mark.parametrize("container", [None, [], "甲寅甲辰甲戌甲寅", 1, True])
def test_invalid_containers_return_no_claims_or_exceptions(container):
    result = evaluate_natal_markers(container)
    assert result["coverage"]["missing_positions"] == list(POSITIONS)
    assert result["coverage"]["available_positions"] == []
    assert all(rule["status"] == "insufficient_input" and not rule["evidence"]
               for rule in result["rules"])


def test_withheld_solar_term_boundary_pillars_remain_unavailable():
    result = evaluate_natal_markers({"year": "", "month": "", "day": "甲寅", "time": ""})
    assert result["coverage"]["missing_positions"] == ["year", "month", "time"]
    year = rules(result)["dohwa_year_triad"]
    assert year["status"] == "insufficient_input"
    assert year["reference_branch"] is None and year["target_branch"] is None
    assert rules(result)["dohwa_day_triad"]["target_branch"] == "卯"


def test_observed_matches_survive_unknown_hour_with_explicit_incomplete_coverage():
    source = chart("子", "未", "子", "寅")
    source["time"] = ""
    result = evaluate_natal_markers(source)
    assert result["coverage"]["missing_positions"] == ["time"]
    assert not result["coverage"]["complete"]
    observed = rules(result)
    assert observed["wonjin_all_pairs"]["status"] == "detected"
    assert len(observed["wonjin_all_pairs"]["evidence"]) == 2
    assert observed["dohwa_broad_branches"]["status"] == "detected"
    assert observed["dohwa_year_triad"]["status"] == "insufficient_input"
    assert observed["dohwa_day_triad"]["status"] == "insufficient_input"


def test_missing_reference_does_not_borrow_the_other_reference_or_broad_rule():
    result = rules(evaluate_natal_markers({"year": "", "month": "乙卯", "day": "甲寅", "time": ""}))
    assert result["dohwa_year_triad"]["status"] == "insufficient_input"
    assert result["dohwa_year_triad"]["evidence"] == []
    assert result["dohwa_day_triad"]["status"] == "detected"
    assert result["dohwa_broad_branches"]["status"] == "detected"


def test_invalid_unrelated_pillar_does_not_erase_a_valid_pair():
    result = evaluate_natal_markers({"year": "甲子", "month": "乙未", "day": "invalid", "time": ""})
    assert result["coverage"]["invalid_positions"] == ["day"]
    assert rules(result)["wonjin_all_pairs"]["evidence"] == [
        {"positions": ["year", "month"], "branches": ["子", "未"]}]
    assert rules(result)["wonjin_all_pairs"]["status"] == "detected"


def test_hour_alias_and_unknown_metadata_cannot_fill_missing_provider_positions():
    source = negative_chart()
    source["hour"] = source.pop("time")
    source["strength"] = 100
    result = evaluate_natal_markers(source)
    assert result["coverage"]["missing_positions"] == ["time"]
    assert all(rule["status"] == "insufficient_input" for rule in result["rules"])
    assert "strength" not in json.dumps(result)


def test_output_is_stable_across_mapping_order_and_does_not_mutate_or_share_input():
    source = chart("子", "未", "子", "未")
    source["extra"] = {"values": [1, 2, 3]}
    original = deepcopy(source)
    first = evaluate_natal_markers(source)
    reverse = evaluate_natal_markers(dict(reversed(list(source.items()))))
    assert json.dumps(first, ensure_ascii=False) == json.dumps(reverse, ensure_ascii=False)
    assert source == original
    first["coverage"]["available_positions"].clear()
    first["rules"][0]["evidence"][0]["positions"].clear()
    assert evaluate_natal_markers(source) == reverse
