"""Phase 0 smoke test: confirms Strands + AWS Bedrock wiring works end to end.

Requires:
  - AWS credentials configured (env vars, ~/.aws/credentials, or SSO) with a
    region that has Bedrock model access granted for the account.
  - Model access enabled in the Bedrock console for the model Strands picks
    by default (Anthropic Claude). See:
    https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
"""

import sys

from strands import Agent


def main() -> None:
    # See agent/orchestrator.py for why: Windows consoles can't always
    # encode what the model streams to stdout.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    agent = Agent(
        system_prompt=(
            "You are a smoke-test assistant for the FormBuddy project. "
            "Reply with exactly one short sentence confirming you are alive."
        )
    )
    result = agent("Are you working?")
    print(result)


if __name__ == "__main__":
    main()
