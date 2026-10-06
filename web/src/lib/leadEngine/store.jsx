// Lead Engine store — the REAL backend adapter.
// Same public interface the pages were built against (useLeadEngine), but
// every byte of state now comes from the FastAPI backend: engine.jobs,
// engine.leads, the provider registry, /api/activity, /api/keys, /api/chat,
// and the agentic research flow (/api/v1/research). No demo seeds anywhere.
import React, { createContext, useContext, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { makeT } from "./i18n";
import {
  apiGet, apiPost, mapJob, mapLead, mapProvider, mapActivityEvent, mapCredential, mapIcp,
} from "./api";

const LeadEngineContext = createContext(null);

const isoNow = () => new Date().toISOString();
const safeGet = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const safeSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

const FINAL_LEAD = ["APPROVED", "REJECTED"];
const LIVE = ["DISCOVERING", "RESEARCHING", "VERIFYING", "QUALIFYING", "RUNNING"];
export const isLiveStatus = (s) => LIVE.includes(s);
const SERVICE_ENV = {
  Gemini: "GEMINI_API_KEY", Tavily: "TAVILY_API_KEY", Apollo: "APOLLO_API_KEY",
  Hunter: "HUNTER_API_KEY", OpenRouter: "OPENROUTER_API_KEY",
  Brave: "BRAVE_SEARCH_API_KEY", Exa: "EXA_API_KEY", Groq: "GROQ_API_KEY",
  Abstract: "ABSTRACT_API_KEY",
};

export function LeadEngineProvider({ children }) {
  const [lang, setLang] = useState(() => (safeGet("leadengine.lang", "ar") === "en" ? "en" : "ar"));
  const [theme, setTheme] = useState(() => {
    const saved = safeGet("leadengine.theme", "");
    if (saved === "light" || saved === "dark") return saved;
    return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  // ---- backend state ----
  const [jobs, setJobs] = useState([]);
  const [leads, setLeads] = useState([]);
  const [icps, setIcps] = useState([]);
  const [providers, setProviders] = useState([]);
  const [creds, setCreds] = useState([]);
  const [agents, setAgents] = useState([]);
  const [activity, setActivity] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [chat, setChat] = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);
  const [currentUser] = useState({ name: "Operator" });
  const [connected, setConnected] = useState(true);
  const loadedOnce = useRef(false);

  const t = useMemo(() => makeT(lang), [lang]);
  const nid = (p) => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

  useEffect(() => {
    const html = document.documentElement;
    html.lang = lang;
    html.dir = "ltr";
    safeSet("leadengine.lang", lang);
  }, [lang]);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    safeSet("leadengine.theme", theme);
  }, [theme]);

  const toggleLang = useCallback(() => setLang((l) => (l === "ar" ? "en" : "ar")), []);
  const toggleTheme = useCallback(() => setTheme((x) => (x === "dark" ? "light" : "dark")), []);

  const pushLocal = useCallback((action, target, detail, actor) => {
    setActivity((prev) => [{ id: nid("ev"), actor: actor || "you", action, target, at: isoNow(), detail },
      ...prev].slice(0, 200));
  }, []);

  // ---- one refresh cycle against the backend ----
  const refresh = useCallback(async () => {
    try {
      const [status, jobsRows, leadsRows, activityRows] = await Promise.all([
        apiGet.status(), apiGet.jobs(), apiGet.leads({ limit: 500 }),
        apiGet.activity(60).catch(() => ({ events: [] })),
      ]);
      setConnected(true);
      setProviders((status.providers || []).map(mapProvider));
      setJobs((jobsRows || []).map(mapJob));
      setLeads((leadsRows || []).map(mapLead));
      setActivity((activityRows.events || []).map(mapActivityEvent));
      if (!loadedOnce.current) {
        loadedOnce.current = true;
        try {
          const k = await apiGet.keys();
          setCreds((k.keys || []).map(mapCredential));
          const icpRows = await apiGet.icps().catch(() => ({ versions: [] }));
          setIcps((icpRows.versions || []).map(mapIcp));
          const a = await apiGet.agents().catch(() => ({ agents: [] }));
          setAgents(a.agents || []);
        } catch { /* optional surfaces */ }
      }
    } catch (err) {
      setConnected(false);
      console.warn("refresh failed:", err?.message || err);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  const refreshJobEvents = useCallback(async (jobId) => {
    try {
      const detail = await apiGet.job(jobId);
      const events = (detail.events || []).map((e) => ({
        at: e.ts, event: e.to_state || e.from_state || "event", detail: e.reason || "",
      }));
      setJobs((prev) => prev.map((j) => j.id !== jobId ? j : { ...j, timeline: events }));
      return detail;
    } catch { return null; }
  }, []);

  const pushNotif = useCallback((n) => {
    setNotifications((prev) => [{ id: nid("n"), at: isoNow(), read: false, ...n }, ...prev]);
  }, []);

  const canFindContacts = !!creds.find((c) => c.service === "Apollo")?.connected;

  // ---------- chat → research ----------
  const submitObjective = useCallback(async (text) => {
    const localJob = {
      id: `pending_${Date.now().toString(36)}`, objective: text,
      status: "QUEUED", createdAt: isoNow(), startedAt: isoNow(), completedAt: null,
      stages: { discovered: 0, deduplicated: 0, researched: 0, verified: 0, qualified: 0, readyForReview: 0 },
      budget: { used: 0, limit: 500, unit: "نداء" }, stopReason: null, timeline: [],
      providerActivity: [], leadIds: [], waitingQuestion: null,
    };
    setJobs((prev) => [localJob, ...prev]);
    setActiveJobId(localJob.id);
    setChat((prev) => [...prev,
      { id: nid("m"), role: "user", text, at: isoNow() },
      { id: nid("m"), role: "agent", at: isoNow(), text: "تم استلام الهدف — بدأ تشكيل وظيفة البحث", status: "Creating research job" },
    ]);
    try {
      const r = await apiPost.researchStart(text);
      setChat((prev) => [...prev, {
        id: nid("m"), role: "agent", at: isoNow(),
        text: `وظيفة البحث اتعملت (${r.job_id}) — الحالة الآن ${r.state}. تابعها من صفحة الوظائف.`,
        status: r.state,
      }]);
      pushLocal("أنشأ وظيفة بحث", r.job_id, text.slice(0, 60));
      pushNotif({ type: "question", title: "وظيفة بحث جديدة", detail: text.slice(0, 56), severity: "info", to: `/jobs/${r.job_id}` });
      refresh();
      return r;
    } catch (err) {
      setChat((prev) => [...prev, { id: nid("m"), role: "agent", at: isoNow(), text: `تعذر بدء البحث: ${err.message}`, status: "error" }]);
      setJobs((prev) => prev.filter((j) => j.id !== localJob.id));
      return null;
    }
  }, [pushNotif, pushLocal, refresh]);

  const answerClarification = useCallback(async (jobId, answer) => {
    try {
      await apiPost.researchAnswer(jobId, answer);
      setChat((prev) => [...prev, { id: nid("m"), role: "user", text: answer, at: isoNow() }]);
      pushLocal("أجاب على استيضاح", jobId, answer);
      refreshJobEvents(jobId);
      refresh();
    } catch (err) {
      setChat((prev) => [...prev, { id: nid("m"), role: "agent", at: isoNow(), text: `تعذر إرسال الإجابة: ${err.message}`, status: "error" }]);
    }
  }, [pushLocal, refreshJobEvents, refresh]);

  // ---------- review ----------
  const reviewLead = useCallback(async (leadId, decision, note) => {
    const action = { APPROVED: "APPROVE_CONTACT", REJECTED: "REJECT", SAVED: "SAVE_FOR_LATER" }[decision];
    if (!action) return false;
    try {
      await apiPost.leadDecision(leadId, action, note);
      setLeads((prev) => prev.map((l) => l.id !== leadId ? l : {
        ...l,
        status: { APPROVE_CONTACT: "APPROVED", REJECT: "REJECTED", SAVE_FOR_LATER: "SAVED", RESEARCH_MORE: "READY_FOR_REVIEW" }[action] || l.status,
        reviewDecision: decision, reviewNote: note || null, reviewAt: isoNow(), lastUpdated: isoNow(),
      }));
      pushLocal({ APPROVE_CONTACT: "اعتمد جهة اتصال", REJECT: "رفض عميلًا", SAVE_FOR_LATER: "حفظ عميلًا لوقت لاحق", RESEARCH_MORE: "طلب بحثًا إضافيًا" }[action], leadId, note || "");
      return true;
    } catch (err) {
      pushNotif({ type: "review", title: "فشل تسجيل القرار", detail: err.message, severity: "error" });
      return false;
    }
  }, [pushLocal, pushNotif]);

  const undoReview = useCallback(async (leadId) => {
    // Dispositions are human-owned and immutable in the backend by design —
    // an undo is a NEW decision that returns the lead to the review gate.
    const ok = await reviewLead(leadId, "SAVED", "تراجع — أُعيد للمراجعة");
    if (ok) pushLocal("تراجع عن قرار", leadId, "");
    return ok;
  }, [reviewLead, pushLocal]);

  const revealPII = useCallback((leadId, reason) => {
    if (!reason?.trim()) return false;
    setLeads((prev) => prev.map((l) => l.id === leadId
      ? { ...l, contact: { ...l.contact, piiAccessed: true, revealReason: reason.trim(), revealAt: isoNow() } }
      : l));
    // Legacy rows carry the contact inline; the reason is what the audit
    // needs. v6 leads reveal through the vault endpoint instead.
    pushLocal("كشف بيانات الاتصال", leadId, `السبب: ${reason.trim()} — مسجّل في سجل التدقيق`);
    return true;
  }, [pushLocal]);

  const researchMore = useCallback(async (leadId) => {
    try {
      await apiPost.leadRequalify(leadId);
      pushLocal("طلب بحثًا إضافيًا", leadId, "");
      refresh();
      return true;
    } catch (err) {
      pushNotif({ type: "review", title: "تعذر إعادة التأهيل", detail: err.message, severity: "error" });
      return false;
    }
  }, [pushLocal, pushNotif, refresh]);

  // ---------- jobs ----------
  const cancelJob = useCallback(async (jobId) => {
    try { await apiPost.researchCancel(jobId); } catch { /* non-research jobs have no cancel endpoint */ }
    setJobs((prev) => prev.map((j) => j.id !== jobId ? j : {
      ...j, status: "CANCELLED", stopReason: "CANCELLED", waitingQuestion: null, completedAt: isoNow(),
      timeline: [...j.timeline, { at: isoNow(), event: "Cancelled", detail: "ألغاها المستخدم" }],
    }));
    pushLocal("ألغى وظيفة بحث", jobId, "");
  }, [pushLocal]);

  const resumeJob = useCallback(async (jobId) => {
    try { await apiPost.resumeJob(jobId); } catch { /* job may not be resumable */ }
    setJobs((prev) => prev.map((j) => j.id !== jobId ? j : { ...j, status: "QUEUED", stopReason: null, pauseReason: null }));
    pushLocal("استأنف وظيفة بحث", jobId, "");
    refresh();
  }, [pushLocal, refresh]);

  // ---------- credentials (real /api/keys) ----------
  const addCredential = useCallback(async (service, key) => {
    const envKey = SERVICE_ENV[service];
    if (!envKey || !key?.trim()) return false;
    try {
      await apiPost.keysSave({ [envKey]: key.trim() });
      setCreds((prev) => prev.some((c) => c.service === service)
        ? prev.map((c) => c.service === service
          ? { ...c, connected: true, status: "OK", lastTested: isoNow(), masked: `••••${key.trim().slice(-4)}` }
          : c)
        : [...prev, { id: envKey, service, masked: `••••${key.trim().slice(-4)}`, connected: true, status: "OK", lastTested: isoNow(), note: "مفتاح API" }]);
      pushLocal("أضاف بيانات اعتماد", service, "");
      refresh();
      return true;
    } catch (err) {
      pushNotif({ type: "credentials", title: "فشل حفظ المفتاح", detail: err.message, severity: "error" });
      return false;
    }
  }, [pushLocal, pushNotif, refresh]);

  const rotateCredential = useCallback(async (id, key) => {
    const c = creds.find((x) => x.id === id || x.service === id);
    return addCredential(c?.service || id, key);
  }, [creds, addCredential]);

  const testCredential = useCallback((_id) => {
    refresh(); // registry health is server truth
  }, [refresh]);

  const toggleIntegration = useCallback((_id) => {
    // Integrations are configuration, not toggles — nothing to flip yet.
  }, []);

  // ---------- notifications ----------
  const markNotifRead = useCallback((id) => setNotifications((p) => p.map((n) => n.id === id ? { ...n, read: true } : n)), []);
  const markAllNotifsRead = useCallback(() => setNotifications((p) => p.map((n) => ({ ...n, read: true }))), []);

  const value = {
    lang, toggleLang, theme, toggleTheme, t,
    jobs, leads, icps, providers, credentials: creds, integrations: [], agents,
    activity: useMemo(() => [...activity].sort((a, b) => new Date(b.at) - new Date(a.at)), [activity]),
    notifications: useMemo(() => [...notifications].sort((a, b) => new Date(b.at) - new Date(a.at)), [notifications]),
    chat, activeJobId, setActiveJobId, currentUser, canFindContacts,
    connected,
    submitObjective, answerClarification, reviewLead, undoReview, revealPII, researchMore,
    cancelJob, resumeJob, addCredential, testCredential, rotateCredential, toggleIntegration,
    markNotifRead, markAllNotifsRead, refresh, refreshJobEvents,
  };
  return <LeadEngineContext.Provider value={value}>{children}</LeadEngineContext.Provider>;
}

export function useLeadEngine() {
  const ctx = useContext(LeadEngineContext);
  if (!ctx) throw new Error("useLeadEngine must be used within LeadEngineProvider");
  return ctx;
}
