import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "wouter";
import {
  Sun, Moon, RefreshCw, Activity, Wifi, WifiOff, Menu, Search, Zap, LogOut,
  LayoutDashboard, MessageSquare, KeyRound, PlayCircle, Database,
  MailCheck, Settings, Bot, Plug,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useUI } from "@/hooks/useTheme";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

const PAGES = [
  { href: "/", label: "نظرة عامة", icon: LayoutDashboard },
  { href: "/chat", label: "المساعد الذكي", icon: MessageSquare },
  { href: "/jobs", label: "المهام", icon: PlayCircle },
  { href: "/leads", label: "النتائج", icon: Database },
  { href: "/verify", label: "فحص إيميل", icon: MailCheck },
  { href: "/keys", label: "المفاتيح والمزودون", icon: KeyRound },
  { href: "/integrations", label: "التكاملات و MCP", icon: Plug },
  { href: "/agents", label: "الوكلاء", icon: Bot },
  { href: "/config", label: "الإعدادات", icon: Settings },
];

export function Topbar() {
  const { theme, toggleTheme, sidebar, setSidebar } = useUI();
  const qc = useQueryClient();
  const [, navigate] = useLocation();
  const { data, error, loading } = useLiveData(() => apiGet.status(), 5000);
  const { data: usage } = useLiveData<any>(() => apiGet.keysUsage(), 60000);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const totalLeads = data?.leads_total ?? 0;
  const activeJobs = data?.recent_jobs?.filter((j) => ["RUNNING", "QUEUED", "RESUMING"].includes(j.state)).length ?? 0;
  const healthy = (data?.providers ?? []).filter((p) => p.status === "active").length;
  const totalProviders = (data?.providers ?? []).length || 0;

  // Persistent usage meter (Apollo-style topbar counter)
  const usageRows: any[] = usage?.providers ?? [];
  const activeKeys = usageRows.reduce((n: number, p: any) => n + (p.keys_configured || 0), 0);
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
    if (!q) return PAGES;
    return PAGES.filter((p) => p.label.toLowerCase().includes(q) || p.href.includes(q));
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
    navigate(href);
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

      {/* Command search — navigates anywhere */}
      <div className="relative hidden sm:block w-full max-w-sm mx-auto" dir="rtl">
        <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)] pointer-events-none" />
        <input
          ref={searchRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) go(results[0].href);
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
                  {results.map((p) => {
                    const Icon = p.icon;
                    return (
                      <li key={p.href}>
                        <button
                          onClick={() => go(p.href)}
                          className="w-full flex items-center gap-2.5 px-3.5 h-9 text-[13px] text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                        >
                          <Icon className="h-4 w-4 text-[var(--fg-soft)]" />
                          {p.label}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </>
        )}
      </div>

      {/* Live stats */}
      <div className={cn(
        "ms-auto flex items-center gap-2.5",
        loading ? "opacity-60" : ""
      )}>
        <div className="hidden md:flex items-center gap-2.5 text-xs text-[var(--fg-muted)]">
          <span className="flex items-center gap-1.5 tnum">
            <Activity className="h-3.5 w-3.5 text-[var(--accent)]" />
            {activeJobs} <span>مهام نشطة</span>
          </span>
          <span className="text-[var(--border)]">·</span>
          <span className="flex items-center gap-1.5 tnum">
            <span className="font-semibold text-[var(--fg)]">{totalLeads}</span>
            <span>عميل محتمل</span>
          </span>
          <span className="text-[var(--border)]">·</span>
          <span className="flex items-center gap-1.5 tnum">
            <span className="font-semibold text-[var(--success)]">{healthy}</span>
            <span>من {totalProviders} مزوّد</span>
          </span>
          {maxQuota != null && (
            <>
              <span className="text-[var(--border)]">·</span>
              <button
                onClick={() => navigate("/keys")}
                className="flex items-center gap-1.5 tnum hover:text-[var(--fg)] transition-colors"
                title="أعلى استهلاك حصة بين المزودين — اضغط للتفاصيل"
              >
                <Zap className="h-3.5 w-3.5" style={{ color: quotaTone }} />
                <span className="font-semibold" style={{ color: quotaTone }}>{maxQuota}%</span>
                <span>من الحصص</span>
                <span className="text-[var(--border)]">·</span>
                <span className="tnum">{activeKeys} مفتاح</span>
              </button>
            </>
          )}
        </div>

        {loading ? (
          <Badge variant="default" className="gap-1.5">
            <RefreshCw className="h-3 w-3 animate-spin" />
            يتحدّث
          </Badge>
        ) : error ? (
          <Badge variant="danger" className="gap-1.5">
            <WifiOff className="h-3 w-3" />
            غير متصل
          </Badge>
        ) : (
          <Badge variant="success" className="gap-1.5" title="الاتصال بالسيرفر سليم">
            <Wifi className="h-3 w-3" />
            متصل
          </Badge>
        )}

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
