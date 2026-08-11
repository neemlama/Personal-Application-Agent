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
    proposalBody.innerHTML =
      fieldRow("Program", p.program_id) + `<div style="margin-top:8px;">${escapeHtml(p.summary_for_human)}</div>`;
  } else if (["submitted", "rejected", "submission_failed"].includes(session.status)) {
    proposalCard.hidden = false;
    proposalActions.hidden = true; // decision is final -- no point showing a disabled note+buttons
    proposalBody.innerHTML = fieldRow("Program", session.proposal ? session.proposal.program_id : "—");
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
  eligibility_matched: "🔎 Matched eligible programs",
  application_proposed: "📋 Proposed an application",
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

// Initial load: greet + sync any existing session state (e.g. after a page refresh).
addMessage(
  "Namaste! Tell me about your situation — age, education level, family details, district — and I'll look for scholarships or subsidies you may qualify for.",
  "agent"
);
refreshSession();
refreshActivity();
