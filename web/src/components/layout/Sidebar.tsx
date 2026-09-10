import { Link, useLocation } from "wouter";
import {
  LayoutDashboard,
  KeyRound,
  Boxes,
  PlayCircle,
  Database,
  MailCheck,
  Settings,
  Bot,
  Plug,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Zap,
  X,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUI } from "@/hooks/useTheme";
import { useEffect } from "react";

const NAV = [
  { href: "/", label: "نظرة عامة", icon: LayoutDashboard },
  { href: "/chat", label: "المساعد الذكي", icon: Bot, badge: "AI" },
  { href: "/keys", label: "مفاتيح API", icon: KeyRound },
  { href: "/providers", label: "المزوّدون", icon: Boxes },
  { href: "/jobs", label: "المهام", icon: PlayCircle },
  { href: "/leads", label: "النتائج", icon: Database },
  { href: "/verify", label: "فحص إيميل", icon: MailCheck },
  { href: "/config", label: "الإعدادات", icon: Settings },
  { href: "/integrations", label: "التكاملات و MCP", icon: Plug },
  { href: "/agents", label: "الوكلاء", icon: Bot },
];

const EXTERNAL = [
  { href: "/welcome", label: "صفحة الترحيب", icon: Sparkles },
  { href: "/pricing", label: "الأسعار", icon: KeyRound },
  { href: "/docs", label: "التوثيق", icon: BookOpen },
];

export function Sidebar() {
  const [location] = useLocation();
  const { sidebar, toggleSidebar, setSidebar } = useUI();
  const collapsed = sidebar === "collapsed";

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebar("expanded");
  }, [location, setSidebar]);

  // Lock body scroll when mobile sidebar is open
  useEffect(() => {
    if (window.innerWidth < 1024 && sidebar === "collapsed") {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [sidebar]);

  return (
    <>
      {/* Mobile backdrop */}
      {sidebar === "collapsed" && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30 backdrop-blur-sm"
          onClick={() => setSidebar("expanded")}
        />
      )}
      <aside
        className={cn(
          "glass border-r border-[var(--border)] transition-all duration-300 ease-out",
          "flex flex-col h-screen sticky top-0 z-30",
          "fixed left-0 lg:sticky",
          sidebar === "collapsed"
            ? "translate-x-0 lg:w-[68px] w-[280px]"
            : "-translate-x-full lg:translate-x-0 lg:w-[240px]"
        )}
      >
      {/* Brand */}
      <div className="flex items-center justify-between gap-3 px-4 h-16 border-b border-[var(--border-soft)]">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-[image:var(--gradient)] shadow-md">
            <Zap className="h-5 w-5 text-white" />
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-semibold text-sm gradient-text">محرك الـLeads</span>
              <span className="text-[10px] text-[var(--fg-soft)]">v1.0 — RTL</span>
            </div>
          )}
        </div>
        {/* Mobile close button */}
        {!collapsed && (
          <button
            onClick={() => setSidebar("collapsed")}
            className="lg:hidden p-1.5 rounded-md text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)]"
            aria-label="إغلاق القائمة"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = location === item.href || (item.href !== "/" && location.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 h-10 text-sm font-medium",
                "transition-all duration-200",
                active
                  ? "bg-[var(--accent-soft)] text-[var(--accent-hover)]"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-hover)]"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-[var(--accent)]" />
              )}
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
              {!collapsed && item.badge && (
                <span className="ms-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-soft)] text-[var(--accent-hover)]">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--border-soft)] p-3 space-y-1">
        {!collapsed && EXTERNAL.map((e) => {
          const Icon = e.icon;
          return (
            <Link
              key={e.href}
              href={e.href}
              className="w-full flex items-center gap-2.5 rounded-md h-8 px-2.5 text-xs text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
            >
              <Icon className="h-3.5 w-3.5" />
              {e.label}
            </Link>
          );
        })}
        {!collapsed && (
          <div className="my-2 rounded-lg p-2.5 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
            <div className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span>نظام ذكي واعي بالحصص</span>
            </div>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center gap-2 h-8 rounded-md text-xs text-[var(--fg-soft)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)]"
        >
          {collapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {!collapsed && <span>طيّ القائمة</span>}
        </button>
      </div>
    </aside>
    </>
  );
}
