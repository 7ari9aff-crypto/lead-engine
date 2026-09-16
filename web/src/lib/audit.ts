// Operator Audit Trail & Activity Logger
// Tracks high-value operator actions (exports, webhooks, ICP updates, bulk verifications)
// Persists in localStorage and forwards to backend event dispatch when available.

export interface AuditAction {
  id: string;
  kind: "export.csv" | "export.instantly" | "export.webhook" | "icp.saved" | "icp.activated" | "leads.verified" | "leads.status_changed" | "leads.deleted";
  title: string;
  description: string;
  targetCount?: number;
  metadata?: Record<string, any>;
  timestamp: string;
}

const STORAGE_KEY = "leadEngine.auditLog.v1";

export function loadAuditLog(): AuditAction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function logAuditAction(
  kind: AuditAction["kind"],
  title: string,
  description: string,
  targetCount?: number,
  metadata?: Record<string, any>
): AuditAction {
  const entry: AuditAction = {
    id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    kind,
    title,
    description,
    targetCount,
    metadata,
    timestamp: new Date().toISOString(),
  };

  try {
    const existing = loadAuditLog();
    const updated = [entry, ...existing].slice(0, 200); // keep last 200 actions
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch (e) {
    console.warn("Failed to persist audit action to localStorage:", e);
  }

  // Attempt async fire-and-forget sync to backend events if endpoint exists
  try {
    fetch("/api/events/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        title,
        description,
        count: targetCount,
        metadata,
      }),
    }).catch(() => {});
  } catch {}

  return entry;
}
