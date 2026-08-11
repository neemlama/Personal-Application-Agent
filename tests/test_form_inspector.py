"""Tests for inspect_form's pure-Python JSON parsing. The actual live page
inspection needs real AgentCore Browser access — exercise it manually
(tests/manual_form_filler_livecheck.py exercises the full inspect ->
propose -> fill pipeline live)."""

import json

import pytest

from agent.tools.form_inspector import _parse_json


def test_parse_json_handles_plain_json():
    result = _parse_json('{"ok": true, "fields": [], "submit_selector": "#go", "notes": ""}')
    assert result["ok"] is True
    assert result["submit_selector"] == "#go"


def test_parse_json_strips_markdown_fence():
    wrapped = '```json\n{"ok": true, "fields": []}\n```'
    result = _parse_json(wrapped)
    assert result["ok"] is True


def test_parse_json_handles_prose_prefix():
    raw = 'Here is what I found on the page:\n\n{"ok": true, "fields": [{"label": "Name"}]}'
    result = _parse_json(raw)
    assert result["ok"] is True
    assert result["fields"][0]["label"] == "Name"


def test_parse_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        _parse_json("not json at all")
