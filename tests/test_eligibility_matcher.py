"""Tests for eligibility_matcher — runs fully local, no AWS needed
(PROGRAM_CATALOG_SOURCE defaults to the local seed JSON)."""

from agent.tools.eligibility_matcher import eligibility_matcher


def _matched_ids(results: list[dict]) -> set[str]:
    return {r["program"]["program_id"] for r in results if r["matched"]}


def test_returns_one_row_per_catalog_program():
    results = eligibility_matcher({})
    assert len(results) == 4  # matches infra/seed-data/programs.json count


def test_empty_profile_excludes_nothing_it_cant_justify():
    # Normal case: no data given -> nothing hard-disqualifies, everything is
    # a candidate. Missing data must never silently drop a program.
    results = eligibility_matcher({})
    assert _matched_ids(results) == {
        "school-scholarship-programme",
        "ctevt-special-scholarship",
        "ugc-disadvantaged-scholarship",
        "samajik-suraksha-bhatta",
    }


def test_school_age_child_matches_school_programme_only():
    # Normal case: a 12-year-old should not be a plausible candidate for a
    # higher-ed-only or elderly-only program.
    profile = {"age": 12, "education_level": "school"}
    matched = _matched_ids(eligibility_matcher(profile))
    assert "school-scholarship-programme" in matched
    assert "ugc-disadvantaged-scholarship" not in matched  # level mismatch
    assert "samajik-suraksha-bhatta" not in matched  # min_age 70, no mitigating group


def test_elderly_dalit_gets_reduced_age_threshold_as_candidate():
    # Edge case: 62-year-old Dalit applicant is under the stated min_age (70)
    # for the allowance, but Dalit citizens get a reduced threshold (60) per
    # other_notes — matcher must NOT hard-exclude, must surface as candidate
    # for the agent to reason over.
    profile = {"age": 62, "marginalized_groups": ["Dalit"]}
    matched = _matched_ids(eligibility_matcher(profile))
    assert "samajik-suraksha-bhatta" in matched


def test_elderly_no_mitigating_group_under_70_is_excluded():
    # Same age, no group membership that could justify a reduced threshold.
    profile = {"age": 62}
    results = eligibility_matcher(profile)
    row = next(r for r in results if r["program"]["program_id"] == "samajik-suraksha-bhatta")
    assert row["matched"] is False
    assert "age" in row["exclusion_reasons"]


def test_income_cap_excludes_when_over_and_program_has_a_cap():
    # None of the current seed programs set max_family_income_npr, so a huge
    # income should exclude nothing today — this guards the *logic*, not
    # today's data, in case a future entry sets a real cap.
    results = eligibility_matcher({"family_income_npr": 10_000_000})
    assert all("family_income" not in r["exclusion_reasons"] for r in results)


def test_citizenship_mismatch_excludes():
    # Dangerous/invalid case: explicit non-Nepali citizenship should exclude
    # every program that requires NP citizenship.
    results = eligibility_matcher({"citizenship": "IN"})
    assert _matched_ids(results) == set()


def test_geographic_scope_only_excludes_when_program_lists_specific_local_levels():
    # None of the seed programs currently restrict to a local-level list
    # (CTEVT's scope is a free-text description, not a list), so this should
    # exclude nothing today — again guarding the logic for when a scoped
    # program is added.
    results = eligibility_matcher({"local_level": "Some Remote Rural Municipality"})
    assert all("geographic_scope" not in r["exclusion_reasons"] for r in results)
