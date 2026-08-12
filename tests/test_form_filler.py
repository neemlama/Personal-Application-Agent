"""Tests for fill_and_submit_form's pure-Python logic — no browser, no AWS.
The actual browser-driven fill/submit needs live AgentCore Browser access;
exercise that manually against the mock RSVP form (see
tests/manual_form_filler_livecheck.py)."""

import json

import pytest

from agent.tools.form_filler import _build_task_prompt, _parse_result_json

SAMPLE_FIELDS = [
    {"label": "Full Name", "field_type": "text", "selector": "#full_name", "required": True, "value": "Alex Rai"},
    {"label": "Email Address", "field_type": "email", "selector": "#email", "required": True, "value": "alex@example.com"},
    {"label": "Bringing a plus-one", "field_type": "checkbox", "selector": "#plus_one", "required": False, "value": True},
]


def test_parse_result_json_handles_plain_json():
    result = _parse_result_json('{"ok": true, "confirmation_text": "RSVP-ABC123", "notes": "done"}')
    assert result["ok"] is True
    assert result["confirmation_text"] == "RSVP-ABC123"


def test_parse_result_json_strips_markdown_code_fence():
    wrapped = '```json\n{"ok": true, "confirmation_text": "X", "notes": ""}\n```'
    result = _parse_result_json(wrapped)
    assert result["ok"] is True


def test_parse_result_json_handles_prose_prefix():
    # Confirmed live pre-pivot: models sometimes prefix JSON with a sentence
    # despite explicit "ONLY JSON" instructions.
    raw = 'All steps completed. Here is the result:\n\n{"ok": true, "confirmation_text": "RSVP-XYZ", "notes": "done"}'
    result = _parse_result_json(raw)
    assert result["ok"] is True
    assert result["confirmation_text"] == "RSVP-XYZ"


def test_parse_result_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        _parse_result_json("no json here at all")


def test_build_task_prompt_includes_every_field_and_its_value():
    prompt = _build_task_prompt("https://example.com/rsvp", SAMPLE_FIELDS, "#submit-btn")
    assert "https://example.com/rsvp" in prompt
    assert "#full_name" in prompt and "Alex Rai" in prompt
    assert "#email" in prompt and "alex@example.com" in prompt
    assert "#submit-btn" in prompt


def test_build_task_prompt_falls_back_when_no_submit_selector_known():
    prompt = _build_task_prompt("https://example.com/rsvp", SAMPLE_FIELDS, None)
    assert "find and click the form's submit button" in prompt
