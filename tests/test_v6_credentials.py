"""V6 credential hydration: same store + format as legacy, but it must say why
nothing loaded, and V6 entry points must not import lead_engine to do it."""
import base64
from pathlib import Path

import pytest

from infrastructure.credentials import hydrate_environment

ORG = "fc4505fe-382e-4df9-bc2a-f97ae17590db"
KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()
ROOT = Path(__file__).resolve().parent.parent


def _legacy_encrypt(plain, monkeypatch):
    """Encrypt with the LEGACY writer, so we prove the formats stay compatible."""
    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY", KEY)
    from lead_engine.secrets import encrypt_secret
    return encrypt_secret(plain)


def _env(**kw):
    return {"LEAD_ENGINE_ENCRYPTION_KEY": KEY, **kw}


def test_reads_what_the_legacy_writer_stored(monkeypatch):
    rows = [{"env_key": "TAVILY_API_KEY", "encrypted_value": _legacy_encrypt("tvly-secret-1", monkeypatch)},
            {"env_key": "GEMINI_API_KEY", "encrypted_value": _legacy_encrypt("gem-secret-2", monkeypatch)}]
    env = _env()
    res = hydrate_environment(lambda org: rows, ORG, environ=env)
    assert env["TAVILY_API_KEY"] == "tvly-secret-1" and env["GEMINI_API_KEY"] == "gem-secret-2"
    assert res.count == 2 and set(res.loaded) == {"TAVILY_API_KEY", "GEMINI_API_KEY"} and res.reason is None


def test_summary_never_contains_a_secret_value(monkeypatch):
    rows = [{"env_key": "TAVILY_API_KEY", "encrypted_value": _legacy_encrypt("tvly-TOP-SECRET", monkeypatch)}]
    res = hydrate_environment(lambda org: rows, ORG, environ=_env())
    assert "TOP-SECRET" not in res.summary() and "TOP-SECRET" not in repr(res)
    assert "TAVILY_API_KEY" in res.summary()          # names are fine


def test_explicit_env_is_never_overwritten(monkeypatch):
    rows = [{"env_key": "TAVILY_API_KEY", "encrypted_value": _legacy_encrypt("from-db", monkeypatch)}]
    env = _env(TAVILY_API_KEY="explicit")
    res = hydrate_environment(lambda org: rows, ORG, environ=env)
    assert env["TAVILY_API_KEY"] == "explicit"
    assert res.count == 0 and res.skipped_existing == ("TAVILY_API_KEY",)


def test_empty_store_is_reported_not_silent():
    res = hydrate_environment(lambda org: [], ORG, environ=_env())
    assert res.count == 0 and res.reason is None
    assert "loaded=0" in res.summary()                # the line that was missing in production


@pytest.mark.parametrize("env,org,needle", [
    ({}, ORG, "ENCRYPTION_KEY not set"),
    (_env(), None, "ORG_ID not set"),
    ({"LEAD_ENGINE_ENCRYPTION_KEY": "!!!not-base64!!!"}, ORG, "not valid base64"),
    ({"LEAD_ENGINE_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"short").decode()}, ORG, "invalid length"),
])
def test_every_misconfiguration_has_a_named_reason(env, org, needle):
    res = hydrate_environment(lambda o: [], org, environ=dict(env))
    assert res.count == 0 and needle in (res.reason or "")


def test_unreadable_store_returns_a_reason_instead_of_raising():
    def boom(org):
        raise RuntimeError("connection refused: postgres://user:PASSWORD@host/db")
    res = hydrate_environment(boom, ORG, environ=_env())
    assert res.count == 0 and "unreadable" in res.reason
    assert "PASSWORD" not in res.summary()            # exception text (may hold a DSN) is not echoed


def test_one_bad_row_does_not_block_the_good_ones(monkeypatch):
    rows = [{"env_key": "BROKEN_KEY", "encrypted_value": "zz-not-hex"},
            {"env_key": "TAVILY_API_KEY", "encrypted_value": _legacy_encrypt("ok", monkeypatch)}]
    env = _env()
    res = hydrate_environment(lambda org: rows, ORG, environ=env)
    assert env["TAVILY_API_KEY"] == "ok" and res.undecryptable == ("BROKEN_KEY",)
    assert "BROKEN_KEY" not in env


def test_wrong_encryption_key_marks_rows_undecryptable(monkeypatch):
    rows = [{"env_key": "TAVILY_API_KEY", "encrypted_value": _legacy_encrypt("x", monkeypatch)}]
    other = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()
    res = hydrate_environment(lambda org: rows, ORG, environ={"LEAD_ENGINE_ENCRYPTION_KEY": other})
    assert res.count == 0 and res.undecryptable == ("TAVILY_API_KEY",)


def test_hydrate_from_database_uses_the_system_plane_and_org(monkeypatch):
    from infrastructure.credentials import hydrate_from_database
    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY", KEY)
    seen = {}

    class Cur:
        def execute(self, sql, params):
            seen["sql"], seen["params"] = sql, params

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Db:
        def tx_system(self):
            return Conn()

    res = hydrate_from_database(Db(), ORG)
    assert seen["params"] == (ORG,) and "organization_provider_credentials" in seen["sql"]
    assert "status = 'active'" in seen["sql"] and res.reason is None


# ---- the actual migration goal: V6 entry points stop importing legacy hydration ----
@pytest.mark.parametrize("path", ["apps/worker/__main__.py", "apps/api/__main__.py", "v6api/bridge.py"])
def test_entry_points_no_longer_use_the_legacy_hydrator(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "lead_engine.secrets" not in src and "lead_engine.db" not in src
    assert "hydrate_and_log" in src


def test_hydration_runs_before_the_provider_gateway_is_built():
    """build_gateway() reads os.environ at construction, so order is the whole point."""
    for path in ("apps/worker/__main__.py", "apps/api/__main__.py", "v6api/bridge.py"):
        src = (ROOT / path).read_text(encoding="utf-8")
        assert src.index("hydrate_and_log(db") < src.index("build_gateway()"), path


def test_log_identifies_the_org_without_exposing_its_id():
    """CI masks the raw org id as ***, so the log carries a fingerprint instead."""
    res = hydrate_environment(lambda org: [], ORG, environ=_env())
    assert ORG not in res.summary() and "fc4505fe" not in res.summary()
    assert f"org#{res.org_fingerprint}" in res.summary()
    assert res.org_fingerprint == "cc2e2f5d"                       # sha256(org)[:8], stable
    other = hydrate_environment(lambda org: [], "96773dcc-73ed-41be-b2c3-7800eabb04cc", environ=_env())
    assert other.org_fingerprint != res.org_fingerprint             # distinguishes v1 from V6 org


def test_fingerprint_is_present_even_when_nothing_loaded():
    res = hydrate_environment(lambda org: [], ORG, environ={})      # no encryption key
    assert "org#cc2e2f5d" in res.summary() and "ENCRYPTION_KEY" in res.summary()
    assert hydrate_environment(lambda org: [], None, environ=_env()).org_fingerprint == "none"
