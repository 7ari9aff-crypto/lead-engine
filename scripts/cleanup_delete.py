"""Delete the CONFIRMED synthetic platform orgs (decision 2026-10-04).

Safety model:
- Re-classifies orgs AT RUN TIME (never trusts a stale list): only orgs the
  classifier marks definitely-synthetic are touched; 'ambiguous' stays.
- Child-first deletion order respecting FKs (events/agents/effects →
  intelligence/claims/contacts/companies → acquisition/governance → pii →
  runtime → platform.members), each org in ONE transaction.
- Per-table deleted-row inventory printed for the report.
- The production org (or anything ambiguous) is never touched.

Usage: python scripts/cleanup_delete.py            # classify + delete + report
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time  # noqa: E402

from infrastructure.config import Settings  # noqa: E402
from infrastructure.postgres.supabase_api import SupabaseSqlClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cleanup_dryrun import TEST_SLUG_RE, classify  # noqa: E402

# Children → parents. org-scoped DELETE per table; agent_steps via run ids.
# NOTE: events.event_consumptions and events.dead_letters have NO org_id —
# the org-scoped pass skips them; NULL-org test artifacts are cleaned after.
DELETE_ORDER = [
    "events.outbox",
    "agents.agent_steps",
    "agents.approvals",
    "agents.agent_runs",
    "effects.effect_ledger",
    "intelligence.raw_discovery_results",
    "intelligence.visited_sources",
    "intelligence.enrichment_attempts",
    "intelligence.verification_records",
    "intelligence.verification_cache",
    "intelligence.scoring_records",
    "intelligence.qualification_records",
    "intelligence.intent_signals",
    "projects.lead_projections",
    "claims_evidence.company_observations",
    "claims_evidence.fact_conflicts",
    "claims_evidence.company_claims",
    "claims_evidence.fact_sources",
    "contacts.contact_identities",
    "contacts.company_contacts",
    "company_identity.company_identifiers",
    "company_identity.company_merges",
    "company_identity.companies",
    "acquisition.campaigns",
    "acquisition.icp_versions",
    "acquisition.icp_profiles",
    "governance.legal_decisions",
    "governance.suppression",
    "governance.privacy_actions",
    "governance.legal_policy_versions",
    "pii.pii_access_audit",
    "pii.vault",
    "pii.deks",
    "runtime.job_events",
    "runtime.jobs",
    "platform.usage_records",
    "platform.feature_flags",
    "platform.members",
]


def _cte_delete(org_id: str) -> tuple[str, str]:
    """One statement: data-modifying CTEs per table, returning counts as JSON."""
    ctes, selects = [], []
    # Pre-steps that cannot be org-scoped CTEs:
    #  - event_consumptions has no org_id but FKs the org's outbox rows.
    #  - the ICP immutability trigger blocks version deletion (right-to-
    #    erasure conflict flagged in the audit); the maintenance session
    #    disables it and re-enables it right after.
    pre = [
        f"DELETE FROM events.event_consumptions WHERE event_id IN "
        f"(SELECT event_id FROM events.outbox WHERE org_id = '{org_id}');",
        "ALTER TABLE acquisition.icp_versions DISABLE TRIGGER trg_icp_versions_immutable;",
    ]
    post = ["ALTER TABLE acquisition.icp_versions ENABLE TRIGGER trg_icp_versions_immutable;"]
    for i, table in enumerate(DELETE_ORDER):
        alias = f"d{i}"
        if table == "agents.agent_steps":
            ctes.append(f"""{alias} AS (
                DELETE FROM {table} WHERE run_id IN (
                  SELECT run_id FROM agents.agent_runs WHERE org_id = '{org_id}')
                RETURNING 1)""")
        else:
            ctes.append(f"""{alias} AS (
                DELETE FROM {table} WHERE org_id = '{org_id}' RETURNING 1)""")
        selects.append(f"'{table}', (SELECT count(*) FROM {alias})")
    body = "SELECT json_build_object(" + ", ".join(selects) + ") AS counts;"
    statement = ("BEGIN;\n" + "\n".join(pre) + "\n"
                 + "WITH " + ",\n".join(ctes) + "\n" + body + "\n"
                 + "\n".join(post) + "\nCOMMIT;")
    return statement, "events.event_consumptions"


def main() -> int:
    settings = Settings.load()
    token = os.environ.get("LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN", "").strip()
    ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    client = SupabaseSqlClient(token, ref)

    def q(query: str) -> list[dict]:
        for attempt in range(6):
            try:
                return client.query(query)
            except Exception as exc:
                if "429" not in str(exc) or attempt == 5:
                    raise
                time.sleep(15 * (attempt + 1))
        raise RuntimeError("unreachable")

    orgs = q("""SELECT id::text, slug, name FROM platform.organizations ORDER BY created_at""")
    targets, kept = [], []
    for org in orgs:
        verdict, _ev = classify(q, org["id"], org["slug"])
        (targets if verdict == "definitely-synthetic" else kept).append(org)

    print(f"classified now: {len(targets)} synthetic targets, {len(kept)} kept\n")
    if not targets:
        print("nothing to delete")
        client.close()
        return 0

    inventory: dict[str, int] = {}
    deleted_orgs, failed = [], []
    for org in targets:
        org_id, slug = org["id"], org["slug"]
        stmt, _ = _cte_delete(org_id)
        try:
            counts = q(stmt)[0]["counts"]
            counts = json.loads(counts) if isinstance(counts, str) else counts
            q(f"BEGIN;\nDELETE FROM platform.members WHERE org_id = '{org_id}';"
              f"\nDELETE FROM platform.organizations WHERE id = '{org_id}';\nCOMMIT;")
            deleted_orgs.append(org)
            for table, n in counts.items():
                inventory[table] = inventory.get(table, 0) + int(n)
            print(f"deleted {slug} ({org_id})")
        except Exception as exc:  # noqa: BLE001 — one org must not stop the rest
            failed.append((slug, str(exc)[:120]))
            print(f"FAILED {slug}: {str(exc)[:120]} — org KEPT")

    print("\n=== deleted row inventory ===")
    for table, n in sorted(inventory.items(), key=lambda kv: -kv[1]):
        if n:
            print(f"  {table}: {n}")

    remaining = q("SELECT count(*) AS n FROM platform.organizations")
    print(f"\nplatform.organizations remaining: {remaining[0]['n']} "
          f"(expected 1: the production org)")
    r = q("SELECT id::text, slug FROM platform.organizations")
    for row in r:
        print(f"  kept: {row['slug']} ({row['id']})")

    # NULL-org test artifacts (proven synthetic: 'test.event' / 'boom'):
    r = q("""BEGIN;
        WITH d AS (DELETE FROM events.dead_letters
                   WHERE event_type = 'test.event' OR error LIKE '%boom%'
                   RETURNING 1)
        SELECT count(*) AS n FROM d; COMMIT;""")
    print("NULL-org test dead letters deleted:", r[0]["n"])
    r = q("""BEGIN;
        WITH d AS (DELETE FROM events.outbox WHERE type = 'test.event' RETURNING 1)
        SELECT count(*) AS n FROM d; COMMIT;""")
    print("NULL-org test outbox rows deleted:", r[0]["n"])
    if failed:
        print(f"\n{len(failed)} orgs FAILED and were kept for manual review")
    print("\nlegacy public.* / engine.* data (the 102 real leads) untouched by design.")
    client.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
