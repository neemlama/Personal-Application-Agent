"""propose_form_fill (agent-facing tool) + resume_after_approval
(externally-driven, NOT an agent tool) — the two halves of the human
approval session boundary.

propose_form_fill is the actual handoff point: calling it is the
orchestrator declaring "I'm done reasoning, here's exactly what I'd fill
in and submit, a human needs to decide." Nothing after this point runs
autonomously. Treat it as the consequential action it is, not a routine
tool call.

resume_after_approval is deliberately NOT decorated with @tool — the agent
does not call this on itself. It's invoked externally (CLI/API) only after
an actual human has reviewed the proposal. On "approved" it drives
fill_and_submit_form (AgentCore Browser) to complete the real submission.

Known gap, scoped out deliberately rather than silently: if
fill_and_submit_form fails (network blip, page changed, etc.), status
lands on "submission_failed" and stops there — no automatic retry yet. A
human would need a manual follow-up path, not built in this pass.
"""

from typing import Any, Literal

from strands import tool

from agent.tools.audit_log import log_decision
from agent.tools.form_filler import fill_and_submit_form
from agent.tools.session_store import get_session, save_pending_proposal, update_status


def _missing_required_fields(fields: list[dict[str, Any]]) -> list[str]:
    return [f["label"] for f in fields if f.get("required") and f.get("value") in (None, "")]


@tool
def propose_form_fill(
    session_id: str,
    url: str,
    fields: list[dict[str, Any]],
    submit_selector: str | None,
    summary_for_human: str,
) -> dict[str, Any]:
    """Save a proposed form submission and mark it awaiting human approval.

    Call this only after inspect_form has told you what the form actually
    contains AND you have a value for every field you're confident about.
    This is the handoff: it durably records the exact fill plan (so it
    survives to a second, later invocation) and logs it to the audit trail
    with requires_human_approval=True. No submission happens here or as a
    result of calling this.

    Args:
        session_id: The session this proposal belongs to.
        url: The form's URL.
        fields: [{"label", "field_type", "selector", "required", "value"},
            ...] — one entry per field inspect_form discovered. Leave
            "value" as null/empty for anything you don't have data for —
            do NOT invent a value. If any REQUIRED field has no value,
            this call is refused (see Raises) so you can ask the user
            instead of proposing an incomplete plan.
        submit_selector: CSS selector for the submit button, from
            inspect_form.
        summary_for_human: Your plain-language explanation of what you're
            about to submit and why — this is what the human approver reads.

    Returns:
        The saved session record: {session_id, status: "pending_approval",
        proposal, decision_note}.

    Raises:
        ValueError: one or more required fields have no value. The message
            lists which ones — go back and ask the user for them.
    """
    missing = _missing_required_fields(fields)
    if missing:
        raise ValueError(
            f"Refusing to propose: these required fields have no value yet: {missing}. "
            "Ask the user for them rather than guessing."
        )

    proposal = {
        "url": url,
        "fields": fields,
        "submit_selector": submit_selector,
        "summary_for_human": summary_for_human,
    }
    record = save_pending_proposal(session_id, proposal)

    log_decision(
        session_id=session_id,
        actor="agent",
        action="form_fill_proposed",
        detail={"url": url, "summary": summary_for_human},
        requires_human_approval=True,
    )

    return record


def resume_after_approval(
    session_id: str,
    decision: Literal["approved", "rejected"],
    note: str = "",
) -> str:
    """Second half of the approval flow. Called externally after a human has
    actually reviewed the proposal saved by propose_form_fill — never by
    the agent on itself.

    Raises:
        KeyError: no proposal exists for session_id.
        ValueError: the session was already decided (idempotency guard —
            prevents a double-click or repeated call from processing the
            same approval/rejection twice, which matters a lot once
            "approved" triggers a real submission).
    """
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"No pending proposal found for session_id={session_id!r}")
    if session["status"] != "pending_approval":
        raise ValueError(
            f"Session {session_id} was already resolved (status={session['status']!r}); "
            "refusing to process the same decision twice."
        )

    url = session["proposal"]["url"]

    log_decision(
        session_id=session_id,
        actor="human",
        action=f"submission_{decision}",
        detail={"note": note, "url": url},
        requires_human_approval=False,
    )
    update_status(session_id, status=decision, decision_note=note)

    if decision == "rejected":
        return f"Rejected. No further action taken for session {session_id}."

    # decision == "approved" -- drive the actual submission now. This is
    # the one place in the whole system that takes an irreversible external
    # action, and it can only be reached after the guard above confirms a
    # human decision was just recorded for this exact session.
    fields = session["proposal"]["fields"]
    submit_selector = session["proposal"]["submit_selector"]
    result = fill_and_submit_form(session_id=session_id, url=url, fields=fields, submit_selector=submit_selector)

    if result["ok"]:
        log_decision(
            session_id=session_id,
            actor="agent",
            action="submission_completed",
            detail={"url": url, "confirmation_text": result["confirmation_text"]},
            requires_human_approval=False,
        )
        update_status(session_id, status="submitted", decision_note=note)
        return f"Approved and submitted for session {session_id}. Confirmation: {result['confirmation_text']}"

    # Submission failed -- land on a distinct terminal-ish status (not
    # "approved", not "pending_approval") so it's visibly not silently
    # retried by a repeat call, and not confused with an undecided session.
    # No automatic retry built yet -- see module docstring.
    log_decision(
        session_id=session_id,
        actor="agent",
        action="submission_failed",
        detail={"url": url, "notes": result["notes"]},
        requires_human_approval=False,
    )
    update_status(session_id, status="submission_failed", decision_note=note)
    return f"Approved, but submission failed for session {session_id}: {result['notes']}"
