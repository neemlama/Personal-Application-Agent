"""Manual live check for form_filler against real AgentCore Browser — NOT
part of the pytest suite (not named test_*.py, never auto-collected; the
rest of the suite stays zero-AWS-dependency).

Run directly to re-verify the actual browser-driven submission works, e.g.
after an SDK upgrade or a mock portal change:

    uv run python tests/manual_form_filler_livecheck.py

Fills and submits a real (mock) application via AWS's managed remote
browser. Takes ~1-2 minutes; watch it live in the AgentCore Browser console
if you want (see docs printed at the end of the AWS quickstart).
"""

import json
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.tools.form_filler import form_filler  # noqa: E402
from tests.test_form_filler import COMPLETE_PROFILE  # noqa: E402

if __name__ == "__main__":
    print("Submitting mock application via AgentCore Browser... (this takes a bit)")
    result = form_filler(
        session_id="manual-livecheck-session",
        program_id="ctevt-special-scholarship",
        applicant_profile=COMPLETE_PROFILE,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    assert result["ok"] is True, f"expected ok=True, got notes: {result['notes']}"
    assert result["reference_number"], "expected a non-empty reference_number"
    assert result["reference_number"].startswith("CTEVT-MOCK-"), "unexpected reference number format"
    print("\nPASS: form_filler completed a real submission against the mock portal.")
