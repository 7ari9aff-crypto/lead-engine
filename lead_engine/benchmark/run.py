"""Benchmark runner + seed-list loader (manual CSV path for V0)."""
import csv

from ..config import DATA_DIR, OUTPUTS_DIR, load_env, load_icp, load_settings
from ..db import open_db
from ..pipeline.orchestrator import PipelineOrchestrator
from .metrics import compute_metrics, write_outputs


def load_seed_csv(path) -> list:
    """Manual seed list — the V0 escape hatch when free APIs underdeliver."""
    seeds = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            seeds.append({
                "name": row.get("name", ""),
                "domain": row.get("domain") or None,
                "city": row.get("city") or None,
                "email": row.get("email") or None,
                "phone": row.get("phone") or None,
                "website": row.get("website") or None,
                "snippet": row.get("notes", ""),
                "sources": ["manual_seed"],
                "source_urls": [row.get("website")] if row.get("website") else [],
                "source_queries": ["manual_seed"],
            })
    return seeds


def run_benchmark(icp="v0_saudi_dental",
                  job_id=None, seed_csv=None, write=True, agent_run_id=None):
    """icp: ICP name (loaded from config/icp/) or a full ICP dict (chat/MCP)."""
    import json

    load_env()
    DATA_DIR.mkdir(exist_ok=True)
    db = open_db()
    settings = load_settings()
    icp_dict = icp if isinstance(icp, dict) else load_icp(icp)
    orchestrator = PipelineOrchestrator(db, settings, agent_run_id=agent_run_id)
    seed_leads = load_seed_csv(seed_csv) if seed_csv else None
    summary = orchestrator.run_job(icp_dict, job_id=job_id, seed_leads=seed_leads)
    leads = summary.get("leads", [])
    usage_rows = db.query("SELECT units FROM usage_ledger WHERE job_id=?", (summary["job_id"],))
    metrics = compute_metrics(summary, leads, usage_rows)
    outputs = write_outputs(metrics, summary, leads) if write else {}
    existing = {}
    row = db.one("SELECT params FROM jobs WHERE job_id=?", (summary["job_id"],))
    if row and row["params"]:
        try:
            existing = json.loads(row["params"])
        except json.JSONDecodeError:
            existing = {}
    existing["metrics"] = metrics
    existing["outputs"] = outputs
    db.execute("UPDATE jobs SET params=? WHERE job_id=?",
               (json.dumps(existing, ensure_ascii=False, default=str), summary["job_id"]))
    db.conn.close()
    return summary, metrics, outputs
