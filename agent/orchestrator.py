"""Sahayogi orchestrator agent — generic web form filler.

Given a URL and whatever the user has told it about themselves, this agent:
  1. calls inspect_form to discover the actual fields on that page (no
     pre-built map — this is genuine live discovery, not a lookup)
  2. matches what it knows about the user against the discovered fields,
     leaving anything it doesn't have data for as unfilled rather than
     inventing a plausible-looking value
  3. calls log_decision to record what it found and drafted
  4. calls propose_form_fill to hand off an exact fill plan for human
     approval — this is the actual autonomy boundary, not just a text reply.
     propose_form_fill itself refuses to save a plan with missing required
     fields, so an incomplete plan can never reach a human as if it were
     ready.

It has no submission tool. Submission only runs from resume_after_approval()
(agent/tools/proposal.py), invoked externally after a human has actually
reviewed the proposal — never by the agent on itself.
"""

import sys

from strands import Agent

from agent.tools.audit_log import log_decision
from agent.tools.document_parser import document_parser
from agent.tools.form_inspector import inspect_form
from agent.tools.proposal import propose_form_fill, resume_after_approval

SYSTEM_PROMPT = """\
You are Sahayogi, an assistant that fills out web forms on the user's \
behalf — event RSVPs, signups, applications, any form with a URL — using \
what they've told you about themselves, and only ever submits after they \
explicitly approve the exact plan. Reply in whichever language the user \
writes to you in.

Every user message includes a line "session_id: <id>" — use that exact \
value whenever you call log_decision or propose_form_fill.

If the user gives you a path to a photo of a document (an ID, a card, \
anything with relevant info printed on it), call document_parser on it \
before asking them to retype details that are already in the photo. If \
legible=false or fields are listed in low_confidence_fields, say so \
plainly and ask the user to confirm rather than guessing.

Process whenever the user gives you a form URL:
1. Call inspect_form on the URL to discover its actual fields. If ok=false \
(login wall, CAPTCHA, page didn't load, no form found), tell the user \
plainly why you can't proceed — do not invent fields for a form you \
couldn't actually read.
2. For each discovered field, match it against what the user has told you \
so far in this conversation. Use your judgment on label wording — a field \
labeled "Full Name" matches "my name is...", a field labeled "Email \
Address" matches an email the user gave you, etc. Leave "value" empty for \
any field you don't have real data for.
3. If any REQUIRED field has no value, ask the user for exactly those \
fields — do not call propose_form_fill yet, and never fabricate a \
plausible-looking value to fill the gap.
4. Call log_decision once to record the discovered fields and your draft \
mapping (actor="agent", action="fields_matched").
5. Once every required field has a real value, call propose_form_fill with \
the complete field list (each entry: label, field_type, selector, \
required, value — carry these through exactly as inspect_form gave them, \
just filling in "value"), the submit_selector from inspect_form, and a \
clear summary_for_human describing exactly what you're about to submit and \
why. This call will itself refuse and tell you what's missing if you got \
the completeness check wrong — if that happens, go back and ask the user, \
don't retry with a made-up value.
6. Present your findings to the user in your reply regardless: what form \
you found, what you filled in and from where, what's still needed, and — \
if you called propose_form_fill — that it's now awaiting their approval \
before anything is submitted.

You never submit anything on the user's behalf and you have no tool that \
does so. propose_form_fill only records a proposal for a human to \
review — it does not submit anything either.
"""


def build_agent() -> Agent:
    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[inspect_form, log_decision, document_parser, propose_form_fill],
    )


def run(session_id: str, message: str) -> str:
    agent = build_agent()
    result = agent(f"session_id: {session_id}\n\n{message}")
    return str(result)


def _force_utf8_stdout() -> None:
    # Windows consoles default to a legacy codepage (e.g. cp1252) that can't
    # encode emoji or non-Latin scripts the model may output, and Strands
    # streams tokens straight to stdout.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _cli_propose(argv: list[str]) -> None:
    default_message = (
        "I'd like to RSVP to this community meetup: "
        "https://example.com/meetup-rsvp. My name is Alex Rai, email "
        "alex@example.com, phone 9800000000, bringing 2 guests, vegetarian, "
        "T-shirt size L."
    )
    message = " ".join(argv) or default_message
    # Don't print the return value: Strands' default callback handler
    # already streams the full response to stdout as it's generated.
    run(session_id="cli-test-session", message=message)


def _cli_resume(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in ("approved", "rejected"):
        print('Usage: python -m agent.orchestrator --resume <session_id> approved|rejected ["note"]')
        raise SystemExit(1)
    session_id, decision = argv[0], argv[1]
    note = " ".join(argv[2:])
    print(resume_after_approval(session_id, decision=decision, note=note))


if __name__ == "__main__":
    _force_utf8_stdout()

    args = sys.argv[1:]
    if args and args[0] == "--resume":
        _cli_resume(args[1:])
    else:
        _cli_propose(args)
