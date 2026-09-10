/* محرّك الـLeads — منطق لوحة التحكم (vanilla JS) */
"use strict";

// ------------------------------------------------------------ vocabulary
const T = {
  providerStatus: { active: ["نشط", "b-green"], cooldown: ["تبريد", "b-amber"],
                    exhausted: ["مستنفد", "b-red"], disabled: ["معطّل", "b-gray"],
                    unavailable: ["غير متاح", "b-gray"] },
  jobState: { QUEUED: ["في الانتظار", "b-gray"], RUNNING: ["قيد التشغيل", "b-blue"],
              DEGRADED: ["متدهور", "b-amber"], PAUSED: ["متوقف مؤقتًا", "b-amber"],
              RESUMING: ["يستأنف", "b-blue"], COMPLETED: ["مكتمل", "b-green"],
              FAILED: ["فاشل", "b-red"] },
  leadStage: { ACCEPTED: ["مقبولة", "b-green"], REVIEW: ["مراجعة", "b-amber"],
               REJECTED: ["مرفوضة", "b-red"] },
  emailStatus: { DELIVERABLE: ["صالح", "b-green"], RISKY: ["مشكوك", "b-amber"],
                 CATCH_ALL: ["catch-all", "b-amber"], INVALID: ["غير صالح", "b-red"],
                 UNKNOWN: ["غير معروف", "b-gray"] },
  providerType: { search: "بحث", llm: "نموذج لغوي", data: "بيانات", email: "بريد" },
  quotaKind: { credits: "credits", usd: "$", requests: "طلبات", account: "حساب",
               dynamic: "حد ديناميكي", unlimited: "غير محدود" },
  processingMode: { cloud: ["سحابي", "b-blue"], degraded_local: ["محلي متدهور", "b-amber"] },
  configTabs: { settings: "settings.yaml", cache_policy: "cache_policy.yaml",
                icp_v0_saudi_dental: "icp/v0_saudi_dental.yaml", legal_sa: "legal_policies/sa.yaml" },
};

// ------------------------------------------------------------ helpers
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const badge = (pair) => pair ? `<span class="badge ${pair[1]}">${pair[0]}</span>` : "";

const dt = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const fmtTime = (iso) => { try { return dt.format(new Date(iso)); } catch { return iso || "—"; } };

function ago(iso) {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "الآن";
  if (s < 3600) return `منذ ${Math.floor(s / 60)} د`;
  if (s < 86400) return `منذ ${Math.floor(s / 3600)} س`;
  return `منذ ${Math.floor(s / 86400)} يوم`;
}
const num = (n) => Number(n || 0).toLocaleString("en-US");
const confClass = (pct) => pct >= 100 ? "full" : (pct >= 60 ? "warn" : "");

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

let toastTimer;
function toast(msg, kind = "ok") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

function openModal(title, html) {
  $("#modal-title").innerHTML = title;
  $("#modal-body").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
$("#modal-close").onclick = () => $("#modal").classList.add("hidden");
$("#modal").onclick = (e) => { if (e.target.id === "modal") $("#modal").classList.add("hidden"); };

// ------------------------------------------------------------ status pill
function renderPill(s) {
  const pill = $("#system-pill"), text = $("#pill-text");
  document.querySelector('[data-testid="app-version"]').textContent = `v${s.version}`;
  const j = s.jobs_by_state || {};
  const running = (j.RUNNING || 0) + (j.RESUMING || 0);
  const paused = j.PAUSED || 0;
  const failed = j.FAILED || 0;
  const activeProviders = s.providers.filter((p) => p.status === "active" && (p.has_key || p.is_local)).length;
  pill.className = "pill";
  if (running) { pill.classList.add("busy"); text.textContent = `قيد التشغيل — ${running} مهمة`; }
  else if (paused) { pill.classList.add("warn"); text.textContent = `متوقف مؤقتًا — ${paused} مهمة`; }
  else if (failed) { pill.classList.add("err"); text.textContent = `${failed} مهمة فاشلة`; }
  else { pill.classList.add("ok"); text.textContent = `جاهز — ${activeProviders} مزوّد متاح`; }
}

// ------------------------------------------------------------ overview
function renderOverview(s) {
  const j = s.jobs_by_state || {};
  const st = s.leads_by_stage || {};
  const totalUnits = s.usage_totals.reduce((a, u) => a + Number(u.units || 0), 0);
  const totalCalls = s.usage_totals.reduce((a, u) => a + Number(u.calls || 0), 0);
  const provActive = s.providers.filter((p) => p.status === "active" && (p.has_key || p.is_local)).length;
  const cards = [
    { n: `${provActive}/${s.providers.length}`, l: "مزوّدون متاحون", sub: `${s.providers.filter((p) => p.status === "exhausted").length} مستنفد` },
    { n: num(j.COMPLETED || 0), l: "مهام مكتملة", sub: `${j.PAUSED || 0} متوقفة · ${j.RUNNING || 0} تعمل` },
    { n: num(s.leads_total), l: "leads مخزّنة", sub: `${st.ACCEPTED || 0} مقبولة · ${st.REVIEW || 0} مراجعة` },
    { n: num(totalUnits), l: "units مستهلكة", sub: `${num(totalCalls)} استدعاء API` },
    { n: num(Object.values(s.cache_entries || {}).reduce((a, b) => a + b, 0)), l: "صفوف الكاش", sub: `L1:${s.cache_entries["1"] || 0} · L2:${s.cache_entries["2"] || 0} · L3:${s.cache_entries["3"] || 0}` },
    { n: s.system.supabase_configured ? "متصل" : "غير مضبوط", l: "Supabase", sub: `v${s.version} · Python ${s.system.python}` },
  ];
  $("#overview-cards").innerHTML = cards.map((c) =>
    `<div class="stat"><div class="num">${esc(c.n)}</div><div class="lbl">${c.l}</div><div class="sub">${esc(c.sub)}</div></div>`).join("");

  $("#overview-jobs").innerHTML = (s.recent_jobs || []).slice(0, 7).map((job) => `
    <div class="feed-row" data-testid="feed-job">
      <span class="mono" dir="ltr">${esc(job.job_id)}</span>
      <span class="grow">${esc(job.icp_id || "")} ${badge(T.jobState[job.state])}</span>
      <span class="time">${ago(job.updated_at)}</span>
    </div>`).join("") || `<p class="muted">لا مهام بعد — شغّل أول benchmark من تبويب المهام.</p>`;

  const top = (s.usage_totals || []).slice(0, 7);
  $("#overview-usage").innerHTML = top.map((u) => `
    <div class="feed-row">
      <span class="mono" dir="ltr">${esc(u.provider)}</span>
      <span class="grow muted">${esc(u.task)}</span>
      <span>${num(u.units)} units · ${num(u.calls)} استدعاء</span>
    </div>`).join("") || `<p class="muted">لا استهلاك مسجّل بعد.</p>`;

  const sys = s.system;
  $("#system-info").innerHTML = [
    ["قاعدة البيانات", `<span class="mono" dir="ltr">${esc(sys.db_path)}</span>`],
    ["Supabase", sys.supabase_configured ? badge(["متصل", "b-green"]) : badge(["غير مضبوط — أضف المفاتيح في .env", "b-amber"])],
    ["الإصدار", `<span class="mono" dir="ltr">v${esc(s.version)} · Python ${esc(sys.python)}</span>`],
    ["مجلد الإعدادات", `<span class="mono" dir="ltr">${esc(sys.config_dir)}</span>`],
  ].map(([k, v]) => `<div class="row"><span class="k">${k}</span><span>${v}</span></div>`).join("");
}

// ------------------------------------------------------------ providers
function quotaBar(p) {
  if (p.quota_limit == null) {
    return `<div class="qbar"><div class="txt">${T.quotaKind[p.quota_kind] || p.quota_kind || "—"} · غير محدود</div></div>`;
  }
  const pct = Math.min(100, Math.round((p.quota_used / p.quota_limit) * 100));
  return `<div class="qbar">
    <div class="bar"><div class="fill ${confClass(pct)}" style="width:${pct}%"></div></div>
    <div class="txt">${num(p.quota_used)} / ${num(p.quota_limit)} ${T.quotaKind[p.quota_kind] || ""} (${pct}%)</div>
  </div>`;
}

function renderProviders(s) {
  const rows = [...s.providers].sort((a, b) =>
    (a.task || "").localeCompare(b.task || "") || a.priority - b.priority);
  $("#providers-table tbody").innerHTML = rows.map((p) => {
    const keyState = p.is_local ? badge(["محلي", "b-purple"])
      : p.has_key ? badge(["مضبوط", "b-green"]) : badge(["ناقص", "b-red"]);
    const canControl = p.has_key || p.is_local;
    return `<tr data-testid="provider-row">
      <td class="mono" dir="ltr">${esc(p.name)}</td>
      <td class="mono" dir="ltr">${esc(p.task)}</td>
      <td>${T.providerType[p.type] || esc(p.type)}</td>
      <td>${p.priority}</td>
      <td>${badge(T.providerStatus[p.status] || [p.status, "b-gray"])}${p.status_reason ? `<div class="muted" style="font-size:11px" dir="ltr">${esc(p.status_reason)}</div>` : ""}</td>
      <td>${keyState}</td>
      <td>${quotaBar(p)}</td>
      <td>${num(p.calls)}<div class="muted" style="font-size:11px">${num(p.units)} units</div></td>
      <td class="muted">${ago(p.last_used)}</td>
      <td>
        <button class="btn" style="padding:4px 10px" data-testid="button-toggle-provider"
          onclick="toggleProvider('${esc(p.name)}','${esc(p.task)}',${p.status === "disabled"})"
          ${canControl ? "" : "disabled title='لا مفتاح — عدّل .env'"}>${p.status === "disabled" ? "تفعيل" : "تعطيل"}</button>
        <button class="btn ghost" style="padding:4px 10px" data-testid="button-reset-provider"
          onclick="resetProvider('${esc(p.name)}','${esc(p.task)}')">تصفير</button>
      </td>
    </tr>`;
  }).join("");
}

window.toggleProvider = async (name, task, enable) => {
  try {
    await api(`/api/providers/${name}/${task}/status`, { method: "POST", body: { status: enable ? "active" : "disabled" } });
    toast(enable ? `تم تفعيل ${name}` : `تم تعطيل ${name}`);
    loadTab("providers");
  } catch (e) { toast(e.message, "err"); }
};
window.resetProvider = async (name, task) => {
  try {
    await api(`/api/providers/${name}/${task}/reset`, { method: "POST" });
    toast(`تم تصفير رصيد ${name}/${task}`);
    loadTab("providers");
  } catch (e) { toast(e.message, "err"); }
};

// ------------------------------------------------------------ keys
async function renderKeys() {
  const data = await api("/api/keys");
  const byGroup = {};
  for (const k of data.keys) (byGroup[k.group] = byGroup[k.group] || []).push(k);
  $("#keys-groups").innerHTML = Object.entries(byGroup).map(([group, keys]) => `
    <div class="card" data-testid="keys-group-${group}">
      <h3>${esc(data.groups[group] || group)}</h3>
      ${keys.map((k) => `
        <div class="key-row">
          <label class="key-label">
            <span class="mono" dir="ltr">${esc(k.name)}</span>
            ${k.configured
              ? `<span class="badge b-green">مضبوط — <span class="mono" dir="ltr">${esc(k.masked)}</span></span>`
              : `<span class="badge b-red">ناقص</span>`}
          </label>
          <input type="${k.plain ? "text" : "password"}" dir="ltr" autocomplete="off"
            data-key="${esc(k.name)}"
            placeholder="${k.configured ? "اتركه فارغًا للاحتفاظ بالحالي" : "الصق المفتاح هنا"}"
            data-testid="key-input-${esc(k.name)}">
        </div>`).join("")}
    </div>`).join("");
}

$("#btn-keys-save").onclick = async () => {
  const body = {};
  document.querySelectorAll("#keys-groups input[data-key]").forEach((inp) => {
    if (inp.value.trim() !== "") body[inp.dataset.key] = inp.value.trim();
  });
  if (!Object.keys(body).length) return toast("اكتب مفتاح واحد على الأقل", "err");
  try {
    await api("/api/keys", { method: "POST", body });
    toast("تم الحفظ — المفاتيح شغالة فورًا");
    document.querySelectorAll("#keys-groups input[data-key]").forEach((i) => (i.value = ""));
    await renderKeys();
  } catch (e) { toast(e.message, "err"); }
};

// ------------------------------------------------------------ wipe data
$("#btn-wipe").onclick = async () => {
  if (!confirm("هيتم مسح كل المهام والـleads والكاش وسجل الاستهلاك نهائيًا. متأكد؟")) return;
  if (!confirm("تأكيد أخير: مسح كل البيانات المحلية؟")) return;
  try {
    await api("/api/data/reset", { method: "POST" });
    toast("تم مسح كل البيانات المحلية");
    loadTab("overview");
  } catch (e) { toast(e.message, "err"); }
};

// ------------------------------------------------------------ chat
let chatHistory = [];

function appendMsg(role, text) {
  const log = $("#chat-log");
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  div.appendChild(bubble);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function appendToolTrace(tools) {
  if (!tools || !tools.length) return;
  const log = $("#chat-log");
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = tools.map((t) => {
    const args = Object.entries(t.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ");
    const state = t.ok === false ? "⚠️" : "⚙️";
    return `<span class="tool-chip" data-testid="tool-chip">${state} ${esc(t.name)}(${esc(args)})</span>`;
  }).join("");
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendMsg("user", text);
  chatHistory.push({ role: "user", content: text });
  const thinking = appendMsg("assistant", "…شغّال");
  $("#btn-chat-send").disabled = true;
  try {
    const res = await api("/api/chat", { method: "POST", body: { messages: chatHistory.slice(-12) } });
    thinking.remove();
    appendToolTrace(res.tools);
    appendMsg("assistant", res.reply || "(رد فاضي)");
    chatHistory.push({ role: "assistant", content: res.reply || "" });
  } catch (e) {
    thinking.remove();
    appendMsg("assistant", `حصل خطأ: ${e.message}`);
  } finally { $("#btn-chat-send").disabled = false; }
}
$("#btn-chat-send").onclick = sendChat;
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// ------------------------------------------------------------ jobs
async function renderJobs(s) {
  const tbody = $("#jobs-table tbody");
  tbody.innerHTML = (s.recent_jobs || []).map((job) => `
    <tr data-testid="job-row" style="cursor:pointer" onclick="openJob('${esc(job.job_id)}')">
      <td class="mono" dir="ltr">${esc(job.job_id)}</td>
      <td class="mono" dir="ltr">${esc(job.icp_id || "")}</td>
      <td>${badge(T.jobState[job.state] || [job.state, "b-gray"])}</td>
      <td class="mono truncate" dir="ltr">${esc(job.pause_reason || "—")}</td>
      <td class="muted">${fmtTime(job.created_at)}</td>
      <td class="muted">${ago(job.updated_at)}</td>
    </tr>`).join("") || `<tr><td colspan="6" class="muted">لا مهام بعد.</td></tr>`;
}

window.openJob = async (jobId) => {
  try {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job, events = data.events || [];
    let metricsHtml = "";
    try {
      const stored = job.params ? JSON.parse(job.params) : null;
      if (stored && stored.metrics) {
        const m = stored.metrics;
        metricsHtml = `<div class="result-card"><h3>مقاييس التشغيل</h3><div class="kv"><span class="k">كانديدات خام</span><span>${num(m.discovery_raw_candidates)}</span></div>
          <div class="kv"><span class="k">بعد الـdedup</span><span>${num(m.unique_after_dedup)} (مكرر ${m.duplicate_rate})</span></div>
          <div class="kv"><span class="k">leads نهائية</span><span>${num(m.final_leads)} مقبولة + ${num(m.review_leads)} مراجعة</span></div>
          <div class="kv"><span class="k">استهلاك</span><span>${num(m.quota_units_total)} units (${m.quota_units_per_final_lead ?? "—"} لكل lead)</span></div>
          <div class="kv"><span class="k">التكلفة</span><span>$${m.total_cost_usd}</span></div></div>`;
      }
    } catch { /* params not JSON */ }

    const actions = [];
    if (job.state === "PAUSED") actions.push(`<button class="btn primary" data-testid="button-resume" onclick="resumeJob('${esc(jobId)}')">استئناف</button>`);
    if (job.state === "COMPLETED" || job.state === "DEGRADED") actions.push(`<button class="btn primary" data-testid="button-sync" onclick="syncJob('${esc(jobId)}')">مزامنة مع Supabase</button>`);
    if (job.state === "COMPLETED" || job.state === "DEGRADED") actions.push(`<button class="btn" data-testid="button-report" onclick="showReport('${esc(jobId)}')">عرض التقرير</button>`);

    openModal(`المهمة <span class="mono" dir="ltr">${esc(jobId)}</span>`, `
      <div class="kv"><span class="k">الحالة</span>${badge(T.jobState[job.state] || [job.state, "b-gray"])}</div>
      ${job.pause_reason ? `<div class="kv"><span class="k">سبب الإيقاف</span><span class="mono" dir="ltr">${esc(job.pause_reason)}</span></div>` : ""}
      ${job.resume_at ? `<div class="kv"><span class="k">يُعاد المحاولة</span><span class="mono" dir="ltr">${esc(job.resume_at)}</span></div>` : ""}
      ${metricsHtml}
      <div class="result-card"><h3>سجل الأحداث</h3>
        <div class="timeline">${events.map((e) => `
          <div class="ev" data-testid="job-event">
            <span class="muted" style="min-width:130px">${fmtTime(e.ts)}</span>
            <span>${esc(e.from_state || "—")} ← ${esc(e.to_state)}</span>
            ${e.reason ? `<span class="muted mono" dir="ltr">${esc(e.reason)}</span>` : ""}
          </div>`).join("") || `<p class="muted">لا أحداث.</p>`}
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px">${actions.join("")}</div>`);
  } catch (e) { toast(e.message, "err"); }
};

window.resumeJob = async (jobId) => {
  try {
    const res = await api(`/api/jobs/${jobId}/resume`, { method: "POST", body: {} });
    toast(`تم الاستئناف — الحالة: ${res.state}`);
    $("#modal").classList.add("hidden");
    loadTab("jobs");
  } catch (e) { toast(e.message, "err"); }
};
window.syncJob = async (jobId) => {
  try {
    const res = await api("/sync-supabase", { method: "POST", body: { job_id: jobId } });
    toast(`تمت المزامنة: ${res.companies} شركة، ${res.leads} leads`);
  } catch (e) { toast(e.message, "err"); }
};
window.showReport = async (jobId) => {
  try {
    const res = await api(`/report/${jobId}`);
    openModal(`تقرير <span class="mono" dir="ltr">${esc(jobId)}</span>`,
      `<div class="md" data-testid="report-md">${esc(res.report_markdown)}</div>`);
  } catch (e) { toast(e.message, "err"); }
};

$("#btn-run").onclick = async () => {
  const btn = $("#btn-run");
  try {
    btn.disabled = true;
    const res = await api("/api/jobs/start", {
      method: "POST",
      body: { icp: $("#run-icp").value.trim(), dry_run: $("#run-dry").checked },
    });
    toast(`بدأت المهمة ${res.job_id} — تابع حالتها في الجدول`);
    switchTab("jobs");
    pollJob(res.job_id);
  } catch (e) { toast(e.message, "err"); }
  finally { btn.disabled = false; }
};

let polling = null;
function pollJob(jobId) {
  clearInterval(polling);
  polling = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      if (!["QUEUED", "RUNNING", "RESUMING"].includes(job.job.state)) {
        clearInterval(polling);
        toast(`المهمة ${jobId}: ${T.jobState[job.job.state][0]}`, job.job.state === "COMPLETED" ? "ok" : "err");
      }
      if ($("#tab-jobs").classList.contains("active")) renderJobs(await api("/api/status"));
    } catch { /* keep polling */ }
  }, 3000);
}

// ------------------------------------------------------------ leads
async function renderLeads(s) {
  const jobSel = $("#leads-job");
  const current = jobSel.value;
  const options = (s.recent_jobs || []).map((j) => `<option value="${esc(j.job_id)}">${esc(j.job_id)} (${T.jobState[j.state][0]})</option>`).join("");
  jobSel.innerHTML = `<option value="">الكل</option>${options}`;
  if (current) jobSel.value = current;

  const params = new URLSearchParams();
  if (jobSel.value) params.set("job_id", jobSel.value);
  if ($("#leads-stage").value) params.set("stage", $("#leads-stage").value);
  const leads = await api(`/leads?${params}`);
  $("#leads-table tbody").innerHTML = leads.map((l) => `
    <tr data-testid="lead-row">
      <td class="truncate" title="${esc(l.name)}">${esc(l.name || "—")}</td>
      <td>${esc(l.city || "—")}</td>
      <td class="mono truncate" dir="ltr">${esc(l.domain || "—")}</td>
      <td>${l.tier ? badge([`tier ${esc(l.tier)}`, l.tier === "A" ? "b-green" : l.tier === "B" ? "b-blue" : "b-gray"]) : "—"}</td>
      <td><strong>${l.score ?? "—"}</strong></td>
      <td class="mono truncate" dir="ltr">${esc(l.email || "—")}</td>
      <td>${badge(T.emailStatus[l.email_status] || ["—", "b-gray"])}</td>
      <td class="truncate">${esc(l.decision_maker || "—")}</td>
      <td>${badge(T.processingMode[l.processing_mode] || ["—", "b-gray"])}</td>
      <td>${badge(T.leadStage[l.legal_decision] || [l.legal_decision || "—", "b-gray"])}</td>
    </tr>`).join("") || `<tr><td colspan="10" class="muted">لا نتائج — شغّل مهمة أولًا.</td></tr>`;
}
$("#leads-job").onchange = () => loadTab("leads");
$("#leads-stage").onchange = () => loadTab("leads");
$("#btn-export").onclick = () => { window.location.href = "/api/export/leads.csv"; };

// ------------------------------------------------------------ verify
$("#btn-verify").onclick = async () => {
  const email = $("#verify-email").value.trim();
  if (!email) return toast("اكتب إيميل الأول", "err");
  try {
    const res = await api("/verify-email", { method: "POST", body: { email, dry_run: $("#verify-dry").checked } });
    const pair = T.emailStatus[res.status] || [res.status, "b-gray"];
    const conf = Math.round((res.confidence || 0) * 100);
    $("#verify-result").innerHTML = `
      <div class="result-card" data-testid="verify-result">
        <div class="kv"><span class="k">النتيجة</span>${badge(pair)} <strong>${esc(res.status)}</strong></div>
        <div class="kv"><span class="k">الثقة</span><span style="flex:1">${conf}%<div class="confbar"><div class="fill" style="width:${conf}%"></div></div></span></div>
        <div class="kv"><span class="k">المزوّد</span><span class="mono" dir="ltr">${esc(res.provider || res.via || "—")}</span></div>
        <div class="kv"><span class="k">السبب</span><span class="mono" dir="ltr">${esc(res.details?.reason || res.method || "—")}</span></div>
      </div>`;
  } catch (e) { toast(e.message, "err"); }
};

// ------------------------------------------------------------ config
let activeConfigKey = "settings";
function renderConfigSubtabs() {
  $("#config-subtabs").innerHTML = Object.entries(T.configTabs).map(([key, label]) =>
    `<button class="subtab ${key === activeConfigKey ? "active" : ""}" data-testid="config-subtab-${key}" onclick="selectConfig('${key}')">${label}</button>`).join("");
}
window.selectConfig = async (key) => {
  activeConfigKey = key;
  renderConfigSubtabs();
  try {
    const all = await api("/api/config");
    $("#config-text").value = all[key].text;
    $("#config-path").textContent = all[key].path;
  } catch (e) { toast(e.message, "err"); }
};
$("#btn-config-save").onclick = async () => {
  try {
    await api(`/api/config/${activeConfigKey}`, { method: "PUT", body: { text: $("#config-text").value } });
    toast("تم الحفظ — بينطبق من التشغيل الجاي");
  } catch (e) { toast(e.message, "err"); }
};

// ------------------------------------------------------------ tabs & polling
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  loadTab(name);
}
document.querySelectorAll(".tab").forEach((t) => t.onclick = () => switchTab(t.dataset.tab));

async function loadTab(name, silent = false) {
  try {
    if (name === "keys") { await renderKeys(); return; }
    const s = await api("/api/status");
    renderPill(s);
    if (name === "overview") renderOverview(s);
    if (name === "providers") renderProviders(s);
    if (name === "jobs") await renderJobs(s);
    if (name === "leads") await renderLeads(s);
  } catch (e) {
    if (!silent) toast(`تعذر تحميل الحالة: ${e.message}`, "err");
  }
}

setInterval(() => {
  const active = document.querySelector(".tab.active")?.dataset.tab;
  if (active && active !== "config") loadTab(active, true);
}, 5000);

// boot
renderConfigSubtabs();
selectConfig("settings");
switchTab("overview");
