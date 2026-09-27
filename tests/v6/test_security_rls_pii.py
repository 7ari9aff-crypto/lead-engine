"""PII vault + tenant isolation (RLS) security tests (ADR-0006, §20)."""
from __future__ import annotations

import psycopg
import pytest

from infrastructure.pii.vault import TenantVault


def test_store_decrypt_roundtrip_and_mask(org, vault):
    tv = TenantVault(vault, org)
    ref = tv.store("email", "info@alpha-dental.sa")
    plain = tv.decrypt(ref, "verification", actor="pytest")
    assert plain == "info@alpha-dental.sa"
    assert tv.masked("email", "info@alpha-dental.sa") == "i***o@alpha-dental.sa"
    assert tv.masked("phone", "+966500000001") == "+96***01"


def test_wrong_purpose_is_rejected_and_audited(org, vault, db):
    tv = TenantVault(vault, org)
    ref = tv.store("email", "x@y.sa")
    tv.decrypt(ref, "verification", actor="pytest")          # legitimate access
    with pytest.raises(PermissionError):
        tv.decrypt(ref, "marketing", actor="attacker")        # never allowed
    # audit row exists only for the legitimate access
    with db.tx(org) as conn, conn.cursor() as cur:
        rows = cur.execute(
            "SELECT purpose, actor FROM pii.pii_access_audit WHERE ref_id = %s",
            (ref,)).fetchall()
    assert [r["purpose"] for r in rows] == ["verification"]
    assert rows[0]["actor"] == "pytest"


def test_cross_tenant_vault_access_denied(org, vault, uows):
    from uuid import uuid4

    from application.usecases.onboard import OnboardOrg
    from infrastructure.repos.system import BootstrapPg

    tv = TenantVault(vault, org)
    ref = tv.store("email", "secret@tenant-a.sa")

    other = OnboardOrg(BootstrapPg(uows._db)).execute(
        f"org-{uuid4().hex[:10]}", "Other", "pro", "owner-2")
    other_vault = TenantVault(vault, other["org_id"])
    with pytest.raises((KeyError, PermissionError)):
        other_vault.decrypt(ref, "verification", actor="pytest")


def test_rls_hides_other_tenants_business_rows(org, uows, db):
    from uuid import uuid4

    from application.usecases.onboard import OnboardOrg
    from infrastructure.repos.system import BootstrapPg

    with uows(org) as tx:
        company_id = tx.repos.companies.create_company(
            str(uuid4()), "Alpha Dental", "alpha-dental.sa", "SA", "dental", "Riyadh")
        tx.repos.companies.add_identifier(company_id, "domain", "alpha-dental.sa")

    other = OnboardOrg(BootstrapPg(db)).execute(
        f"org-{uuid4().hex[:10]}", "Other", "pro", "owner-2")
    with uows(other["org_id"]) as tx:
        assert tx.repos.companies.find_by_domain("alpha-dental.sa") is None
        rows = tx.repos.projects.list_leads()
        assert rows == []

    # WITH CHECK: a row carrying ANOTHER tenant's org_id is rejected even when
    # the connection's tenant is set (the actual spoofing vector). Postgres
    # reports RLS violations as 42501 InsufficientPrivilege.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with uows(other["org_id"]) as tx:
            cur = tx.cursor
            cur.execute(
                "INSERT INTO company_identity.companies (org_id, canonical_name)"
                " VALUES (%s, 'Spoofed')",
                (org,),
            )


def test_missing_tenant_fails_closed(db):
    """No app.tenant_id set → FORCE RLS denies every business row."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM company_identity.companies")
        assert cur.fetchone()["n"] == 0
