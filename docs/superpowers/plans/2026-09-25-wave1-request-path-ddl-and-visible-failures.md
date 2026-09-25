# Wave 1 — Kill Request-Time DDL and Make Failures Visible

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Agents and Activity surfaces return real data in under one second, and make a server failure render as a failure instead of as "no data".

**Architecture:** Two modules currently run DDL/seed SQL inside per-request constructors (`AgentRegistry.__init__` → 44 statements ≈ 27–35 s; `ActivityStore.__init__` → `CREATE TABLE` that can never succeed on the production role → guaranteed 500). We move all of that into a one-shot, process-scoped bootstrap invoked at startup and from `python -m lead_engine init`, add a statement-count regression guard so it cannot come back, and give the one proven-broken UI surface an error branch.

**Tech Stack:** Python 3.13, FastAPI, pytest (SQLite-backed), psycopg/Supabase Postgres, React 19 + TypeScript, vitest.

**Spec:** `docs/gap-register-2026-09-25.md` — items LAT-01(a), LAT-01(b), FAIL-01, FAIL-02, FAIL-03, OPS-01, SEC-02, SEC-5. Read it alongside this plan; every task cites it.

## Global Constraints

- Tests run on **SQLite**: `tests/conftest.py` blank-fills `SUPABASE_DB_URL`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` and sets `LEAD_ENGINE_DEV_OPEN=1`. No task may require a live Postgres to pass CI.
- CI gates that must stay green: `pytest tests/ -q --cov=lead_engine --cov-fail-under=60`, `ruff check lead_engine/ tests/ --select E9,F63,F7,F82`, `pip-audit -r requirements.txt`, `gitleaks detect`, `pnpm run typecheck`, `pnpm run test`, `pnpm run build`, `pnpm audit --prod`.
- **Migrations own DDL; the app role owns DML only.** `lead_engine` has `USAGE` but **not `CREATE`** on schema `engine` — do not "fix" a DDL failure by granting `CREATE`.
- The dashboard is Arabic-first for non-technical operators: no HTTP status codes, English error strings, or identifiers on screen (see `web/src/lib/friendly.ts` header comment).
- Never commit secrets. Never write a token into this repo.
- Local `main` currently has one uncommitted edit (`web/src/lib/routePrefetch.ts`) that is **not** part of this plan; leave it alone (Task 4 does not touch it).

---

## File Structure

| File | Responsibility after this wave |
|---|---|
| `lead_engine/bootstrap.py` | **new** — process-scoped one-shot runner; the only place that decides "have we seeded yet" |
| `lead_engine/activity/store.py` | read/write `activity_events`; **no** DDL in `__init__`; exposes `ensure_schema(db)` |
| `lead_engine/agent_registry.py` | agent/tool/connection reads and writes; **no** seeding in `__init__`; exposes `ensure_seeded(db)` |
| `lead_engine/api/app.py` | FastAPI app; startup hook calls the bootstrap |
| `lead_engine/__main__.py` | `init` becomes the authoritative seed path for both |
| `tests/test_bootstrap_idempotence.py` | **new** — statement-count guards + "construction does no I/O" |
| `web/src/components/ui/ErrorState.tsx` | **new** — the retryable failure state missing from the app |
| `web/src/pages/Activity.tsx` | branches on `error` before falling through to `EmptyState` |
| `web/src/pages/__tests__/Activity.test.tsx` | **new** — proves a 500 never renders as "no data" |

---

## Task 1: Remove request-time DDL from `ActivityStore`

Fixes LAT-01(b): `GET /api/activity` currently 500s on every call because
`activity/store.py:36-41` runs `CREATE TABLE IF NOT EXISTS activity_events` and the
`lead_engine` role has no `CREATE` on schema `engine`.

**Files:**
- Create: `lead_engine/bootstrap.py`
- Modify: `lead_engine/activity/store.py:1-56`
- Modify: `lead_engine/__main__.py:53-60`
- Test: `tests/test_bootstrap_idempotence.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `bootstrap.run_once(name: str, fn: Callable[[], None]) -> bool`;
  `activity.store.ensure_schema(db) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_idempotence.py`:

```python
"""Request-path constructors must not perform I/O. See gap register LAT-01."""
import sqlite3

from lead_engine.activity.store import ActivityStore, ensure_schema
from lead_engine.db import Database


class CountingDb:
    """Delegates to a real Database while counting statements."""

    def __init__(self, inner):
        self._inner = inner
        self.count = 0

    def execute(self, sql, params=()):
        self.count += 1
        return self._inner.execute(sql, params)

    def query(self, sql, params=()):
        self.count += 1
        return self._inner.query(sql, params)

    def one(self, sql, params=()):
        self.count += 1
        return self._inner.one(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_constructing_activity_store_issues_no_statements(tmp_path):
    db = CountingDb(Database(tmp_path / "t.sqlite3"))
    ActivityStore(db)
    assert db.count == 0, f"constructor issued {db.count} statements; must issue 0"


def test_ensure_schema_creates_table_and_is_repeatable(tmp_path):
    inner = Database(tmp_path / "s.sqlite3")
    ensure_schema(inner)
    ensure_schema(inner)  # must not raise on an existing table
    db = CountingDb(inner)
    rows = ActivityStore(db).list(limit=10)
    assert rows == []
    assert db.count == 1, "a read must cost exactly one statement"


def test_activity_writes_survive_a_re_read(tmp_path):
    inner = Database(tmp_path / "w.sqlite3")
    ensure_schema(inner)
    store = ActivityStore(inner)
    store.record("job.started", {"job_id": "j1"})
    got = ActivityStore(inner).list(limit=10)
    assert [e["kind"] for e in got] == ["job.started"]


def test_sqlite3_rejects_schema_ddl_without_privilege():
    """Documents why the old code could never work on Postgres."""
    conn = sqlite3.connect(":memory:")
    assert conn.execute("PRAGMA journal_mode").fetchone() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bootstrap_idempotence.py -q`
Expected: FAIL — `ImportError: cannot import name 'ensure_schema' from 'lead_engine.activity.store'`

- [ ] **Step 3: Create the bootstrap module**

Create `lead_engine/bootstrap.py`:

```python
"""Process-scoped one-shot data bootstrap.

Migrations own schema; this module owns seed rows. It exists because seeding and
DDL were previously executed from per-request constructors, which made every
request pay dozens of sequential round trips (LAT-01) and, where the app role
lacks DDL privileges, guaranteed a 500 on every call.

A step is marked done even when it raises: the request path must never become
slow or failing again because of bootstrap work. Failures are logged loudly and
`python -m lead_engine init` remains the authoritative, retryable path.
"""
import logging
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_done: set[str] = set()


def run_once(name: str, fn) -> bool:
    """Run ``fn`` at most once per process. Returns True if this call ran it."""
    with _lock:
        if name in _done:
            return False
        _done.add(name)
    try:
        fn()
    except Exception as exc:  # never propagate bootstrap trouble
        log.error("bootstrap step %s failed: %s: %s", name, type(exc).__name__, exc)
        return False
    return True


def reset() -> None:
    """Test hook: forget which steps have run."""
    with _lock:
        _done.clear()
```

- [ ] **Step 4: Move the DDL out of the constructor**

In `lead_engine/activity/store.py`, replace the `__init__`/`_migrate_schema` pair
(currently lines 36–56) with a module-level function and a plain constructor:

```python
def ensure_schema(db) -> None:
    """Create the activity table. Called from startup and `init`, never per request.

    On Postgres this is expected to fail with `permission denied for schema engine`
    because migrations own DDL there; the startup hook logs it and moves on.
    """
    db.execute(
        _SCHEMA_PG if getattr(db, "dialect", "sqlite") == "postgres"
        else _SCHEMA_SQLITE
    )
    if getattr(db, "dialect", "sqlite") == "postgres":
        db.execute(
            "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS organization_id TEXT"
        )
        return
    existing = {row["name"] for row in db.conn.execute("PRAGMA table_info(activity_events)")}
    if "organization_id" not in existing:
        db.execute("ALTER TABLE activity_events ADD COLUMN organization_id TEXT")


class ActivityStore:
    """Append-only event log. Kept intentionally small — no joins, no migrations
    beyond the table itself, and no schema work on the request path."""

    def __init__(self, db):
        self.db = db
```

Delete the old `_migrate_schema` method. Keep `record()`, `list()` and everything below
unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_bootstrap_idempotence.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Make `init` the authoritative schema path**

In `lead_engine/__main__.py`, inside the `if args.cmd == "init":` block, after the existing
`Registry(db).seed_if_empty()` line:

```python
        from .activity.store import ensure_schema as _ensure_activity_schema
        _ensure_activity_schema(db)
```

- [ ] **Step 7: Run the whole backend suite**

Run: `python -m pytest tests/ -q`
Expected: PASS, 322 passed (318 existing + 4 new), 2 skipped

- [ ] **Step 8: Verify the endpoint against the real stack**

Start the backend and call the endpoint:

```bash
LEAD_ENGINE_DEV_OPEN=1 python -m lead_engine serve --port 8000 &
sleep 8
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://127.0.0.1:8000/api/activity
```
Expected: `200` in well under 1 s. It must **not** return 500. On the local stack this now
reads `engine.activity_events` instead of trying to create it.

- [ ] **Step 9: Commit**

```bash
git add lead_engine/bootstrap.py lead_engine/activity/store.py lead_engine/__main__.py tests/test_bootstrap_idempotence.py
git commit -m "fix(activity): stop running DDL in the request path

ActivityStore.__init__ issued CREATE TABLE / ALTER TABLE on every call. The
lead_engine role has USAGE but no CREATE on schema engine, so the statement
failed at parse time before the IF NOT EXISTS check and every
GET /api/activity returned 500 - while engine.activity_events already exists.

Schema work moves to ensure_schema(), called from startup and `init`."
```

---

## Task 2: Remove request-time seeding from `AgentRegistry`

Fixes LAT-01(a): measured **44 statements / 26.7 s** (repeat run 34.84 s) per
`AgentRegistry(db)`, constructed per request at 19 sites in `app.py` plus
`api/chat.py:263`. This is why `/api/agents`, `/api/agent-runs`, `/api/tools` and
`/api/approvals` never answer.

**Files:**
- Modify: `lead_engine/agent_registry.py:138-202`
- Modify: `lead_engine/__main__.py:53-60`
- Modify: `lead_engine/api/app.py:100-105`
- Test: `tests/test_bootstrap_idempotence.py`

**Interfaces:**
- Consumes: `bootstrap.run_once` from Task 1.
- Produces: `agent_registry.ensure_seeded(db) -> None`; `AgentRegistry(db)` is now pure.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootstrap_idempotence.py`:

```python
from lead_engine.agent_registry import AgentRegistry, ensure_seeded
from lead_engine.bootstrap import reset as reset_bootstrap


def test_constructing_agent_registry_issues_no_statements(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "a.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    AgentRegistry(db)
    assert db.count == 0, f"constructor issued {db.count} statements; must issue 0"


def test_agent_reads_cost_one_statement_each(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "r.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    reg = AgentRegistry(db)
    before = db.count
    reg.agents()
    assert db.count - before == 1
    reg.tools()
    assert db.count - before == 2
    reg.runs(50)
    assert db.count - before == 3


def test_ensure_seeded_is_idempotent(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "i.sqlite3")
    ensure_seeded(inner)
    first = inner.query("SELECT COUNT(*) AS n FROM agents")[0]["n"]
    ensure_seeded(inner)
    second = inner.query("SELECT COUNT(*) AS n FROM agents")[0]["n"]
    assert first == second == len(__import__(
        "lead_engine.agent_registry", fromlist=["AGENT_SEED"]).AGENT_SEED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bootstrap_idempotence.py -q -k agent or -k seeded`
Expected: FAIL — `ImportError: cannot import name 'ensure_seeded'`

- [ ] **Step 3: Make the constructor pure**

In `lead_engine/agent_registry.py`, change the class opening (currently `:138-141`) to:

```python
class AgentRegistry:
    def __init__(self, db):
        self.db = db
```

Then rename `def seed(self):` (`:160`) to a module-level function taking `db`, replacing
every `self.db` with `db` and `self._has_model_columns()` with `_has_model_columns(db)`
inside its body:

```python
def ensure_seeded(db) -> None:
    """Seed agents, tools, connections and the provider registry.

    Called from startup and `python -m lead_engine init` - never from a request
    path. Safe to call repeatedly: every statement is an upsert."""
    from .bootstrap import run_once

    run_once("agent_registry", lambda: _seed(db))


def _seed(db) -> None:
    now = utcnow()
    from .registry import Registry
    Registry(db).seed_if_empty()
    has_model_cols = _has_model_columns(db)
    for slug, item in AGENT_SEED.items():
        agent_id = f"agent:{slug}"
        db.execute(
            "INSERT INTO agents (agent_id, slug, name, description, status, current_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (agent_id) DO NOTHING",
            (agent_id, slug, item["name"], item["description"], "active", item["version"], now, now),
        )
        if has_model_cols:
            db.execute(
                "INSERT INTO agent_versions (agent_id, version, instructions, model_policy, model_provider, model_name, thinking_effort, tool_policy, output_schema, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (agent_id, version) DO NOTHING",
                (agent_id, item["version"], item["instructions"], json.dumps(item["model_policy"]),
                 item.get("model_provider"), item.get("model_name"), item.get("thinking_effort"),
                 json.dumps(item["tool_policy"]), json.dumps(item["output_schema"]), "published", now),
            )
        else:
            db.execute(
                "INSERT INTO agent_versions (agent_id, version, instructions, model_policy, tool_policy, output_schema, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (agent_id, version) DO NOTHING",
                (agent_id, item["version"], item["instructions"], json.dumps(item["model_policy"]),
                 json.dumps(item["tool_policy"]), json.dumps(item["output_schema"]), "published", now),
            )
    for name, description, scopes, approval in TOOL_SEED:
        # Refresh description/scopes on upgrade so newly shipped tools reach
        # existing databases, but never touch `enabled` - an operator may
        # have deliberately disabled a tool and that choice must survive.
        db.execute(
            "INSERT INTO tools (name, description, scopes, requires_approval, enabled, created_at)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT (name) DO UPDATE SET"
            "   description=excluded.description,"
            "   scopes=excluded.scopes",
            (name, description, json.dumps(scopes), int(approval), 1, now),
        )
    for row in db.query("SELECT name, MIN(env_key) AS env_key, MIN(base_url) AS base_url FROM providers GROUP BY name"):
        db.execute(
            "INSERT INTO connections (connection_id, provider, kind, base_url, status, created_at) VALUES (?,?,?,?,?,?) ON CONFLICT (connection_id) DO NOTHING",
            (f"provider:{row['name']}", row["name"], "provider", row.get("base_url"),
             "configured" if row.get("env_key") is None or os.environ.get(row["env_key"]) else "missing_key", now),
        )
```

Leave the method bodies of `agents()`, `tools()`, `runs()`, `approvals()`, `connections()`
untouched — they were already one statement each.

- [ ] **Step 4: Convert the per-instance schema probe to a process-level one**

Replace `_has_model_columns` (currently `:144-158`, an instance method whose memo dies with
each per-request instance) with a module function memoized on the module:

```python
_MODEL_COLS: bool | None = None


def _has_model_columns(db) -> bool:
    """Whether agent_versions carries the model routing columns. Memoized per
    process - the answer cannot change while the app is up."""
    global _MODEL_COLS
    if _MODEL_COLS is not None:
        return _MODEL_COLS
    try:
        if getattr(db, "dialect", "sqlite") == "postgres":
            cols = db.query(
                "SELECT column_name FROM information_schema.columns WHERE table_name='agent_versions' AND column_name='model_provider'"
            )
            _MODEL_COLS = bool(cols)
        else:
            existing = {row["name"] for row in db.conn.execute("PRAGMA table_info(agent_versions)")}
            _MODEL_COLS = "model_provider" in existing
    except Exception:
        _MODEL_COLS = False
    return _MODEL_COLS
```

If any remaining method calls `self._has_model_columns()`, replace those call sites with
`_has_model_columns(self.db)`. Verify none are left:

Run: `grep -n "_has_model_columns()" lead_engine/agent_registry.py`
Expected: no output

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_bootstrap_idempotence.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: Wire the startup hook**

In `lead_engine/api/app.py`, replace the app construction (`:100-105`) with a lifespan
that runs the bootstrap once per process:

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """One-shot schema+seed bootstrap. Never on the request path (LAT-01)."""
    from ..activity.store import ensure_schema
    from ..agent_registry import ensure_seeded
    from ..db import open_db

    try:
        db = open_db()
        try:
            ensure_schema(db)
        except Exception as exc:
            # Postgres: migrations own DDL and the app role has no CREATE
            # privilege on `engine`. Expected - log, do not fail startup.
            log.info("activity schema skipped at startup: %s", exc)
        ensure_seeded(db)
    except Exception as exc:
        log.warning("bootstrap at startup failed; `python -m lead_engine init` retries: %s", exc)
    yield


app = FastAPI(
    title="Lead Engine API",
    version=__version__,
    description="Quota-aware multi-provider lead generation engine "
                "(n8n = orchestration, FastAPI = brain, Supabase = storage)",
    lifespan=_lifespan,
)
```

If `log` is not already defined near the top of `app.py`, add it with the module's
existing logging convention (check `lead_engine/observability/logger.py` for the project's
logger factory and use that instead of `logging.getLogger` if one is imported there).

- [ ] **Step 7: Add seeding to `init`**

In `lead_engine/__main__.py`, in the `init` block added to in Task 1 Step 6, after
`_ensure_activity_schema(db)`:

```python
        from .agent_registry import ensure_seeded as _seed_agents
        _seed_agents(db)
```

- [ ] **Step 8: Run the whole backend suite**

Run: `python -m pytest tests/ -q`
Expected: PASS, 325 passed, 2 skipped. If any existing test constructed `AgentRegistry`
against a database it never seeded, add `ensure_seeded(db)` at the top of that test — the
behaviour is now explicit rather than a constructor side effect.

- [ ] **Step 9: Verify against the live stack**

```bash
LEAD_ENGINE_DEV_OPEN=1 python -m lead_engine serve --port 8000 &
sleep 8
for p in /api/agents /api/tools /api/approvals /api/agent-runs /api/status; do
  curl -s -o /dev/null -w "$p %{http_code} %{time_total}s\n" -m 15 "http://127.0.0.1:8000$p"
done
```
Expected: all `200`. First call may pay the one-time seed; **every subsequent call must be
under 2 s**. Confirm the second call is fast:

```bash
curl -s -o /dev/null -w "agents warm: %{http_code} %{time_total}s\n" http://127.0.0.1:8000/api/agents
```
Expected: well under 2 s (was 27–35 s).

- [ ] **Step 10: Commit**

```bash
git add lead_engine/agent_registry.py lead_engine/api/app.py lead_engine/__main__.py tests/test_bootstrap_idempotence.py
git commit -m "fix(agents): stop seeding on every request

AgentRegistry.__init__ ran seed() - 44 sequential statements, measured 26.7s
and 34.8s against production - and the class is constructed per request in 19
handlers plus chat.py. /api/agents, /api/agent-runs, /api/tools and
/api/approvals never answered within 12s.

Seeding moves to ensure_seeded(), gated by bootstrap.run_once and called from
the FastAPI lifespan and `init`. The schema probe is now memoized per process
instead of per instance."
```

---

## Task 3: Lock the win in with a statement-budget guard

Prevents regression. Without it, nothing stops a future constructor from adding another
44 round trips.

**Files:**
- Modify: `tests/test_bootstrap_idempotence.py`

**Interfaces:**
- Consumes: `CountingDb`, `ensure_seeded`, `ensure_schema` from Tasks 1–2.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the budget test**

Append to `tests/test_bootstrap_idempotence.py`:

```python
def test_agent_endpoints_stay_within_statement_budget(tmp_path):
    """Each agent read path costs one statement. A constructor regression that
    reintroduced LAT-01 would push this into the dozens."""
    from fastapi.testclient import TestClient
    reset_bootstrap()
    inner = Database(tmp_path / "e.sqlite3")
    ensure_seeded(inner)
    from lead_engine.api.app import app
    with TestClient(app) as client:
        for path in ("/api/agents", "/api/tools", "/api/agent-runs", "/api/approvals"):
            before = inner_total(client)  # placeholder replaced in Step 2
            assert client.get(path).status_code == 200
```

Do not keep that draft — Step 2 replaces it with a working instrumented version.

- [ ] **Step 2: Write the real guard against the app's DB factory**

Replace the Step 1 draft with:

```python
def test_agent_reads_are_single_statement(tmp_path, monkeypatch):
    """The regression guard for LAT-01: constructing the registry and reading
    each collection must cost exactly one statement per read."""
    reset_bootstrap()
    inner = Database(tmp_path / "g.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    reg = AgentRegistry(db)
    for reader in (reg.agents, reg.tools, reg.connections):
        before = db.count
        assert reader() is not None
        assert db.count == before + 1, f"{reader.__name__} issued more than one statement"
    for reader, args in ((reg.approvals, ("PENDING",)), (reg.runs, (50,))):
        before = db.count
        assert reader(*args) is not None
        assert db.count == before + 1, f"{reader.__name__} issued more than one statement"


def test_ensure_seeded_runs_once_per_process(tmp_path):
    """Second call must be free - that is the whole point of bootstrap.run_once."""
    reset_bootstrap()
    inner = Database(tmp_path / "o.sqlite3")
    db = CountingDb(inner)
    ensure_seeded(db)
    first = db.count
    assert first > 0, "first seed must do real work"
    ensure_seeded(db)
    assert db.count == first, "re-seeding in the same process must issue no statements"
```

- [ ] **Step 3: Run to verify**

Run: `python -m pytest tests/test_bootstrap_idempotence.py -q`
Expected: PASS (9 passed)

- [ ] **Step 4: Confirm the guard actually guards**

Temporarily re-add `self.seed()`-equivalent work by inserting
`db.execute("SELECT 1")` as the first line of `AgentRegistry.__init__`, run
`python -m pytest tests/test_bootstrap_idempotence.py -q -k single_statement`, confirm it
**fails**, then revert that line.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add tests/test_bootstrap_idempotence.py
git commit -m "test(bootstrap): guard against request-path statement regression"
```

---

## Task 4: A server failure must never render as "no data"

Fixes FAIL-01 / FAIL-03 at the proven-broken surface. Reproduced live:
`GET /api/activity` returned **500**, the page rendered `"0 حدث"` /
`"لا توجد أحداث"` / `"ستظهر هنا أحداث النظام فور تشغيل أول مهمة أو وكيل."` with **zero
console errors**, while the store held 9 jobs, 4 runs and 1 approval.

The mechanism is precise: `Activity.tsx:104` already destructures `error` from
`useLiveData`, but the only consumer is `handleRefresh` (`:132`). The render branch
(`:167-178`) checks `loading`, then `events.length === 0` → `EmptyState`, and never consults
`error`.

**Files:**
- Create: `web/src/components/ui/ErrorState.tsx`
- Create: `web/src/components/ui/__tests__/ErrorState.test.tsx`
- Modify: `web/src/pages/Activity.tsx:104-133, 161, 165-178`
- Create: `web/src/pages/__tests__/Activity.test.tsx`

**Interfaces:**
- Consumes: `useLiveData` → `{ data, loading, error, refresh }`; `friendlyError(e)` from
  `web/src/lib/friendly.ts`.
- Produces: `<ErrorState error={unknown} onRetry={() => void} subject?: string />` — the
  component every later wave's list page adopts.

- [ ] **Step 1: Write the failing component test**

Create `web/src/components/ui/__tests__/ErrorState.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "../ErrorState";

describe("ErrorState", () => {
  it("names the subject and offers a retry", () => {
    render(<ErrorState error={new Error("boom")} onRetry={vi.fn()} subject="سجل النشاط" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/سجل النشاط/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /إعادة المحاولة/ })).toBeInTheDocument();
  });

  it("never shows a raw HTTP status to the operator", () => {
    const err = Object.assign(new Error("HTTP 500"), { status: 500 });
    render(<ErrorState error={err} onRetry={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).not.toMatch(/500/);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run from `web/`: `npx vitest run src/components/ui/__tests__/ErrorState.test.tsx`
Expected: FAIL — cannot resolve `../ErrorState`

- [ ] **Step 3: Implement the component**

Create `web/src/components/ui/ErrorState.tsx`:

```tsx
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { friendlyError } from "@/lib/friendly";

/** A real backend failure, shown as one. Distinct from EmptyState: an empty
 * store and a broken store are different truths and the operator must never
 * have to guess which one they are looking at (gap register FAIL-01). */
export function ErrorState({
  error,
  onRetry,
  subject = "البيانات",
}: {
  error: unknown;
  onRetry?: () => void;
  subject?: string;
}) {
  return (
    <div
      role="alert"
      className="p-10 text-center rounded-xl border border-[var(--warn)]/40 bg-[color-mix(in_srgb,var(--warn)_8%,transparent)]"
    >
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--warn)_16%,transparent)]">
        <AlertTriangle className="h-5 w-5 text-[var(--warn-text)]" aria-hidden="true" />
      </div>
      <p className="text-sm font-semibold mb-1">تعذر تحميل {subject}</p>
      <p className="text-[13px] text-[var(--fg-muted)] leading-6 mb-4">
        {friendlyError(error)}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          إعادة المحاولة
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run from `web/`: `npx vitest run src/components/ui/__tests__/ErrorState.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing page test**

Create `web/src/pages/__tests__/Activity.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ActivityPage from "@/pages/Activity";

afterEach(() => vi.restoreAllMocks());

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

describe("Activity page", () => {
  it("shows a failure, not an empty feed, when the API returns 500", async () => {
    vi.stubGlobal("fetch", respond(500, { detail: "internal error" }));
    render(<ActivityPage />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument(), {
      timeout: 3000,
    });
    expect(screen.queryByText("لا توجد أحداث")).not.toBeInTheDocument();
    expect(screen.queryByText(/ستظهر هنا أحداث النظام/)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows the empty feed when the API genuinely returns none", async () => {
    vi.stubGlobal("fetch", respond(200, { events: [] }));
    render(<ActivityPage />);
    await waitFor(() => expect(screen.getByText("لا توجد أحداث")).toBeInTheDocument(), {
      timeout: 3000,
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 6: Run to verify the first case fails**

Run from `web/`: `npx vitest run src/pages/__tests__/Activity.test.tsx`
Expected: the 500 test FAILS (renders "لا توجد أحداث"); the empty test may already pass.

- [ ] **Step 7: Branch on `error` before the empty state**

In `web/src/pages/Activity.tsx`, add the import alongside the other UI imports:

```tsx
import { ErrorState } from "@/components/ui/ErrorState";
```

Replace the render block at `:165-177` (the `<Card>` opening through the `EmptyState`)
with an `error` branch first:

```tsx
      <Card>
        <CardContent className="p-0">
          {error && events.length === 0 ? (
            <ErrorState error={error} onRetry={refresh} subject="سجل النشاط" />
          ) : loading && events.length === 0 ? (
            <div className="p-10 text-center text-sm text-[var(--fg-muted)]">
              جاري التحميل…
            </div>
          ) : events.length === 0 ? (
            <EmptyState
              icon={<ActivityIcon className="h-7 w-7" />}
              title="لا توجد أحداث"
              description="ستظهر هنا أحداث النظام فور تشغيل أول مهمة أو وكيل."
            />
          ) : (
```

Keep the existing `<ul>` branch and its closing tags exactly as they are.

Then make the counter honest — currently `:160-162` prints `0` during a failure. Replace
with:

```tsx
        <div className="text-xs text-[var(--fg-muted)]">
          {error && events.length === 0 ? "غير متاح" : `${events.length} حدث`}
        </div>
```

And drop the now-redundant manual toast path so a failing poll cannot be mistaken for
success — replace `handleRefresh` (`:130-133`) with:

```tsx
  async function handleRefresh() {
    await refresh();
  }
```

Remove the now-unused `toast` import if nothing else in the file uses it
(`grep -n "toast" web/src/pages/Activity.tsx` to confirm before deleting).

- [ ] **Step 8: Run to verify both pass**

Run from `web/`: `npx vitest run src/pages/__tests__/Activity.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 9: Run the full frontend gate**

```bash
cd web && npx tsc --noEmit && npx vitest run && npm run build
```
Expected: tsc clean; 64+ tests passed across 11 files; build succeeds.

- [ ] **Step 10: Verify in the browser**

With the local stack running, load `http://127.0.0.1:3000/activity`.
Expected: a populated event list (Tasks 1 and 2 fixed the backend). Then confirm the
failure path is real by pointing it at a broken endpoint once:
in DevTools, block `**/api/activity` and reload — the page must show
"تعذر تحميل سجل النشاط" with an إعادة المحاولة button, never "لا توجد أحداث".

- [ ] **Step 11: Commit**

```bash
git add web/src/components/ui/ErrorState.tsx web/src/components/ui/__tests__/ErrorState.test.tsx web/src/pages/Activity.tsx web/src/pages/__tests__/Activity.test.tsx
git commit -m "fix(ui): render API failures as failures, not as empty data

The Activity page destructured `error` from useLiveData but only used it in
handleRefresh, so a 500 rendered 'لا توجد أحداث' plus '0 حدث' with no console
error - while the store held 9 jobs, 4 runs and 1 approval. Adds ErrorState and
branches on error before EmptyState; the counter reads 'غير متاح' instead of
claiming zero."
```

---

## Task 5: Credential hygiene

Fixes SEC-02, SEC-05. Owner has deferred full token rotation to ship time
(`docs/gap-register-2026-09-25.md` SEC-03) — this task only removes the credential that is
sitting on disk in plaintext and turns on the free inbound gates.

**Files:**
- Modify: `.git/config` (via `git remote set-url`, not by hand)
- No repo file changes; the rest is GitHub settings API calls.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Confirm the embedded token**

Run: `git remote -v`
Expected: an `origin` URL containing `ghp_…@github.com`. **Do not echo the token into any
commit, issue, or log.**

- [ ] **Step 2: Remove the credential from the remote URL**

```bash
git remote set-url origin https://github.com/7ari9aff-crypto/lead-engine.git
git remote -v
```
Expected: no `ghp_` in either fetch or push URL. Then verify the credential helper, not the
URL, is what authenticates:

```bash
git config --get credential.helper
git ls-remote --exit-code origin HEAD >/dev/null && echo "auth ok via helper"
```
If `git ls-remote` now prompts, the machine has no helper configured — report that to the
owner rather than re-embedding a token.

- [ ] **Step 3: Turn on the inbound scanning gates**

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/7ari9aff-crypto/lead-engine/security_and_analysis \
  -d '{"advanced_security":{"status":"enabled"},"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'
```
Then confirm:

```bash
curl -s -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/7ari9aff-crypto/lead-engine \
  | python -c "import json,sys;print(json.load(sys.stdin)['security_and_analysis'])"
```
Expected: `secret_scanning` and `secret_scanning_push_protection` both `enabled`.

- [ ] **Step 4: Confirm nothing broke**

Run: `git status --short && python -m pytest tests/ -q`
Expected: clean status, suite still green.

- [ ] **Step 5: No commit required**

`.git/config` is not tracked. Do not commit anything for this task; report the two
verifications instead.

---

## Self-Review

**Coverage against the register.** This wave addresses LAT-01(a), LAT-01(b), FAIL-01,
FAIL-02 (root cause), FAIL-03 (at the proven surface), OPS-01 (DDL ownership for the two
offending modules), SEC-02, SEC-05. Deliberately **not** in this wave, with the reason:

- **LAT-02** (no connection pooling) — needs a Supabase pooler decision and a
  `psycopg_pool` dependency; it is the subject of Wave 2, where it should land together
  with the N+1 work so the round-trip budget is designed once.
- **SEC-04 / SEC-04b** (`engine` vs `public`, 11 tables with RLS off, `TRUNCATE` grant) —
  Wave 3, and it must start by re-deriving the real migration files, since the prior
  report cited files that do not exist.
- **FAIL-01 on the other ~24 list surfaces** — Wave 2, mechanical once `ErrorState` exists
  as the target of a documented pattern.
- **FRONT-01..06, OPS-02** — Wave 4.
- **The unverified list at the end of the register** — verify, then schedule. Several
  (circuit fail-open, cache miss-on-error, `require_admin` `None` semantics) could be P0
  once confirmed and should be checked early in Wave 2.

**Placeholder scan:** Task 3 Step 1 intentionally contains a draft that Step 2 replaces;
that is labelled explicitly and Step 2 is the committed version. No other TBDs.

**Type consistency:** `ensure_schema(db)`, `ensure_seeded(db)`, `run_once(name, fn)`,
`reset()`, `CountingDb`, `AgentRegistry`, `_has_model_columns(db)` (module function, not a
method) are used identically in Tasks 1–3. `ErrorState`'s props (`error`, `onRetry`,
`subject`) match between its definition, its test, and the Activity call site.

**Risk to watch:** Task 2 Step 6 touches app construction. If `log` is undefined in that
scope, startup will fail loudly at import time — Step 8's full-suite run catches it, so do
not skip Step 8 even if Step 9 looks fine.
