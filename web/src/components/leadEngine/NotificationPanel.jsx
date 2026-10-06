import React from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { TimeAgo } from "./primitives";
import { CheckCheck } from "lucide-react";

const SEV_DOT = {
  success: "bg-[hsl(var(--success))]",
  warning: "bg-[hsl(var(--warning))]",
  danger: "bg-[hsl(var(--danger))]",
  info: "bg-[hsl(var(--info))]",
};

export function NotificationPanel({ onClose }) {
  const { t, lang, notifications, markAllNotifsRead, markNotifRead } = useLeadEngine();
  const navigate = useNavigate();

  return (
    <div className="absolute top-full mt-1 end-0 w-[340px] max-w-[calc(100vw-2rem)] card-surface z-50 animate-scale-in origin-top overflow-hidden">
      <div className="flex items-center justify-between px-4 h-12 border-b border-border">
        <h3 className="text-sm font-semibold">{lang === "ar" ? "الإشعارات" : "Notifications"}</h3>
        <button onClick={markAllNotifsRead} className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition">
          <CheckCheck className="w-3.5 h-3.5" /> {lang === "ar" ? "تعليم الكل كمقروء" : "Mark all read"}
        </button>
      </div>
      <div className="max-h-[420px] overflow-y-auto scrollbar-thin">
        {notifications.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">{lang === "ar" ? "لا إشعارات" : "No notifications"}</div>
        ) : notifications.map((n) => (
          <button
            key={n.id}
            onClick={() => { markNotifRead(n.id); if (n.to) { navigate(n.to); onClose?.(); } }}
            className={cn("w-full text-start flex gap-3 px-4 py-3 border-b border-border/60 hover:bg-muted/60 transition", !n.read && "bg-[hsl(var(--accent))]/40")}
          >
            <span className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0", SEV_DOT[n.severity] || SEV_DOT.info)} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium leading-snug">{n.title}</span>
              <span className="block text-[11px] text-muted-foreground mt-0.5">{n.detail}</span>
              <span className="block mt-1"><TimeAgo iso={n.at} /></span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}