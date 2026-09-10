import { Sun, Moon, RefreshCw, Activity, Wifi, WifiOff, Menu } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { useUI } from "@/hooks/useTheme";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet } from "@/lib/api";
import { relativeTime } from "@/lib/utils";
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
    <header className="sticky top-0 z-20 glass border-b border-[var(--border)] h-16 flex items-center px-4 gap-3">
      {/* Mobile menu button */}
      <Button
        size="icon-sm"
        variant="ghost"
        onClick={() => setSidebar(sidebar === "expanded" ? "collapsed" : "expanded")}
        className="lg:hidden"
        title="القائمة"
      >
        <Menu className="h-5 w-5" />
      </Button>

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
            <Wifi className="h-3 w-3" />
            متصل
          </Badge>
        )}
      </div>

      <div className="hidden md:flex items-center gap-2 text-xs text-[var(--fg-muted)]">
        <Activity className="h-3.5 w-3.5" />
        <span>{activeJobs} مهمة نشطة</span>
        <span className="text-[var(--fg-soft)]">·</span>
        <span>{totalLeads} ليد</span>
        <span className="text-[var(--fg-soft)]">·</span>
        <span>
          {healthy}/{totalProviders} مزوّد صحّي
        </span>
      </div>

      <div className="ms-auto flex items-center gap-2">
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
