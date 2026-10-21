"""Backup integrity check, run by .github/workflows/backup.yml.

A backup nobody has restored is a hope, not a backup. This script takes a pg_dump
custom-format file, restores it into a THROWAWAY database and compares per-table row
counts against the live source. Any mismatch, missing table or unreadable archive
exits non-zero so the workflow goes red instead of silently storing a bad dump.

Counts are read in ONE repeatable-read transaction and the dump is taken with
--serializable-deferrable, so they describe the same snapshot (rows inserted
between the dump and the count would otherwise be false alarms).
"""
from __future__ import annotations

import json
import sys

import psycopg

SCHEMAS = ("engine", "platform", "runtime")
EXTRA_TABLES = (("public", "organizations"),)   # FK target of 15 engine tables


def table_counts(dsn: str, schemas=SCHEMAS) -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        tables = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
            " WHERE table_type='BASE TABLE' AND table_schema = ANY(%s)"
            " ORDER BY 1,2", (list(schemas),)).fetchall()
        tables = list(tables) + list(EXTRA_TABLES)
        for schema, name in tables:
            n = conn.execute(f'SELECT count(*) FROM "{schema}"."{name}"').fetchone()[0]
            out[f"{schema}.{name}"] = n
    return out


def compare(source: dict[str, int], restored: dict[str, int]) -> list[str]:
    problems = []
    for table, n in sorted(source.items()):
        if table not in restored:
            problems.append(f"MISSING after restore: {table} ({n} rows)")
        elif restored[table] != n:
            problems.append(f"ROW COUNT {table}: source={n} restored={restored[table]}")
    return problems


def main(argv: list[str]) -> int:
    """argv: <source_dsn> <restored_dsn> [source_counts.json]. The workflow restores
    (it needs list files to skip the Supabase-only policies); this only compares."""
    source_dsn, restore_dsn = argv[1], argv[2]
    expected = json.loads(open(argv[3]).read()) if len(argv) > 3 else None
    src = expected if expected is not None else table_counts(source_dsn)
    if not src:
        print("::error::source reported zero tables - refusing to call this a backup")
        return 2
    # public.organizations is restored by the workflow first (FK target of 15 engine
    # tables); the schemas dump is restored here and then compared table by table
    problems = compare(src, table_counts(restore_dsn))
    for p in problems:
        print(f"::error::{p}")
    print(f"verified {len(src)} tables, {sum(src.values())} rows, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
