import { useState, useEffect, useMemo, useRef } from "react";
import { useLocation } from "wouter";
import {
  Search,
  Database,
  LayoutDashboard,
  Sparkles,
  Briefcase,
  Key,
  ShieldAlert,
  Settings,
  Download,
  MailCheck,
  Sun,
  Moon,
  ExternalLink,
  ArrowRight,
  Command,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiGet, type LeadRow } from "@/lib/api";

type CommandItem = {
  id: string;
  title: string;
  subtitle?: string;
  category: "تنقل" | "إجراءات" | "عملاء";
  icon: React.ReactNode;
  action: () => void;
};

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const [, setLocation] = useLocation();

  // Load leads once for quick search
  useEffect(() => {
    if (open) {
      apiGet.leads({ limit: 100 }).then(setLeads).catch(() => {});
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Global keyboard listener for ESC
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) onClose();
        else onClose(); // parent handles toggling
      }
      if (e.key === "Escape" && open) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const items: CommandItem[] = useMemo(() => {
    const list: CommandItem[] = [
      // Navigation
      {
        id: "nav-leads",
        title: "العملاء المحتملون (Leads)",
        subtitle: "استعراض وتصفية وتصدير العملاء",
        category: "تنقل",
        icon: <Database className="h-4 w-4 text-[var(--accent)]" />,
        action: () => { setLocation("/leads"); onClose(); },
      },
      {
        id: "nav-overview",
        title: "لوحة التحكم (Overview)",
        subtitle: "تحليلات الأداء والنشاط والـ Funnel",
        category: "تنقل",
        icon: <LayoutDashboard className="h-4 w-4 text-emerald-500" />,
        action: () => { setLocation("/overview"); onClose(); },
      },
      {
        id: "nav-research",
        title: "وكيل البحث العميق (Deep Research)",
        subtitle: "البحث الذكي المستقل وتحليل الشركات",
        category: "تنقل",
        icon: <Sparkles className="h-4 w-4 text-purple-500" />,
        action: () => { setLocation("/research"); onClose(); },
      },
      {
        id: "nav-jobs",
        title: "قائمة المهام (Jobs)",
        subtitle: "متابعة المهام وحالات التشغيل",
        category: "تنقل",
        icon: <Briefcase className="h-4 w-4 text-blue-500" />,
        action: () => { setLocation("/jobs"); onClose(); },
      },
      {
        id: "nav-keys",
        title: "مفاتيح المزودين (API Keys)",
        subtitle: "إدارة الحصص والمفاتيح السحابية",
        category: "تنقل",
        icon: <Key className="h-4 w-4 text-amber-500" />,
        action: () => { setLocation("/keys"); onClose(); },
      },
      {
        id: "nav-review",
        title: "المراجعة وحل التعارضات (Review)",
        subtitle: "مراجعة الحقائق والقرارات البشرية",
        category: "تنقل",
        icon: <ShieldAlert className="h-4 w-4 text-rose-500" />,
        action: () => { setLocation("/review"); onClose(); },
      },
      {
        id: "nav-config",
        title: "الإعدادات العامة (Config)",
        subtitle: "تخصيص معايير الـ ICP والسياسات",
        category: "تنقل",
        icon: <Settings className="h-4 w-4 text-slate-400" />,
        action: () => { setLocation("/config"); onClose(); },
      },

      // Quick Actions
      {
        id: "act-theme",
        title: "تبديل المظهر (Dark / Light Theme)",
        subtitle: "تبديل المظهر الداكن والفاتح",
        category: "إجراءات",
        icon: <Sun className="h-4 w-4 text-amber-400" />,
        action: () => {
          const isDark = document.documentElement.classList.contains("dark");
          if (isDark) {
            document.documentElement.classList.remove("dark");
            localStorage.setItem("theme", "light");
          } else {
            document.documentElement.classList.add("dark");
            localStorage.setItem("theme", "dark");
          }
          onClose();
        },
      },
    ];

    // Search matches from leads
    if (query.trim().length >= 2) {
      const q = query.toLowerCase();
      const matchedLeads = leads
        .filter(
          (l) =>
            (l.name || "").toLowerCase().includes(q) ||
            (l.city || "").toLowerCase().includes(q) ||
            (l.domain || "").toLowerCase().includes(q)
        )
        .slice(0, 5);

      for (const ml of matchedLeads) {
        list.push({
          id: `lead-${ml.lead_id || ml.name}`,
          title: ml.name || "منشأة",
          subtitle: `${ml.city || "المملكة"} · ${ml.domain || "بدون نطاق"} · درجات: ${ml.score?.toFixed(0) || "—"}`,
          category: "عملاء",
          icon: <Database className="h-4 w-4 text-[var(--accent)]" />,
          action: () => {
            setLocation("/leads");
            onClose();
          },
        });
      }
    }

    // Filter by query
    if (!query.trim()) return list;
    const q = query.toLowerCase();
    return list.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        (item.subtitle && item.subtitle.toLowerCase().includes(q))
    );
  }, [query, leads, setLocation, onClose]);

  // Handle arrow key navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (items.length || 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + items.length) % (items.length || 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (items[selectedIndex]) {
        items[selectedIndex].action();
      }
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 sm:pt-28 px-4 animate-fade-in">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Palette Container */}
      <div
        className="relative w-full max-w-xl rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-2xl overflow-hidden z-10 animate-scale-in"
        dir="rtl"
        onKeyDown={handleKeyDown}
      >
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3.5 border-b border-[var(--border-soft)] gap-3 bg-[var(--bg)]">
          <Search className="h-5 w-5 text-[var(--accent)] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="اكتب أمراً أو ابحث عن صفحة، عميل، أو إجراء... (Ctrl + K)"
            className="flex-1 bg-transparent border-none outline-none text-[14px] text-[var(--fg)] placeholder-[var(--fg-muted)]"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="p-1 text-[var(--fg-muted)] hover:text-[var(--fg)] rounded"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono text-[var(--fg-muted)] bg-[var(--bg-soft)] border border-[var(--border)] rounded">
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div className="max-h-[380px] overflow-y-auto p-2 divide-y divide-[var(--border-soft)]/50">
          {items.length === 0 ? (
            <div className="py-10 text-center text-sm text-[var(--fg-muted)]">
              لا توجد نتائج تطابق "{query}"
            </div>
          ) : (
            <div className="space-y-1">
              {items.map((item, index) => {
                const isSelected = index === selectedIndex;
                return (
                  <div
                    key={item.id}
                    onClick={() => item.action()}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all",
                      isSelected
                        ? "bg-[var(--accent)] text-white shadow-sm"
                        : "hover:bg-[var(--bg-hover)] text-[var(--fg)]"
                    )}
                  >
                    <div
                      className={cn(
                        "p-2 rounded-lg shrink-0",
                        isSelected
                          ? "bg-white/20 text-white"
                          : "bg-[var(--bg-soft)]"
                      )}
                    >
                      {item.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium truncate flex items-center justify-between">
                        <span>{item.title}</span>
                        <span
                          className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded",
                            isSelected
                              ? "bg-white/20 text-white"
                              : "bg-[var(--bg-soft)] text-[var(--fg-muted)]"
                          )}
                        >
                          {item.category}
                        </span>
                      </div>
                      {item.subtitle && (
                        <div
                          className={cn(
                            "text-[11px] truncate mt-0.5",
                            isSelected ? "text-white/80" : "text-[var(--fg-muted)]"
                          )}
                        >
                          {item.subtitle}
                        </div>
                      )}
                    </div>
                    {isSelected && (
                      <ArrowRight className="h-4 w-4 shrink-0 text-white rotate-180" />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="px-4 py-2 bg-[var(--bg-soft)] border-t border-[var(--border-soft)] flex items-center justify-between text-[11px] text-[var(--fg-muted)]">
          <div className="flex items-center gap-3">
            <span>
              <kbd className="font-mono bg-[var(--bg)] px-1.5 py-0.5 rounded border border-[var(--border)]">↑</kbd>
              <kbd className="font-mono bg-[var(--bg)] px-1.5 py-0.5 rounded border border-[var(--border)] mr-1">↓</kbd>
              للتنقل
            </span>
            <span>
              <kbd className="font-mono bg-[var(--bg)] px-1.5 py-0.5 rounded border border-[var(--border)]">↵</kbd>
              للاختيار
            </span>
          </div>
          <span>Lead Engine Power Console</span>
        </div>
      </div>
    </div>
  );
}
