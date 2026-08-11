"""propose_application (agent-facing tool) + resume_after_approval
(externally-driven, NOT an agent tool) — the two halves of the human
approval session boundary.

propose_application is the actual handoff point: calling it is the
orchestrator declaring "I'm done reasoning, here's what I'd submit, a human
needs to decide." Nothing after this point runs autonomously. Treat it as
the consequential action it is, not a routine tool call.

resume_after_approval is deliberately NOT decorated with @tool — the agent
does not call this on itself. It's invoked externally (CLI/API) only after
an actual human has reviewed the proposal, which is the entire point of
the session-boundary design (see docs / Phase 3 architecture decision). On
"approved" it now actually drives form_filler (Phase 7 — AgentCore
Browser) to complete the real submission.

Known gap, scoped out deliberately rather than silently: if form_filler
fails (network blip, portal change, etc.), status lands on
"submission_failed" and stops there — no automatic retry yet. A human
would need a manual follow-up path, not built in this pass.
"""

from typing import Any, Literal

from strands import tool

from agent.tools.audit_log import log_decision
from agent.tools.form_filler import form_filler
from agent.tools.session_store import get_session, save_pending_proposal, update_status


@tool
def propose_application(
    session_id: str,
    program_id: str,
    applicant_profile: dict[str, Any],
    summary_for_human: str,
) -> dict[str, Any]:
    """Save a proposed application and mark it awaiting human approval.

    Call this once you've decided which program to propose and drafted a
    clear explanation for the human — not before. This is the handoff: it
    durably records the proposal (so it survives to a second, later
    invocation) and logs it to the audit trail with
    requires_human_approval=True. No submission happens here or as a
    result of calling this — submission is a separate, not-yet-implemented
    capability that can only run after resume_after_approval sees an
    "approved" decision.

    Args:
        session_id: The session this proposal belongs to.
        program_id: The catalog program_id being proposed.
        applicant_profile: The applicant profile used to reach this proposal
            (whatever was passed to eligibility_matcher, plus anything
            merged in from document_parser).
        summary_for_human: Your plain-language explanation of what you're
            proposing and why — this is what the human approver reads.

    Returns:
        The saved session record: {session_id, status: "pending_approval",
        proposal, decision_note}.
    """
    proposal = {
        "program_id": program_id,
        "applicant_profile": applicant_profile,
        "summary_for_human": summary_for_human,
    }
    record = save_pending_proposal(session_id, proposal)

    log_decision(
        session_id=session_id,
        actor="agent",
        action="application_proposed",
        detail={"program_id": program_id, "summary": summary_for_human},
        requires_human_approval=True,
    )

    return record


def resume_after_approval(
    session_id: str,
    decision: Literal["approved", "rejected"],
    note: str = "",
) -> str:
    """Second half of the approval flow. Called externally after a human has
    actually reviewed the proposal saved by propose_application — never by
    the agent on itself.

    Raises:
        KeyError: no proposal exists for session_id.
        ValueError: the session was already decided (idempotency guard —
            prevents a double-click or repeated call from processing the
            same approval/rejection twice, which matters a lot once
            "approved" triggers a real submission in Phase 7).
    """
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"No pending proposal found for session_id={session_id!r}")
    if session["status"] != "pending_approval":
        raise ValueError(
            f"Session {session_id} was already resolved (status={session['status']!r}); "
            "refusing to process the same decision twice."
        )

    program_id = session["proposal"]["program_id"]

    log_decision(
        session_id=session_id,
        actor="human",
        action=f"submission_{decision}",
        detail={"note": note, "program_id": program_id},
        requires_human_approval=False,
    )
    update_status(session_id, status=decision, decision_note=note)

    if decision == "rejected":
        return f"Rejected. No further action taken for session {session_id}."

    # decision == "approved" -- drive the actual submission now. This is
    # the one place in the whole system that takes an irreversible external
    # action, and it can only be reached after the guard above confirms a
    # human decision was just recorded for this exact session.
    applicant_profile = session["proposal"]["applicant_profile"]
    result = form_filler(session_id=session_id, program_id=program_id, applicant_profile=applicant_profile)

    if result["ok"]:
        log_decision(
            session_id=session_id,
            actor="agent",
            action="submission_completed",
            detail={"program_id": program_id, "reference_number": result["reference_number"]},
            requires_human_approval=False,
        )
        update_status(session_id, status="submitted", decision_note=note)
        return (
            f"Approved and submitted for session {session_id}. "
            f"Reference number: {result['reference_number']}"
        )

    # Submission failed -- land on a distinct terminal-ish status (not
    # "approved", not "pending_approval") so it's visibly not silently
    # retried by a repeat call, and not confused with an undecided session.
    # No automatic retry built yet -- see module docstring.
    log_decision(
        session_id=session_id,
        actor="agent",
        action="submission_failed",
        detail={"program_id": program_id, "notes": result["notes"]},
        requires_human_approval=False,
    )
    update_status(session_id, status="submission_failed", decision_note=note)
    return f"Approved, but submission failed for session {session_id}: {result['notes']}"
