import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { NotificationPanel } from "./NotificationPanel";
import { Menu, Search, Globe, Bell, Sun, Moon } from "lucide-react";

export function Topbar({ onMenu }) {
  const { t, lang, toggleLang, theme, toggleTheme, notifications, currentUser, leads, jobs } = useLeadEngine();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [showNotif, setShowNotif] = useState(false);
  const unread = notifications.filter((n) => !n.read).length;

  const q = query.trim().toLowerCase();
  const leadHits = q
    ? leads.filter((l) => l.company.name.toLowerCase().includes(q) || (l.company.domain || "").includes(q))
        .slice(0, 4).map((l) => ({ type: "lead", id: l.id, label: l.company.name, sub: l.company.domain, to: `/leads/${l.id}` }))
    : [];
  const jobHits = q
    ? jobs.filter((j) => j.id.toLowerCase().includes(q) || (j.objective || "").toLowerCase().includes(q))
        .slice(0, 3).map((j) => ({ type: "job", id: j.id, label: (j.objective || j.id).slice(0, 60), sub: j.id, to: `/jobs/${j.id}` }))
    : [];
  const results = [...leadHits, ...jobHits];

  return (
    <header className="h-16 shrink-0 border-b border-border bg-card/80 backdrop-blur-sm flex items-center gap-3 px-4 lg:px-6">
      <button onClick={onMenu} className="lg:hidden p-2 rounded-lg hover:bg-muted transition" aria-label={lang === "ar" ? "القائمة" : "Menu"}>
        <Menu className="w-5 h-5" />
      </button>

      <div className="relative flex-1 max-w-xl">
        <div className="relative">
          <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-4 h-4 text-muted-foreground" />
          <input dir="auto"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); }}
            aria-label={lang === "ar" ? "بحث" : "Search"}
            placeholder={lang === "ar" ? "ابحث عن عميل أو وظيفة…" : "Search leads or jobs…"}
            className="w-full h-9 ps-9 pe-3 rounded-lg border border-input bg-background text-sm focus-ring placeholder:text-muted-foreground"
          />
        </div>
        {q && results.length === 0 && (
          <div className="absolute top-full mt-1 inset-x-0 card-surface p-3 z-40 text-sm text-muted-foreground">{lang === "ar" ? "لا نتائج مطابقة." : "No matches."}</div>
        )}
        {results.length > 0 && (
          <div className="absolute top-full mt-1 inset-x-0 card-surface p-1.5 z-40 animate-scale-in max-h-96 overflow-y-auto scrollbar-thin">
            {results.map((r) => (
              <button
                key={`${r.type}-${r.id}`}
                onClick={() => { navigate(r.to); setQuery(""); }}
                className="w-full flex items-center gap-2 rounded-md px-2.5 py-2 text-sm hover:bg-muted transition text-start"
              >
                <span className="w-auto h-6 px-1.5 rounded-md grid place-items-center text-[10px] font-medium bg-secondary text-muted-foreground shrink-0">
                  {r.type === "lead" ? (lang === "ar" ? "عميل" : "Lead") : (lang === "ar" ? "وظيفة" : "Job")}
                </span>
                <span className="min-w-0">
                  <span className="block font-medium truncate">{r.label}</span>
                  <span className="block text-[11px] text-muted-foreground truncate">{r.sub}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="ms-auto flex items-center gap-1.5">
        <button onClick={toggleTheme} className="h-9 w-9 grid place-items-center rounded-lg border border-border hover:bg-muted transition" aria-label={lang === "ar" ? "تبديل المظهر" : "Toggle theme"} title={theme === "dark" ? (lang === "ar" ? "الوضع الفاتح" : "Light mode") : (lang === "ar" ? "الوضع الداكن" : "Dark mode")}>
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        <button onClick={toggleLang} aria-label={lang === "ar" ? "Switch to English" : "التبديل إلى العربية"} className="h-9 px-3 inline-flex items-center gap-1.5 rounded-lg border border-border text-sm font-medium hover:bg-muted transition">
          <Globe className="w-4 h-4" />
          <span>{lang === "ar" ? "EN" : "ع"}</span>
        </button>

        <div className="relative">
          <button onClick={() => setShowNotif((s) => !s)} aria-label={`${lang === "ar" ? "الإشعارات" : "Notifications"}${unread ? ` (${unread})` : ""}`} className="h-9 w-9 grid place-items-center rounded-lg border border-border hover:bg-muted transition relative">
            <Bell className="w-4 h-4" />
            {unread > 0 && <span className="absolute -top-1 -end-1 min-w-[16px] h-4 px-1 rounded-full bg-[hsl(var(--danger))] text-white text-[10px] font-semibold grid place-items-center tnum">{unread}</span>}
          </button>
          {showNotif && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowNotif(false)} />
              <NotificationPanel onClose={() => setShowNotif(false)} />
            </>
          )}
        </div>

        <div className="ms-1 flex items-center gap-2 ps-2">
          <div className="w-8 h-8 rounded-full bg-secondary border border-border grid place-items-center text-foreground text-xs font-semibold">
            {currentUser.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
          </div>
          <div className="hidden sm:block leading-tight">
            <div className="text-xs font-medium">{currentUser.name}</div>
            <div className="text-[10px] text-muted-foreground">{currentUser.role === "admin" ? (lang === "ar" ? "مدير" : "Admin") : (lang === "ar" ? "عضو" : "Member")} · {currentUser.organization}</div>
          </div>
        </div>
      </div>
    </header>
  );
}