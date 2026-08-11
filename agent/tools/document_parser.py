"""document_parser — extract structured fields from a photo of a government
document (citizenship certificate, SEE marksheet, caste/category
certificate, income certificate, ward residency letter).

Runs its own isolated Bedrock vision call (a throwaway Strands Agent)
rather than reasoning about the image inline in the orchestrator's main
conversation, so extraction is a clean, structured, independently testable
artifact instead of prose mixed into the chat. This tool only extracts —
the orchestrator decides what to do with the result (merge into a profile,
flag a mismatch, ask the user to reupload).

Image ContentBlock format ({"image": {"format": ..., "source": {"bytes":
...}}}) confirmed against the installed strands_tools.image_reader source
(.venv/Lib/site-packages/strands_tools/image_reader.py), not guessed.
"""

import json
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from strands import Agent, tool

DocumentType = Literal[
    "citizenship",
    "see_marksheet",
    "caste_certificate",
    "income_certificate",
    "residency_letter",
    "other",
]

_FIELD_HINTS: dict[str, list[str]] = {
    "citizenship": ["full_name", "citizenship_number", "date_of_birth", "district", "father_name", "mother_name"],
    "see_marksheet": ["full_name", "symbol_number", "exam_year_bs", "school_name", "gpa_or_division"],
    "caste_certificate": ["full_name", "caste_or_ethnicity", "issuing_office", "issue_date_bs"],
    "income_certificate": ["full_name", "annual_income_npr", "issuing_office", "issue_date_bs"],
    "residency_letter": ["full_name", "local_level", "ward_number", "issuing_office", "issue_date_bs"],
    "other": [],
}

_SUPPORTED_FORMATS = {"png", "jpeg", "jpg", "gif", "webp"}


def _load_image_block(image_path: str) -> dict[str, Any]:
    path = Path(image_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"File not found at path: {path}")

    with Image.open(path) as img:
        image_format = (img.format or "png").lower()
    if image_format not in _SUPPORTED_FORMATS:
        image_format = "png"
    if image_format == "jpg":
        image_format = "jpeg"

    return {"format": image_format, "source": {"bytes": path.read_bytes()}}


def _extraction_prompt(document_type: str) -> str:
    fields = _FIELD_HINTS.get(document_type, [])
    field_list = ", ".join(fields) if fields else "whatever identifying fields are visible"
    return (
        "You are extracting structured data from a photo of a Nepali "
        f"government document (declared type: {document_type}). Look for "
        f"these fields if present: {field_list}. Respond with ONLY a "
        "single JSON object, no prose, no markdown code fence, with "
        "exactly these keys:\n"
        '  "legible": true|false,\n'
        '  "extracted_fields": {"<field>": "<value or null>", ...},\n'
        '  "low_confidence_fields": ["<field names you are unsure about>"],\n'
        '  "notes": "<anything unusual: damage, mismatched document type, etc>"\n'
        "If the image is not legible, or is not the declared document type "
        'at all, set "legible": false and explain in notes. Never invent '
        "a value you cannot actually read in the image."
    )


def _parse_model_json(raw_text: str) -> dict[str, Any]:
    """Isolated from the model call so it's unit-testable with canned strings."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def _failure(notes: str) -> dict[str, Any]:
    return {"ok": False, "legible": False, "extracted_fields": {}, "low_confidence_fields": [], "notes": notes}


@tool
def document_parser(image_path: str, document_type: DocumentType = "other") -> dict[str, Any]:
    """Extract structured fields from a photo of a government document.

    Args:
        image_path: Path to the image file (png/jpeg/gif/webp).
        document_type: Declared document type — one of "citizenship",
            "see_marksheet", "caste_certificate", "income_certificate",
            "residency_letter", "other". An incorrect declared type is
            fine — the model notes a mismatch in `notes` rather than
            force-fitting the wrong fields.

    Returns:
        {"ok": bool, "legible": bool, "extracted_fields": dict,
         "low_confidence_fields": list[str], "notes": str}
        Never raises — any failure (missing file, unreadable image,
        unparseable model output) comes back as {"ok": False, ...} with
        the reason in "notes", so the orchestrator can always react.
    """
    try:
        image_block = _load_image_block(image_path)
    except (FileNotFoundError, OSError) as e:
        return _failure(str(e))

    extractor = Agent(system_prompt=_extraction_prompt(document_type))
    response = extractor(
        [
            {"image": image_block},
            {"text": "Extract the fields now."},
        ]
    )

    try:
        parsed = _parse_model_json(str(response))
    except json.JSONDecodeError:
        return _failure(f"Model did not return valid JSON: {str(response)[:300]!r}")

    return {
        "ok": True,
        "legible": bool(parsed.get("legible", False)),
        "extracted_fields": parsed.get("extracted_fields", {}),
        "low_confidence_fields": parsed.get("low_confidence_fields", []),
        "notes": parsed.get("notes", ""),
    }
