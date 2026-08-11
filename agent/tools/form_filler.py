"""form_filler — drives AgentCore Browser through a program's online
application portal to complete an approved submission.

Only ever called from resume_after_approval(), after a human has already
approved the proposal — never autonomously, never before approval, and
never called by the orchestrator's main agent on itself (it has no tool
that does this; see orchestrator.py's system prompt).

Runs its own isolated Strands Agent with the AgentCore Browser tool
registered, same isolation pattern as document_parser's vision extractor —
its raw tool-call chatter is not something a user should see mid-approval.

Two deliberate safety properties, both because this is the one tool in the
whole system that takes an irreversible external action:
  1. Pre-flight field check (pure Python, no browser, no model call) refuses
     to even start if the profile is missing fields the form requires,
     rather than letting the browser agent improvise/fabricate a value for
     a blank citizenship number or date of birth.
  2. PORTAL_MAP only knows how to fill programs it has an explicit,
     human-curated field mapping for — same "cannot guess a form we
     haven't verified" principle as the program catalog itself.
"""

import json
import os
from typing import Any

from strands import Agent

# Known portal structures, keyed by program_id. A real deployment would
# document each program's actual application flow this way before enabling
# automated filling for it -- attempting an unmapped program_id is refused,
# not guessed at.
PORTAL_MAP: dict[str, dict[str, Any]] = {
    "ctevt-special-scholarship": {
        # HTTPS S3 REST endpoint, not the HTTP "website hosting" endpoint --
        # confirmed live that AgentCore Browser's managed environment
        # blocks plain HTTP navigation with net::ERR_BLOCKED_BY_CLIENT.
        # REST endpoint has no automatic index-document resolution, so
        # every navigate/link target below is an explicit filename, never
        # a bare "/".
        "base_url": os.environ.get(
            "MOCK_PORTAL_BASE_URL",
            "https://sahayogi-mock-portal-557723775608.s3.amazonaws.com",
        ),
        # (page path, [(field_name, selector), ...], next-button selector)
        "steps": [
            (
                "/step1-personal.html",
                [
                    "full_name",
                    "date_of_birth_bs",
                    "citizenship_number",
                    "gender",
                    "father_name",
                    "mother_name",
                    "phone_number",
                ],
            ),
            (
                "/step2-education.html",
                ["see_symbol_number", "exam_year_bs", "school_name", "gpa_or_division", "desired_program"],
            ),
            (
                "/step3-eligibility.html",
                ["province", "local_level", "caste_ethnicity", "family_annual_income_npr"],
            ),
            (
                "/step4-documents.html",
                ["doc_citizenship", "doc_transcript", "doc_category_certificate", "doc_residency"],
            ),
        ],
        # Fields that are plain text/select/number inputs -- typed via the
        # "type" action. Everything else in a step's field list is treated
        # as a checkbox -- clicked, not typed, and only if the profile value
        # is truthy.
        "checkbox_fields": {"doc_citizenship", "doc_transcript", "doc_category_certificate", "doc_residency"},
        "select_fields": {"gender", "desired_program", "province"},
    }
}


# Confirmed live: an orchestrator-constructed profile uses reasonable but
# non-canonical field names ("dob_bs" not "date_of_birth_bs", "phone" not
# "phone_number", etc). Rather than trying to force exact vocabulary out of
# an LLM via prompting (unreliable — wording will keep drifting run to
# run), normalize known synonyms here. This is a translation layer, not a
# relaxation of the "never fabricate" rule below: every key on the right is
# still either present in the input or explicitly derived from something
# the user actually said, never invented.
_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "ctevt-special-scholarship": {
        "dob_bs": "date_of_birth_bs",
        "phone": "phone_number",
        "see_gpa": "gpa_or_division",
        "see_year_bs": "exam_year_bs",
        "see_school": "school_name",
        "program_applied": "desired_program",
        "family_income_npr": "family_annual_income_npr",
    }
}

# documents_ready free-text list -> doc_* booleans, by keyword match.
_DOCUMENT_KEYWORDS: dict[str, list[str]] = {
    "doc_citizenship": ["citizenship"],
    "doc_transcript": ["transcript", "marksheet", "see"],
    "doc_category_certificate": ["caste", "category"],
    "doc_residency": ["residency", "residence"],
}


def _normalize_profile(program_id: str, applicant_profile: dict[str, Any]) -> dict[str, Any]:
    profile = dict(applicant_profile)

    for alias, canonical in _FIELD_ALIASES.get(program_id, {}).items():
        if alias in profile and canonical not in profile:
            profile[canonical] = profile[alias]

    if "caste_ethnicity" not in profile and profile.get("marginalized_groups"):
        profile["caste_ethnicity"] = profile["marginalized_groups"][0]

    if "documents_ready" in profile:
        ready_text = " ".join(str(x).lower() for x in profile["documents_ready"])
        for field, keywords in _DOCUMENT_KEYWORDS.items():
            if field not in profile and any(kw in ready_text for kw in keywords):
                profile[field] = True

    return profile


def _required_fields(program_id: str) -> list[str]:
    portal = PORTAL_MAP[program_id]
    fields: list[str] = []
    for _path, names in portal["steps"]:
        fields.extend(names)
    return fields


def missing_fields(program_id: str, applicant_profile: dict[str, Any]) -> list[str]:
    """Pure Python, no browser/model call — which required fields are absent
    after normalization (see _normalize_profile)."""
    profile = _normalize_profile(program_id, applicant_profile)
    return [f for f in _required_fields(program_id) if f not in profile or profile[f] in (None, "")]


def _build_task_prompt(portal: dict[str, Any], applicant_profile: dict[str, Any], session_name: str) -> str:
    lines = [
        f'Use the browser tool. First call init_session with session_name="{session_name}" and a short description.',
        f"Then navigate to {portal['base_url']}{portal['steps'][0][0]}",
        "",
        "For each of the following pages, in order: type the given value into the input "
        'matching CSS selector "#<field_name>" for text/number/select fields (for <select> '
        "elements, use the click action on the option's visible text if typing doesn't work, "
        "or use the evaluate action to set .value and dispatch a change event), and for "
        'checkbox fields, use the click action on "#<field_name>" ONLY if the given value is '
        "true. After all fields on a page are filled, click the visible submit/next button "
        '(selector: button[type="submit"]) to advance to the next page.',
        "",
    ]
    for path, field_names in portal["steps"]:
        lines.append(f"Page {path}:")
        for name in field_names:
            value = applicant_profile.get(name)
            kind = "checkbox" if name in portal["checkbox_fields"] else "field"
            lines.append(f'  - {kind} "{name}" = {value!r}')
        lines.append("")

    lines += [
        "After the last page (step4-documents.html), you'll land on step5-review.html — "
        "a read-only review page. Check the declaration checkbox "
        '(selector "#declaration") — this represents the human approval that already '
        'happened before you were invoked — then click button[type="submit"] to submit.',
        "",
        "You should land on confirmation.html. Use get_text with selector "
        '"#ref-number" to read the generated reference number, and take a screenshot '
        "for the record.",
        "",
        "Respond with ONLY a single JSON object, no prose, no markdown fence:",
        '{"ok": true|false, "reference_number": "<string or null>", "notes": "<what happened, '
        'especially any error, unexpected page state, or step you could not complete>"}',
    ]
    return "\n".join(lines)


def _parse_result_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Confirmed live: despite explicit "ONLY a single JSON object, no
    # prose" instructions, the model sometimes still prefixes a sentence
    # ("All steps completed successfully. Here is the result:") before the
    # JSON. Fall back to extracting the {...} block instead of failing a
    # run that actually succeeded.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("no JSON object found in model output", text, 0)


def form_filler(session_id: str, program_id: str, applicant_profile: dict[str, Any]) -> dict[str, Any]:
    """Fill and submit a program's application using AgentCore Browser.

    NOT a Strands @tool — deliberately not callable by the orchestrator's
    main agent. Only resume_after_approval() calls this, after a human
    decision is already recorded.

    Returns:
        {"ok": bool, "reference_number": str | None, "notes": str}
        ok=False (with no browser session ever started) if the program has
        no known portal mapping, or if applicant_profile is missing fields
        the form requires — never fabricates a value to fill the gap.
    """
    if program_id not in PORTAL_MAP:
        return {
            "ok": False,
            "reference_number": None,
            "notes": f"No known portal mapping for program_id={program_id!r}; refusing to guess a form flow.",
        }

    applicant_profile = _normalize_profile(program_id, applicant_profile)
    missing = missing_fields(program_id, applicant_profile)
    if missing:
        return {
            "ok": False,
            "reference_number": None,
            "notes": f"Missing required fields, refusing to submit with fabricated data: {missing}",
        }

    portal = PORTAL_MAP[program_id]
    browser_session_name = f"sahayogi-{session_id[:20]}".lower().replace("_", "-")

    # Local import: keeps the AgentCore Browser dependency chain
    # (bedrock-agentcore, playwright) off the import path for every other
    # tool/test that doesn't need it.
    from strands_tools.browser import AgentCoreBrowser

    region = os.environ.get("AWS_REGION", "us-east-1")
    browser_tool = AgentCoreBrowser(region=region)
    filler_agent = Agent(
        system_prompt=(
            "You are a form-filling agent. Follow the given instructions exactly, "
            "step by step, using the browser tool. Do not skip fields. Do not invent "
            "values not given to you. If a step fails or the page doesn't look as "
            "expected, note it in your final JSON response rather than guessing."
        ),
        tools=[browser_tool.browser],
        callback_handler=None,  # raw tool chatter isn't user-facing; see module docstring
    )

    task_prompt = _build_task_prompt(portal, applicant_profile, browser_session_name)
    response = filler_agent(task_prompt)

    try:
        result = _parse_result_json(str(response))
    except json.JSONDecodeError:
        return {
            "ok": False,
            "reference_number": None,
            "notes": f"Browser agent did not return valid JSON: {str(response)[:500]!r}",
        }

    return {
        "ok": bool(result.get("ok", False)),
        "reference_number": result.get("reference_number"),
        "notes": result.get("notes", ""),
    }
