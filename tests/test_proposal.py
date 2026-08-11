"""Tests for propose_form_fill + resume_after_approval — fully local,
isolating both the session store and audit log per test.

fill_and_submit_form is mocked (via monkeypatch on
agent.tools.proposal.fill_and_submit_form) for the "submission succeeds"
path so this stays a fast, zero-AWS test — the real browser-driven path is
covered by tests/manual_form_filler_livecheck.py against actual AgentCore
Browser."""

import pytest

from agent.tools.audit_log import read_local_entries
from agent.tools.proposal import propose_form_fill, resume_after_approval
from agent.tools.session_store import get_session

COMPLETE_FIELDS = [
    {"label": "Full Name", "field_type": "text", "selector": "#full_name", "required": True, "value": "Alex Rai"},
    {"label": "Email Address", "field_type": "email", "selector": "#email", "required": True, "value": "alex@example.com"},
    {"label": "Phone Number", "field_type": "tel", "selector": "#phone", "required": False, "value": ""},
]

INCOMPLETE_FIELDS = [
    {"label": "Full Name", "field_type": "text", "selector": "#full_name", "required": True, "value": "Alex Rai"},
    {"label": "Email Address", "field_type": "email", "selector": "#email", "required": True, "value": ""},  # missing!
]


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_STORE_LOCAL_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("AUDIT_LOG_LOCAL_PATH", str(tmp_path / "audit.jsonl"))
    yield


def _propose(session_id="s1", fields=None):
    return propose_form_fill(
        session_id=session_id,
        url="https://example.com/rsvp",
        fields=fields if fields is not None else COMPLETE_FIELDS,
        submit_selector="#submit-btn",
        summary_for_human="Submitting the RSVP with your name, email, and phone.",
    )


def test_propose_saves_pending_session_and_logs_it():
    result = _propose()
    assert result["status"] == "pending_approval"

    session = get_session("s1")
    assert session["proposal"]["url"] == "https://example.com/rsvp"

    entries = read_local_entries("s1")
    assert len(entries) == 1
    assert entries[0]["action"] == "form_fill_proposed"
    assert entries[0]["requires_human_approval"] is True
    assert entries[0]["actor"] == "agent"


def test_propose_refuses_when_a_required_field_has_no_value():
    # Safety property: an incomplete plan must never be saveable as if it
    # were ready for approval -- catches the case even if the orchestrator's
    # own completeness check was skipped or wrong.
    with pytest.raises(ValueError, match="Email Address"):
        _propose(fields=INCOMPLETE_FIELDS)

    assert get_session("s1") is None  # nothing was saved


def test_approval_with_complete_fields_submits_successfully(monkeypatch):
    monkeypatch.setattr(
        "agent.tools.proposal.fill_and_submit_form",
        lambda session_id, url, fields, submit_selector: {
            "ok": True,
            "confirmation_text": "RSVP-FAKE123",
            "notes": "mocked success",
        },
    )
    _propose()
    message = resume_after_approval("s1", decision="approved", note="looks right")

    assert "RSVP-FAKE123" in message
    assert get_session("s1")["status"] == "submitted"

    entries = read_local_entries("s1")
    assert [e["action"] for e in entries] == ["form_fill_proposed", "submission_approved", "submission_completed"]
    assert entries[2]["detail"]["confirmation_text"] == "RSVP-FAKE123"


def test_approval_when_submission_fails_does_not_crash(monkeypatch):
    monkeypatch.setattr(
        "agent.tools.proposal.fill_and_submit_form",
        lambda session_id, url, fields, submit_selector: {
            "ok": False,
            "confirmation_text": None,
            "notes": "page timed out",
        },
    )
    _propose()
    message = resume_after_approval("s1", decision="approved")

    assert "submission failed" in message.lower()
    assert get_session("s1")["status"] == "submission_failed"


def test_normal_rejection_flow():
    _propose()
    message = resume_after_approval("s1", decision="rejected", note="wrong event")

    assert "Rejected" in message
    assert get_session("s1")["status"] == "rejected"
    assert get_session("s1")["decision_note"] == "wrong event"

    # Rejection must never reach fill_and_submit_form -- only two entries.
    entries = read_local_entries("s1")
    assert [e["action"] for e in entries] == ["form_fill_proposed", "submission_rejected"]


def test_resuming_a_session_that_was_never_proposed_raises():
    with pytest.raises(KeyError):
        resume_after_approval("never-proposed", decision="approved")


def test_double_approval_is_rejected_not_processed_twice(monkeypatch):
    monkeypatch.setattr(
        "agent.tools.proposal.fill_and_submit_form",
        lambda session_id, url, fields, submit_selector: {
            "ok": True,
            "confirmation_text": "RSVP-FAKE123",
            "notes": "mocked success",
        },
    )
    _propose()
    resume_after_approval("s1", decision="approved")

    with pytest.raises(ValueError):
        resume_after_approval("s1", decision="approved")

    entries = read_local_entries("s1")
    assert len(entries) == 3


def test_rejected_then_new_proposal_needs_a_new_session_id():
    _propose("s1")
    resume_after_approval("s1", decision="rejected")

    with pytest.raises(ValueError):
        _propose("s1")

    result = _propose("s2")
    assert result["status"] == "pending_approval"
