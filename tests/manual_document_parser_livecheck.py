"""Manual live check for document_parser against real Bedrock — NOT part of
the pytest suite (deliberately not named test_*.py, so it's never
auto-collected; the rest of the suite must stay zero-AWS-dependency).

Run directly when you want to re-verify the vision extraction actually
works, e.g. after a model/SDK upgrade:

    uv run python tests/manual_document_parser_livecheck.py

Uses the synthetic fixture at tests/fixtures/sample_see_marksheet.png —
fabricated data, not a real document, safe to send to the API repeatedly.
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.tools.document_parser import document_parser  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_see_marksheet.png"


def check(label: str, document_type: str, expect_legible: bool) -> None:
    print(f"\n=== {label} ===")
    result = document_parser(image_path=str(FIXTURE), document_type=document_type)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    assert result["ok"] is True, "tool should never fail on a valid readable image"
    assert result["legible"] is expect_legible, f"expected legible={expect_legible}"
    print(f"--- PASS: {label} ---")


if __name__ == "__main__":
    if not FIXTURE.exists():
        raise SystemExit(f"Fixture missing: {FIXTURE}. Regenerate it before running this check.")

    # Correct declared type -> should extract fields cleanly.
    check("correct document_type (see_marksheet)", "see_marksheet", expect_legible=True)

    # Wrong declared type -> should refuse to force-fit, flag mismatch, not
    # hallucinate citizenship fields onto a marksheet.
    check("mismatched document_type (citizenship)", "citizenship", expect_legible=False)

    print("\nAll manual checks passed.")
