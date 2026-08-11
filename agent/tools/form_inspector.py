"""inspect_form — visits an arbitrary URL and reads back its form structure.

This is the genuinely hard part of the generic-form-filling pivot: there's
no pre-built map of the page like the old scholarship-specific PORTAL_MAP.
The agent has to discover field labels, types, and selectors live, from
whatever HTML the page actually returns.

Isolated Strands Agent + AgentCore Browser tool, same pattern as
document_parser's vision extractor and form_filler's fill agent —
callback_handler=None because its tool-call chatter isn't user-facing.

Deliberate scope limits, stated rather than silently assumed:
  - Reads the FIRST <form> found on the page. Multi-form pages (e.g. a
    search box plus the actual RSVP form) may need a hint; not handled.
  - No login walls, no CAPTCHA solving, no JS-heavy SPA forms that render
    fields after complex interaction. Static/server-rendered forms only.
  - Does not fill or submit anything -- read-only.
"""

import json
from typing import Any

from strands import Agent, tool

_INSPECTOR_PROMPT = """\
You are inspecting a web form, not filling it out. Navigate to the given \
URL (use init_session first, then navigate), then use get_html to read the \
page's HTML source.

Find the first <form> on the page (or the most prominent set of input \
fields if there's no explicit <form> tag). For every field in it, \
determine:
  - label: the human-readable label (from an associated <label>, aria-label, \
    placeholder, or nearby text -- best guess if ambiguous)
  - field_type: one of "text", "email", "tel", "number", "date", \
    "textarea", "select", "checkbox"
  - selector: a CSS selector you could use to target this exact element -- \
    strongly prefer "#id" if the element has an id, otherwise a \
    name= attribute selector, otherwise the most specific selector you can \
    construct
  - options: for "select" fields, the list of visible option text values; \
    null for everything else
  - required: true if the element has a required attribute or is visually/\
    textually marked required (e.g. an asterisk)

Also identify submit_selector: a CSS selector for the form's submit \
button.

Respond with ONLY a single JSON object, no prose, no markdown fence:
{"ok": true|false, "fields": [{"label": "...", "field_type": "...", \
"selector": "...", "options": null, "required": true|false}, ...], \
"submit_selector": "...", "notes": "<anything unusual: no form found, \
login wall, CAPTCHA, JS-rendered content that didn't load, etc>"}

If you cannot find a usable form (login required, CAPTCHA, page didn't \
load, no form present), set "ok": false and explain why in notes -- do not \
invent fields that aren't really there.
"""


def _parse_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("no JSON object found in model output", text, 0)


@tool
def inspect_form(url: str, region: str = "us-east-1") -> dict[str, Any]:
    """Visit url and return its discovered form structure.

    Unlike fill_and_submit_form, this IS a direct agent tool — it's
    read-only (never fills or submits anything), so there's no approval
    boundary to protect here, same reasoning as document_parser being a
    direct tool while form_filler is not.

    Returns:
        {"ok": bool, "fields": [...], "submit_selector": str|None,
         "notes": str}
        ok=False (e.g. login wall, CAPTCHA, page didn't load, unparseable
        model output) always comes back structured, never raises.
    """
    from strands_tools.browser import AgentCoreBrowser  # local: heavy dep, see form_filler.py

    browser_tool = AgentCoreBrowser(region=region)
    inspector = Agent(system_prompt=_INSPECTOR_PROMPT, tools=[browser_tool.browser], callback_handler=None)

    response = inspector(f"Inspect the form at this URL: {url}")

    try:
        result = _parse_json(str(response))
    except json.JSONDecodeError:
        return {
            "ok": False,
            "fields": [],
            "submit_selector": None,
            "notes": f"Inspector did not return valid JSON: {str(response)[:500]!r}",
        }

    return {
        "ok": bool(result.get("ok", False)),
        "fields": result.get("fields", []),
        "submit_selector": result.get("submit_selector"),
        "notes": result.get("notes", ""),
    }
