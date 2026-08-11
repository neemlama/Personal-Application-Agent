# Sahayogi

> An agent that helps rural/first-gen students and families discover scholarships and
> government subsidies they're eligible for, and prepares the application — pausing for
> human approval before anything is ever submitted.

Built for the AWS Agents for Humans Hackathon with the Strands Agents SDK.

**Status:** early scaffold — Phase 0 in progress.

## Why

Families entitled to real scholarships/subsidies often don't claim them because the
application process is complex, in a language they're not fluent in, or requires
navigating an unfamiliar government portal. Sahayogi does the eligibility research and
form preparation autonomously, and only ever acts on a human's explicit approval for
anything consequential (i.e. actual submission).

## Architecture

See [`docs/architecture.md`](docs/architecture.md) *(coming in Phase 3 writeup)*.

## Development

```bash
uv sync
uv run python agent/main.py
```

## License

MIT — see [LICENSE](LICENSE).
