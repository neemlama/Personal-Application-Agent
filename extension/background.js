// FormBuddy extension service worker. Two jobs:
//   1. Make the toolbar icon open the side panel (standard MV3 pattern).
//   2. Relay EXTRACT_PAGE / FILL_FIELDS requests from the side panel into
//      the active tab via chrome.scripting.executeScript.
//
// Deliberately does NOT declare a persistent content script -- these two
// functions are injected on demand, only when the side panel asks for
// them, keeping the extension's footprint on every page minimal.

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
});

// --- Functions injected into the page. Everything inside must be
// self-contained (no closures over outer scope -- executeScript serializes
// the function body and runs it in the page's own JS context). ---

function extractPageForInspection() {
  const form = document.querySelector("form");
  const scope = form || document.body;
  return {
    html: scope.outerHTML,
    url: window.location.href,
    title: document.title,
  };
}

function fillFieldsInPage(fields) {
  // fields: [{selector, field_type, value}]. Never clicks a submit button
  // -- filling only, the human always does the actual submit.
  const results = [];
  for (const f of fields) {
    if (f.value === null || f.value === undefined || f.value === "") {
      results.push({ label: f.label, ok: true, skipped: true });
      continue;
    }
    try {
      const el = document.querySelector(f.selector);
      if (!el) {
        results.push({ label: f.label, ok: false, error: "selector not found: " + f.selector });
        continue;
      }
      if (f.field_type === "checkbox") {
        if (Boolean(f.value) !== el.checked) el.click();
      } else if (f.field_type === "select") {
        const options = Array.from(el.options || []);
        const match = options.find((o) => o.value === f.value || o.text.trim() === String(f.value).trim());
        if (!match) {
          results.push({ label: f.label, ok: false, error: "no matching option for " + f.value });
          continue;
        }
        el.value = match.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        el.value = f.value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
      results.push({ label: f.label, ok: true });
    } catch (e) {
      results.push({ label: f.label, ok: false, error: String(e) });
    }
  }
  return results;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("No active tab found");
  return tab;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "EXTRACT_PAGE") {
    (async () => {
      try {
        const tab = await getActiveTab();
        const [{ result }] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: extractPageForInspection,
        });
        sendResponse({ ok: true, ...result });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true; // keep sendResponse alive for the async work above
  }

  if (msg.type === "FILL_FIELDS") {
    (async () => {
      try {
        const tab = await getActiveTab();
        const [{ result }] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: fillFieldsInPage,
          args: [msg.fields],
        });
        sendResponse({ ok: true, results: result });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }

  return false;
});
