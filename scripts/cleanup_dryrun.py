"""Production-cleanup DRY RUN (decision 2026-10-04: report only, NO deletes).

Classifies every platform.organizations row as:
  definitely-synthetic — test-named slug, only fixture artifacts (fake
                         providers, test org-name patterns, zero real data)
  definitely-real      — real leads/jobs or real provider traffic
  ambiguous            — everything else (stays until reviewed by a human)

SQL runs through the Management API (the direct role cannot see RLS'd rows).
Output: a per-org evidence report. Nothing is written to the database.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.postgres.supabase_api import SupabaseSqlClient  # noqa: E402

TEST_SLUG_RE = re.compile(r"^(org-[0-9a-f]{8,12}|x-org|flow-org|pi-i-.*|test.*|q-[0-9a-f]{5})$")


def classify(q, org_id: str, slug: str) -> tuple[str, list[str]]:
    evidence: list[str] = []

    def one(query: str) -> tuple:
        r = q(query)
        return tuple(r[0].values()) if r else (0,)

    leads, last_lead = one(f"""SELECT count(*) AS n,
        max(created_at)::text AS last FROM engine.leads
        WHERE organization_id = '{org_id}'""")
    legacy_jobs = one(f"SELECT count(*) AS n FROM engine.jobs WHERE organization_id = '{org_id}'")[0]
    v6_jobs = one(f"SELECT count(*) AS n FROM runtime.jobs WHERE org_id = '{org_id}'")[0]
    fake_effects = one(f"""SELECT count(*) AS n FROM effects.effect_ledger
        WHERE org_id = '{org_id}' AND provider_id LIKE 'fake-%'""")[0]
    vault_rows = one(f"SELECT count(*) AS n FROM pii.vault WHERE org_id = '{org_id}'")[0]
    members = one(f"SELECT count(*) AS n FROM platform.members WHERE org_id = '{org_id}'")[0]
    real_traffic = one(f"""SELECT count(*) AS n FROM engine.usage_ledger
        WHERE organization_id = '{org_id}'
          AND provider NOT LIKE 'fake%' AND provider NOT LIKE 'demo%'
          AND provider != 'local_smtp'""")[0]

    synthetic_signals = 0
    if TEST_SLUG_RE.match(slug or ""):
        synthetic_signals += 2
        evidence.append(f"slug '{slug}' matches a test-naming pattern")
    if fake_effects:
        synthetic_signals += 2
        evidence.append(f"{fake_effects} fake-provider effects")
    if not leads and not legacy_jobs and not v6_jobs:
        synthetic_signals += 1
        evidence.append("zero leads and zero jobs on both planes")
    if members <= 1 and not leads:
        synthetic_signals += 1
        evidence.append("single owner, no data")
    if real_traffic:
        evidence.append("REAL provider traffic in usage_ledger")
    if leads and leads >= 50:
        evidence.append(f"{leads} leads — production-scale data")

    if real_traffic or (leads and leads >= 50):
        return "definitely-real", evidence
    if synthetic_signals >= 2:
        return "definitely-synthetic", evidence
    return "ambiguous", evidence


def main() -> int:
    settings = Settings.load()
    token = os.environ.get("LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN", "").strip()
    ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    client = SupabaseSqlClient(token, ref)

    import time

    def q(query: str) -> list[dict]:
        for attempt in range(6):
            try:
                return client.query(query)
            except Exception as exc:
                if "429" not in str(exc) or attempt == 5:
                    raise
                time.sleep(15 * (attempt + 1))
        raise RuntimeError("unreachable")

    orgs = q("""SELECT id::text, slug, name, plan_code, created_at::date AS created
                FROM platform.organizations ORDER BY created_at""")
    print(f"platform.organizations: {len(orgs)} rows\n")
    buckets: dict[str, list] = {"definitely-real": [], "definitely-synthetic": [],
                                "ambiguous": []}
    for org in orgs:
        verdict, evidence = classify(q, org["id"], org["slug"])
        buckets[verdict].append((org, evidence))
    for verdict in ("definitely-real", "definitely-synthetic", "ambiguous"):
        rows = buckets[verdict]
        print(f"=== {verdict}: {len(rows)} ===")
        for org, evidence in rows:
            print(f"  {org['id']} | {org['slug']} | {org['name']} | {org['created']}")
            for e in evidence:
                print(f"      - {e}")
        print()
    print("NO ROWS WERE MODIFIED. Only rows listed as definitely-synthetic AND")
    print("re-confirmed by a human get a targeted delete pass (org + its")
    print("leads/jobs/events, audit history preserved).")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
