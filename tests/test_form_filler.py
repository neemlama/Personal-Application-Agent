"""Tests for form_filler's pure-Python guard logic — no browser, no AWS.
The actual browser-driven fill/submit needs live AgentCore Browser access;
exercise that manually against the mock portal (see form_filler's module
docstring), same caveat as document_parser's vision call."""

from agent.tools.form_filler import PORTAL_MAP, _normalize_profile, _parse_result_json, form_filler, missing_fields

# Real profile shape an orchestrator run actually produced live (2026-08-11,
# session e2e-demo-1) -- not a hypothetical. Different vocabulary than the
# form's canonical field names, which is exactly the case _normalize_profile
# exists to handle.
REAL_ORCHESTRATOR_PROFILE = {
    "full_name": "Sunita Nepali",
    "dob_bs": "2065-03-12",
    "age": 17,
    "citizenship_number": "12-34-56-78901",
    "gender": "Female",
    "father_name": "Ram Nepali",
    "mother_name": "Sita Nepali",
    "phone": "9800000000",
    "country": "NP",
    "citizenship": "NP",
    "education_level": "SEE",
    "see_gpa": 3.65,
    "see_symbol_number": "TEST-2082-004521",
    "see_year_bs": 2082,
    "see_school": "Sample Secondary School",
    "program_applied": "Diploma in Civil Engineering",
    "local_level": "Kalikot",
    "province": "Karnali",
    "marginalized_groups": ["Dalit"],
    "family_income_npr": 150000,
    "single_woman_or_widow": False,
    "documents_ready": ["citizenship", "SEE transcript", "caste/category certificate", "residency proof"],
}

COMPLETE_PROFILE = {
    "full_name": "Test Person",
    "date_of_birth_bs": "2065-03-12",
    "citizenship_number": "12-34-56-78901",
    "gender": "Female",
    "father_name": "Test Father",
    "mother_name": "Test Mother",
    "phone_number": "9800000000",
    "see_symbol_number": "TEST-2082-004521",
    "exam_year_bs": "2082",
    "school_name": "Sample Secondary School",
    "gpa_or_division": "3.65",
    "desired_program": "Diploma in Civil Engineering",
    "province": "Karnali",
    "local_level": "Kalikot",
    "caste_ethnicity": "Dalit",
    "family_annual_income_npr": "150000",
    "doc_citizenship": True,
    "doc_transcript": True,
    "doc_category_certificate": True,
    "doc_residency": True,
}


def test_unmapped_program_refuses_without_touching_browser():
    # Dangerous case: no known portal mapping must refuse cleanly, and must
    # do so before any browser/AWS dependency is even imported (this test
    # would fail with an ImportError if it weren't short-circuited first,
    # since bedrock-agentcore/playwright aren't wired for live use in tests).
    result = form_filler(session_id="s1", program_id="not-a-real-program", applicant_profile=COMPLETE_PROFILE)
    assert result["ok"] is False
    assert result["reference_number"] is None
    assert "no known portal mapping" in result["notes"].lower()


def test_missing_fields_refuses_without_touching_browser():
    # Dangerous case: incomplete profile must refuse rather than let the
    # browser agent fabricate a citizenship number or DOB.
    incomplete = {k: v for k, v in COMPLETE_PROFILE.items() if k != "citizenship_number"}
    result = form_filler(session_id="s1", program_id="ctevt-special-scholarship", applicant_profile=incomplete)
    assert result["ok"] is False
    assert "citizenship_number" in result["notes"]


def test_missing_fields_helper_lists_every_gap():
    incomplete = {"full_name": "Test Person"}  # only one of many required fields
    missing = missing_fields("ctevt-special-scholarship", incomplete)
    assert "citizenship_number" in missing
    assert "see_symbol_number" in missing
    assert "full_name" not in missing


def test_missing_fields_treats_empty_string_and_none_as_missing():
    profile = dict(COMPLETE_PROFILE)
    profile["full_name"] = ""
    profile["father_name"] = None
    missing = missing_fields("ctevt-special-scholarship", profile)
    assert "full_name" in missing
    assert "father_name" in missing


def test_complete_profile_has_no_missing_fields():
    # Sanity check that the fixture profile used by other tests (and by the
    # manual live check) actually satisfies every required field.
    assert missing_fields("ctevt-special-scholarship", COMPLETE_PROFILE) == []


def test_portal_map_field_lists_have_no_duplicates_across_steps():
    for program_id, portal in PORTAL_MAP.items():
        seen = []
        for _path, names in portal["steps"]:
            seen.extend(names)
        assert len(seen) == len(set(seen)), f"duplicate field name across steps in {program_id}"


def test_parse_result_json_handles_plain_json():
    result = _parse_result_json('{"ok": true, "reference_number": "CTEVT-MOCK-ABC123", "notes": "done"}')
    assert result["ok"] is True
    assert result["reference_number"] == "CTEVT-MOCK-ABC123"


def test_parse_result_json_handles_prose_prefix():
    # Regression test: confirmed live that the browser agent sometimes
    # prefixes the JSON with a sentence despite "ONLY JSON" instructions --
    # e.g. 'All steps completed successfully. Here is the result:\n\n{...}'
    raw = (
        "All steps completed successfully. Here is the result:\n\n"
        '{"ok": true, "reference_number": "CTEVT-MOCK-FC7ALE", "notes": "All 5 pages completed."}'
    )
    result = _parse_result_json(raw)
    assert result["ok"] is True
    assert result["reference_number"] == "CTEVT-MOCK-FC7ALE"


def test_parse_result_json_raises_on_garbage_with_no_braces():
    import json

    import pytest

    with pytest.raises(json.JSONDecodeError):
        _parse_result_json("no json here at all")


def test_normalize_profile_maps_known_aliases():
    normalized = _normalize_profile("ctevt-special-scholarship", REAL_ORCHESTRATOR_PROFILE)
    assert normalized["date_of_birth_bs"] == "2065-03-12"
    assert normalized["phone_number"] == "9800000000"
    assert normalized["gpa_or_division"] == 3.65
    assert normalized["exam_year_bs"] == 2082
    assert normalized["school_name"] == "Sample Secondary School"
    assert normalized["desired_program"] == "Diploma in Civil Engineering"


def test_normalize_profile_derives_caste_ethnicity_from_marginalized_groups():
    normalized = _normalize_profile("ctevt-special-scholarship", REAL_ORCHESTRATOR_PROFILE)
    assert normalized["caste_ethnicity"] == "Dalit"


def test_normalize_profile_derives_doc_booleans_from_documents_ready_list():
    normalized = _normalize_profile("ctevt-special-scholarship", REAL_ORCHESTRATOR_PROFILE)
    assert normalized["doc_citizenship"] is True
    assert normalized["doc_transcript"] is True
    assert normalized["doc_category_certificate"] is True
    assert normalized["doc_residency"] is True


def test_normalize_profile_never_overwrites_an_explicit_canonical_value():
    profile = dict(REAL_ORCHESTRATOR_PROFILE)
    profile["doc_residency"] = False  # applicant explicitly said no, not just unmentioned
    normalized = _normalize_profile("ctevt-special-scholarship", profile)
    assert normalized["doc_residency"] is False  # must not be derived back to True


def test_real_orchestrator_profile_has_zero_missing_fields_after_normalization():
    # The actual regression: before _normalize_profile existed, this exact
    # live profile failed missing_fields() on every renamed/derived field
    # despite the applicant having supplied all of the underlying
    # information. This is the case that must now pass clean.
    assert missing_fields("ctevt-special-scholarship", REAL_ORCHESTRATOR_PROFILE) == []


def test_normalize_profile_does_not_mutate_the_input_dict():
    original = dict(REAL_ORCHESTRATOR_PROFILE)
    _normalize_profile("ctevt-special-scholarship", REAL_ORCHESTRATOR_PROFILE)
    assert REAL_ORCHESTRATOR_PROFILE == original
