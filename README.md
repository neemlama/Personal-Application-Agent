# FormBuddy

> An agent that fills out web forms for you — RSVPs, signups, applications, any form
> with a URL — and only ever submits after you explicitly approve the exact plan.

Built for the AWS Agents for Humans Hackathon with the Strands Agents SDK.

## Why

Filling out the same kind of information into form after form is genuinely repetitive
work — event RSVPs, signups, applications. FormBuddy reads whatever form you point it
at, matches it against what you've told it about yourself, and drafts an exact fill
plan. It never fabricates a value for a field it doesn't have real data for — it asks
instead. Nothing is ever submitted without your explicit approval.

## Two modes, one brain

| | Cloud mode | Chrome extension mode |
|---|---|---|
| You give it | a URL | the tab you already have open |
| It reads the form via | AgentCore Browser (managed remote browser) | a content script reading your own tab |
| On approval, it | fills **and submits** via AgentCore Browser | fills only — **you** click Submit |
| Your profile | sent in the chat conversation | stays in `chrome.storage.local`, sent only when you click Analyze |

Same orchestrator, same approval boundary, same audit trail either way — only *how it
sees the page* and *who executes the fill* differs. See
[`agent/orchestrator.py`](agent/orchestrator.py) and
[`agent/tools/proposal.py`](agent/tools/proposal.py).

## Safety model

```
Chat/page → agent researches the form → drafts a fill plan
    ↓
Missing required field? → agent asks you, never invents a value
    ↓
propose_form_fill (refuses to save an incomplete plan)
    ↓
HUMAN reviews the exact plan and approves or rejects
    ↓
Cloud mode: AgentCore Browser fills + submits
Extension mode: your browser fills the fields, you click Submit
```

Every step is logged to an audit trail (`agent/tools/audit_log.py`) — who did what, when,
and why.

## Project layout

```
agent/            Orchestrator + tools (form inspection, filling, approval flow)
api/               FastAPI backend — thin HTTP wrapper around agent/, serves frontend/
frontend/          Web chat UI (cloud mode)
extension/         Chrome extension (Manifest V3) — side panel UI (extension mode)
demo/mock-rsvp/    A demo form (S3-hosted) used for reliable, repeatable testing
tests/             pytest suite (zero-AWS-dependency) + manual live-check scripts
docs/              Design notes
```

## Running it

**Backend** (required for both modes):
```bash
uv sync
uv run uvicorn api.main:app --port 8000
```

**Web UI (cloud mode):** open `http://localhost:8000`.

**Chrome extension (extension mode):**
1. `chrome://extensions` → enable Developer mode → **Load unpacked** → select `extension/`
2. Pin the FormBuddy icon, click it on any tab with a form, fill in your profile once

**CLI (for testing/debugging):**
```bash
uv run python -m agent.orchestrator "your message here"
uv run python -m agent.orchestrator --resume <session_id> approved
```

## Testing

```bash
uv run pytest tests/
```
Fully local, zero AWS dependency. Live checks against real AgentCore Browser /
Bedrock live in `tests/manual_*.py` (not auto-run — see each file's docstring).

## License

MIT — see [LICENSE](LICENSE).
