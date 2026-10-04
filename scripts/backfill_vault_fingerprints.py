"""Backfill pii.vault.secret_fingerprint and reconcile duplicates.

Every vault row gets a keyed HMAC-SHA256 fingerprint of its PLAINTEXT,
computed in-memory with the deployment master key — the plaintext never
leaves this process and no access-audit row is written (this is schema
maintenance, not a purpose-bound read).

SQL runs through the Supabase Management API when credentials exist
(bypasses RLS, needed to enumerate tenants); falls back to the direct DSN.

Dry-run by default: reports per-org counts and duplicate groups.
    python scripts/backfill_vault_fingerprints.py            # report only
    python scripts/backfill_vault_fingerprints.py --apply    # backfill + reconcile + unique index
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from infrastructure.config import Settings  # noqa: E402
from infrastructure.pii.vault import _fingerprint, _unwrap_dek  # noqa: E402
from infrastructure.postgres.supabase_api import SupabaseSqlClient  # noqa: E402


class Sql:
    """One query surface: Management API when configured, direct DSN otherwise."""

    def __init__(self, settings: Settings):
        token = os.environ.get("LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN", "").strip()
        ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
        self._client: SupabaseSqlClient | None = None
        self._conn = None
        if token and ref:
            self._client = SupabaseSqlClient(token, ref)
        else:
            import psycopg

            self._conn = psycopg.connect(
                settings.admin_database_url or settings.database_url,
                row_factory=psycopg.rows.dict_row)

    def q(self, sql: str) -> list[dict]:
        if self._client is not None:
            import time

            for attempt in range(6):
                try:
                    return self._client.query(sql)
                except Exception as exc:
                    if "429" not in str(exc) or attempt == 5:
                        raise
                    time.sleep(15 * (attempt + 1))
            raise RuntimeError("unreachable")
        with self._conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        elif self._conn is not None:
            self._conn.close()


def _orgs(sql: Sql) -> list[str]:
    # pii.vault is FORCE-RLS'd, so the org list comes from the system plane —
    # every org with vault rows ran pipeline jobs.
    rows = sql.q("""SELECT DISTINCT org_id::text AS org_id FROM (
                      SELECT org_id FROM runtime.jobs
                      UNION SELECT org_id FROM effects.effect_ledger
                    ) s WHERE org_id IS NOT NULL""")
    return [r["org_id"] for r in rows]


def _as_bytes(v) -> bytes:
    """Management API returns bytea as a node-style Buffer object
    ({"type": "Buffer", "data": [..]}); the direct DSN returns bytes."""
    if isinstance(v, bytes):
        return v
    if isinstance(v, dict) and isinstance(v.get("data"), list):
        return bytes(v["data"])
    if isinstance(v, str):
        return bytes.fromhex(v[2:] if v.startswith("\\x") else v)
    return bytes(v)


def _vault_rows(sql: Sql) -> list[dict]:
    # bypassrls role: no tenant GUC needed for maintenance.
    return sql.q("""SELECT v.id::text, v.org_id::text AS org_id, v.kind,
                           v.ciphertext, v.iv, d.wrapped_dek
                    FROM pii.vault v JOIN pii.deks d ON d.id = v.dek_id
                    ORDER BY v.created_at, v.id""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="backfill fingerprints, reconcile duplicates, create the unique index")
    args = parser.parse_args()

    settings = Settings.load()
    master = AESGCM(settings.master_key)
    master_key = settings.master_key
    sql = Sql(settings)

    rows = _vault_rows(sql)
    orgs = _orgs(sql)
    by_org: dict[str, list[dict]] = {}
    for r in rows:
        by_org.setdefault(r["org_id"], []).append(r)
    # Iterate over orgs that ACTUALLY have vault rows — the jobs/effects
    # enumeration misses orgs whose jobs were cleaned but vault rows remain.

    seen: dict[str, str] = {}          # fingerprint -> kept vault id (global)
    dups: list[tuple[str, str]] = []   # (dup_id, kept_id)
    updates: list[tuple[str, str]] = []  # (vault_id, fingerprint)

    for org in by_org:
        org_rows = by_org.get(org, [])
        if not org_rows:
            continue
        org_seen: dict[str, str] = {}
        org_dups = 0
        for r in org_rows:
            dek = _unwrap_dek(master, _as_bytes(r["wrapped_dek"]))
            value = AESGCM(dek).decrypt(_as_bytes(r["iv"]), _as_bytes(r["ciphertext"]), None)
            fp = _fingerprint(master_key, r["kind"], value.decode("utf-8"))
            updates.append((r["id"], fp))
            kept = org_seen.get(fp)
            if kept:
                dups.append((r["id"], kept))
                org_dups += 1
                continue
            org_seen[fp] = r["id"]
        total_note = f"{len(org_rows)} rows, {org_dups} duplicates"
        print(f"org {org}: {total_note}")
        for dup_id, kept_id in dups[-5:]:
            print(f"    dup {dup_id} -> kept {kept_id}")

    print(f"\n{'APPLY' if args.apply else 'DRY RUN'}: {len(rows)} rows, "
          f"{len(dups)} duplicates, {len(updates)} fingerprints to write")

    if not args.apply:
        sql.close()
        return 0

    # ONE request for the whole backfill (the Management API throttles hard).
    stmts = ["BEGIN;"] + [
        f"UPDATE pii.vault SET secret_fingerprint = '{fp}' WHERE id = '{vid}';"
        for vid, fp in updates] + ["COMMIT;"]
    sql.q("\n".join(stmts))
    print("fingerprints written:", len(updates))
    # Re-point contact identities at the kept row, then drop redundant rows
    # (their audit rows go too — FK requires it; the kept row keeps the
    # canonical access history for that secret).
    r = sql.q("""WITH dups AS (
                   SELECT id, row_number() OVER (PARTITION BY org_id, kind, secret_fingerprint
                                                 ORDER BY created_at, id) AS rn,
                          first_value(id) OVER (PARTITION BY org_id, kind, secret_fingerprint
                                                ORDER BY created_at, id) AS kept_id
                   FROM pii.vault WHERE secret_fingerprint IS NOT NULL)
                 UPDATE contacts.contact_identities i
                    SET pii_ref_id = d.kept_id
                   FROM dups d
                  WHERE i.pii_ref_id = d.id AND d.rn > 1
                 RETURNING 1""")
    print("re-pointed contact identities:", len(r))
    r = sql.q("""WITH dups AS (
                   SELECT id, row_number() OVER (PARTITION BY org_id, kind, secret_fingerprint
                                                 ORDER BY created_at, id) AS rn
                   FROM pii.vault WHERE secret_fingerprint IS NOT NULL)
                 DELETE FROM pii.pii_access_audit a USING dups d
                  WHERE a.ref_id = d.id AND d.rn > 1 RETURNING 1""")
    print("deleted duplicate audit rows:", len(r))
    r = sql.q("""WITH dups AS (
                   SELECT id, row_number() OVER (PARTITION BY org_id, kind, secret_fingerprint
                                                 ORDER BY created_at, id) AS rn
                   FROM pii.vault WHERE secret_fingerprint IS NOT NULL)
                 DELETE FROM pii.vault v USING dups d
                  WHERE v.id = d.id AND d.rn > 1 RETURNING 1""")
    print("deleted duplicate vault rows:", len(r))
    r = sql.q("SELECT count(*) AS n FROM pii.vault WHERE secret_fingerprint IS NULL")
    if r[0]["n"]:
        print(f"ABORT: {r[0]['n']} rows still without fingerprint — unique index NOT created")
        sql.close()
        return 1
    sql.q("""CREATE UNIQUE INDEX IF NOT EXISTS ux_vault_fingerprint
             ON pii.vault (org_id, kind, secret_fingerprint)""")
    print("unique index created")
    print(f"DONE: {len(rows)} rows scanned, {len(dups)} duplicates reconciled")
    sql.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
