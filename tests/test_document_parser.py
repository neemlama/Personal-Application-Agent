"""Tests for document_parser's pure-Python logic (JSON parsing, file
handling). Does NOT test the actual Bedrock vision call — that needs a real
image and live model access; exercise it manually via the orchestrator once
AWS access is available, same as agent/orchestrator.py itself."""

import json

import pytest

from agent.tools.document_parser import _failure, _load_image_block, _parse_model_json, document_parser


def test_parse_model_json_handles_plain_json():
    result = _parse_model_json('{"legible": true, "extracted_fields": {"full_name": "Test"}}')
    assert result["legible"] is True
    assert result["extracted_fields"]["full_name"] == "Test"


def test_parse_model_json_strips_markdown_code_fence():
    wrapped = '```json\n{"legible": true, "extracted_fields": {}}\n```'
    result = _parse_model_json(wrapped)
    assert result["legible"] is True


def test_parse_model_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        _parse_model_json("this is not json at all")


def test_load_image_block_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        _load_image_block("/definitely/not/a/real/path.png")


def test_document_parser_returns_ok_false_not_an_exception_on_missing_file():
    # Dangerous/failure case: the tool must never raise into the agent loop
    # — a bad path should come back as a structured failure the orchestrator
    # can react to (e.g. ask the user to reupload).
    result = document_parser(image_path="/definitely/not/a/real/path.png")
    assert result["ok"] is False
    assert result["legible"] is False
    assert "not found" in result["notes"].lower()


def test_failure_shape_matches_success_shape_keys():
    # Callers should be able to rely on the same keys existing either way.
    failure = _failure("some reason")
    assert set(failure.keys()) >= {"ok", "legible", "extracted_fields", "low_confidence_fields", "notes"}
