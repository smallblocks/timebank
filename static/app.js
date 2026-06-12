/* TimeBank frontend — no build step, no external assets. */

const $ = (sel) => document.querySelector(sel);
const app = $("#app");
let parentToken = localStorage.getItem("tb_parent_token") || null;

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (parentToken) headers["X-Parent-Token"] = parentToken;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { parentToken = null; localStorage.removeItem("tb_parent_token"); route(); throw new Error("auth"); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------- router ---------------- */

window.addEventListener("hashchange", route);
window.addEventListener("load", route);

function route() {
  const h = location.hash || "#/";
  if (h.startsWith("#/kid/")) return kidView(parseInt(h.split("/")[2], 10));
  if (h === "#/parent") return parentView();
  return pickerView();
}

/* ---------------- kid picker ---------------- */

async function pickerView() {
  const kids = await api("/api/kids");
  app.innerHTML = `
    <div class="kidview">
      <div class="topbar">
        <h1>Who are you?</h1>
        <button class="linklike" onclick="location.hash='#/parent'">Parents</button>
      </div>
      <div class="picker">
        ${kids.map((k) => `
          <button style="background:${esc(k.color)}" onclick="location.hash='#/kid/${k.id}'">
            <span>${esc(k.name)}</span><span class="bal">${k.balance} min</span>
          </button>`).join("") || `<p class="empty">No kids yet. Parents: tap “Parents” to set up.</p>`}
      </div>
    </div>`;
}

/* ---------------- kid view ---------------- */

let lastBalance = {};

async function kidView(kidId) {
  let data;
  try { data = await api(`/api/kids/${kidId}/today`); }
  catch { location.hash = "#/"; return; }
  const { kid, balance, tasks, pending_redemptions } = data;
  const hasPendingSpend = pending_redemptions.length > 0;

  app.innerHTML = `
    <div class="kidview">
      <div class="kid-head">
        <span class="kid-name" style="color:${esc(kid.color)}">${esc(kid.name)}</span>
        <span class="kid-date">${new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</span>
      </div>
      <div class="bank">
        <div class="num" id="bankNum">0</div>
        <div class="lbl">minutes in your bank</div>
      </div>
      <div class="tasklist">
        ${tasks.map((t) => taskCard(t)).join("") || `<p class="empty">No tasks today. Nice.</p>`}
      </div>
      ${hasPendingSpend
        ? `<p class="note">Asked for ${pending_redemptions[0].minutes} min — waiting for a parent ⏳</p>`
        : `<button class="spend" id="spendBtn" ${balance < 15 ? "disabled" : ""}>Spend my minutes</button>
           <div class="spend-row" id="spendRow" hidden>
             ${[15, 30, 45, 60].map((m) =>
               `<button data-m="${m}" ${m > balance ? "disabled" : ""}>${m}</button>`).join("")}
           </div>
           ${balance < 15 ? `<p class="note">Earn 15 minutes to unlock spending</p>` : ""}`}
      <p class="note"><a href="#/" style="color:inherit">Switch kid</a></p>
    </div>`;

  animateCount($("#bankNum"), lastBalance[kidId] ?? balance, balance);
  lastBalance[kidId] = balance;

  document.querySelectorAll(".taskcard.open").forEach((el) => {
    el.addEventListener("click", async () => {
      try { await api("/api/completions", { method: "POST", body: JSON.stringify({ task_id: +el.dataset.id }) }); }
      catch (e) { alert(e.message); }
      kidView(kidId);
    });
  });
  const spendBtn = $("#spendBtn");
  if (spendBtn) spendBtn.addEventListener("click", () => { $("#spendRow").hidden = false; spendBtn.hidden = true; });
  document.querySelectorAll("#spendRow button").forEach((b) => {
    b.addEventListener("click", async () => {
      try { await api("/api/redemptions", { method: "POST", body: JSON.stringify({ kid_id: kidId, minutes: +b.dataset.m }) }); }
      catch (e) { alert(e.message); }
      kidView(kidId);
    });
  });
}

function taskCard(t) {
  const status = t.status;
  const icon = status === "approved" ? `<span class="check">✓</span>`
    : status === "pending" ? "⏳" : "";
  const cls = status === "open" ? "open" : status;
  const right = status === "approved" ? `${icon} +${t.minutes}`
    : status === "pending" ? `${icon} waiting`
    : `+${t.minutes} min`;
  return `<button class="taskcard ${cls}" data-id="${t.id}" ${status !== "open" ? "disabled" : ""}>
    <span>${esc(t.title)}</span><span class="mins">${right}</span>
  </button>`;
}

function animateCount(el, from, to) {
  if (!el) return;
  if (from === to || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = to; return; }
  const start = performance.now(), dur = 700;
  const step = (now) => {
    const p = Math.min((now - start) / dur, 1);
    el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---------------- parent view ---------------- */

let parentTab = "approvals";

async function parentView() {
  if (!parentToken) return pinView();
  app.innerHTML = `
    <div class="topbar"><h1>Parents</h1>
      <button class="linklike" id="lockBtn">Lock</button></div>
    <div class="tabs">
      ${["approvals", "tasks", "kids", "settings"].map((t) =>
        `<button class="${parentTab === t ? "on" : ""}" data-tab="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}
    </div>
    <div id="panel"></div>`;
  $("#lockBtn").addEventListener("click", () => {
    parentToken = null; localStorage.removeItem("tb_parent_token"); location.hash = "#/";
  });
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.addEventListener("click", () => { parentTab = b.dataset.tab; parentView(); }));
  const panel = $("#panel");
  try {
    if (parentTab === "approvals") await approvalsPanel(panel);
    if (parentTab === "tasks") await tasksPanel(panel);
    if (parentTab === "kids") await kidsPanel(panel);
    if (parentTab === "settings") await settingsPanel(panel);
  } catch (e) { if (e.message !== "auth") panel.innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
}

function pinView() {
  app.innerHTML = `
    <h1>Parents</h1>
    <div class="field"><label>PIN</label>
      <input id="pin" type="password" inputmode="numeric" autocomplete="off"></div>
    <button class="btn wide" id="go">Sign in</button>
    <p class="note">Default PIN is 1031 — change it in Settings.</p>
    <p class="note"><a href="#/" style="color:inherit">Back</a></p>`;
  $("#go").addEventListener("click", async () => {
    try {
      const r = await api("/api/auth", { method: "POST", body: JSON.stringify({ pin: $("#pin").value }) });
      parentToken = r.token; localStorage.setItem("tb_parent_token", r.token); parentView();
    } catch { alert("Wrong PIN"); }
  });
}

async function approvalsPanel(panel) {
  const { completions, redemptions } = await api("/api/approvals");
  panel.innerHTML = `
    <h2>Task sign-offs</h2>
    ${completions.map((c) => `
      <div class="row">
        <div><span class="pill" style="background:${esc(c.color)}">${esc(c.kid_name)}</span>
          ${esc(c.title)} <span class="meta">+${c.minutes} min</span></div>
        <div class="actions">
          <button class="btn ok" data-act="approve" data-id="${c.id}">Approve</button>
          <button class="btn no" data-act="reject" data-id="${c.id}">Reject</button>
        </div>
      </div>`).join("") || `<p class="empty">Nothing waiting</p>`}
    <h2>Time requests</h2>
    ${redemptions.map((r) => `
      <div class="row">
        <div><span class="pill" style="background:${esc(r.color)}">${esc(r.kid_name)}</span>
          ${r.minutes} min <span class="meta">bank: ${r.balance}</span></div>
        <div class="actions">
          <button class="btn ok" data-ract="grant" data-id="${r.id}">Grant</button>
          <button class="btn no" data-ract="deny" data-id="${r.id}">Deny</button>
        </div>
      </div>`).join("") || `<p class="empty">Nothing waiting</p>`}`;
  panel.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/completions/${b.dataset.id}/review`, { method: "POST", body: JSON.stringify({ action: b.dataset.act }) });
    parentView();
  }));
  panel.querySelectorAll("[data-ract]").forEach((b) => b.addEventListener("click", async () => {
    const r = await api(`/api/redemptions/${b.dataset.id}/review`, { method: "POST", body: JSON.stringify({ action: b.dataset.ract }) });
    if (r.status === "granted") alert(`Now open Screen Time and give ${r.kid} ${r.minutes} minutes.`);
    parentView();
  }));
}

async function tasksPanel(panel) {
  const [tasks, kids] = await Promise.all([api("/api/tasks"), api("/api/kids")]);
  const kidName = (id) => (kids.find((k) => k.id === id) || {}).name || "?";
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  panel.innerHTML = `
    ${tasks.map((t) => `
      <div class="row">
        <div>${esc(t.title)}
          <div class="meta">${esc(kidName(t.kid_id))} · +${t.minutes} min ·
            ${t.recurrence === "weekly" ? days[t.weekday] + "s" : t.recurrence}</div></div>
        <button class="btn ghost" data-del="${t.id}">Remove</button>
      </div>`).join("") || `<p class="empty">No tasks yet</p>`}
    <h2>Add a task</h2>
    <div class="field"><label>Task</label><input id="tTitle" placeholder="Make your bed"></div>
    <div class="grid2">
      <div class="field"><label>Kid</label>
        <select id="tKid">${kids.map((k) => `<option value="${k.id}">${esc(k.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Minutes earned</label>
        <input id="tMin" type="number" inputmode="numeric" value="15"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>Repeats</label>
        <select id="tRec"><option value="daily">Every day</option>
          <option value="weekly">Weekly</option><option value="once">One time</option></select></div>
      <div class="field"><label>Day (weekly)</label>
        <select id="tDay">${days.map((d, i) => `<option value="${i}">${d}</option>`).join("")}</select></div>
    </div>
    <button class="btn wide" id="tAdd">Add task</button>`;
  panel.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/tasks/${b.dataset.del}`, { method: "DELETE" }); parentView();
  }));
  $("#tAdd").addEventListener("click", async () => {
    const rec = $("#tRec").value;
    try {
      await api("/api/tasks", { method: "POST", body: JSON.stringify({
        kid_id: +$("#tKid").value, title: $("#tTitle").value,
        minutes: +$("#tMin").value, recurrence: rec,
        weekday: rec === "weekly" ? +$("#tDay").value : null }) });
      parentView();
    } catch (e) { alert(e.message); }
  });
}

async function kidsPanel(panel) {
  const kids = await api("/api/kids");
  const colors = ["#2F7D4F", "#3A5FA8", "#C2543A", "#7A4FA0", "#C99A1B", "#2A8C8C"];
  panel.innerHTML = `
    ${kids.map((k) => `
      <div class="row">
        <div><span class="pill" style="background:${esc(k.color)}">${esc(k.name)}</span>
          <span class="meta">bank: ${k.balance} min</span></div>
        <div class="actions">
          <button class="btn ghost" data-adj="${k.id}" data-name="${esc(k.name)}">Adjust</button>
          <button class="btn ghost" data-del="${k.id}">Remove</button>
        </div>
      </div>`).join("") || `<p class="empty">No kids yet</p>`}
    <h2>Add a kid</h2>
    <div class="grid2">
      <div class="field"><label>Name</label><input id="kName"></div>
      <div class="field"><label>Color</label>
        <select id="kColor">${colors.map((c) => `<option value="${c}">${c}</option>`).join("")}</select></div>
    </div>
    <button class="btn wide" id="kAdd">Add kid</button>`;
  $("#kAdd").addEventListener("click", async () => {
    await api("/api/kids", { method: "POST", body: JSON.stringify({ name: $("#kName").value, color: $("#kColor").value }) });
    parentView();
  });
  panel.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    if (confirm("Remove this kid?")) { await api(`/api/kids/${b.dataset.del}`, { method: "DELETE" }); parentView(); }
  }));
  panel.querySelectorAll("[data-adj]").forEach((b) => b.addEventListener("click", async () => {
    const d = prompt(`Adjust ${b.dataset.name}'s bank by how many minutes? (negative to remove)`);
    if (!d) return;
    await api("/api/adjust", { method: "POST", body: JSON.stringify({ kid_id: +b.dataset.adj, delta: +d, reason: "Parent adjustment" }) });
    parentView();
  }));
}

async function settingsPanel(panel) {
  const s = await api("/api/settings");
  panel.innerHTML = `
    <div class="field"><label>Notification URL (ntfy topic, e.g. https://ntfy.yourdomain.com/timebank)</label>
      <input id="sNtfy" value="${esc(s.ntfy_url || "")}" placeholder="Leave blank for in-app only"></div>
    <div class="field"><label>New parent PIN (blank to keep)</label>
      <input id="sPin" type="password" inputmode="numeric" autocomplete="off"></div>
    <button class="btn wide" id="sSave">Save settings</button>
    <p class="note">Notifications fire when a kid finishes a task or asks to spend time,
      and again when you grant time — with the exact minutes to set in Screen Time.</p>`;
  $("#sSave").addEventListener("click", async () => {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({
      ntfy_url: $("#sNtfy").value, parent_pin: $("#sPin").value || null }) });
    alert("Saved");
  });
}
