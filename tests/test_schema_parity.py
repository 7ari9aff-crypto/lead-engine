"""Static guard: every table the application's SQL touches must exist in BOTH
schema sources.

Why this exists: the app connects to Postgres with `search_path=engine`
(lead_engine/db_pg.py), while `lead_engine/db.py` carries a parallel SQLite
SCHEMA. Those two drifted - `audit_logs` was written by three call sites
(db.py Database.audit, db_pg.py PgDatabase.audit, codeops.py) but existed only
in the SQLite schema and in Supabase's `public`, never in `engine`. Every
review approve/reject/requalify therefore committed its mutation and then
raised UndefinedTable from the audit call, returning HTTP 500 with no audit
record. All 331 tests passed because SQLite has the table: the defect was
production-only, which is precisely the class of bug CI cannot see.

This test needs no database. It compares names, so it runs anywhere.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "lead_engine"
MIGRATIONS = ROOT / "supabase" / "migrations"

# `INSERT INTO t` / `UPDATE t SET` / `FROM t WHERE` - anchored to the tokens
# that follow a table name, so prose and Python imports do not match.
_REF = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|FROM|JOIN)\s+([a-z][a-z0-9_]{2,})\b"
    r"(?=\s+(?:SET|WHERE|GROUP|ORDER|LIMIT|VALUES|ON|\(|;|$))",
    re.IGNORECASE,
)
# Only lines that look like SQL, to keep docstrings and `from x import y` out.
_SQLISH = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE)\b", re.I)
_DDL_TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[\w.]+\.)?([a-z][a-z0-9_]*)", re.I)

# Not app-owned tables: introspection and Postgres-internal targets.
EXTERNAL = {
    "information_schema", "pg_class", "pg_index", "pg_policies", "pg_roles",
    "pg_tables", "sqlite_master", "unnest", "generate_series",
}


def _python_sql_tables() -> set[str]:
    found: set[str] = set()
    for path in PKG.rglob("*.py"):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not (_SQLISH.search(stripped) and (stripped.startswith(('"', "'", "f'", 'f"'))
                                                  or '"""' not in stripped)):
                continue
            for m in _REF.finditer(stripped):
                found.add(m.group(1).lower())
    return found


def _sqlite_schema_tables() -> set[str]:
    src = (PKG / "db.py").read_text(encoding="utf-8")
    return {m.group(1).lower() for m in _DDL_TABLE.finditer(src)}


def _migration_tables() -> set[str]:
    names: set[str] = set()
    for sql in sorted(MIGRATIONS.glob("*.sql")):
        names |= {m.group(1).lower() for m in _DDL_TABLE.finditer(sql.read_text(encoding="utf-8"))}
    return names


# Known, deliberately-unfixed divergence, discovered by this test on 2026-09-25.
# These five tables exist in the `engine` schema and are written by the code,
# but were never added to lead_engine/db.py's SQLite SCHEMA - so any local dev
# or test path that touches the outbox / notifications / webhook delivery /
# event-consumption / tenant-provisioning features fails with "no such table"
# while the same code works in production. SQLite parity is not the property
# that caused the audit outage, so it is xfailed rather than silently dropped:
# strict=True means adding these tables to SCHEMA flips XPASS into a failure
# and forces the marker to be removed.
SQLITE_ONLY_GAPS = [
    "event_consumptions", "notifications", "outbox",
    "tenant_provisioning", "webhook_deliveries",
]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "5 engine tables referenced by the code are absent from the SQLite "
        "SCHEMA (gap register: SQLite/Postgres dual-model divergence, reverse "
        "direction of the audit_logs outage). Fix by adding them to "
        "lead_engine/db.py SCHEMA, then delete this marker."
    ),
)
def test_referenced_tables_are_defined_in_sqlite_schema():
    """A table must be in db.py SCHEMA or the SQLite path breaks the suite."""
    missing = sorted(_python_sql_tables() - _sqlite_schema_tables() - EXTERNAL)
    assert missing == [], (
        "SQL references tables absent from lead_engine/db.py SCHEMA: "
        f"{missing}. Add them to SCHEMA or drop the reference."
    )
    assert set(missing) <= set(SQLITE_ONLY_GAPS), f"new SQLite gaps beyond the known set: {missing}"


def test_referenced_tables_are_created_by_migrations():
    """A table must be in supabase/migrations or production hits UndefinedTable.

    This is the assertion that would have caught the audit_logs outage.
    """
    missing = sorted(_python_sql_tables() - _migration_tables() - EXTERNAL)
    assert not missing, (
        "SQL references tables that no migration creates, so they do not "
        f"exist in the `engine` schema at runtime: {missing}. Add a migration "
        "to supabase/migrations/."
    )


def test_both_sources_agree_on_audit_logs():
    """Pinned regression for the exact outage, independent of the parsers above."""
    assert "audit_logs" in _sqlite_schema_tables(), "audit_logs vanished from SQLite SCHEMA"
    assert "audit_logs" in _migration_tables(), "audit_logs vanished from supabase/migrations"


# ---- RLS posture guard (plan W4b) -------------------------------------------
#
# Migration 20260911000007_rls_engine.sql enables + forces `tenant_isolation`
# for EVERY table that has an organization_id column *at the time it ran*
# (information_schema loop). Tables created by later migrations are protected
# individually (truth_layer re-mirrors the loop over an explicit array;
# research_jobs uses a direct ALTER). The residual risk is a FUTURE migration
# that adds an org-scoped table and forgets RLS — the exact shape of the
# audit_logs outage, one layer up. This guard pins the invariant statically.

_RLS_ENABLE = re.compile(r"\benable\s+row\s+level\s+security\b", re.IGNORECASE)
_ARRAY_MEMBER = re.compile(r"array\[([^\]]*)\]", re.IGNORECASE)
_ORG_COLUMN = re.compile(r"^\s*organization_id\b", re.MULTILINE | re.IGNORECASE)
_ALTER_ADD_ORG = re.compile(
    r"alter\s+table\s+(?:if\s+exists\s+)?(?:engine\.)?([a-z][a-z0-9_]*)\s+"
    r"add\s+column\s+(?:if\s+not\s+exists\s+)?organization_id\b",
    re.IGNORECASE)
_CREATE_TABLE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:engine\.)?([a-z][a-z0-9_]*)\s*\(",
    re.IGNORECASE,
)

# Migration 007's information_schema loop protects every org table created at
# or before it; later tables must protect themselves (or be exempted).
_LOOP_007_STAMP = "20260911000007"

# audit_logs: deliberate RLS exemption — the write path must never fail and a
# __no_org__ sentinel context has no GUC to satisfy a WITH CHECK (see
# 20260925000002_audit_logs_read_path.sql and the gap register).
RLS_EXEMPT = {"audit_logs"}


def _migration_files() -> list[tuple[str, Path]]:
    return [(p.name[:14], p) for p in sorted(MIGRATIONS.glob("*.sql"))]


def _created_org_tables() -> dict[str, str]:
    """table -> earliest migration stamp granting it an organization_id column,
    via either CREATE TABLE block or ALTER TABLE ... ADD COLUMN organization_id
    (agents/activity_events get theirs from 20260911000006_tenant_scoping)."""
    created: dict[str, str] = {}
    for stamp, path in _migration_files():
        sql = path.read_text(encoding="utf-8", errors="ignore")
        for m in _ALTER_ADD_ORG.finditer(sql):
            created.setdefault(m.group(1).lower(), stamp)
        for m in _CREATE_TABLE.finditer(sql):
            depth, i = 1, m.end()
            while i < len(sql) and depth:
                depth += sql[i] == "("
                depth -= sql[i] == ")"
                i += 1
            if _ORG_COLUMN.search(sql[m.end():i - 1]):
                created.setdefault(m.group(1).lower(), stamp)
    return created


def _rls_enabled_tables() -> set[str]:
    """Tables with explicit protection evidence in migration text: either a
    direct ALTER ... ENABLE ROW LEVEL SECURITY naming the table, or membership
    of an array[] literal in a file that also enables RLS (the truth_layer
    foreach pattern)."""
    direct = re.compile(
        r"alter\s+table\s+(?:engine\.)?([a-z][a-z0-9_]*)\s+enable\s+row\s+level\s+security",
        re.IGNORECASE)
    enabled: set[str] = set()
    for _, path in _migration_files():
        sql = path.read_text(encoding="utf-8", errors="ignore")
        if not _RLS_ENABLE.search(sql):
            continue
        enabled |= {m.group(1).lower() for m in direct.finditer(sql)}
        for arr in _ARRAY_MEMBER.finditer(sql):
            enabled |= {t.strip().strip("'\"").lower()
                        for t in arr.group(1).split(",") if t.strip()}
    return enabled


def test_org_scoped_migrations_enable_rls():
    """Every migration-created organization_id table is RLS-protected: covered
    by the 007 loop (created early enough), named in an explicit ENABLE, or on
    the documented exemption list. A new org table arriving without one of
    those fails here instead of shipping an unisolated table."""
    from lead_engine.db_pg import ORG_TABLES

    created = _created_org_tables()
    missing_org_decl = sorted(ORG_TABLES - set(created))
    assert not missing_org_decl, (
        f"ORG_TABLES entries not created with an organization_id column in any "
        f"migration: {missing_org_decl}")

    protected = _rls_enabled_tables()
    uncovered = sorted(
        t for t, stamp in created.items()
        if stamp > _LOOP_007_STAMP and t not in protected and t not in RLS_EXEMPT
    )
    assert not uncovered, (
        f"organization_id tables created after the 007 auto-RLS loop with no "
        f"ENABLE ROW LEVEL SECURITY migration statement: {uncovered}. Add the "
        f"ALTER (or the array-loop form) to a migration, or document the "
        f"exemption in RLS_EXEMPT with register rationale.")
