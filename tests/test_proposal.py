"""Tests for propose_application + resume_after_approval — fully local,
isolating both the session store and audit log per test."""

import pytest

from agent.tools.audit_log import read_local_entries
from agent.tools.proposal import propose_application, resume_after_approval
from agent.tools.session_store import get_session


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_STORE_LOCAL_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("AUDIT_LOG_LOCAL_PATH", str(tmp_path / "audit.jsonl"))
    yield


def _propose(session_id="s1"):
    return propose_application(
        session_id=session_id,
        program_id="ctevt-special-scholarship",
        applicant_profile={"age": 16, "marginalized_groups": ["Dalit"]},
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


def test_normal_approval_flow():
    _propose()
    message = resume_after_approval("s1", decision="approved", note="verified with school")

    assert "Approved" in message
    assert get_session("s1")["status"] == "approved"

    entries = read_local_entries("s1")
    assert len(entries) == 2  # propose + approve
    assert entries[1]["action"] == "submission_approved"
    assert entries[1]["actor"] == "human"


def test_normal_rejection_flow():
    _propose()
    message = resume_after_approval("s1", decision="rejected", note="wrong program")

    assert "Rejected" in message
    assert get_session("s1")["status"] == "rejected"
    assert get_session("s1")["decision_note"] == "wrong program"


def test_resuming_a_session_that_was_never_proposed_raises():
    # Dangerous case: nothing to approve — must fail loudly, not silently no-op.
    with pytest.raises(KeyError):
        resume_after_approval("never-proposed", decision="approved")


def test_double_approval_is_rejected_not_processed_twice():
    # Dangerous case: prevents a double-click (or replayed request) from
    # being treated as two separate approvals once a real submission tool
    # exists in Phase 7 — approving twice must not submit twice.
    _propose()
    resume_after_approval("s1", decision="approved")

    with pytest.raises(ValueError):
        resume_after_approval("s1", decision="approved")

    # Only the original propose + first approval were logged, not a second.
    entries = read_local_entries("s1")
    assert len(entries) == 2


def test_rejected_then_new_proposal_needs_a_new_session_id():
    _propose("s1")
    resume_after_approval("s1", decision="rejected")

    with pytest.raises(ValueError):
        _propose("s1")  # same session_id, already resolved -- must not silently reopen

    # A fresh session_id works fine.
    result = _propose("s2")
    assert result["status"] == "pending_approval"
