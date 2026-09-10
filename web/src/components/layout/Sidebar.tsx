import { Link, useLocation } from "wouter";
import {
  LayoutDashboard,
  KeyRound,
  Boxes,
  PlayCircle,
  Database,
  MailCheck,
  Bot,
  Settings,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUI } from "@/hooks/useTheme";

const NAV = [
  { href: "/", label: "نظرة عامة", icon: LayoutDashboard },
  { href: "/chat", label: "المساعد الذكي", icon: Bot, badge: "AI" },
  { href: "/keys", label: "مفاتيح API", icon: KeyRound },
  { href: "/providers", label: "المزوّدون", icon: Boxes },
  { href: "/jobs", label: "المهام", icon: PlayCircle },
  { href: "/leads", label: "النتائج", icon: Database },
  { href: "/verify", label: "فحص إيميل", icon: MailCheck },
  { href: "/config", label: "الإعدادات", icon: Settings },
];

export function Sidebar() {
  const [location] = useLocation();
  const { sidebar, toggleSidebar } = useUI();
  const collapsed = sidebar === "collapsed";

  return (
    <aside
      className={cn(
        "glass border-l border-[var(--border)] transition-all duration-300 ease-out",
        "flex flex-col h-screen sticky top-0 z-30",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-[var(--border-soft)]">
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
                <span className="absolute right-0 top-1.5 bottom-1.5 w-[3px] rounded-l-full bg-[var(--accent)]" />
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
      <div className="border-t border-[var(--border-soft)] p-3">
        {!collapsed && (
          <div className="mb-2 rounded-lg p-3 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
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
  );
}
