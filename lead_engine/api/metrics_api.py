"""SLO / Metrics surface — closes the Observability gap (plan-improvement T3).

Two endpoints, one recorder:

* ``GET /metrics`` — Prometheus text exposition (scrape-friendly: counters,
  gauges, and a latency histogram). Guarded like every other ``/api`` path,
  so the scraper authenticates with the same token the dashboard uses.
* ``GET /api/v1/slo`` — the JSON summary the dashboard renders (uptime, error
  rate, p50/p95/p99 latency, throughput, and the same business gauges).

The recorder is deliberately in-process (stdlib only, no new dependency):
counters are cheap and the fleet is small. Multi-replica aggregation is a
Prometheus job — each replica is scraped independently and summed by the
query layer, which is exactly what the text format is designed for.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Any, Iterable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from ..entitlements import get_limits
from ..observability import get_logger

router = APIRouter(tags=["observability"])
log = get_logger("lead_engine.api.metrics")

# ---------------------------------------------------------------------------
# SLO targets — the numbers operators are held to. Kept here (not scattered in
# the frontend) so the API and the dashboard can never disagree about "good".
# ---------------------------------------------------------------------------

SLO_TARGETS = {
    "availability": 0.995,      # 99.5% non-5xx over the process lifetime
    "latency_p95_ms": 500.0,    # p95 of served request duration
    "error_rate": 0.01,         # share of 5xx among all responses
}

# Prometheus histogram buckets (seconds) — tuned for an API that mostly
# answers in single-digit milliseconds and occasionally streams.
_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)

_LATENCY_SAMPLE_CAP = 2_000
# Cardinality guard: a malicious/buggy caller cannot mint unbounded label sets.
_MAX_LABEL_SERIES = 200


class MetricsRegistry:
    """Thread-safe in-process counters, gauges, and a latency histogram."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        # (method, path, status) -> count
        self._requests: OrderedDict[tuple[str, str, int], int] = OrderedDict()
        # cumulative bucket counts; len == len(_BUCKETS) + 1 (the +Inf bucket)
        self._bucket_counts = [0] * (len(_BUCKETS) + 1)
        self._latency_sum = 0.0
        self._latency_count = 0
        self._latency_samples: deque[float] = deque(maxlen=_LATENCY_SAMPLE_CAP)
        self._overloaded = 0  # requests rejected by rate limiting

    # ---- recording ------------------------------------------------------

    def observe(self, method: str, path: str, status: int, duration_s: float) -> None:
        """Record one served request. Must never raise into the request path."""
        try:
            key = (method, path, int(status))
            with self._lock:
                if key in self._requests or len(self._requests) < _MAX_LABEL_SERIES:
                    self._requests[key] = self._requests.get(key, 0) + 1
                self._latency_sum += duration_s
                self._latency_count += 1
                self._latency_samples.append(duration_s * 1000.0)
                for i, edge in enumerate(_BUCKETS):
                    if duration_s <= edge:
                        self._bucket_counts[i] += 1
                self._bucket_counts[-1] += 1
        except Exception:  # pragma: no cover - telemetry must not break serving
            pass

    def count_overloaded(self) -> None:
        with self._lock:
            self._overloaded += 1

    # ---- reading --------------------------------------------------------

    def _percentile(self, pct: float) -> float:
        if not self._latency_samples:
            return 0.0
        ordered = sorted(self._latency_samples)
        idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * len(ordered))) - 1))
        return ordered[idx]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            requests = dict(self._requests)
            bucket_counts = list(self._bucket_counts)
            latency_sum = self._latency_sum
            latency_count = self._latency_count
            overloaded = self._overloaded
            started = self.started_at
        total = sum(requests.values())
        server_errors = sum(n for (_, _, s), n in requests.items() if s >= 500)
        client_errors = sum(n for (_, _, s), n in requests.items() if 400 <= s < 500)
        return {
            "uptime_seconds": round(time.time() - started, 3),
            "requests_total": total,
            "server_errors_total": server_errors,
            "client_errors_total": client_errors,
            "rate_limited_total": overloaded,
            "error_rate": round(server_errors / total, 6) if total else 0.0,
            "availability": round(1 - (server_errors / total), 6) if total else 1.0,
            "latency": {
                "count": latency_count,
                "sum_seconds": round(latency_sum, 6),
                "p50_ms": round(self._percentile(50), 3),
                "p95_ms": round(self._percentile(95), 3),
                "p99_ms": round(self._percentile(99), 3),
                "buckets": [
                    {"le_seconds": edge, "count": bucket_counts[i]}
                    for i, edge in enumerate(_BUCKETS)
                ],
                "inf_count": bucket_counts[-1],
            },
            "series": [
                {"method": m, "path": p, "status": s, "count": n}
                for (m, p, s), n in sorted(requests.items(), key=lambda kv: -kv[1])
            ],
        }
    def render_prometheus(self, extra_gauges: dict[str, float]) -> str:
        snap = self.snapshot()
        lines: list[str] = []

        def emit(name: str, help_text: str, kind: str) -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")

        emit("lead_engine_uptime_seconds", "Seconds since the API process started.", "gauge")
        lines.append(f"lead_engine_uptime_seconds {snap['uptime_seconds']}")

        emit("lead_engine_requests_total",
             "Served HTTP requests by method, path and status.", "counter")
        for row in snap["series"]:
            lines.append(
                f'lead_engine_requests_total{{method="{row["method"]}",'
                f'path="{row["path"]}",status="{row["status"]}"}} {row["count"]}'
            )

        emit("lead_engine_rate_limited_total",
             "Requests rejected by the rate limiter.", "counter")
        lines.append(f"lead_engine_rate_limited_total {snap['rate_limited_total']}")

        # Latency histogram in the exact shape Prometheus expects (cumulative).
        emit("lead_engine_request_duration_seconds", "Request latency histogram.", "histogram")
        for bucket in snap["latency"]["buckets"]:
            lines.append(
                f'lead_engine_request_duration_seconds_bucket{{le="{bucket["le_seconds"]}"}} '
                f'{bucket["count"]}'
            )
        lines.append(
            f'lead_engine_request_duration_seconds_bucket{{le="+Inf"}} '
            f'{snap["latency"]["inf_count"]}'
        )
        lines.append(f"lead_engine_request_duration_seconds_sum {snap['latency']['sum_seconds']}")
        lines.append(f"lead_engine_request_duration_seconds_count {snap['latency']['count']}")

        emit("lead_engine_business_gauge", "Tenant-scoped business counters.", "gauge")
        for name, value in sorted((extra_gauges or {}).items()):
            lines.append(f'lead_engine_business_gauge{{metric="{name}"}} {value}')

        return "\n".join(lines) + "\n"


REGISTRY = MetricsRegistry()


# ---------------------------------------------------------------------------
# Tenant resolution mirrors policy_api: claims first, fail-closed, env bridge.
# ---------------------------------------------------------------------------


def get_db(request: Request = None):
    from ..tenant import db_handle

    yield from db_handle(request)


def _org_scoped(db) -> tuple[str, list]:
    org = getattr(db, "org_id", None)
    if org and not str(org).startswith("__"):
        return "WHERE organization_id = ?", [org]
    # Unscoped (dev / machine) context: platform rows only. Never aggregate
    # across tenants — the same fail-closed rule the live stream follows.
    return "WHERE organization_id IS NULL", []


def business_gauges(db) -> dict[str, float]:
    """Business counters read at scrape time (cheap aggregate queries)."""
    gauges: dict[str, float] = {}
    where, params = _org_scoped(db)
    for name, table in (
        ("leads_total", "leads"),
        ("jobs_total", "jobs"),
        ("job_events_total", "job_events"),
        ("usage_calls_total", "usage_ledger"),
    ):
        try:
            row = db.one(f"SELECT COUNT(*) AS n FROM {table} {where}", params)
            gauges[name] = float((row or {}).get("n") or 0)
        except Exception:
            continue
    try:
        rows = db.query(f"SELECT state, COUNT(*) AS n FROM jobs {where} GROUP BY state", params)
        for r in rows:
            state = str(r.get("state") or "UNKNOWN").lower()
            gauges[f"jobs_state_{state}"] = float(r.get("n") or 0)
    except Exception:
        pass
    return gauges


@router.get("/api/v1/slo")
def slo_summary(db=Depends(get_db)) -> dict[str, Any]:
    """JSON SLO summary + business gauges for the dashboard panel."""
    snap = REGISTRY.snapshot()
    gauges = business_gauges(db)

    checks = {
        "availability": snap["availability"] >= SLO_TARGETS["availability"],
        "latency_p95": snap["latency"]["p95_ms"] <= SLO_TARGETS["latency_p95_ms"],
        "error_rate": snap["error_rate"] <= SLO_TARGETS["error_rate"],
    }
    # Uptime is only meaningful once a handful of requests have been served.
    warm = snap["requests_total"] >= 10
    return {
        "targets": SLO_TARGETS,
        "observed": {
            "availability": snap["availability"],
            "error_rate": snap["error_rate"],
            "latency_p50_ms": snap["latency"]["p50_ms"],
            "latency_p95_ms": snap["latency"]["p95_ms"],
            "latency_p99_ms": snap["latency"]["p99_ms"],
            "uptime_seconds": snap["uptime_seconds"],
            "requests_total": snap["requests_total"],
        },
        "checks": checks,
        "within_slo": all(checks.values()) if warm else None,
        "warming_up": not warm,
        "gauges": gauges,
        "top_paths": snap["series"][:8],
    }


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus_metrics(db=Depends(get_db)) -> str:
    """Prometheus text exposition — scraped by the monitoring stack."""
    try:
        extra = business_gauges(db)
    except Exception:  # pragma: no cover
        extra = {}
    return REGISTRY.render_prometheus(extra)


@router.get("/api/v1/entitlements-summary")
def entitlements_summary(db=Depends(get_db)) -> dict[str, Any]:
    """Daily limits for the calling org — shown next to the SLO panel."""
    org = getattr(db, "org_id", None)
    try:
        limits = get_limits(org) if org else {}
    except Exception:
        limits = {}
    return {"organization_id": org, "limits": _jsonable_limits(limits)}


def _jsonable_limits(limits: Any) -> dict[str, Any]:
    if isinstance(limits, dict):
        return {str(k): v for k, v in limits.items()}
    keys: Iterable[str] = (
        "max_jobs_per_day", "max_leads_per_day", "max_provider_calls_per_day",
    )
    return {k: getattr(limits, k, None) for k in keys if hasattr(limits, k)}
