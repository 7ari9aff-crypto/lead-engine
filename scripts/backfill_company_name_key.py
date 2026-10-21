"""Backfill company_identity.companies.name_key from canonical_name.

Writes ONLY the new, nullable name_key column. It never merges, deletes or
rewrites canonical_name (companies are append-only identity records), so it is
safe to re-run and safe to abandon half way.

It also REPORTS (never applies) groups of rows that now share a key within one
org + city: those are merge *candidates* for a human to review, not actions.

Dry-run by default:
    python scripts/backfill_company_name_key.py           # report only
    python scripts/backfill_company_name_key.py --apply   # fill name_key
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.acquisition.company import name_key  # noqa: E402


def plan(rows: list[dict]) -> dict:
    """Pure: decide updates and merge candidates from the current rows.

    rows: id, org_id, canonical_name, domain, city, name_key
    """
    updates: list[tuple[str, str | None]] = []
    skipped_generic = 0
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = name_key(r.get("canonical_name"))
        if not key:
            skipped_generic += 1          # generic name: intentionally no key
            if r.get("name_key"):         # ...and a STALE key must not keep matching
                updates.append((str(r["id"]), None))
            continue
        if r.get("name_key") != key:
            updates.append((str(r["id"]), key))
        groups[(str(r["org_id"]), (r.get("city") or "").strip().lower(), key)].append(r)

    candidates = []
    for (_org, _city, key), members in groups.items():
        if len(members) < 2:
            continue
        domains = {(m.get("domain") or "").lower() for m in members} - {""}
        # different domains = different businesses; only same/unknown-domain
        # groups are plausible duplicates
        if len(domains) > 1:
            continue
        candidates.append({"key": key, "ids": [str(m["id"]) for m in members],
                           "names": [m.get("canonical_name") for m in members]})
    return {"updates": updates, "skipped_generic": skipped_generic,
            "merge_candidates": candidates}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from scripts.backfill_vault_fingerprints import Sql
    from infrastructure.config import Settings

    sql = Sql(Settings.load())
    try:
        has_col = bool(sql.q("""SELECT 1 FROM information_schema.columns
                                WHERE table_schema = 'company_identity'
                                  AND table_name = 'companies'
                                  AND column_name = 'name_key'"""))
        if not has_col and args.apply:
            print("name_key column is missing: apply migration "
                  "20261021120000_company_name_key.sql first. Nothing written.")
            return 2
        key_expr = "name_key" if has_col else "NULL::text AS name_key"
        if not has_col:
            print("(name_key column not migrated yet: reporting only)\n")
        rows = sql.q(f"""SELECT id::text AS id, org_id::text AS org_id, canonical_name,
                                domain, city, {key_expr}
                         FROM company_identity.companies WHERE merged_into_id IS NULL""")
        result = plan(rows)
        print(f"companies scanned     : {len(rows)}")
        print(f"name_key to write     : {len(result['updates'])}")
        print(f"generic (left NULL)   : {result['skipped_generic']}")
        print(f"merge candidates      : {len(result['merge_candidates'])} (report only)")
        for c in result["merge_candidates"]:
            print("  -", c["key"], "->", c["names"])
        if not args.apply:
            print("\nDRY RUN: nothing written. Re-run with --apply.")
            return 0
        for cid, key in result["updates"]:
            val = "NULL" if key is None else "'" + key.replace("'", "''") + "'"
            sql.q(f"UPDATE company_identity.companies SET name_key = {val} "
                  f"WHERE id = '{cid}'::uuid AND name_key IS DISTINCT FROM {val}")
        print(f"\nAPPLIED: {len(result['updates'])} rows updated.")
        return 0
    finally:
        sql.close()


if __name__ == "__main__":
    raise SystemExit(main())
