// Sahayogi frontend — talks only to the same-origin FastAPI backend
// (api/main.py). No framework, no build step: deliberately simple.

const SESSION_KEY = "sahayogi_session_id";

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2, 10) + "-" + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

const sessionId = getSessionId();

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const proposalCard = document.getElementById("proposal-card");
const proposalBody = document.getElementById("proposal-body");
const proposalActions = document.getElementById("proposal-actions");
const decisionResult = document.getElementById("decision-result");
const decisionNote = document.getElementById("decision-note");
const approveBtn = document.getElementById("approve-btn");
const rejectBtn = document.getElementById("reject-btn");
const activityLog = document.getElementById("activity-log");

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendChat(message) {
  addMessage(message, "user");
  inputEl.value = "";
  formEl.querySelector("button").disabled = true;
  const thinking = addMessage("Sahayogi is thinking...", "thinking");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    const data = await res.json();
    thinking.remove();
    addMessage(data.reply, "agent");
  } catch (err) {
    thinking.remove();
    addMessage("Something went wrong reaching Sahayogi: " + err, "agent");
  } finally {
    formEl.querySelector("button").disabled = false;
    refreshSession();
    refreshActivity();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = inputEl.value.trim();
  if (message) sendChat(message);
});

function fieldRow(label, value) {
  return `<div><strong>${label}:</strong> ${value}</div>`;
}

function renderProposalBody(proposal) {
  const fieldRows = (proposal.fields || [])
    .map((f) => {
      const value = f.value === null || f.value === undefined || f.value === "" ? "<em>(empty)</em>" : escapeHtml(String(f.value));
      const reqTag = f.required ? ' <span style="color:#b45309;">*</span>' : "";
      return `<tr><td>${escapeHtml(f.label)}${reqTag}</td><td>${value}</td></tr>`;
    })
    .join("");

  return (
    fieldRow("URL", `<a href="${escapeHtml(proposal.url)}" target="_blank" rel="noopener">${escapeHtml(proposal.url)}</a>`) +
    `<div style="margin-top:10px;">${escapeHtml(proposal.summary_for_human)}</div>` +
    (fieldRows ? `<table class="review-table" style="margin-top:10px;">${fieldRows}</table>` : "")
  );
}

async function refreshSession() {
  const res = await fetch(`/api/session/${encodeURIComponent(sessionId)}`);
  const session = await res.json();

  if (session.status === "pending_approval") {
    const p = session.proposal;
    proposalCard.hidden = false;
    proposalActions.hidden = false;
    decisionResult.hidden = true;
    approveBtn.disabled = false;
    rejectBtn.disabled = false;
    proposalBody.innerHTML = renderProposalBody(p);
  } else if (["submitted", "rejected", "submission_failed"].includes(session.status)) {
    proposalCard.hidden = false;
    proposalActions.hidden = true; // decision is final -- no point showing a disabled note+buttons
    proposalBody.innerHTML = session.proposal ? renderProposalBody(session.proposal) : "—";
    decisionResult.hidden = false;
    if (session.status === "submitted") {
      decisionResult.className = "decision-result success";
      decisionResult.textContent = "✅ Submitted. This session is closed.";
    } else if (session.status === "rejected") {
      decisionResult.className = "decision-result pending";
      decisionResult.textContent = "❌ Rejected. No submission was made.";
    } else {
      decisionResult.className = "decision-result error";
      decisionResult.textContent = "⚠️ Submission failed. See agent activity for details.";
    }
  } else {
    proposalCard.hidden = true;
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function decide(decision) {
  approveBtn.disabled = true;
  rejectBtn.disabled = true;
  decisionResult.hidden = false;
  decisionResult.className = "decision-result pending";
  decisionResult.textContent =
    decision === "approved"
      ? "⏳ Approved — Sahayogi is now filling out the real application via a live browser session. This can take 1–2 minutes..."
      : "⏳ Recording rejection...";

  try {
    const res = await fetch(`/api/session/${encodeURIComponent(sessionId)}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note: decisionNote.value }),
    });
    if (!res.ok) {
      const err = await res.json();
      decisionResult.className = "decision-result error";
      decisionResult.textContent = "⚠️ " + (err.detail || "Request failed");
      return;
    }
    const data = await res.json();
    if (data.status === "submitted") {
      decisionResult.className = "decision-result success";
      decisionResult.textContent = "✅ " + data.message;
    } else if (data.status === "rejected") {
      decisionResult.className = "decision-result pending";
      decisionResult.textContent = "❌ " + data.message;
    } else {
      decisionResult.className = "decision-result error";
      decisionResult.textContent = "⚠️ " + data.message;
    }
  } catch (err) {
    decisionResult.className = "decision-result error";
    decisionResult.textContent = "⚠️ " + err;
  } finally {
    refreshActivity();
    refreshSession(); // re-render from authoritative server state (hides actions once resolved)
  }
}

approveBtn.addEventListener("click", () => decide("approved"));
rejectBtn.addEventListener("click", () => decide("rejected"));

const ACTION_LABELS = {
  fields_matched: "🔎 Read the form and matched your details",
  form_fill_proposed: "📋 Proposed a submission",
  submission_approved: "✅ Human approved",
  submission_rejected: "❌ Human rejected",
  submission_completed: "🎉 Submission completed",
  submission_failed: "⚠️ Submission failed",
};

async function refreshActivity() {
  const res = await fetch(`/api/session/${encodeURIComponent(sessionId)}/audit`);
  const entries = await res.json();
  activityLog.innerHTML = "";
  for (const e of entries) {
    const li = document.createElement("li");
    const label = ACTION_LABELS[e.action] || e.action;
    const time = new Date(e.timestamp * 1000).toLocaleTimeString();
    li.innerHTML = `<span class="actor">${e.actor === "agent" ? "🤖" : "🧑"}</span> <span class="action">${label}</span><span class="time">${time}</span>`;
    activityLog.appendChild(li);
  }
}

document.getElementById("new-session-btn").addEventListener("click", () => {
  // A session_id can only ever be proposed on once (propose_application
  // refuses to overwrite a decided session -- see agent/tools/proposal.py).
  // The only way to start a genuinely new conversation is a fresh id.
  if (!confirm("Start a new conversation? This clears the current chat and proposal from view (nothing is deleted server-side).")) {
    return;
  }
  localStorage.removeItem(SESSION_KEY);
  window.location.reload();
});

// Initial load: greet + sync any existing session state (e.g. after a page refresh).
addMessage(
  "Namaste! Give me a link to a form you need filled out (an RSVP, a signup, an application) and tell me about yourself, and I'll read the actual form, draft what I'd submit, and wait for your approval before doing anything.",
  "agent"
);
refreshSession();
refreshActivity();
