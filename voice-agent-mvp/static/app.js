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
const jreq = (url, method, body) => {
  const opts = method
    ? { method, headers: body !== undefined ? { "Content-Type": "application/json" } : {}, body: body !== undefined ? JSON.stringify(body) : undefined }
    : undefined;
  return rawReq(url, opts).then(async (r) => {
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.status); }
    return r.json();
  });
};

const api = {
  list: () => jreq("/api/agents"),
  get: (id) => jreq("/api/agents/" + id),
  create: (d) => jreq("/api/agents", "POST", d),
  update: (id, d) => jreq("/api/agents/" + id, "PUT", d),
  remove: (id) => rawReq("/api/agents/" + id, { method: "DELETE" }),
  docs: (id) => jreq(`/api/agents/${id}/documents`),
  delDoc: (docId) => rawReq(`/api/documents/${docId}`, { method: "DELETE" }),
  calls: (id) => jreq(`/api/agents/${id}/calls`),
  callDetail: (callId) => jreq(`/api/calls/${callId}`),
  saveCall: (d) => rawReq("/api/calls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) }),
  bookings: (id) => jreq(`/api/agents/${id}/bookings`),
  myRole: (id) => jreq(`/api/agents/${id}/my-role`),
  members: (id) => jreq(`/api/agents/${id}/members`),
  addMember: (id, d) => jreq(`/api/agents/${id}/members`, "POST", d),
  updateMemberRole: (id, uid, d) => jreq(`/api/agents/${id}/members/${uid}`, "PUT", d),
  removeMember: (id, uid) => rawReq(`/api/agents/${id}/members/${uid}`, { method: "DELETE" }),
  googleSettings: (id) => jreq(`/api/agents/${id}/google/settings`),
  saveGoogleSettings: (id, d) => jreq(`/api/agents/${id}/google/settings`, "POST", d),
  testGCal: (id, d) => jreq(`/api/agents/${id}/google/test-calendar`, "POST", d || {}),
  testGSheets: (id, d) => jreq(`/api/agents/${id}/google/test-sheets`, "POST", d || {}),
  syncGoogleDoc: (id, d) => jreq(`/api/agents/${id}/google/sync-doc`, "POST", d),
  syncAllSheets: (id) => jreq(`/api/agents/${id}/google/sync-all-sheets`, "POST"),
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
  showApp(data.email || email);
  showDashboard();
}

// ----------------------------- voices -----------------------------
async function loadVoices() {
  const sel = $("voice");
  const prev = sel.value;
  sel.innerHTML = "";

  // 1. Studio Neural Voices (Human Quality)
  try {
    const res = await fetch("/api/voices");
    if (res.ok) {
      const neuralVoices = await res.json();
      const group = document.createElement("optgroup");
      group.label = "✨ Studio Neural Voices (Human Quality)";
      neuralVoices.forEach((v) => {
        const o = document.createElement("option");
        o.value = v.id;
        o.textContent = v.name;
        group.appendChild(o);
      });
      sel.appendChild(group);
    }
  } catch (e) {}

  // 2. Browser local voices (fallback)
  voices = synth.getVoices() || [];
  if (voices.length > 0) {
    const group2 = document.createElement("optgroup");
    group2.label = "💻 Browser System Voices";
    voices.forEach((v) => {
      const o = document.createElement("option");
      o.value = v.name;
      o.textContent = `${v.name} (${v.lang})`;
      group2.appendChild(o);
    });
    sel.appendChild(group2);
  }

  if (prev && [...sel.options].some((o) => o.value === prev)) {
    sel.value = prev;
  } else if (sel.options.length > 0) {
    const def = [...sel.options].find((o) => o.value === "en-IN-NeerjaNeural");
    sel.value = def ? def.value : sel.options[0].value;
  }
}
loadVoices();
if (typeof synth.onvoiceschanged !== "undefined") synth.onvoiceschanged = loadVoices;

function setVoice(name) {
  const sel = $("voice");
  if (name && [...sel.options].some((o) => o.value === name)) {
    sel.value = name;
  } else if (sel.options.length > 0) {
    const def = [...sel.options].find((o) => o.value === "en-IN-NeerjaNeural");
    sel.value = def ? def.value : sel.options[0].value;
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
function updateLastTurn(text) {
  const log = $("transcript");
  const lastMsg = log.querySelector(".turn.agent:last-child .msg");
  if (lastMsg) {
    lastMsg.textContent = text;
    log.scrollTop = log.scrollHeight;
  }
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
  if (name === "guardrails") loadGuardrailsAndMembers();
  if (name === "google") loadGoogleSettings();
  if (name === "docker") fetchHardwareRecommendations();
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
  // Bug 10 Fix: replace deprecated execCommand('copy') with modern Clipboard API
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(textEl.value)
      .then(() => toast("Copied to clipboard!"))
      .catch(() => {
        // Fallback for cases where clipboard permission is denied
        textEl.select();
        document.execCommand("copy");
        toast("Copied to clipboard!");
      });
  } else {
    textEl.select();
    document.execCommand("copy");
    toast("Copied to clipboard!");
  }
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
    const roleTag = a.user_role && a.user_role !== "owner" ? `<span class="role-badge ${a.user_role}" style="font-size:10px; padding:1px 6px;">${a.user_role}</span>` : "";
    const tags = [roleTag, a.use_knowledge ? "📚 KB" : "", a.tools_enabled ? "📋 Bookings" : "", a.barge_in ? "🎤 Barge-in" : ""].filter(Boolean).join(" · ");
    card.innerHTML =
      `<div class="agent-card-body"><h3>${esc(a.name)}</h3>` +
      `<p>${esc(a.system_prompt.slice(0, 100))}${a.system_prompt.length > 100 ? "…" : ""}</p>` +
      `<p class="tags">${tags}</p></div>`;
    const actions = document.createElement("div");
    actions.className = "agent-card-actions";
    const open = document.createElement("button"); open.className = "primary"; open.textContent = "Open"; open.onclick = () => openAgent(a.id);
    const del = document.createElement("button"); del.className = "danger"; del.textContent = "Delete";
    del.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete "${a.name}"?`)) return;
      const res = await api.remove(a.id);
      if (res.ok) {
        toast(`Deleted "${a.name}"`);
        showDashboard();
      } else {
        const d = await res.json().catch(() => ({}));
        toast("Delete failed: " + (d.detail || res.statusText));
      }
    };
    actions.append(open, del);
    card.appendChild(actions);
    list.appendChild(card);
  });
}

// ----------------------------- editor -----------------------------
function fillEditor(a) {
  currentAgentId = a ? a.id : null;
  const role = (a && a.user_role) || "owner";
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

  // Role badges & permissions
  const badge = $("myRoleBadge");
  if (badge) {
    badge.textContent = `Role: ${role.toUpperCase()}`;
    badge.className = `role-badge ${role}`;
  }
  const canManage = !a || (a && a.permissions && a.permissions.can_manage_members) !== false;
  if ($("addMemberSection")) $("addMemberSection").style.display = canManage ? "flex" : "none";
  if ($("deleteBtn")) $("deleteBtn").style.display = (currentAgentId && (role === "owner" || !a)) ? "" : "none";

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
  currentAgentId = (saved && saved.id) || currentAgentId;
  $("editorTitle").textContent = "Edit agent";
  $("deleteBtn").style.display = "";
  flash("✓ Saved");
}
async function deleteCurrent() {
  if (!currentAgentId) return;
  if (!confirm(`Delete "${$("name").value}"?`)) return;
  const res = await api.remove(currentAgentId);
  if (res.ok) {
    toast("Agent deleted");
    currentAgentId = null;
    showDashboard();
  } else {
    const d = await res.json().catch(() => ({}));
    toast("Delete failed: " + (d.detail || res.statusText));
  }
}
async function testWebhook() {
  if (!currentAgentId) { flash("Save the agent first."); return; }
  const url = $("booking_webhook").value.trim();
  if (!url) { toast("Enter a webhook URL first."); return; }
  await saveAgent();
  toast("🚀 Sending test webhook payload...");
    try {
      const r = await rawReq(`/api/agents/${currentAgentId}/test-webhook`, { method: "POST" });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok) {
        // Bug 1 Fix: server now returns duration_ms and response_preview
        toast(`✅ Webhook Delivered (HTTP ${d.status} in ${d.duration_ms ?? "?"}ms)`);
        if (d.response_preview) {
          console.log("Webhook destination response:", d.response_preview);
        }
      } else {
        toast(`❌ Webhook Failed: ${d.error || d.detail || ('HTTP ' + (d.status || r.status))} (${d.duration_ms ?? 0}ms)`);
      }
    } catch (err) {
      toast(`❌ Webhook Error: ${err.message}`);
    }
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
  const btn = $("uploadFileBtn");
  btn.disabled = true;
  btn.textContent = "Processing & chunking...";
  try {
    const fd = new FormData(); fd.append("file", f);
    const r = await rawReq(`/api/agents/${currentAgentId}/documents`, { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Upload failed: " + (d.detail || r.status)); return; }
    $("docFile").value = "";
    if ($("use_knowledge")) $("use_knowledge").checked = true;
    toast(`Document added (${d.chunks || 1} chunks)`);
    loadDocuments();
  } catch (e) {
    toast("Upload error: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload file";
  }
}
async function uploadText() {
  if (!requireSaved("kbHint", "the knowledge base")) return;
  const t = $("docText").value.trim();
  if (!t) { toast("Paste some text first."); return; }
  const btn = $("uploadTextBtn");
  btn.disabled = true;
  btn.textContent = "Saving text...";
  try {
    const fd = new FormData(); fd.append("text", t); fd.append("filename", "pasted.txt");
    const r = await rawReq(`/api/agents/${currentAgentId}/documents`, { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Failed to add text: " + (d.detail || r.status)); return; }
    $("docText").value = "";
    if ($("use_knowledge")) $("use_knowledge").checked = true;
    toast(`Text added (${d.chunks || 1} chunks)`);
    loadDocuments();
  } catch (e) {
    toast("Error: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Add pasted text";
  }
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
function renderBookingsList(rows) {
  const list = $("bookingList");
  list.innerHTML = rows.length ? "" : '<p class="empty">No bookings captured yet.</p>';
  rows.forEach((b) => {
    const div = document.createElement("div"); div.className = "booking"; div.dataset.id = b.id;
    const isConflict = b.schedule_status === "RESCHEDULE_PROPOSED";
    if (isConflict) div.classList.add("booking-conflict");

    div.innerHTML =
      `<div class="booking-header">` +
        `<div style="display:flex; align-items:center; gap:6px;">` +
          `<strong class="booking-name">${esc(b.name) || "(no name)"}</strong>` +
          (b._is_abstracted ? `<span class="role-badge receptionist" style="font-size:10px; padding:1px 6px;">🔒 Abstracted</span>` : "") +
        `</div>` +
        `<div class="booking-actions">` +
          (b.gcal_url ? `<a class="btn-gcal" href="${b.gcal_url}" target="_blank" rel="noopener" title="Add to Google Calendar">📅 Google Cal</a>` : "") +
          (b.ics_url ? `<a class="btn-ics" href="${b.ics_url}" download="booking-${b.id}.ics" title="Download .ics Calendar file">📥 .ics</a>` : "") +
          `<button class="btn-edit-booking" onclick="startEditBooking(${b.id})" title="Edit">✏️</button>` +
          `<button class="btn-del-booking" onclick="deleteBookingItem(${b.id},${currentAgentId})" title="Delete">🗑️</button>` +
        `</div>` +
      `</div>` +
      `<div class="booking-view">` +
        `<div class="booking-meta">${b.phone ? "📱 " + esc(b.phone) + " " : ""}${b.datetime ? "🗓️ " + esc(b.datetime) : ""}</div>` +
        (b.reason ? `<div class="booking-reason">${esc(b.reason)}</div>` : "") +
        (isConflict ? `<div class="quantum-reschedule-alert">⚠️ <strong>PennyLane VQC Conflict Detected:</strong> Proposing alternative: <em>${esc(b.proposed_alternative || "Next Slot")}</em></div>` : "") +
        `<small>${fmt(b.created_at)}</small>` +
      `</div>` +
      `<form class="booking-edit hidden" onsubmit="submitEditBooking(event,${b.id},${currentAgentId})">` +
        `<input name="name" placeholder="Name" value="${esc(b.name || "")}" />` +
        `<input name="phone" placeholder="Phone" value="${esc(b.phone || "")}" />` +
        `<input name="datetime" placeholder="Date/Time" value="${esc(b.datetime || "")}" />` +
        `<input name="reason" placeholder="Reason" value="${esc(b.reason || "")}" />` +
        `<div class="booking-edit-btns"><button type="submit">💾 Save</button><button type="button" onclick="cancelEditBooking(${b.id})">✖ Cancel</button></div>` +
      `</form>`;
    list.appendChild(div);
  });
}

function startEditBooking(id) {
  const div = document.querySelector(`.booking[data-id="${id}"]`);
  if (!div) return;
  div.querySelector(".booking-view").classList.add("hidden");
  div.querySelector(".booking-edit").classList.remove("hidden");
}

function cancelEditBooking(id) {
  const div = document.querySelector(`.booking[data-id="${id}"]`);
  if (!div) return;
  div.querySelector(".booking-edit").classList.add("hidden");
  div.querySelector(".booking-view").classList.remove("hidden");
}

async function submitEditBooking(e, bookingId, agentId) {
  e.preventDefault();
  const form = e.target;
  const payload = {
    name: form.name.value.trim(),
    phone: form.phone.value.trim(),
    datetime: form.datetime.value.trim(),
    reason: form.reason.value.trim(),
  };
  try {
    const updated = await jreq(`/api/agents/${agentId}/bookings/${bookingId}`, "PUT", payload);
    toast("✅ Booking updated");
    loadBookings();
  } catch (err) {
    toast("❌ Update failed: " + err.message);
  }
}

async function deleteBookingItem(bookingId, agentId) {
  if (!confirm("Delete this booking?")) return;
  try {
    await jreq(`/api/agents/${agentId}/bookings/${bookingId}`, "DELETE");
    toast("🗑️ Booking deleted");
    loadBookings();
  } catch (err) {
    toast("❌ Delete failed: " + err.message);
  }
}

async function loadBookings() {
  if (!requireSaved("bookHint", "bookings")) { $("bookingList").innerHTML = ""; return; }
  const rows = await api.bookings(currentAgentId);
  renderBookingsList(rows);
}

// ----------------------------- call control -----------------------------
function resetCallButton() { const b = $("callBtn"); b.textContent = "📞 Start call"; b.classList.remove("active"); }
async function startCall() {
  // Bug 7 Fix: pre-check mic permission before starting so user gets a clear error
  // instead of the call silently falling back to LocalWhisper with no explanation.
  if (navigator.permissions) {
    try {
      const perm = await navigator.permissions.query({ name: "microphone" });
      if (perm.state === "denied") {
        setStatus("Microphone access is blocked. Allow mic in browser settings.", "error");
        return;
      }
    } catch (e) { /* permissions API not available in this browser — proceed */ }
  }

  if (!engine) {
    engine = new CallEngine({
      onStatus: setStatus, onTurn: addTurn, onTurnUpdate: updateLastTurn,
      onEvent: (e) => {
        if (e.type === "booking_saved") {
          toast("📋 Booking captured: " + (e.booking.name || "details saved"));
          loadBookings();
        } else if (e.type === "booking_updated") {
          toast("✏️ Booking updated: " + (e.booking.name || "details updated"));
          loadBookings();
        }
      },
    });
  }
  if (!engine.supported()) { setStatus("Calls need mic access (Chrome or Edge)", "error"); return; }
  $("transcript").innerHTML = "";
  $("callBtn").textContent = "📵 Hang up"; $("callBtn").classList.add("active");
  const c = collectConfig();
  const sttEngine = ($("sttEngineSelect") && $("sttEngineSelect").value) || "local";
  call = { uid: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()), startedAt: new Date().toISOString() };
  engine.start({
    system: c.system_prompt, greeting: c.greeting, voiceName: c.voice_name, rate: c.rate,
    lang: c.lang, bargeIn: c.barge_in, agentId: currentAgentId, callUid: call.uid,
    sttEngine: sttEngine,
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

$("optimizePromptBtn").onclick = async () => {
  const btn = $("optimizePromptBtn");
  const sysArea = $("system");
  const orig = sysArea.value.trim();
  if (!orig) { toast("Enter a draft prompt first."); return; }
  
  btn.disabled = true;
  btn.textContent = "✨ Annealing...";
  try {
    const r = await fetch("/api/optimize-prompt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: orig })
    });
    if (!r.ok) throw new Error("Optimization failed");
    const d = await r.json();
    if (d.optimized) {
      sysArea.value = d.optimized;
      toast(`⚛️ Quantum selected: ${d.selected_label || 'Variant ' + (d.selected_index + 1)}!`);
    }
  } catch (e) {
    toast("Optimization failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "✨ Quantum Optimize";
  }
};


// ----------------------------- guardrails & members -----------------------------
async function loadGuardrailsAndMembers() {
  if (!requireSaved("guardrailHint", "Guardrails and Roles")) {
    $("memberList").innerHTML = "";
    return;
  }
  try {
    const roleInfo = await api.myRole(currentAgentId);
    const badge = $("myRoleBadge");
    if (badge) {
      badge.textContent = `Role: ${(roleInfo.role || "owner").toUpperCase()}`;
      badge.className = `role-badge ${roleInfo.role || "owner"}`;
    }
    const canManage = roleInfo.permissions && roleInfo.permissions.can_manage_members;
    if ($("addMemberSection")) $("addMemberSection").style.display = canManage ? "flex" : "none";

    const members = await api.members(currentAgentId);
    renderMemberList(members, canManage);
  } catch (e) {
    console.error("Error loading members:", e);
  }
}

function renderMemberList(members, canManage) {
  const list = $("memberList");
  list.innerHTML = members.length ? "" : '<p class="empty">No team members added yet.</p>';
  $("memberCountBadge").textContent = `${members.length} member(s)`;

  members.forEach((m) => {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML =
      `<div>` +
        `<strong>${esc(m.email)}</strong> ` +
        (m.is_creator ? `<small style="color:var(--green); font-weight:600;">(Primary Owner)</small>` : `<span class="role-badge ${m.role}" style="font-size:10px; padding:1px 6px;">${m.role}</span>`) +
        `<div style="font-size:11px; color:var(--muted);">${fmt(m.created_at)}</div>` +
      `</div>`;

    if (canManage && !m.is_creator) {
      const actions = document.createElement("div");
      actions.style.display = "flex";
      actions.style.gap = "6px";
      actions.style.alignItems = "center";

      const sel = document.createElement("select");
      sel.style.padding = "4px 8px";
      sel.style.fontSize = "12px";
      sel.innerHTML = `
        <option value="manager" ${m.role === "manager" ? "selected" : ""}>Manager</option>
        <option value="receptionist" ${m.role === "receptionist" ? "selected" : ""}>Receptionist</option>
        <option value="viewer" ${m.role === "viewer" ? "selected" : ""}>Viewer</option>
      `;
      sel.onchange = async () => {
        try {
          await api.updateMemberRole(currentAgentId, m.user_id, { role: sel.value });
          toast(`Updated role for ${m.email}`);
          loadGuardrailsAndMembers();
        } catch (e) {
          toast("Update failed: " + e.message);
        }
      };

      const del = document.createElement("button");
      del.className = "danger small";
      del.textContent = "Remove";
      del.onclick = async () => {
        if (!confirm(`Remove ${m.email} from this agent?`)) return;
        try {
          await api.removeMember(currentAgentId, m.user_id);
          toast(`Removed ${m.email}`);
          loadGuardrailsAndMembers();
        } catch (e) {
          toast("Remove failed: " + e.message);
        }
      };

      actions.append(sel, del);
      row.appendChild(actions);
    }
    list.appendChild(row);
  });
}

async function addMemberItem() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const email = $("newMemberEmail").value.trim();
  const role = $("newMemberRole").value;
  if (!email || !email.includes("@")) { toast("Enter a valid email address."); return; }

  const btn = $("addMemberBtn");
  btn.disabled = true;
  try {
    await api.addMember(currentAgentId, { email, role });
    $("newMemberEmail").value = "";
    toast(`✓ Added ${email} as ${role}!`);
    loadGuardrailsAndMembers();
  } catch (e) {
    toast("Failed to add member: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

// ----------------------------- google integrations -----------------------------
async function loadGoogleSettings() {
  if (!requireSaved("googleHint", "Google Integrations")) return;
  try {
    const s = await api.googleSettings(currentAgentId);
    $("google_calendar_id").value = s.google_calendar_id || "";
    $("google_sheet_id").value = s.google_sheet_id || "";
    $("google_auto_sync_calendar").checked = !!s.google_auto_sync_calendar;
    $("google_auto_sync_sheets").checked = !!s.google_auto_sync_sheets;
    $("google_enable_meet").checked = !!s.google_enable_meet;

    const credStatus = $("googleCredStatus");
    if (s.google_credentials_configured) {
      credStatus.textContent = "✓ Cloud credentials active and configured.";
      credStatus.style.color = "var(--green)";
    } else {
      credStatus.textContent = "No credentials configured. Integration runs in intelligent verified sandbox mode.";
      credStatus.style.color = "var(--muted)";
    }
  } catch (e) {
    console.error("Error loading Google settings:", e);
  }
}

async function saveGoogleConfig() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const payload = {
    google_calendar_id: $("google_calendar_id").value.trim(),
    google_sheet_id: $("google_sheet_id").value.trim(),
    google_auto_sync_calendar: $("google_auto_sync_calendar").checked,
    google_auto_sync_sheets: $("google_auto_sync_sheets").checked,
    google_enable_meet: $("google_enable_meet").checked,
  };
  const rawCreds = $("google_credentials_json").value.trim();
  if (rawCreds) {
    payload.google_credentials_json = rawCreds;
  }
  const btn = $("saveGoogleSettingsBtn");
  btn.disabled = true;
  try {
    await api.saveGoogleSettings(currentAgentId, payload);
    $("google_credentials_json").value = "";
    toast("✓ Google integration settings saved!");
    loadGoogleSettings();
  } catch (e) {
    toast("Failed to save: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function testCalendar() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const calVal = $("google_calendar_id").value.trim() || "primary";
  const meetVal = $("google_enable_meet").checked;
  const btn = $("testGCalBtn");
  btn.disabled = true;
  btn.textContent = "Connecting...";
  try {
    const res = await api.testGCal(currentAgentId, {
      google_calendar_id: calVal,
      google_enable_meet: meetVal
    });
    if (res.ok) {
      toast(`📅 Calendar Event Ready! (${res.status || 'OK'})`);
      if (res.html_link) {
        window.open(res.html_link, "_blank", "noopener");
      }
      loadGoogleSettings();
    } else {
      toast("Calendar test failed: " + (res.error || "Unknown"));
    }
  } catch (e) {
    let msg = e.message;
    try {
      const parsed = JSON.parse(e.message);
      if (parsed.detail) msg = parsed.detail;
    } catch (_) {}
    toast("Calendar test error: " + msg);
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Calendar Connection";
  }
}

async function testSheets() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const sheetInput = $("google_sheet_id").value.trim();
  if (!sheetInput) {
    toast("⚠️ Please enter your Google Sheet ID or URL in the field above.");
    $("google_sheet_id").focus();
    return;
  }
  const btn = $("testGSheetBtn");
  btn.disabled = true;
  btn.textContent = "Appending...";
  try {
    const res = await api.testGSheets(currentAgentId, { google_sheet_id: sheetInput });
    if (res.ok) {
      toast(`📊 Google Sheet row appended (${res.updated_range || 'Sheet1'})!`);
      loadGoogleSettings();
    } else {
      toast("Sheet test failed: " + (res.error || "Unknown"));
    }
  } catch (e) {
    let msg = e.message;
    try {
      const parsed = JSON.parse(e.message);
      if (parsed.detail) msg = parsed.detail;
    } catch (_) {}
    toast("Sheet test error: " + msg);
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Sheet Row";
  }
}

async function syncAllExistingSheets() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const btn = $("syncAllSheetsBtn");
  btn.disabled = true;
  btn.textContent = "Syncing...";
  try {
    const res = await api.syncAllSheets(currentAgentId);
    if (res.ok) {
      toast(`✓ Synced ${res.synced_count} of ${res.total} bookings to Google Sheet!`);
    } else {
      toast("Sync failed: " + (res.error || "Unknown"));
    }
  } catch (e) {
    toast("Sync error: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Sync All Bookings";
  }
}

async function importGoogleDocToKB() {
  if (!currentAgentId) { toast("Save the agent first."); return; }
  const url = $("google_doc_url").value.trim();
  if (!url) { toast("Paste a Google Doc URL first."); return; }

  const btn = $("importGDocBtn");
  btn.disabled = true;
  btn.textContent = "Importing & Chunking...";
  try {
    const res = await api.syncGoogleDoc(currentAgentId, { doc_url: url });
    if (res.ok) {
      $("google_doc_url").value = "";
      toast(`📥 Imported "${res.title}" (${res.chunks} chunks indexed)!`);
      loadDocuments();
    } else {
      toast("Import failed: " + (res.detail || res.error || "Unknown"));
    }
  } catch (e) {
    toast("Import error: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "📥 Import Doc to KB";
  }
}

let currentTailoredModels = {
  llm_model: "qwen2.5:7b",
  llm_base_url: "http://ollama:11434/v1",
  stt_model: "whisper-large-v3-turbo",
  stt_base_url: "http://ollama:11434/v1",
  tts_voice: "kokoro",
  has_gpu: true,
  privacy_strict: true
};

async function fetchHardwareRecommendations() {
  const privacy = $("spec_privacy") ? $("spec_privacy").value === "strict" : true;
  const vram = $("spec_vram") ? parseFloat($("spec_vram").value) : 8.0;
  const ram = $("spec_ram") ? parseFloat($("spec_ram").value) : 16.0;
  const calls = $("spec_calls") ? parseInt($("spec_calls").value) : 1;
  const has_gpu = vram > 0;

  try {
    const res = await jreq("/api/recommend-models", "POST", {
      vram_gb: vram,
      ram_gb: ram,
      has_gpu: has_gpu,
      privacy_strict: privacy,
      concurrent_calls: calls
    });

    const rec = res.recommended;
    if (!rec) return;

    currentTailoredModels = {
      llm_model: rec.llm.model,
      llm_base_url: rec.llm.provider === "ollama" ? "http://ollama:11434/v1" : "https://api.groq.com/openai/v1",
      stt_model: rec.stt.model,
      stt_base_url: rec.stt.provider.includes("local") ? "http://ollama:11434/v1" : "https://api.groq.com/openai/v1",
      tts_voice: rec.tts.voice,
      has_gpu: rec.has_gpu,
      privacy_strict: privacy
    };

    if ($("recTag")) $("recTag").textContent = rec.tag;
    if ($("recTitle")) $("recTitle").textContent = rec.title;
    if ($("recPrivacy")) $("recPrivacy").textContent = rec.privacy;
    if ($("recLatency")) $("recLatency").textContent = `~${rec.est_latency_ms} ms`;
    if ($("recLlmName")) $("recLlmName").textContent = rec.llm.name;
    if ($("recLlmReq")) $("recLlmReq").textContent = `${rec.llm.vram_req} · ${rec.llm.provider.toUpperCase()}`;
    if ($("recSttName")) $("recSttName").textContent = rec.stt.name;
    if ($("recSttReq")) $("recSttReq").textContent = `${rec.stt.vram_req} · ${rec.stt.provider.toUpperCase()}`;
    if ($("recTtsName")) $("recTtsName").textContent = rec.tts.name;
    if ($("recTtsReq")) $("recTtsReq").textContent = `${rec.tts.vram_req} · ${rec.tts.provider.toUpperCase()}`;
    if ($("recSummary")) $("recSummary").textContent = rec.summary;

    if ($("dockerPullCommand")) {
      if (rec.llm.provider === "ollama") {
        $("dockerPullCommand").textContent = `docker exec -it voice_agent_ollama ollama pull ${rec.llm.model}`;
      } else {
        $("dockerPullCommand").textContent = `# Cloud LPU pre-configured (Model: ${rec.llm.model} via Groq)`;
      }
    }

    const altsList = $("recAltsList");
    if (altsList) {
      altsList.innerHTML = "";
      (res.alternatives || []).forEach((alt) => {
        const btn = document.createElement("button");
        btn.className = "small btn-secondary";
        btn.style.cssText = "font-size:11px; padding:4px 8px; margin:2px;";
        btn.textContent = `⚡ ${alt.title} (~${alt.est_latency_ms}ms)`;
        btn.onclick = () => {
          currentTailoredModels.llm_model = alt.llm;
          currentTailoredModels.stt_model = alt.stt;
          currentTailoredModels.tts_voice = alt.tts;
          if ($("recLlmName")) $("recLlmName").textContent = alt.llm;
          if ($("recLatency")) $("recLatency").textContent = `~${alt.est_latency_ms} ms`;
          if ($("recSummary")) $("recSummary").textContent = alt.tradeoff;
          if ($("dockerPullCommand")) {
            $("dockerPullCommand").textContent = `docker exec -it voice_agent_ollama ollama pull ${alt.llm}`;
          }
          toast(`Selected profile: ${alt.title}`);
        };
        altsList.appendChild(btn);
      });
    }
  } catch (err) {
    console.warn("Model recommendation fetch error:", err);
  }
}

function downloadDockerAppliance() {
  if (!currentAgentId) {
    toast("Save the agent first before exporting.");
    return;
  }
  toast(`📦 Packaging Docker appliance with ${currentTailoredModels.llm_model}...`);
  const query = new URLSearchParams({
    llm_model: currentTailoredModels.llm_model,
    llm_base_url: currentTailoredModels.llm_base_url,
    stt_model: currentTailoredModels.stt_model,
    tts_voice: currentTailoredModels.tts_voice,
    has_gpu: currentTailoredModels.has_gpu,
    privacy_strict: currentTailoredModels.privacy_strict
  });
  const a = document.createElement("a");
  a.href = `/api/agents/${currentAgentId}/export-docker?${query.toString()}`;
  a.download = `voice_agent_${currentAgentId}_appliance.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// Event listeners
if ($("addMemberBtn")) $("addMemberBtn").onclick = addMemberItem;
if ($("testGCalBtn")) $("testGCalBtn").onclick = testCalendar;
if ($("testGSheetBtn")) $("testGSheetBtn").onclick = testSheets;
if ($("syncAllSheetsBtn")) $("syncAllSheetsBtn").onclick = syncAllExistingSheets;
if ($("importGDocBtn")) $("importGDocBtn").onclick = importGoogleDocToKB;
if ($("saveGoogleSettingsBtn")) $("saveGoogleSettingsBtn").onclick = saveGoogleConfig;
if ($("downloadDockerBtn")) $("downloadDockerBtn").onclick = downloadDockerAppliance;
if ($("exportDockerQuickBtn")) $("exportDockerQuickBtn").onclick = downloadDockerAppliance;

// Spec inputs auto-refresh recommendation
["spec_privacy", "spec_vram", "spec_ram", "spec_calls"].forEach((id) => {
  if ($(id)) $(id).onchange = fetchHardwareRecommendations;
});

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
