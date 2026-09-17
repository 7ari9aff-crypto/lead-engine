import { useEffect, useState, useSyncExternalStore } from "react";
import { useLocation } from "wouter";
import {
  Sun, Moon, RefreshCw, WifiOff, Menu, Search, Zap, LogOut, Settings2, Globe, Radio,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useUI } from "@/hooks/useTheme";
import { useLanguage } from "@/hooks/useLanguage";
import { useInstantQuery } from "@/hooks/useInstantQuery";
import { apiGet, apiPost, type StatusResponse } from "@/lib/api";
import { liveStore } from "@/lib/liveStore";
import { signOut } from "@/lib/supabase";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

const PAGE_TITLES: Record<string, string> = {
  "/": "مركز القيادة",
  "/analytics": "التحليلات",
  "/chat": "المساعد الذكي",
  "/jobs": "الحملات",
  "/leads": "العملاء المحتملون",
  "/research": "مهام البحث",
  "/review": "لوحة المراجعة",
  "/verify": "فحص الإيميل",
  "/keys": "الاستهلاك والمفاتيح",
  "/integrations": "التكاملات",
  "/agents": "الوكلاء",
  "/activity": "سجل النشاط",
  "/icp": "معايير الفلترة (ICP)",
  "/config": "الإعدادات",
};

import { CommandPalette } from "./CommandPalette";

export function Topbar() {
  const { theme, toggleTheme, sidebar, setSidebar } = useUI();
  const { lang, toggleLang } = useLanguage();
  const qc = useQueryClient();
  const [location] = useLocation();
  const { data: session, error } = useInstantQuery<{ authenticated: boolean; mode?: string }>(
    ["authSession"],
    () => apiGet.authSession(),
    { instant: false, staleTime: 60_000, retry: 0 }
  );
  // Shared, already-live status cache (the SSE bridge writes into it) — the
  // topbar never opens its own heavy endpoint (the old topbar polled
  // /api/keys/usage every page, which makes outbound provider calls).
  const { data: status } = useInstantQuery<StatusResponse>(["status"], () => apiGet.status(), {
    staleTime: 5_000,
  });
  const live = useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshotState);
  const needsSetup = !error && session?.mode === "closed";
  const [paletteOpen, setPaletteOpen] = useState(false);

  // One quiet usage chip — the details live in the Consumption page.
  const quotaPercents = (status?.providers ?? [])
    .map((p) =>
      p.quota_limit ? Math.min(100, Math.round((100 * (p.quota_used || 0)) / p.quota_limit)) : null
    )
    .filter((x): x is number => x != null && Number.isFinite(x));
  const maxQuota = quotaPercents.length ? Math.max(...quotaPercents) : null;
  const quotaTone =
    maxQuota == null ? "var(--fg-muted)" :
    maxQuota >= 85 ? "var(--danger)" :
    maxQuota >= 60 ? "var(--warn)" : "var(--success)";

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
        <button
          onClick={() => setPaletteOpen(true)}
          className="w-full h-9 py-1.5 px-3 rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] text-right flex items-center justify-between text-[13px] text-[var(--fg-soft)] hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer group shadow-xs"
        >
          <div className="flex items-center gap-2.5">
            <Search className="h-4 w-4 text-[var(--fg-soft)] group-hover:text-[var(--accent)] transition-colors" />
            <span className="group-hover:text-[var(--fg)] transition-colors">ابحث عن صفحة، عميل، أو إجراء…</span>
          </div>
          <kbd className="inline-flex items-center h-5 px-2 rounded-md border border-[var(--border)] bg-[var(--bg-elev)] text-[11px] font-mono text-[var(--fg-muted)] group-hover:border-[var(--accent)] transition-colors">
            Ctrl K
          </kbd>
        </button>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {/* Right: one usage chip + actions */}
      <div className="ms-auto flex items-center gap-1.5 shrink-0">
        {needsSetup ? (
          <span
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--warn)]/50 bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] text-[12.5px] font-medium text-[var(--warn)]"
            title="المنصة في وضع مقفول لحد ما متغيرات البيئة تتضبط على الاستضافة: SUPABASE_URL و SUPABASE_DB_URL و LEAD_ENGINE_ORG_ID و LEAD_ENGINE_ENCRYPTION_KEY ومفاتيح المزودين — ثم أعد النشر"
          >
            <Settings2 className="h-3.5 w-3.5" />
            محتاجة ضبط أول مرة
          </span>
        ) : error ? (
          <span className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--danger)]/40 bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-[12.5px] font-medium text-[var(--danger)]">
            <WifiOff className="h-3.5 w-3.5" />
            غير متصل
          </span>
        ) : (
          <>
            <button
              onClick={() => liveStore.refresh()}
              className={cn(
                "hidden sm:flex items-center gap-1.5 h-8 px-2.5 rounded-lg border text-[12px] font-medium transition-colors",
                live.state === "live"
                  ? "border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_10%,transparent)] text-[var(--success)]"
                  : "border-[var(--border-soft)] bg-[var(--bg-soft)] text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
              title={
                live.state === "live"
                  ? "متصل مباشرًا — التحديثات توصلك لحظيًا"
                  : live.state === "connecting"
                  ? "جارٍ فتح الاتصال المباشر…"
                  : "التحديث بالاستطلاع (اتصال مباشر غير متاح) — اضغط للمحاولة"
              }
            >
              <span className="relative flex h-2 w-2">
                {live.state === "live" && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--success)] opacity-60" />
                )}
                <span
                  className={cn(
                    "relative inline-flex rounded-full h-2 w-2",
                    live.state === "live" ? "bg-[var(--success)]" : "bg-[var(--fg-soft)]"
                  )}
                />
              </span>
              {live.state === "live" ? "مباشر" : live.state === "connecting" ? "اتصال…" : "تحديث"}
              <Radio className="h-3 w-3 opacity-70" />
            </button>
            {maxQuota != null && (
              <button
                onClick={() => window.location.assign("/keys")}
                className="hidden sm:flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] text-[12.5px] font-medium text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--border)] transition-colors"
                title="أعلى استهلاك حصة بين المزودين — التفاصيل في صفحة الاستهلاك"
              >
                <Zap className="h-3.5 w-3.5" style={{ color: quotaTone }} />
                <span className="tnum font-semibold" style={{ color: quotaTone }}>{maxQuota}%</span>
                <span>من الحصص</span>
              </button>
            )}
          </>
        )}

        <Button size="icon-sm" variant="ghost" onClick={() => qc.invalidateQueries()} title="تحديث الآن">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={toggleLang}
          className="text-xs h-8 px-2.5 font-medium gap-1 text-[var(--fg-soft)] hover:text-[var(--fg)] border border-[var(--border-soft)] hover:border-[var(--border)]"
          title={lang === "ar" ? "Switch interface to English" : "تحويل الواجهة للعربية"}
        >
          <Globe className="h-3.5 w-3.5 text-[var(--accent)]" />
          <span className="font-semibold">{lang === "ar" ? "EN" : "عربي"}</span>
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={toggleTheme} title={theme === "dark" ? "وضع نهاري" : "وضع ليلي"}>
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          title="تسجيل الخروج"
          onClick={async () => {
            try { await signOut(); } catch { /* local mode */ }
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
