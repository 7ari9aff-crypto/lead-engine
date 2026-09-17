#!/usr/bin/env python
"""Restore-verification script — closes the PITR drill (runbook-restore §5).

After a Supabase point-in-time restore you end up with a *new* database URL
(the original project is never rewound in place). This script compares the
restored snapshot against the live one so the drill has an auditable result:

    python scripts/verify_restore.py \
        --live "$SUPABASE_DB_URL" \
        --restored "$RESTORED_DB_URL" \
        --save docs/drill-1.json

It checks row counts for the tables the runbook names (engine.jobs,
public.organizations) plus a few tenant-scoped tables, and writes a JSON
record of the drill (date, duration, verdict) for the runbook log.

Exit code 0 = verdict PASS (counts match within tolerance), 1 = FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

# Tables compared per the runbook. (schema, table, tenant_scoped)
TABLES: list[tuple[str, str, bool]] = [
    ("public", "organizations", False),
    ("public", "organization_members", True),
    ("public", "organization_provider_credentials", True),
    ("engine", "jobs", True),
    ("engine", "leads", True),
    ("engine", "usage_ledger", True),
    ("engine", "activity_events", True),
]

# Supabase PITR restores are not byte-identical to the live DB when traffic
# continues after the restore point — allow a small drift so the drill verdict
# is about "did we restore the data", not about a moving target.
TOLERANCE = 0.02  # 2%


def _connect(dsn: str):
    import psycopg

    # statement_timeout keeps a hung restore from freezing the drill; the
    # restricted token (no BYPASSRLS) is what the runbook prescribes.
    conn = psycopg.connect(dsn, connect_timeout=15, options="-c statement_timeout=30000")
    return conn


def count_rows(dsn: str) -> dict[str, int | None]:
    """Row counts per table. None = table missing (schema drift)."""
    out: dict[str, int | None] = {}
    with _connect(dsn) as conn, conn.cursor() as cur:
        for schema, table, _tenant in TABLES:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                out[f"{schema}.{table}"] = int(cur.fetchone()[0])
            except Exception:
                conn.rollback()
                out[f"{schema}.{table}"] = None
    return out


def compare(live: dict, restored: dict) -> tuple[str, list[dict]]:
    rows: list[dict] = []
    mismatches = 0
    for key, live_n in live.items():
        rest_n = restored.get(key)
        ok = None
        if live_n is None or rest_n is None:
            ok = False  # schema drift is a hard failure
        elif live_n == 0:
            ok = rest_n == 0
        else:
            drift = abs(rest_n - live_n) / live_n
            ok = drift <= TOLERANCE
        if not ok:
            mismatches += 1
        rows.append({"table": key, "live": live_n, "restored": rest_n, "ok": ok})
    verdict = "PASS" if mismatches == 0 else "FAIL"
    return verdict, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", default=os.environ.get("SUPABASE_DB_URL", ""),
                    help="live Postgres DSN (default $SUPABASE_DB_URL)")
    ap.add_argument("--restored", required=True,
                    help="restored-project Postgres DSN")
    ap.add_argument("--save", default="", help="write the drill record JSON here")
    args = ap.parse_args()

    if not args.live or not args.restored:
        print("error: --live and --restored are both required", file=sys.stderr)
        return 2

    started = time.time()
    print("counting live tables ...")
    live = count_rows(args.live)
    print("counting restored tables ...")
    restored = count_rows(args.restored)
    verdict, rows = compare(live, restored)
    duration_s = round(time.time() - started, 1)

    record = {
        "drill": 1,
        "date": datetime.now(timezone.utc).isoformat(),
        "duration_s": duration_s,
        "verdict": verdict,
        "tolerance": TOLERANCE,
        "tables": rows,
    }
    print(json.dumps(record, indent=2, ensure_ascii=False))

    if args.save:
        os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
        print(f"saved -> {args.save}")

    # Copy the one-line result into the runbook's drill log by hand.
    print(f"VERDICT: {verdict} in {duration_s}s — "
          f"paste into docs/runbook-restore.md §5")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
