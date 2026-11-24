"""Deterministic branch-pattern checks on already calculated natal pillars.

This module does not calculate birth charts, resolve calendar boundaries, rank
people, or infer personality. Callers must preserve blank/withheld pillars from
the chart provider: a nonempty pillar cannot reveal uncertainty recorded outside
``eight_char``. Provider positions are ``year``, ``month``, ``day``, and ``time``.

Rule scope, frozen as natal-markers-v1:
* wonjin_all_pairs: any unordered pair of available positions, adjacent or not.
* dohwa_year_triad / dohwa_day_triad: separate year/day reference checks.
* dohwa_broad_branches: the separate presence-only 子/午/卯/酉 convention.

References for the chosen conventions, not empirical predictive validity:
https://saju.signalplanner.co.kr/dictionary/wonjinsal
https://encykorea.aks.ac.kr/Article/E0015926
https://saju.signalplanner.co.kr/dictionary/dohwasal

Only implemented rules are returned. An unimplemented rule must be reported as
unsupported by its caller, never inferred to be not_detected from this result.
"""

from itertools import combinations
from .natal_pillars import POSITIONS, confirmed_pillars


SCHEMA_VERSION = 1
RULE_VERSION = "natal-markers-v1"
_WONJIN_PAIRS = frozenset(
    frozenset(pair) for pair in ("子未", "丑午", "寅酉", "卯申", "辰亥", "巳戌")
)
_DOHWA_TARGET = {
    branch: target
    for group, target in (("寅午戌", "卯"), ("巳酉丑", "午"),
                          ("申子辰", "酉"), ("亥卯未", "子"))
    for branch in group
}
_DOHWA_BROAD = frozenset("子午卯酉")


def _status(evidence: list, complete: bool) -> str:
    if evidence:
        return "detected"
    return "not_detected" if complete else "insufficient_input"


def evaluate_natal_markers(eight_char: dict) -> dict:
    """Return JSON-safe facts for four named rules without mutating the input.

    Missing, blank, or None pillars are unavailable; other values must exactly
    match one of the 60 valid pillars. Lists of alternatives, boundary markers,
    partial text, whitespace, and invalid pairs are not salvaged into a branch.
    Invalid containers behave as wholly unavailable input. Unknown keys are
    ignored; ``hour`` is not an alias for the provider's ``time`` key.

    Any observed match is detected even with incomplete coverage. Without an
    observed match, all four valid pillars are required for not_detected. Thus
    missing hours or withheld boundary pillars cannot produce a definitive
    negative. A missing year/day also leaves its reference and target null.

    Rules, coverage positions, and evidence follow POSITIONS order. Repeated
    branches are distinct position evidence, never deduplicated by glyph.
    """
    pillars, missing, invalid = confirmed_pillars(eight_char)
    branches = {position: pillar[1] for position, pillar in pillars.items()}

    complete = len(branches) == len(POSITIONS)
    coverage = {
        "expected_positions": list(POSITIONS),
        "available_positions": list(branches),
        "missing_positions": missing,
        "invalid_positions": invalid,
        "complete": complete,
    }

    wonjin = [
        {"positions": [left, right], "branches": [branches[left], branches[right]]}
        for left, right in combinations(branches, 2)
        if frozenset((branches[left], branches[right])) in _WONJIN_PAIRS
    ]
    rules = [{"id": "wonjin_all_pairs", "status": _status(wonjin, complete),
              "evidence": wonjin}]

    for reference in ("year", "day"):
        reference_branch = branches.get(reference)
        target = _DOHWA_TARGET.get(reference_branch)
        evidence = [
            {"position": position, "branch": branch}
            for position, branch in branches.items()
            if branch == target
        ]
        rules.append({
            "id": f"dohwa_{reference}_triad",
            "status": _status(evidence, complete),
            "reference_position": reference,
            "reference_branch": reference_branch,
            "target_branch": target,
            "evidence": evidence,
        })

    broad = [{"position": position, "branch": branch}
             for position, branch in branches.items() if branch in _DOHWA_BROAD]
    rules.append({"id": "dohwa_broad_branches", "status": _status(broad, complete),
                  "evidence": broad})
    return {"schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
            "coverage": coverage, "rules": rules}
