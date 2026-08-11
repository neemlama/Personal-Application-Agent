"""eligibility_matcher — coarse, deterministic shortlist of catalog programs.

Design intent: this tool does NOT make the final eligibility call. It applies
cheap, reliable, testable hard filters (citizenship, education level, clear
age/income bounds, geographic scope) and returns a shortlist with the reasons
each program matched. The orchestrator agent (LLM) then reasons over each
candidate's nuanced conditions (e.g. reduced age thresholds for specific
groups, documented in `other_notes`) and explains eligibility to the human —
that reasoning step is why this needs an agent and not just a filter script.

Deliberately conservative in one direction only: on ambiguous/missing profile
data, we PREFER to include a program as a candidate (false positive, cheap —
the agent/human filters it out) over silently excluding someone who might
actually qualify (false negative, costly — a real benefit missed).
"""

from typing import Any

from strands import tool

from agent.tools.catalog import load_programs


def _citizenship_excludes(profile: dict[str, Any], program: dict[str, Any]) -> bool:
    required = program["eligibility"].get("citizenship")
    given = profile.get("citizenship")
    return bool(required and given and required != given)


def _education_level_excludes(profile: dict[str, Any], program: dict[str, Any]) -> bool:
    level = program.get("level", "any")
    given = profile.get("education_level")
    return bool(level != "any" and given and level != given)


def _age_excludes(profile: dict[str, Any], program: dict[str, Any]) -> bool:
    age = profile.get("age")
    if age is None:
        return False

    max_age = program["eligibility"].get("max_age")
    if max_age is not None and age > max_age:
        return True

    min_age = program["eligibility"].get("min_age")
    if min_age is not None and age < min_age:
        # Under the stated minimum — but several programs reduce the threshold
        # for specific groups (see other_notes). Only exclude outright if the
        # applicant has no group membership that could plausibly qualify for
        # a reduced threshold; otherwise let it through as a candidate.
        mitigating_groups = set(program["eligibility"].get("marginalized_groups", []))
        applicant_groups = set(profile.get("marginalized_groups", []))
        is_single_woman_or_widow = profile.get("single_woman_or_widow", False)
        if not (mitigating_groups & applicant_groups) and not is_single_woman_or_widow:
            return True

    return False


def _income_excludes(profile: dict[str, Any], program: dict[str, Any]) -> bool:
    cap = program["eligibility"].get("max_family_income_npr")
    income = profile.get("family_income_npr")
    return bool(cap is not None and income is not None and income > cap)


def _geography_excludes(profile: dict[str, Any], program: dict[str, Any]) -> bool:
    scope = program["eligibility"].get("geographic_scope")
    local_level = profile.get("local_level")
    if not isinstance(scope, list) or not local_level:
        return False
    return local_level not in scope


_EXCLUSION_CHECKS = (
    ("citizenship", _citizenship_excludes),
    ("education_level", _education_level_excludes),
    ("age", _age_excludes),
    ("family_income", _income_excludes),
    ("geographic_scope", _geography_excludes),
)


@tool
def eligibility_matcher(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Shortlist catalog programs plausibly relevant to an applicant profile.

    Args:
        profile: Applicant details. Recognized keys (all optional — missing
            fields are never treated as disqualifying, only as "unknown"):
            citizenship (str, e.g. "NP"), age (int), education_level
            (str: "school" | "technical" | "higher_ed"), family_income_npr
            (int), local_level (str), marginalized_groups (list[str]),
            single_woman_or_widow (bool).

    Returns:
        A list of {program, matched: bool, exclusion_reasons: list[str]}
        for every catalog program — callers should treat `matched: True`
        entries as candidates needing the agent's nuanced review, not a
        final eligibility decision.
    """
    results = []
    for program in load_programs():
        reasons = [name for name, check in _EXCLUSION_CHECKS if check(profile, program)]
        results.append(
            {
                "program": program,
                "matched": len(reasons) == 0,
                "exclusion_reasons": reasons,
            }
        )
    return results
