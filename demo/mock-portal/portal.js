// Mock portal client-side state — a fake application system, all data stays
// in the browser's localStorage. No backend. Deliberately: this is a demo
// target for AgentCore Browser automation testing, not a real service.

const STORAGE_KEY = "sahayogi_demo_application";

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch (e) {
    return {};
  }
}

function saveState(partial) {
  const state = loadState();
  Object.assign(state, partial);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  return state;
}

function prefillForm(form) {
  const state = loadState();
  for (const el of form.elements) {
    if (!el.name || !(el.name in state)) continue;
    if (el.type === "checkbox") {
      el.checked = Boolean(state[el.name]);
    } else {
      el.value = state[el.name];
    }
  }
}

function collectForm(form) {
  const data = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    data[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  return data;
}

function goToNext(form, nextPage) {
  saveState(collectForm(form));
  window.location.href = nextPage;
}

function renderReview(targetElId, fieldLabels) {
  const state = loadState();
  const el = document.getElementById(targetElId);
  const rows = fieldLabels
    .map(([key, label]) => {
      const value = state[key];
      const display =
        typeof value === "boolean" ? (value ? "Yes" : "No") : value || "(not provided)";
      return `<tr><td>${label}</td><td>${display}</td></tr>`;
    })
    .join("");
  el.innerHTML = `<table class="review-table">${rows}</table>`;
}

function submitApplication() {
  const state = loadState();
  const refNumber =
    "CTEVT-MOCK-" + Math.random().toString(36).slice(2, 8).toUpperCase();
  state.reference_number = refNumber;
  state.submitted_at = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  window.location.href = "confirmation.html";
}
