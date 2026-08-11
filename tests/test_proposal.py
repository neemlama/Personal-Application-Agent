"""Tests for propose_application + resume_after_approval — fully local,
isolating both the session store and audit log per test.

form_filler is mocked (via monkeypatch on agent.tools.proposal.form_filler,
the name as imported/used there) for the "submission succeeds" path so this
stays a fast, zero-AWS test — the real browser-driven path is covered by
tests/manual_form_filler_livecheck.py against actual AgentCore Browser. The
"submission fails" path below is NOT mocked — it's real form_filler logic
exercising its own missing-fields guard (a deliberately incomplete profile
never reaches the browser/AWS import at all), so that's genuine coverage,
not a stand-in."""

import pytest

from agent.tools.audit_log import read_local_entries
from agent.tools.proposal import propose_application, resume_after_approval
from agent.tools.session_store import get_session


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_STORE_LOCAL_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("AUDIT_LOG_LOCAL_PATH", str(tmp_path / "audit.jsonl"))
    yield


def _propose(session_id="s1", applicant_profile=None):
    return propose_application(
        session_id=session_id,
        program_id="ctevt-special-scholarship",
        applicant_profile=applicant_profile or {"age": 16, "marginalized_groups": ["Dalit"]},
        summary_for_human="You qualify based on age, education, and group membership.",
    )


def test_propose_saves_pending_session_and_logs_it():
    result = _propose()
    assert result["status"] == "pending_approval"

    session = get_session("s1")
    assert session["proposal"]["program_id"] == "ctevt-special-scholarship"

    entries = read_local_entries("s1")
    assert len(entries) == 1
    assert entries[0]["action"] == "application_proposed"
    assert entries[0]["requires_human_approval"] is True
    assert entries[0]["actor"] == "agent"


def test_approval_with_complete_profile_submits_successfully(monkeypatch):
    monkeypatch.setattr(
        "agent.tools.proposal.form_filler",
        lambda session_id, program_id, applicant_profile: {
            "ok": True,
            "reference_number": "FAKE-REF-123",
            "notes": "mocked success",
        },
    )
    _propose()
    message = resume_after_approval("s1", decision="approved", note="verified with school")

    assert "FAKE-REF-123" in message
    assert get_session("s1")["status"] == "submitted"

    entries = read_local_entries("s1")
    assert [e["action"] for e in entries] == ["application_proposed", "submission_approved", "submission_completed"]
    assert entries[2]["detail"]["reference_number"] == "FAKE-REF-123"


def test_approval_with_incomplete_profile_fails_submission_without_crashing():
    # Real (unmocked) form_filler logic: the default test profile has none
    # of the real form's required fields, so this exercises the actual
    # missing-fields guard -- confirms approval never crashes the caller
    # even when submission can't proceed, and never touches AWS to find out.
    _propose()  # incomplete profile by default
    message = resume_after_approval("s1", decision="approved")

    assert "submission failed" in message.lower()
    assert get_session("s1")["status"] == "submission_failed"

    entries = read_local_entries("s1")
    assert [e["action"] for e in entries] == ["application_proposed", "submission_approved", "submission_failed"]


def test_normal_rejection_flow():
    _propose()
    message = resume_after_approval("s1", decision="rejected", note="wrong program")

    assert "Rejected" in message
    assert get_session("s1")["status"] == "rejected"
    assert get_session("s1")["decision_note"] == "wrong program"

    # Rejection must never reach form_filler -- only two entries, not three.
    entries = read_local_entries("s1")
    assert [e["action"] for e in entries] == ["application_proposed", "submission_rejected"]


def test_resuming_a_session_that_was_never_proposed_raises():
    # Dangerous case: nothing to approve — must fail loudly, not silently no-op.
    with pytest.raises(KeyError):
        resume_after_approval("never-proposed", decision="approved")


def test_double_approval_is_rejected_not_processed_twice(monkeypatch):
    # Dangerous case: prevents a double-click (or replayed request) from
    # being treated as two separate approvals — approving twice must not
    # submit twice.
    monkeypatch.setattr(
        "agent.tools.proposal.form_filler",
        lambda session_id, program_id, applicant_profile: {
            "ok": True,
            "reference_number": "FAKE-REF-123",
            "notes": "mocked success",
        },
    )
    _propose()
    resume_after_approval("s1", decision="approved")

    with pytest.raises(ValueError):
        resume_after_approval("s1", decision="approved")

    # Only the original propose + first approval's two entries were logged.
    entries = read_local_entries("s1")
    assert len(entries) == 3


def test_rejected_then_new_proposal_needs_a_new_session_id():
    _propose("s1")
    resume_after_approval("s1", decision="rejected")

    with pytest.raises(ValueError):
        _propose("s1")  # same session_id, already resolved -- must not silently reopen

    # A fresh session_id works fine.
    result = _propose("s2")
    assert result["status"] == "pending_approval"
