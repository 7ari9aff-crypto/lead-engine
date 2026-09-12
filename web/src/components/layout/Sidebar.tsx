import { Link, useLocation } from "wouter";
import {
  LayoutDashboard,
  KeyRound,
  Megaphone,
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
  MessageSquare,
  Activity,
  Building2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUI } from "@/hooks/useTheme";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

// Business-oriented navigation — the user thinks in workspace terms
// (workspace → data → automation → administration), not in internals.
const NAV_SECTIONS = [
  {
    title: "مساحة العمل",
    items: [
      { href: "/", label: "نظرة عامة", icon: LayoutDashboard },
      { href: "/jobs", label: "الحملات", icon: Megaphone },
      { href: "/leads", label: "العملاء المحتملون", icon: Database },
      { href: "/chat", label: "المساعد الذكي", icon: MessageSquare, badge: "AI" },
    ],
  },
  {
    title: "البيانات",
    items: [
      { href: "/verify", label: "فحص الإيميل", icon: MailCheck },
      { href: "/activity", label: "سجل النشاط", icon: Activity },
    ],
  },
  {
    title: "الأنظمة",
    items: [
      { href: "/agents", label: "الوكلاء", icon: Bot },
      { href: "/integrations", label: "التكاملات", icon: Plug },
    ],
  },
  {
    title: "الإدارة",
    items: [
      { href: "/keys", label: "الاستهلاك والمفاتيح", icon: KeyRound },
      { href: "/config", label: "الإعدادات", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const [location] = useLocation();
  const { sidebar, toggleSidebar, setSidebar } = useUI();
  const collapsed = sidebar === "collapsed";
  const [plan, setPlan] = useState<string | null>(null);

  useEffect(() => {
    setSidebar("expanded");
  }, [location, setSidebar]);

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

  // Plan chip for the workspace block (silent fetch — purely cosmetic).
  useEffect(() => {
    apiGet
      .entitlements()
      .then((e: any) => {
        const p = String(e?.plan ?? e?.entitlements?.plan ?? "").toLowerCase();
        if (p) setPlan(p === "free" ? "الخطة المجانية" : p === "pro" ? "خطة Pro" : p);
      })
      .catch(() => {});
  }, []);

  return (
    <>
      {sidebar === "collapsed" && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30 backdrop-blur-sm"
          onClick={() => setSidebar("expanded")}
        />
      )}
      <aside
        className={cn(
          "border-r border-[var(--border)] bg-[var(--bg-elev)] transition-all duration-300 ease-out",
          "flex flex-col h-screen sticky top-0 z-30",
          "fixed left-0 lg:sticky",
          sidebar === "collapsed"
            ? "translate-x-0 lg:w-[70px] w-[280px]"
            : "-translate-x-full lg:translate-x-0 lg:w-[260px]"
        )}
      >
        {/* Workspace switcher */}
        <div className="flex items-center justify-between gap-3 px-4 h-16 border-b border-[var(--border-soft)] shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center justify-center h-9 w-9 rounded-xl bg-[image:var(--gradient)] shadow-md shrink-0">
              <Zap className="h-5 w-5 text-white" />
            </div>
            {!collapsed && (
              <div className="flex flex-col min-w-0">
                <span className="flex items-center gap-1.5 font-semibold text-[14px] leading-tight">
                  <Building2 className="h-3.5 w-3.5 text-[var(--fg-soft)]" />
                  Lead Engine
                </span>
                <span className="text-[11px] text-[var(--fg-soft)] truncate">
                  {plan ?? "مساحة عمل توليد العملاء"}
                </span>
              </div>
            )}
          </div>
          {!collapsed && (
            <button
              onClick={() => setSidebar("collapsed")}
              className="lg:hidden p-1.5 rounded-md text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
              aria-label="إغلاق القائمة"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2.5 space-y-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="space-y-0.5">
              {!collapsed && (
                <div className="px-3 mb-1.5 text-[11px] font-semibold text-[var(--fg-soft)]">
                  {section.title}
                </div>
              )}
              {collapsed && <div className="h-px bg-[var(--border-soft)] mx-2 my-1" />}
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = location === item.href || (item.href !== "/" && location.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 h-9.5 text-[13.5px] font-medium",
                      "transition-all duration-200",
                      active
                        ? "bg-[var(--accent-soft)] text-[var(--accent-hover)]"
                        : "text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-hover)]"
                    )}
                  >
                    {active && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-[var(--accent)]" />
                    )}
                    <Icon className={cn("h-4.5 w-4.5 shrink-0 transition-colors", active && "text-[var(--accent)]")} />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                    {!collapsed && item.badge && (
                      <span className="ms-auto text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-[image:var(--gradient)] text-white">
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-[var(--border-soft)] p-2.5 space-y-0.5 shrink-0">
          {!collapsed && (
            <Link
              href="/pricing"
              className="w-full flex items-center gap-2.5 rounded-md h-8 px-2.5 text-[12.5px] text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
            >
              <Sparkles className="h-3.5 w-3.5" />
              الأسعار والخطط
            </Link>
          )}
          <button
            onClick={toggleSidebar}
            className="w-full flex items-center justify-center gap-2 h-8 rounded-md text-[12.5px] text-[var(--fg-soft)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
          >
            {collapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {!collapsed && <span>طيّ القائمة</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
