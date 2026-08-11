"""Phase 0 smoke test: confirms Strands + AWS Bedrock wiring works end to end.

Requires:
  - AWS credentials configured (env vars, ~/.aws/credentials, or SSO) with a
    region that has Bedrock model access granted for the account.
  - Model access enabled in the Bedrock console for the model Strands picks
    by default (Anthropic Claude). See:
    https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
"""

from strands import Agent


def main() -> None:
    agent = Agent(
        system_prompt=(
            "You are a smoke-test assistant for the Sahayogi project. "
            "Reply with exactly one short sentence confirming you are alive."
        )
    )
    result = agent("Are you working?")
    print(result)


if __name__ == "__main__":
    main()
