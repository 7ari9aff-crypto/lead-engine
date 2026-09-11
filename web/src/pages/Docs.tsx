import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  BookOpen, Search, ChevronDown, ChevronLeft, Play, Loader2,
  RefreshCw, AlertCircle, CheckCircle2, Copy, XCircle, Zap,
} from "lucide-react";
import { apiGet } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Textarea, Label } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/Dialog";
import {
  HTTP_METHODS, METHOD_COLORS, METHOD_LABEL,
  groupByTag, getParameterInputs, getRequestBodySchema, parseEndpoints,
  type Endpoint, type HttpMethod, type InputField,
} from "@/lib/docsGen";

const FILTER_OPTIONS = [
  { value: "all", label: "الكل" },
  ...HTTP_METHODS.map((m) => ({ value: m, label: METHOD_LABEL[m] })),
] as { value: "all" | HttpMethod; label: string }[];

export function DocsPage() {
  const [endpoints, setEndpoints] = useState<Endpoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [methodFilter, setMethodFilter] = useState<"all" | HttpMethod>("all");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setEndpoints(null);
    setError(null);
    apiGet
      .openapi()
      .then((doc) => {
        if (cancelled) return;
        const eps = parseEndpoints(doc);
        if (eps.length === 0) {
          setError("لم يُرجع الـOpenAPI أي endpoints.");
        } else {
          setEndpoints(eps);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "تعذّر تحميل /openapi.json");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const filtered = useMemo(() => {
    if (!endpoints) return [];
    const q = search.trim().toLowerCase();
    return endpoints.filter((ep) => {
      if (methodFilter !== "all" && ep.method !== methodFilter) return false;
      if (!q) return true;
      const hay = `${ep.path} ${ep.method} ${ep.summary} ${ep.description} ${ep.group}`.toLowerCase();
      return hay.includes(q);
    });
  }, [endpoints, search, methodFilter]);

  const groups = useMemo(() => groupByTag(filtered), [filtered]);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<BookOpen className="h-4 w-4 text-white" />}
        title="مرجع الـAPI"
        description="كل endpoints الباك إند مولّدة تلقائيًا من /openapi.json — ابحث، فلتر، وجرّب."
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => setReloadKey((k) => k + 1)}
            disabled={!endpoints && !error}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            تحديث
          </Button>
        }
      />

      {/* Toolbar */}
      <Card>
        <CardContent className="p-4 flex flex-col sm:flex-row gap-3 sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)] pointer-events-none" />
            <Input
              placeholder="ابحث في المسار أو الوصف…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pr-9"
              dir="rtl"
            />
          </div>
          <FilterPills
            options={FILTER_OPTIONS}
            value={methodFilter}
            onChange={(v) => setMethodFilter(v as "all" | HttpMethod)}
          />
        </CardContent>
      </Card>

      {/* Body */}
      {!endpoints && !error && (
        <Card>
          <CardContent className="p-10 flex items-center justify-center gap-3 text-[var(--fg-muted)]">
            <Loader2 className="h-5 w-5 animate-spin" />
            جاري تحميل /openapi.json…
          </CardContent>
        </Card>
      )}

      {error && (
        <EmptyState
          icon={<AlertCircle className="h-8 w-8" />}
          title="ما قدرنا نحمّل التوثيق"
          description={error}
          action={
            <Button variant="outline" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              <RefreshCw className="h-3.5 w-3.5" />
              حاول مرة ثانية
            </Button>
          }
        />
      )}

      {endpoints && filtered.length === 0 && (
        <EmptyState
          icon={<Search className="h-8 w-8" />}
          title="لا توجد نتائج"
          description="جرّب كلمة بحث مختلفة أو غيّر الفلتر."
        />
      )}

      {Object.entries(groups).map(([group, eps]) => (
        <section key={group} className="space-y-3">
          <div className="flex items-center gap-2 px-1">
            <Zap className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-[var(--fg-muted)]">
              {group}
            </h2>
            <Badge variant="outline">{eps.length}</Badge>
          </div>
          <div className="space-y-2">
            {eps.map((ep, i) => (
              <EndpointCard key={`${ep.method}-${ep.path}-${i}`} ep={ep} />
            ))}
          </div>
        </section>
      ))}

      <p className="text-xs text-[var(--fg-soft)] text-center pt-4">
        الصفحة تتغذى من <code dir="ltr" className="text-[11px] px-1 py-0.5 rounded bg-[var(--bg-soft)]">/openapi.json</code>
        تلقائيًا — أي endpoint جديد في الباك إند يظهر هنا بدون تعديل.
      </p>
    </div>
  );
}

function EndpointCard({ ep }: { ep: Endpoint }) {
  const [open, setOpen] = useState(false);
  const [showParams, setShowParams] = useState(false);
  const [showBody, setShowBody] = useState(false);
  const [tryIt, setTryIt] = useState(false);

  const color = METHOD_COLORS[ep.method];
  const params = getParameterInputs(ep.parameters);
  const bodyFields = getRequestBodySchema(ep.requestBody);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
    >
      <Card>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full text-right p-4 flex items-center gap-3 hover:bg-[var(--bg-hover)]/40 transition-colors rounded-xl"
        >
          <span
            className="shrink-0 inline-flex items-center justify-center min-w-[64px] px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wider font-mono"
            style={{
              background: `color-mix(in srgb, ${color} 15%, transparent)`,
              color: color,
            }}
          >
            {METHOD_LABEL[ep.method]}
          </span>
          <code
            dir="ltr"
            className="flex-1 text-sm font-mono text-[var(--fg)] truncate text-left"
          >
            {ep.path}
          </code>
          {ep.summary && (
            <span className="hidden md:block text-xs text-[var(--fg-muted)] truncate max-w-[280px]">
              {ep.summary}
            </span>
          )}
          <ChevronLeft
            className={`h-4 w-4 shrink-0 text-[var(--fg-soft)] transition-transform ${open ? "-rotate-90" : ""}`}
          />
        </button>

        {open && (
          <CardContent className="pt-0 pb-4 space-y-3">
            {ep.description && (
              <p className="text-sm text-[var(--fg-muted)] leading-relaxed">
                {ep.description}
              </p>
            )}
            {!ep.summary && !ep.description && (
              <p className="text-xs text-[var(--fg-soft)] italic">
                ما في وصف لهذا الـendpoint.
              </p>
            )}

            {/* Parameters */}
            {params.length > 0 && (
              <CollapsibleSection label="Parameters" count={params.length}
                open={showParams} onToggle={() => setShowParams((v) => !v)}>
                <ParamTable fields={params} showIn />
              </CollapsibleSection>
            )}

            {/* Body */}
            {bodyFields && bodyFields.length > 0 && (
              <CollapsibleSection label="Request body" count={bodyFields.length}
                open={showBody} onToggle={() => setShowBody((v) => !v)}>
                <ParamTable fields={bodyFields} />
              </CollapsibleSection>
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-2 pt-1">
              <Button variant="primary" size="sm" onClick={() => setTryIt(true)}>
                <Play className="h-3.5 w-3.5" />
                Try it
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {tryIt && (
        <TryItDialog
          endpoint={ep}
          paramFields={params}
          bodyFields={bodyFields ?? []}
          onClose={() => setTryIt(false)}
        />
      )}
    </motion.div>
  );
}

function ParamTable({ fields, showIn }: { fields: InputField[]; showIn?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" dir="ltr">
        <thead className="text-[var(--fg-soft)]">
          <tr className="border-b border-[var(--border-soft)]">
            <th className="text-left py-1.5 px-2 font-medium">Name</th>
            {showIn && <th className="text-left py-1.5 px-2 font-medium">In</th>}
            <th className="text-left py-1.5 px-2 font-medium">Type</th>
            <th className="text-left py-1.5 px-2 font-medium">Required</th>
            <th className="text-left py-1.5 px-2 font-medium">Description</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((p, i) => (
            <tr key={i} className="border-b border-[var(--border-soft)]/40">
              <td className="py-1.5 px-2 font-mono font-semibold">{p.name}</td>
              {showIn && (
                <td className="py-1.5 px-2"><Badge variant="outline">{p.in}</Badge></td>
              )}
              <td className="py-1.5 px-2 text-[var(--fg-muted)]">{p.type}</td>
              <td className="py-1.5 px-2">
                {p.required ? (
                  <span className="text-[var(--danger)] font-medium">yes</span>
                ) : (
                  <span className="text-[var(--fg-soft)]">no</span>
                )}
              </td>
              <td className="py-1.5 px-2 text-[var(--fg-muted)]">{p.description ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CollapsibleSection({
  label, count, open, onToggle, children,
}: { label: string; count: number; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border-soft)] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]/40"
      >
        <span className="flex items-center gap-2">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "" : "-rotate-90"}`} />
          {label}
          <Badge variant="outline">{count}</Badge>
        </span>
      </button>
      {open && <div className="p-3 pt-1 bg-[var(--bg-soft)]/30">{children}</div>}
    </div>
  );
}

function TryItDialog({
  endpoint,
  paramFields,
  bodyFields,
  onClose,
}: {
  endpoint: Endpoint;
  paramFields: InputField[];
  bodyFields: InputField[];
  onClose: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of paramFields) init[f.name] = f.default ?? "";
    if (bodyFields.length === 1 && bodyFields[0].name === "body") {
      init["body"] = "{}";
    } else {
      for (const f of bodyFields) init[f.name] = f.default ?? "";
    }
    return init;
  });
  const [bodyJson, setBodyJson] = useState<string>(
    bodyFields.length === 1 && bodyFields[0].name === "body" ? "" : "{}"
  );
  const [sending, setSending] = useState(false);
  const [respStatus, setRespStatus] = useState<number | null>(null);
  const [respBody, setRespBody] = useState<string>("");

  const color = METHOD_COLORS[endpoint.method];

  async function handleSend() {
    setSending(true);
    setRespStatus(null);
    setRespBody("");
    try {
      // Substitute path params.
      let url = endpoint.path;
      const pathFields = paramFields.filter((p) => p.in === "path");
      for (const p of pathFields) {
        const v = (values[p.name] ?? "").trim();
        if (!v) {
          toast.error(`Missing path param: ${p.name}`);
          setSending(false);
          return;
        }
        url = url.replace(`{${p.name}}`, encodeURIComponent(v));
      }

      // Build query string.
      const qs = new URLSearchParams();
      for (const p of paramFields.filter((q) => q.in === "query")) {
        const v = (values[p.name] ?? "").trim();
        if (v) qs.set(p.name, v);
      }
      const queryStr = qs.toString();
      if (queryStr) url += `?${queryStr}`;

      // Headers (custom header params).
      const headers: Record<string, string> = {};
      for (const p of paramFields.filter((h) => h.in === "header")) {
        const v = (values[p.name] ?? "").trim();
        if (v) headers[p.name] = v;
      }

      let body: BodyInit | undefined;
      if (bodyFields.length > 0) {
        headers["Content-Type"] = "application/json";
        if (bodyFields.length === 1 && bodyFields[0].name === "body") {
          body = bodyJson;
        } else {
          const obj: Record<string, unknown> = {};
          for (const f of bodyFields) {
            const raw = values[f.name];
            if (raw == null || raw === "") continue;
            if (f.type === "number") {
              const n = Number(raw);
              if (Number.isNaN(n)) {
                toast.error(`${f.name} لازم يكون رقم`);
                setSending(false);
                return;
              }
              obj[f.name] = n;
            } else if (f.type === "boolean") {
              obj[f.name] = raw === "true" || raw === "1";
            } else {
              obj[f.name] = raw;
            }
          }
          body = JSON.stringify(obj);
        }
      }

      const res = await fetch(url, {
        method: METHOD_LABEL[endpoint.method],
        credentials: "include",
        headers,
        body,
      });
      setRespStatus(res.status);
      const text = await res.text();
      try {
        setRespBody(text ? JSON.stringify(JSON.parse(text), null, 2) : "(empty body)");
      } catch {
        setRespBody(text || "(empty body)");
      }
      if (res.ok) toast.success(`${res.status} OK`);
      else toast.error(`${res.status} ${res.statusText || "Error"}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setRespStatus(0);
      setRespBody(`Network error: ${msg}`);
      toast.error(msg);
    } finally {
      setSending(false);
    }
  }

  function copyResponse() {
    if (!respBody) return;
    navigator.clipboard.writeText(respBody).then(
      () => toast.success("Response copied"),
      () => toast.error("Copy failed")
    );
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            <span
              className="inline-flex items-center justify-center px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wider font-mono"
              style={{
                background: `color-mix(in srgb, ${color} 15%, transparent)`,
                color: color,
              }}
            >
              {METHOD_LABEL[endpoint.method]}
            </span>
            <code dir="ltr" className="text-sm font-mono">
              {endpoint.path}
            </code>
          </DialogTitle>
          {endpoint.summary && (
            <DialogDescription>{endpoint.summary}</DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pe-1">
          {paramFields.length > 0 && (
            <div className="space-y-3">
              {(["path", "query", "header"] as const).map((loc) => {
                const fields = paramFields.filter((p) => p.in === loc);
                if (fields.length === 0) return null;
                return (
                  <div key={loc}>
                    <div className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-soft)] mb-2">
                      {loc === "path" ? "Path parameters" : loc === "query" ? "Query parameters" : "Headers"}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {fields.map((f) => (
                        <div key={f.name}>
                          <Label className="flex items-center gap-1.5">
                            <code dir="ltr" className="text-xs">{f.name}</code>
                            {f.required && (
                              <span className="text-[var(--danger)] text-[10px]">required</span>
                            )}
                          </Label>
                          {f.enum && f.enum.length > 0 ? (
                            <select
                              className="flex h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] px-3 py-2 text-sm"
                              value={values[f.name] ?? ""}
                              onChange={(e) =>
                                setValues((v) => ({ ...v, [f.name]: e.target.value }))
                              }
                            >
                              <option value="">—</option>
                              {f.enum.map((opt) => (
                                <option key={String(opt)} value={String(opt)}>
                                  {String(opt)}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <Input
                              dir="ltr"
                              placeholder={f.example ?? f.type}
                              value={values[f.name] ?? ""}
                              onChange={(e) =>
                                setValues((v) => ({ ...v, [f.name]: e.target.value }))
                              }
                            />
                          )}
                          {f.description && (
                            <p className="text-[11px] text-[var(--fg-soft)] mt-1">{f.description}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {bodyFields.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-soft)] mb-2">
                Request body
              </div>
              {bodyFields.length === 1 && bodyFields[0].name === "body" ? (
                <Textarea
                  dir="ltr"
                  rows={8}
                  placeholder='{"key": "value"}'
                  value={bodyJson}
                  onChange={(e) => setBodyJson(e.target.value)}
                  className="font-mono text-xs"
                />
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {bodyFields.map((f) => (
                    <div key={f.name}>
                      <Label className="flex items-center gap-1.5">
                        <code dir="ltr" className="text-xs">{f.name}</code>
                        {f.required && (
                          <span className="text-[var(--danger)] text-[10px]">required</span>
                        )}
                        <span className="text-[var(--fg-soft)] text-[10px]">({f.type})</span>
                      </Label>
                      <Input
                        dir="ltr"
                        type={f.type === "number" ? "number" : "text"}
                        placeholder={f.example ?? f.type}
                        value={values[f.name] ?? ""}
                        onChange={(e) =>
                          setValues((v) => ({ ...v, [f.name]: e.target.value }))
                        }
                      />
                      {f.description && (
                        <p className="text-[11px] text-[var(--fg-soft)] mt-1">{f.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {paramFields.length === 0 && bodyFields.length === 0 && (
            <p className="text-sm text-[var(--fg-muted)]">
              هذا الـendpoint ما يحتاج parameters أو body — اضغط Send مباشرة.
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 pt-2 border-t border-[var(--border-soft)]">
          <div className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
            {respStatus !== null &&
              (respStatus >= 200 && respStatus < 300 ? (
                <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
              ) : (
                <XCircle className="h-4 w-4 text-[var(--danger)]" />
              ))}
            {respStatus !== null && (
              <span className="font-mono font-semibold">
                {respStatus === 0 ? "Network error" : respStatus}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              إغلاق
            </Button>
            <Button variant="primary" size="sm" onClick={handleSend} loading={sending}>
              <Play className="h-3.5 w-3.5" />
              Send
            </Button>
          </div>
        </div>

        {respBody && (
          <div className="relative rounded-lg border border-[var(--border-soft)] bg-[var(--bg)] overflow-hidden">
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-soft)] text-[11px] text-[var(--fg-soft)]">
              <span className="font-mono">Response</span>
              <button
                type="button"
                onClick={copyResponse}
                className="flex items-center gap-1 hover:text-[var(--fg)] transition-colors"
              >
                <Copy className="h-3 w-3" />
                Copy
              </button>
            </div>
            <pre
              dir="ltr"
              className="p-3 text-xs font-mono overflow-x-auto max-h-64 text-[var(--fg)]"
            >
              {respBody}
            </pre>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
