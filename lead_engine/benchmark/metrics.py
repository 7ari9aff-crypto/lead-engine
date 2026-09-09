"""V0 benchmark metrics — the numbers that decide if the stack works.

Discovery precision, enrichment success, contact coverage, email validity,
duplicate rate, quota consumed per lead, total cost ($0 target).
"""
from ..config import OUTPUTS_DIR


def _pct(part, whole):
    if not whole:
        return None
    return round(100.0 * len(part) / len(whole), 1)


def compute_metrics(summary: dict, leads: list, usage_rows: list) -> dict:
    stages = summary.get("stages", {})
    accepted = [l for l in leads if l.get("stage") == "ACCEPTED"]
    review = [l for l in leads if l.get("stage") == "REVIEW"]
    with_contact = [l for l in accepted if l.get("email") or l.get("phone")]
    with_email = [l for l in accepted if l.get("email")]
    deliverable = [l for l in accepted if l.get("email_status") == "DELIVERABLE"]
    dedup = stages.get("dedup", {})
    total_units = sum(float(r.get("units") or 0) for r in usage_rows)
    degraded = any(l.get("processing_mode") == "degraded_local" for l in leads)

    return {
        "job_id": summary.get("job_id"),
        "dry_run": summary.get("dry_run", False),
        "discovery_raw_candidates": stages.get("discovery", {}).get("raw_candidates"),
        "unique_after_dedup": dedup.get("output_count"),
        "duplicate_rate": dedup.get("duplicate_rate"),
        "dedup_review_pairs": len(dedup.get("review_pairs") or []),
        "hard_filter_kept": stages.get("hard_filter", {}).get("kept"),
        "hard_filter_dropped": stages.get("hard_filter", {}).get("dropped"),
        "qualification_scored": stages.get("qualification", {}).get("scored"),
        "qualification_skipped": stages.get("qualification", {}).get("skipped"),
        "enrichment": stages.get("enrichment", {}),
        "final_leads": len(accepted),
        "review_leads": len(review),
        "contact_coverage_pct": _pct(with_contact, accepted),
        "email_validity_rate_pct": _pct(deliverable, with_email),
        "quota_units_total": total_units,
        "quota_units_per_final_lead": round(total_units / len(accepted), 2) if accepted else None,
        "total_cost_usd": 0.0,
        "degraded_local_used": degraded,
    }


CSV_COLUMNS = ["name", "domain", "city", "country", "tier", "qualification_score", "score",
               "email", "email_status", "email_confidence", "phone", "decision_maker",
               "decision_maker_title", "linkedin", "branches", "processing_mode",
               "legal_decision", "stage", "requires_review", "website"]


def export_csv(leads: list, path=None) -> str:
    import csv

    path = path or (OUTPUTS_DIR / "leads.csv")
    OUTPUTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({k: ("" if lead.get(k) is None else lead.get(k)) for k in CSV_COLUMNS})
    return str(path)


def render_report(metrics: dict, summary: dict, leads: list) -> str:
    stages = summary.get("stages", {})
    accepted = sorted([l for l in leads if l.get("stage") == "ACCEPTED"],
                      key=lambda l: -(l.get("score") or 0))
    lines = [
        "# V0 Benchmark Report", "",
        f"- job_id: `{metrics['job_id']}`",
        f"- mode: {'DRY-RUN (fixtures, no network)' if metrics['dry_run'] else 'LIVE'}",
        f"- discovery raw candidates: {metrics['discovery_raw_candidates']}",
        f"- unique after dedup: {metrics['unique_after_dedup']} "
        f"(duplicate rate {metrics['duplicate_rate']})",
        f"- hard filter kept: {metrics['hard_filter_kept']} "
        f"(dropped {metrics['hard_filter_dropped']})",
        f"- qualification scored: {metrics['qualification_scored']} "
        f"(skipped {metrics['qualification_skipped']})",
        f"- enrichment: {metrics['enrichment']}",
        f"- **final leads: {metrics['final_leads']}** (review: {metrics['review_leads']})",
        f"- contact coverage: {metrics['contact_coverage_pct']}%",
        f"- email validity rate: {metrics['email_validity_rate_pct']}%",
        f"- quota units: {metrics['quota_units_total']} "
        f"({metrics['quota_units_per_final_lead']} / final lead)",
        f"- total cost: ${metrics['total_cost_usd']}",
        f"- degraded local used: {metrics['degraded_local_used']}",
        "", "## Top leads", "",
    ]
    for lead in accepted[:30]:
        lines.append(
            f"- **{lead.get('name')}** ({lead.get('city')}, {lead.get('domain')}) — "
            f"score {lead.get('score')}, tier {lead.get('tier')}, "
            f"email {lead.get('email')} [{lead.get('email_status')}], "
            f"DM {lead.get('decision_maker') or '—'}"
        )
    gates = stages.get("legal_gate", {})
    if gates:
        lines += ["", "## Legal gate", "",
                  f"- accepted: {gates.get('accepted')}, review: {gates.get('review')}, "
                  f"rejected: {gates.get('rejected')}"]
    return "\n".join(lines) + "\n"


def write_outputs(metrics: dict, summary: dict, leads: list):
    OUTPUTS_DIR.mkdir(exist_ok=True)
    report_path = OUTPUTS_DIR / "report.md"
    csv_path = OUTPUTS_DIR / "leads.csv"
    report_path.write_text(render_report(metrics, summary, leads), encoding="utf-8")
    export_csv(leads, csv_path)
    return {"report": str(report_path), "csv": str(csv_path)}
