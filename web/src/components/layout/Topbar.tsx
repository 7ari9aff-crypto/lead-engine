import { Sun, Moon, RefreshCw, Activity, Wifi, WifiOff, Menu, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useUI } from "@/hooks/useTheme";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

export function Topbar() {
  const { theme, toggleTheme, sidebar, setSidebar } = useUI();
  const qc = useQueryClient();
  const { data, error, loading } = useLiveData(() => apiGet.status(), 5000);

  const totalLeads = data?.leads_total ?? 0;
  const activeJobs = data?.recent_jobs?.filter((j) => ["RUNNING", "QUEUED", "RESUMING"].includes(j.state)).length ?? 0;
  const healthy = (data?.providers ?? []).filter((p) => p.status === "active").length;
  const totalProviders = (data?.providers ?? []).length || 0;

  return (
    <header className="sticky top-0 z-20 glass border-b border-[var(--border)] h-16 flex items-center px-4 gap-3 shrink-0">
      <Button
        size="icon-sm"
        variant="ghost"
        onClick={() => setSidebar(sidebar === "expanded" ? "collapsed" : "expanded")}
        className="lg:hidden"
        title="القائمة"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Status pill */}
      <div className="flex items-center gap-2">
        {loading ? (
          <Badge variant="default" className="gap-1.5">
            <RefreshCw className="h-3 w-3 animate-spin" />
            يتحدّث…
          </Badge>
        ) : error ? (
          <Badge variant="danger" className="gap-1.5">
            <WifiOff className="h-3 w-3" />
            غير متصل
          </Badge>
        ) : (
          <Badge variant="success" className="gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--success)] opacity-60 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--success)]" />
            </span>
            متصل
          </Badge>
        )}
      </div>

      {/* Stats */}
      <div className="hidden md:flex items-center gap-2.5 text-xs text-[var(--fg-muted)]">
        <div className="flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5 text-[var(--accent)]" />
          <span className="font-medium">{activeJobs}</span>
          <span>مهمة نشطة</span>
        </div>
        <span className="text-[var(--border)]">·</span>
        <div className="flex items-center gap-1.5">
          <span className="font-medium">{totalLeads}</span>
          <span>ليد</span>
        </div>
        <span className="text-[var(--border)]">·</span>
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-[var(--success)]">{healthy}</span>
          <span>/ {totalProviders} مزوّد</span>
        </div>
      </div>

      {/* Search */}
      <div className="hidden lg:flex items-center mx-auto max-w-xs flex-1">
        <div className="relative w-full">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)] pointer-events-none" />
          <input
            type="text"
            placeholder="بحث سريع…"
            className="w-full h-9 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] pr-9 pl-3 text-sm text-[var(--fg)] placeholder:text-[var(--fg-soft)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-colors"
          />
        </div>
      </div>

      <div className="ms-auto flex items-center gap-1.5">
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={() => qc.invalidateQueries()}
          title="تحديث الآن"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={toggleTheme}
          title={theme === "dark" ? "وضع نهاري" : "وضع ليلي"}
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
