"use strict";

const $ = (id) => document.getElementById(id);
const synth = window.speechSynthesis;

let voices = [];
let currentAgentId = null;
let engine = null;
let call = null;
let authMode = "login";

const DEFAULT_PROMPT =
  "You are a warm, concise voice assistant. Keep replies to 1-3 spoken " +
  "sentences. Ask one question at a time. No lists, markdown, or emojis.";

// ----------------------------- request helpers (handle 401) -----------------------------
async function rawReq(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 401) { showAuth(); throw new Error("Not authenticated"); }
  return r;
}
const jreq = (url, opts) => rawReq(url, opts).then((r) => r.json());

const api = {
  list: () => jreq("/api/agents"),
  get: (id) => jreq("/api/agents/" + id),
  create: (d) => jreq("/api/agents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) }),
  update: (id, d) => jreq("/api/agents/" + id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) }),
  remove: (id) => rawReq("/api/agents/" + id, { method: "DELETE" }),
  docs: (id) => jreq(`/api/agents/${id}/documents`),
  delDoc: (docId) => rawReq(`/api/documents/${docId}`, { method: "DELETE" }),
  calls: (id) => jreq(`/api/agents/${id}/calls`),
  callDetail: (callId) => jreq(`/api/calls/${callId}`),
  saveCall: (d) => rawReq("/api/calls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) }),
  bookings: (id) => jreq(`/api/agents/${id}/bookings`),
};

// ----------------------------- auth -----------------------------
function showAuth() {
  $("authScreen").classList.remove("hidden");
  $("appRoot").classList.add("hidden");
  $("userBox").classList.add("hidden");
}
function showApp(email) {
  $("authScreen").classList.add("hidden");
  $("appRoot").classList.remove("hidden");
  $("userBox").classList.remove("hidden");
  $("userEmail").textContent = email;
  if (!(window.SpeechRecognition || window.webkitSpeechRecognition)) $("unsupported").classList.remove("hidden");
}
function setAuthMode(m) {
  authMode = m;
  $("authTitle").textContent = m === "login" ? "Log in" : "Create account";
  $("authSubmit").textContent = m === "login" ? "Log in" : "Sign up";
  $("authSwitchText").textContent = m === "login" ? "New here?" : "Already have an account?";
  $("authSwitch").textContent = m === "login" ? "Create an account" : "Log in";
  $("authErr").textContent = "";
}
async function submitAuth() {
  const email = $("authEmail").value.trim();
  const password = $("authPassword").value;
  const path = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { $("authErr").textContent = data.detail || "Something went wrong."; return; }
  $("authPassword").value = "";
  showApp(data.email);
  showDashboard();
}

// ----------------------------- voices -----------------------------
function loadVoices() {
  voices = synth.getVoices();
  const sel = $("voice");
  const prev = sel.value;
  sel.innerHTML = "";
  voices.forEach((v) => {
    const o = document.createElement("option");
    o.value = v.name;
    o.textContent = `${v.name} (${v.lang})`;
    sel.appendChild(o);
  });
  if (prev) sel.value = prev;
}
loadVoices();
if (typeof synth.onvoiceschanged !== "undefined") synth.onvoiceschanged = loadVoices;

function setVoice(name) {
  const sel = $("voice");
  if (name && [...sel.options].some((o) => o.value === name)) sel.value = name;
  else {
    const en = [...sel.options].find((o) => /\(en/.test(o.textContent));
    if (en) sel.value = en.value;
  }
}

// ----------------------------- shared UI -----------------------------
function setStatus(text, cls) { const el = $("status"); el.textContent = text; el.className = "status " + (cls || ""); }
function addTurn(role, text) {
  const log = $("transcript");
  const div = document.createElement("div");
  div.className = "turn " + role;
  const who = document.createElement("span"); who.className = "who";
  who.textContent = role === "user" ? "Caller" : $("name").value || "Agent";
  const msg = document.createElement("span"); msg.className = "msg"; msg.textContent = text;
  div.append(who, msg); log.appendChild(div); log.scrollTop = log.scrollHeight;
}
function flash(msg) { const h = $("saveHint"); h.textContent = msg; h.classList.add("show"); setTimeout(() => h.classList.remove("show"), 1800); }
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); setTimeout(() => t.classList.add("hidden"), 2800); }
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])));
const fmt = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(); };

// ----------------------------- tabs -----------------------------
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  $("tab-" + name).classList.remove("hidden");
  if (name === "knowledge") loadDocuments();
  if (name === "history") loadCalls();
  if (name === "bookings") loadBookings();
  if (name === "embed") {
    const textEl = $("embedScriptText");
    if (currentAgentId) {
      const url = window.location.origin + "/widget.js";
      textEl.value = `<script src="${url}" data-agent-id="${currentAgentId}"></script>`;
    } else {
      textEl.value = "Please save the agent first to get your embed script.";
    }
  }
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => switchTab(t.dataset.tab)));

$("copyEmbedBtn").onclick = () => {
  const textEl = $("embedScriptText");
  textEl.select();
  document.execCommand("copy");
  toast("Copied to clipboard!");
};

// ----------------------------- dashboard -----------------------------
async function showDashboard() {
  if (engine && engine.active) endCall();
  $("agentView").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  renderAgentList(await api.list());
}
function renderAgentList(agents) {
  const list = $("agentList");
  list.innerHTML = "";
  if (!agents.length) { list.innerHTML = '<p class="empty">No agents yet. Create one to get started.</p>'; return; }
  agents.forEach((a) => {
    const card = document.createElement("div");
    card.className = "agent-card";
    const tags = [a.use_knowledge ? "📚 KB" : "", a.tools_enabled ? "📋 Bookings" : "", a.barge_in ? "🎤 Barge-in" : ""].filter(Boolean).join(" · ");
    card.innerHTML =
      `<div class="agent-card-body"><h3>${esc(a.name)}</h3>` +
      `<p>${esc(a.system_prompt.slice(0, 100))}${a.system_prompt.length > 100 ? "…" : ""}</p>` +
      `<p class="tags">${tags}</p></div>`;
    const actions = document.createElement("div");
    actions.className = "agent-card-actions";
    const open = document.createElement("button"); open.className = "primary"; open.textContent = "Open"; open.onclick = () => openAgent(a.id);
    const del = document.createElement("button"); del.className = "danger"; del.textContent = "Delete";
    del.onclick = async () => { if (confirm(`Delete "${a.name}"?`)) { await api.remove(a.id); showDashboard(); } };
    actions.append(open, del);
    card.appendChild(actions);
    list.appendChild(card);
  });
}

// ----------------------------- editor -----------------------------
function fillEditor(a) {
  currentAgentId = a ? a.id : null;
  $("editorTitle").textContent = a ? "Edit agent" : "New agent";
  $("name").value = a ? a.name : "New Agent";
  $("system").value = a ? a.system_prompt : DEFAULT_PROMPT;
  $("greeting").value = a ? a.greeting : "Hi! How can I help you today?";
  $("rate").value = a ? a.rate : 1.0;
  $("lang").value = a ? a.lang : "en-US";
  setVoice(a ? a.voice_name : "");
  $("use_knowledge").checked = a ? !!a.use_knowledge : false;
  $("tools_enabled").checked = a ? !!a.tools_enabled : false;
  $("barge_in").checked = a ? !!a.barge_in : true;
  $("booking_webhook").value = a ? (a.booking_webhook || "") : "";
  $("deleteBtn").style.display = currentAgentId ? "" : "none";
  $("transcript").innerHTML = "";
  setStatus("Ready", "");
  resetCallButton();
}
function showAgentView() { $("dashboard").classList.add("hidden"); $("agentView").classList.remove("hidden"); switchTab("setup"); }
async function openAgent(id) { fillEditor(await api.get(id)); showAgentView(); }
function newAgent() { fillEditor(null); showAgentView(); }

function collectConfig() {
  return {
    name: $("name").value.trim() || "Untitled Agent",
    system_prompt: $("system").value,
    greeting: $("greeting").value,
    voice_name: $("voice").value || "",
    rate: parseFloat($("rate").value) || 1.0,
    lang: $("lang").value,
    use_knowledge: $("use_knowledge").checked,
    tools_enabled: $("tools_enabled").checked,
    barge_in: $("barge_in").checked,
    booking_webhook: $("booking_webhook").value.trim(),
  };
}
async function saveAgent() {
  const data = collectConfig();
  const saved = currentAgentId ? await api.update(currentAgentId, data) : await api.create(data);
  currentAgentId = saved.id;
  $("editorTitle").textContent = "Edit agent";
  $("deleteBtn").style.display = "";
  flash("✓ Saved");
}
async function deleteCurrent() {
  if (!currentAgentId) return;
  if (!confirm(`Delete "${$("name").value}"?`)) return;
  await api.remove(currentAgentId);
  showDashboard();
}
async function testWebhook() {
  if (!currentAgentId) { flash("Save the agent first."); return; }
  if (!$("booking_webhook").value.trim()) { toast("Enter a webhook URL first."); return; }
  await saveAgent();
  const r = await rawReq(`/api/agents/${currentAgentId}/test-webhook`, { method: "POST" });
  const d = await r.json().catch(() => ({}));
  toast(r.ok && d.ok ? "Webhook OK (HTTP " + d.status + ")" : (d.error || d.detail || "Webhook failed"));
}

// ----------------------------- knowledge -----------------------------
function requireSaved(hintId, what) {
  if (currentAgentId) { $(hintId).textContent = ""; return true; }
  $(hintId).textContent = `Save this agent first to use ${what}.`;
  return false;
}
async function loadDocuments() {
  const list = $("docList");
  if (!requireSaved("kbHint", "the knowledge base")) { list.innerHTML = ""; return; }
  const docs = await api.docs(currentAgentId);
  list.innerHTML = docs.length ? "" : '<p class="empty">No documents yet.</p>';
  docs.forEach((d) => {
    const row = document.createElement("div"); row.className = "list-row";
    row.innerHTML = `<span>📄 ${esc(d.filename)} <small>· ${d.chunks} chunk(s)</small></span>`;
    const del = document.createElement("button"); del.className = "danger small"; del.textContent = "Delete";
    del.onclick = async () => { await api.delDoc(d.id); loadDocuments(); };
    row.appendChild(del); list.appendChild(row);
  });
}
async function uploadFile() {
  if (!requireSaved("kbHint", "the knowledge base")) return;
  const f = $("docFile").files[0];
  if (!f) { toast("Choose a file first."); return; }
  const fd = new FormData(); fd.append("file", f);
  const r = await rawReq(`/api/agents/${currentAgentId}/documents`, { method: "POST", body: fd });
  if (!r.ok) { toast("Upload failed: " + ((await r.json().catch(() => ({}))).detail || r.status)); return; }
  $("docFile").value = ""; toast("Document added"); loadDocuments();
}
async function uploadText() {
  if (!requireSaved("kbHint", "the knowledge base")) return;
  const t = $("docText").value.trim();
  if (!t) { toast("Paste some text first."); return; }
  const fd = new FormData(); fd.append("text", t); fd.append("filename", "pasted.txt");
  const r = await rawReq(`/api/agents/${currentAgentId}/documents`, { method: "POST", body: fd });
  if (!r.ok) { toast("Failed to add text."); return; }
  $("docText").value = ""; toast("Text added"); loadDocuments();
}

// ----------------------------- history -----------------------------
async function loadCalls() {
  const list = $("callList"); $("callDetail").innerHTML = "";
  if (!requireSaved("histHint", "call history")) { list.innerHTML = ""; return; }
  const calls = await api.calls(currentAgentId);
  list.innerHTML = calls.length ? "" : '<p class="empty">No calls recorded yet.</p>';
  calls.forEach((c) => {
    const row = document.createElement("div"); row.className = "list-row";
    row.innerHTML = `<span>📞 ${fmt(c.started_at) || "Call #" + c.id} <small>· ${c.num_turns} turns</small></span>`;
    const view = document.createElement("button"); view.className = "small"; view.textContent = "View"; view.onclick = () => viewCall(c.id);
    row.appendChild(view); list.appendChild(row);
  });
}
async function viewCall(id) {
  const c = await api.callDetail(id);
  const box = $("callDetail"); box.innerHTML = "";
  (c.transcript || []).forEach((t) => {
    const div = document.createElement("div"); div.className = "turn " + (t.role === "user" ? "user" : "agent");
    div.innerHTML = `<span class="who">${t.role === "user" ? "Caller" : "Agent"}</span>`;
    const m = document.createElement("span"); m.className = "msg"; m.textContent = t.text || t.content;
    div.appendChild(m); box.appendChild(div);
  });
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ----------------------------- bookings -----------------------------
async function loadBookings() {
  const list = $("bookingList");
  if (!requireSaved("bookHint", "bookings")) { list.innerHTML = ""; return; }
  const rows = await api.bookings(currentAgentId);
  list.innerHTML = rows.length ? "" : '<p class="empty">No bookings captured yet.</p>';
  rows.forEach((b) => {
    const div = document.createElement("div"); div.className = "booking";
    div.innerHTML =
      `<strong>${esc(b.name) || "(no name)"}</strong>` +
      `<div class="booking-meta">${b.phone ? "📱 " + esc(b.phone) + " " : ""}${b.datetime ? "🗓️ " + esc(b.datetime) : ""}</div>` +
      (b.reason ? `<div class="booking-reason">${esc(b.reason)}</div>` : "") +
      `<small>${fmt(b.created_at)}</small>`;
    list.appendChild(div);
  });
}

// ----------------------------- call control -----------------------------
function resetCallButton() { const b = $("callBtn"); b.textContent = "📞 Start call"; b.classList.remove("active"); }
function startCall() {
  if (!engine) {
    engine = new CallEngine({
      onStatus: setStatus, onTurn: addTurn,
      onEvent: (e) => { if (e.type === "booking_saved") toast("📋 Booking captured: " + (e.booking.name || "details saved")); },
    });
  }
  if (!engine.supported()) { setStatus("Calls need Chrome or Edge", "error"); return; }
  $("transcript").innerHTML = "";
  $("callBtn").textContent = "📵 Hang up"; $("callBtn").classList.add("active");
  const c = collectConfig();
  call = { uid: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()), startedAt: new Date().toISOString() };
  engine.start({
    system: c.system_prompt, greeting: c.greeting, voiceName: c.voice_name, rate: c.rate,
    lang: c.lang, bargeIn: c.barge_in, agentId: currentAgentId, callUid: call.uid,
  });
}
async function endCall() {
  if (!engine) return;
  const transcript = engine.transcript.slice();
  engine.hangUp(); resetCallButton();
  if (currentAgentId && transcript.length && call) {
    try {
      await api.saveCall({ agent_id: currentAgentId, call_uid: call.uid, started_at: call.startedAt, ended_at: new Date().toISOString(), transcript });
    } catch (e) {}
  }
  call = null;
}

// ----------------------------- wiring -----------------------------
$("authSubmit").onclick = submitAuth;
$("authPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") submitAuth(); });
$("authSwitch").onclick = (e) => { e.preventDefault(); setAuthMode(authMode === "login" ? "register" : "login"); };
$("logoutBtn").onclick = async () => { await fetch("/api/auth/logout", { method: "POST" }); showAuth(); };
$("newAgentBtn").onclick = newAgent;
$("backBtn").onclick = showDashboard;
$("saveBtn").onclick = saveAgent;
$("deleteBtn").onclick = deleteCurrent;
$("testWebhookBtn").onclick = testWebhook;
$("uploadFileBtn").onclick = uploadFile;
$("uploadTextBtn").onclick = uploadText;
$("callBtn").onclick = () => { if (engine && engine.active) endCall(); else startCall(); };

// ----------------------------- init -----------------------------
async function init() {
  setAuthMode("login");
  try {
    const r = await fetch("/api/me");
    if (r.ok) { const d = await r.json(); showApp(d.email); showDashboard(); }
    else showAuth();
  } catch (e) { showAuth(); }
}
init();
