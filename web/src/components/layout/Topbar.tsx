import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "wouter";
import {
  Sun, Moon, RefreshCw, WifiOff, Menu, Search, Zap, LogOut,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useUI } from "@/hooks/useTheme";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

const PAGE_TITLES: Record<string, string> = {
  "/": "نظرة عامة",
  "/chat": "المساعد الذكي",
  "/jobs": "الحملات",
  "/leads": "العملاء المحتملون",
  "/verify": "فحص الإيميل",
  "/keys": "الاستهلاك والمفاتيح",
  "/integrations": "التكاملات",
  "/agents": "الوكلاء",
  "/activity": "سجل النشاط",
  "/config": "الإعدادات",
};

const NAV_PATHS = [
  "/", "/chat", "/jobs", "/leads", "/verify", "/keys",
  "/integrations", "/agents", "/activity", "/config",
];

export function Topbar() {
  const { theme, toggleTheme, sidebar, setSidebar } = useUI();
  const qc = useQueryClient();
  const [location] = useLocation();
  const { data: usage } = useLiveData<any>(() => apiGet.keysUsage(), 60000);
  const { error } = useLiveData(() => apiGet.status(), 15000);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // One quiet usage chip — the details live in the Consumption page.
  const usageRows: any[] = usage?.providers ?? [];
  const quotaPercents = usageRows
    .map((p: any) => p.live?.percent ?? p.quota?.percent)
    .filter((x: any): x is number => x != null);
  const maxQuota = quotaPercents.length ? Math.max(...quotaPercents) : null;
  const quotaTone =
    maxQuota == null ? "var(--fg-muted)" :
    maxQuota >= 85 ? "var(--danger)" :
    maxQuota >= 60 ? "var(--warn)" : "var(--success)";

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV_PATHS;
    return NAV_PATHS.filter((p) => (PAGE_TITLES[p] ?? "").toLowerCase().includes(q));
  }, [query]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
        setOpen(true);
      }
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function go(href: string) {
    setOpen(false);
    setQuery("");
    window.location.assign(href);
  }

  return (
    <header className="sticky top-0 z-20 glass border-b border-[var(--border)] h-14 flex items-center px-4 gap-3 shrink-0">
      <Button
        size="icon-sm"
        variant="ghost"
        onClick={() => setSidebar(sidebar === "expanded" ? "collapsed" : "expanded")}
        className="lg:hidden"
        title="القائمة"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Page title */}
      <h2 className="text-[15px] font-bold shrink-0 hidden sm:block">
        {PAGE_TITLES[location] ?? "Lead Engine"}
      </h2>

      {/* Command search — centered */}
      <div className="relative hidden md:block w-full max-w-sm mx-auto" dir="rtl">
        <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)] pointer-events-none" />
        <input
          ref={searchRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) go(results[0]);
          }}
          placeholder="ابحث عن صفحة…  Ctrl K"
          className="w-full h-8.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] pr-9 pl-12 text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-soft)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-colors"
        />
        <kbd className="absolute left-2.5 top-1/2 -translate-y-1/2 hidden lg:inline-flex items-center h-5 px-1.5 rounded border border-[var(--border)] bg-[var(--bg-elev)] text-[10px] font-mono text-[var(--fg-soft)]">
          ⌘K
        </kbd>
        {open && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
            <div className="absolute top-full mt-1.5 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow-lg)] z-40 overflow-hidden animate-scale-in">
              {results.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-[var(--fg-muted)]">لا نتائج مطابقة</div>
              ) : (
                <ul className="py-1.5 max-h-72 overflow-y-auto">
                  {results.map((p) => (
                    <li key={p}>
                      <button
                        onClick={() => go(p)}
                        className="w-full flex items-center gap-2.5 px-3.5 h-9 text-[13px] text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                      >
                        <Zap className="h-3.5 w-3.5 text-[var(--fg-soft)]" />
                        {PAGE_TITLES[p]}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>

      {/* Right: one usage chip + actions */}
      <div className="ms-auto flex items-center gap-1.5 shrink-0">
        {error ? (
          <span className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--danger)]/40 bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-[12.5px] font-medium text-[var(--danger)]">
            <WifiOff className="h-3.5 w-3.5" />
            غير متصل
          </span>
        ) : maxQuota != null ? (
          <button
            onClick={() => window.location.assign("/keys")}
            className="hidden sm:flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] text-[12.5px] font-medium text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--border)] transition-colors"
            title="أعلى استهلاك حصة بين المزودين — التفاصيل في صفحة الاستهلاك"
          >
            <Zap className="h-3.5 w-3.5" style={{ color: quotaTone }} />
            <span className="tnum font-semibold" style={{ color: quotaTone }}>{maxQuota}%</span>
            <span>من الحصص</span>
          </button>
        ) : null}

        <Button size="icon-sm" variant="ghost" onClick={() => qc.invalidateQueries()} title="تحديث الآن">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={toggleTheme} title={theme === "dark" ? "وضع نهاري" : "وضع ليلي"}>
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          title="تسجيل الخروج"
          onClick={async () => {
            try { await supabase.auth.signOut(); } catch { /* local mode */ }
            try { await apiPost.logout(); } catch { /* best effort */ }
            window.location.assign("/login");
          }}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
