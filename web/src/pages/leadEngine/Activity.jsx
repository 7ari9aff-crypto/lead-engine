import React, { useState } from "react";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { TimeAgo } from "@/components/leadEngine/primitives";
import { Search } from "lucide-react";

export default function Activity() {
  const { t, lang, activity } = useLeadEngine();
  const [q, setQ] = useState("");
  const actorName = (a) => (a.actor === "SYSTEM" ? (lang === "ar" ? "النظام" : "System") : a.actor);
  const ql = q.toLowerCase();
  const list = activity.filter((a) => !q || actorName(a).toLowerCase().includes(ql) || a.action.toLowerCase().includes(ql) || (a.target || "").toLowerCase().includes(ql) || (a.detail || "").toLowerCase().includes(ql));

  return (
    <>
      <PageHeader title={t("activity.title")} subtitle={lang === "ar" ? "من فعل ماذا، ومتى، وعلى أي عميل أو وظيفة. الأحدث أولًا." : "Who did what, when, and on which lead or job. Newest first."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1200px] space-y-4">
        <div className="relative max-w-sm">
          <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-4 h-4 text-muted-foreground" />
          <input dir="auto" value={q} onChange={(e) => setQ(e.target.value)} placeholder={lang === "ar" ? "بحث في السجل…" : "Search audit log…"} className="w-full h-9 ps-9 pe-3 rounded-lg border border-input bg-background text-sm focus-ring" />
        </div>
        <div className="card-surface overflow-x-auto">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="text-[11px] text-muted-foreground border-b border-border bg-muted/30">
                <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الفاعل" : "Actor"}</th>
                <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الإجراء" : "Action"}</th>
                <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الهدف" : "Target"}</th>
                <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "التفصيل" : "Detail"}</th>
                <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الوقت" : "When"}</th>
              </tr>
            </thead>
            <tbody>
              {list.map((ev) => (
                <tr key={ev.id} className="border-b border-border/50 hover:bg-muted/30 transition">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span className={`w-6 h-6 rounded-full grid place-items-center text-[10px] font-semibold ${ev.actor === "SYSTEM" ? "bg-accent text-primary" : "bg-muted text-foreground"}`}>
                        {ev.actor === "SYSTEM" ? (lang === "ar" ? "ن" : "S") : ev.actor.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                      </span>
                      <span className="font-medium">{actorName(ev)}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">{ev.action}</td>
                  <td className="py-3 px-4 text-muted-foreground text-xs">{ev.target}</td>
                  <td className="py-3 px-4 text-muted-foreground">{ev.detail}</td>
                  <td className="py-3 px-4"><TimeAgo iso={ev.at} /></td>
                </tr>
              ))}
              {list.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-muted-foreground">{lang === "ar" ? "لا نتائج." : "No results."}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}