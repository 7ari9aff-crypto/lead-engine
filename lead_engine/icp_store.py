"""ICP versioning in the database (per the 2026-09-13 architecture decision).

The ICP is no longer a YAML file: it is a versioned, org-scoped row. YAML
files under config/icp/ remain an *import source* only. Exactly one version
per slug is `active`; activating a version retires the previous one. The
agent qualifies against the ACTIVE definition — changing it later must
re-qualify from stored facts, never re-discover.
"""
import json

from .db import utcnow


class ICPStore:
    def __init__(self, db):
        self.db = db

    def _org(self):
        org = getattr(self.db, "org_id", None)
        if getattr(self.db, "dialect", "sqlite") == "sqlite":
            return org or "shared"
        return org

    def create_version(self, slug: str, definition: dict, *,
                       source: str = "manual", created_by: str | None = None,
                       version: str | None = None) -> dict:
        if not slug or not isinstance(definition, dict):
            raise ValueError("slug and a definition dict are required")
        slug = slug.strip().lower().replace(" ", "-")
        if not version:
            rows = self.list_versions(slug)
            version = f"v{len(rows) + 1}"
        org = self._org()
        dup_sql = ("SELECT icp_version_id FROM icp_versions WHERE slug=? AND version=?")
        dup_params = [slug, version]
        if org is None:
            dup_sql += " AND organization_id IS NULL"
        else:
            dup_sql += " AND organization_id=?"
            dup_params.append(org)
        if self.db.one(dup_sql, dup_params):
            raise ValueError(f"ICP version already exists: {slug} {version}")
        icp_version_id = f"icp_{slug}_{version}".replace(" ", "")
        now = utcnow()
        self.db.execute(
            "INSERT INTO icp_versions (icp_version_id, organization_id, slug,"
            " version, definition, source, status, created_by, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,'draft',?,?,?)",
            (icp_version_id, org, slug, version,
             json.dumps(definition, ensure_ascii=False, default=str),
             source, created_by, now, now))
        return self.get(icp_version_id)

    def activate(self, icp_version_id: str) -> dict:
        row = self.get(icp_version_id)
        if not row:
            raise ValueError(f"ICP version not found: {icp_version_id}")
        now = utcnow()
        org_sql, org_params = self._org_filter_sql()
        self.db.execute(
            "UPDATE icp_versions SET status='retired', updated_at=?"
            f" WHERE slug=? AND status='active'{org_sql}",
            (now, row["slug"], *org_params))
        self.db.execute(
            "UPDATE icp_versions SET status='active', updated_at=? WHERE icp_version_id=?",
            (now, icp_version_id))
        return self.get(icp_version_id)

    def active(self, slug: str) -> dict | None:
        sql, params = "SELECT * FROM icp_versions WHERE slug=? AND status='active'", [slug]
        org_sql, org_params = self._org_filter_sql()
        row = self.db.one(sql + org_sql + " ORDER BY created_at DESC LIMIT 1",
                          params + org_params)
        return self._parse(row) if row else None

    def get(self, icp_version_id: str) -> dict | None:
        return self._parse(self.db.one(
            "SELECT * FROM icp_versions WHERE icp_version_id=?", (icp_version_id,)))

    def list_versions(self, slug: str) -> list[dict]:
        sql, params = "SELECT * FROM icp_versions WHERE slug=?", [slug]
        org_sql, org_params = self._org_filter_sql()
        rows = self.db.query(sql + org_sql + " ORDER BY created_at DESC",
                             params + org_params)
        return [self._parse(r) for r in rows]

    def _org_filter_sql(self) -> tuple[str, list]:
        org = self._org()
        if getattr(self.db, "dialect", "sqlite") == "sqlite":
            return " AND organization_id = ?", [org or "shared"]
        if org:
            return " AND organization_id = ?", [org]
        return " AND organization_id IS NULL", []

    @staticmethod
    def _parse(row: dict | None) -> dict | None:
        if not row:
            return None
        raw = row.get("definition")
        if isinstance(raw, str):
            try:
                row["definition"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return row
