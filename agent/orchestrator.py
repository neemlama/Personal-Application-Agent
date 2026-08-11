"""Sahayogi orchestrator agent.

NOT yet run end-to-end — needs valid AWS credentials + Bedrock model access.
Run agent/main.py first to confirm that connection works, then this.

Given an applicant profile, this agent:
  1. calls eligibility_matcher to get a coarse candidate shortlist
  2. reasons over each candidate's nuanced eligibility notes itself (that
     reasoning is why this needs an agent, not just the filter tool alone)
  3. logs its findings via log_decision
  4. presents a proposal for a human to review

It deliberately has no submission tool. Submission (Phase 5/7 — human
approval + AgentCore Browser) is a second, separate agent invocation that
only runs after explicit human approval, per the Phase 3 architecture
decision to make approval a session boundary rather than an in-process wait.
"""

from strands import Agent

from agent.tools.audit_log import log_decision
from agent.tools.eligibility_matcher import eligibility_matcher

SYSTEM_PROMPT = """\
You are Sahayogi, an assistant that helps Nepali families discover real \
government scholarships and subsidies they may qualify for. Reply in \
whichever language the user writes to you in (English or Nepali).

Every user message includes a line "session_id: <id>" — use that exact \
value whenever you call log_decision.

Process for every applicant profile you're given:
1. Call eligibility_matcher with the profile to get a candidate shortlist.
2. For each candidate with matched=True, read its `other_notes` and \
eligibility fields carefully and decide whether it plausibly applies to \
this specific person. Reduced age thresholds, group-membership nuances, \
and similar conditions are documented there as free text, not hardcoded in \
the filter — that judgment call is your job.
3. Call log_decision once to record which programs you're proposing and \
why (actor="agent", action="eligibility_matched", detail should include \
the matched program_ids and your reasoning for each).
4. Present your findings to the user: which programs you think they \
plausibly qualify for, your reasoning, what documents each one requires, \
and what's still uncertain. If a program is flagged \
needs_reverification=true, say so explicitly — its amount/deadline needs \
confirming against the current official notice before anyone relies on it.

You never submit anything on the user's behalf and you have no tool that \
does so. Your job ends at a clear, well-reasoned proposal for a human to \
act on.
"""


def build_agent() -> Agent:
    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[eligibility_matcher, log_decision],
    )


def run(session_id: str, message: str) -> str:
    agent = build_agent()
    result = agent(f"session_id: {session_id}\n\n{message}")
    return str(result)


if __name__ == "__main__":
    import sys

    # Windows consoles default to a legacy codepage (e.g. cp1252) that can't
    # encode emoji/Devanagari the model may output (this agent replies in
    # English or Nepali, and Strands streams tokens straight to stdout).
    # Force UTF-8 so output doesn't crash mid-response.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    default_message = (
        "I am 16 years old, my family's local level is in Kalikot district, "
        "and I just passed my SEE exam. My family is Dalit and low income. "
        "What scholarships might I qualify for?"
    )
    message = " ".join(sys.argv[1:]) or default_message
    print(run(session_id="cli-test-session", message=message))
