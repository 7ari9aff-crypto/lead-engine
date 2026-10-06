import React, { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import {
  LayoutDashboard, MessageSquare, Radar, Target, Building2, ClipboardCheck,
  BarChart3, Activity as ActivityIcon, Server, KeyRound, Blocks, Bot, Settings,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";

const NAV = [
  { group: "nav.commandCenter", items: [{ to: "/", label: "nav.commandCenter", icon: LayoutDashboard, end: true }] },
  {
    group: "nav.research", items: [
      { to: "/chat", label: "nav.chat", icon: MessageSquare },
      { to: "/jobs", label: "nav.jobs", icon: Radar },
      { to: "/icp", label: "nav.icp", icon: Target },
    ],
  },
  {
    group: "nav.leads", items: [
      { to: "/leads", label: "nav.allLeads", icon: Building2 },
      { to: "/review", label: "nav.review", icon: ClipboardCheck },
    ],
  },
  {
    group: "nav.intelligence", items: [
      { to: "/analytics", label: "nav.analytics", icon: BarChart3 },
      { to: "/activity", label: "nav.activity", icon: ActivityIcon },
    ],
  },
  {
    group: "nav.system", items: [
      { to: "/providers", label: "nav.providers", icon: Server },
      { to: "/credentials", label: "nav.credentials", icon: KeyRound },
      { to: "/integrations", label: "nav.integrations", icon: Blocks },
    ],
  },
  {
    group: "nav.admin", items: [
      { to: "/agents", label: "nav.agents", icon: Bot },
      { to: "/settings", label: "nav.settings", icon: Settings },
    ],
  },
];

export default function Layout({ children, collapsed, onToggleCollapse }) {
  const { t, lang, leads } = useLeadEngine();
  // badge = leads that actually wait for the user's decision
  const reviewCount = leads.filter((l) => l.status === "READY_FOR_REVIEW").length;
  const ar = lang === "ar";

  const SidebarInner = (
    <div className="flex flex-col h-full">
      {/* brand */}
      <div className="px-4 h-16 flex items-center gap-2.5 border-b border-[hsl(var(--sidebar-border))]">
        <div className="w-8 h-8 rounded-lg bg-[hsl(var(--sidebar-primary))] text-[hsl(var(--sidebar-primary-foreground))] grid place-items-center font-mono text-[11px] font-semibold tracking-tight">
          LE
        </div>
        <div className={cn("leading-tight transition-all", collapsed && "lg:hidden")}>
          <div className="text-[15px] font-display font-semibold text-white tracking-tight">Lead Engine</div>
          <div className="text-[10px] text-[hsl(var(--sidebar-foreground))]">{t("app.tagline")}</div>
        </div>
      </div>

      {/* nav */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4 space-y-5">
        {NAV.map((section) => (
          <div key={section.group}>
            <div className={cn("px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[hsl(var(--sidebar-foreground))] opacity-85", collapsed && "lg:hidden")}>
              {t(section.group)}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  aria-label={t(item.label)}
                  to={item.to}
                  end={item.end}
                  title={t(item.label)}
                  className={({ isActive }) => cn(
                    "group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-all relative",
                    collapsed && "lg:justify-center",
                    isActive
                      ? "bg-[hsl(var(--sidebar-accent))] text-white font-medium shadow-[inset_3px_0_0_hsl(var(--sidebar-primary))]"
                      : "text-[hsl(var(--sidebar-foreground))] hover:bg-white/5 hover:text-white"
                  )}
                >
                  <item.icon className="w-[18px] h-[18px] shrink-0" />
                  <span className={cn("truncate", collapsed && "lg:hidden")}>{t(item.label)}</span>
                  {item.to === "/review" && reviewCount > 0 && (
                    <span className="ms-auto me-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[hsl(var(--danger))] text-white text-[10px] font-semibold grid place-items-center tnum">{reviewCount}</span>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* footer */}
      <div className={cn("px-3 py-3 border-t border-[hsl(var(--sidebar-border))]", collapsed && "lg:px-2")}>
        <button
          onClick={onToggleCollapse}
          className="hidden lg:flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-xs text-[hsl(var(--sidebar-foreground))] hover:bg-white/5 hover:text-white transition"
        >
          {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          {!collapsed && <span>{ar ? "طي القائمة" : "Collapse"}</span>}
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* sidebar — desktop */}
      <aside className={cn("hidden lg:flex flex-col bg-[hsl(var(--sidebar-background))] transition-all duration-300 shrink-0", collapsed ? "lg:w-[72px]" : "lg:w-60")}>
        {SidebarInner}
      </aside>

      {/* sidebar — mobile drawer handled in Topbar via portal-less fixed panel */}
      <MobileSidebar>{SidebarInner}</MobileSidebar>

      {/* main */}
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
    </div>
  );
}

function MobileSidebar({ children }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  React.useEffect(() => { setOpen(false); }, [location.pathname]);
  // expose toggle via window event
  React.useEffect(() => {
    const handler = () => setOpen((o) => !o);
    window.addEventListener("leadengine:toggleSidebar", handler);
    return () => window.removeEventListener("leadengine:toggleSidebar", handler);
  }, []);
  if (!open) return null;
  return (
    <div className="lg:hidden fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50 animate-fade-in" onClick={() => setOpen(false)} />
      <aside className="absolute top-0 bottom-0 start-0 w-64 bg-[hsl(var(--sidebar-background))] animate-slide-up">{children}</aside>
    </div>
  );
}