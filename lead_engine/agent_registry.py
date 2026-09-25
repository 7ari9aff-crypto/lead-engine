"""Control-plane registry for versioned agents, tools, connections, and runs."""
import json
import os
import uuid
import requests

from .db import utcnow

AGENT_SEED = {
    "lead-generation": {
        "name": "Lead Generation Agent",
        "description": "Discovers, enriches, qualifies, and legally reviews leads.",
        "version": "1.0.0",
        "instructions": "Run the deterministic lead pipeline and use LLMs only for ambiguous qualification tasks.",
        "model_policy": {"task": "reasoning", "fallback": "router"},
        "model_provider": "router",
        "model_name": None,
        "thinking_effort": None,
        "tool_policy": {"scopes": ["search:read", "leads:write", "verification:run"]},
        "output_schema": {"type": "object", "required": ["job_id", "state", "leads"]},
    },
    "engine-maintenance": {
        "name": "Engine Maintenance Agent",
        "description": "وكيل صيانة المحرك: يتتبّع أي عطل في الكود بنفسه — يقرأ الملفات، "
                       "يبحث في الشجرة، يراجع سجل الـgit، ويشغّل الاختبارات الحقيقية — "
                       "ثم يقترح تعديلاً بموافقة إلزامية. لا يكتب أي ملف إلا بعد موافقة صريحة، "
                       "والتطبيق يقع على فرع git جديد، وليس على main أبدًا.",
        "version": "1.0.0",
        "instructions": (
            "أنت مهندس صيانة لهذا النظام نفسه. لما تطلب منك تشخيص مشكلة اتبع المسار: "
            "list_code لعرفة الشجرة، ثم search_code لتحديد المكان، ثم read_code للقراءة "
            "حول المشكلة، ثم git_history لمعرفة آخر تغيير لمس الملف، ثم run_tests لتأكيد "
            "السلوك. ممنوع اختراع أي معلومة عن الكود — كل ادعاء لازم يكون مبنيًا على قراءة "
            "فعلية. لما تحدد الإصلاح، نادِ propose_patch بتعديل كامل ومكتوب بالكامل (مش "
            "وصف ولا pseudo-code) مع ملخص واضح بالعربية. الـpropose لا يغيّر أي ملف — "
            "هو يسجّل موافقة، وقول للمستخدم بوضوح إن التطبيق محتاج موافقته من لوحة الوكلاء. "
            "لا تحاول الكتابة بأي وسيلة أخرى، ولا تشغّل أوامر shell."
        ),
        "model_policy": {"task": "planning", "fallback": "router"},
        "model_provider": "router",
        "model_name": None,
        "thinking_effort": None,
        "tool_policy": {"scopes": ["code:read", "tests:run", "code:write",
                                   "jobs:read", "system:read"]},
        "output_schema": {"type": "object",
                          "required": ["diagnosis", "files", "proposed_change"]},
    },
    "lead-research": {
        "name": "Research Agent",
        "description": "وكيل بحث ذاتي: يخطط، يبحث، يحقق، يوثق الحقائق بمصادرها، "
                       "يكشف التعارض، يؤهل مقابل الـICP، ويتوقف عند بوابة المراجعة البشرية. "
                       "لا يرسل شيئًا لأحد أبدًا.",
        "version": "1.0.0",
        "instructions": (
            "شغّل حلقة البحث: خطط استعلامات، ادور، احفظ كل ملاحظة كحقيقة بمصدرها، "
            "كرر المصادر المستقلة للحقول الحاسمة حتى تتحقق، اكشف التعارض ولا تحله "
            "بصمت، صفِّ المرشحين مقابل الـICP من الحقائق فقط، ثم أعلن done ليتوقف "
            "النظام عند READY_FOR_REVIEW. ممنوع اختراع أي معلومة، وممنوع أي إرسال."
        ),
        "model_policy": {"task": "planning", "fallback": "none"},
        "model_provider": "gemini",
        "model_name": None,
        "thinking_effort": None,
        "tool_policy": {"scopes": ["search:read", "research:read", "evidence:write",
                                   "verification:run", "facts:read",
                                   "qualification:run", "jobs:read",
                                   "interaction:write"]},
        "output_schema": {"type": "object",
                          "required": ["job_id", "state", "stop_reason"]},
    },
    "engine-maintainer": {
        "name": "Engine Maintainer Agent",
        "description": "وكيل صيانة المحرك: يتتبّع المشكلة في الكود بنفسه (قراءة، بحث، "
                       "git، اختبارات)، يحدّد السبب الجذري، ثم يقترح patch كامل — "
                       "ولا يُطبَّق أي تعديل إلا بعد موافقتك الصريحة، وعلى فرع git "
                       "منفصل مع نسخة احتياطية ورجوع بزر واحد.",
        "version": "1.0.0",
        "instructions": (
            "أنت مهندس صيانة تعمل داخل مستودع المشروع. سلوكك الإلزامي: "
            "① لا تخمّن أبدًا — اقرأ الكود الحقيقي (list_code/read_code/search_code) "
            "وتحقّق من السبب الجذري قبل أي اقتراح. "
            "② شغّل الاختبارات (run_tests) لتثبيت المشكلة أولًا، وليصير عندك دليل. "
            "③ راجع git_history/git_show لتعرف ماذا تغيّر ومتى. "
            "④ عندما تتأكد، استدعِ propose_patch بملفات كاملة (content كامل للملف، "
            "مش جزء منه) وsummary واضح بالعربية يشرح السبب والإصلاح. "
            "⑤ لا تحاول أبدًا تنفيذ أي كتابة خارج propose_patch، وممنوع تمامًا "
            "لمس main أو أي ملف أسرار. "
            "⑥ بعد الموافقة، تحقّق النتيجة بـrun_tests واذكرها بصدق — لو فشلت، "
            "قل فشلت واقترح الخطوة التالية."
        ),
        "model_policy": {"task": "reasoning", "fallback": "router"},
        "model_provider": "router",
        "model_name": None,
        "thinking_effort": None,
        "tool_policy": {"scopes": ["code:read", "code:write", "tests:run",
                                   "jobs:read", "system:read"]},
        "output_schema": {"type": "object",
                          "required": ["root_cause", "files", "approval_id"]},
    },
}

TOOL_SEED = [
    ("run_lead_generation", "Run the lead generation pipeline", ["jobs:run"], True),
    ("get_job_status", "Read a job and its events", ["jobs:read"], False),
    ("list_leads", "Read leads with filters", ["leads:read"], False),
    ("verify_email", "Verify an email address", ["verification:run"], False),
    ("system_status", "Read providers, jobs, and usage", ["system:read"], False),
    ("search_companies", "Web search for candidate companies", ["search:read"], False),
    ("research_company", "Deep company investigation via the OpenManus browsing runtime",
     ["research:read", "evidence:write"], False),
    ("save_fact", "Store a sourced fact in the Truth Layer", ["evidence:write"], False),
    ("verify_fact", "Verify a stored fact (5-state email verification)",
     ["verification:run"], False),
    ("list_facts", "Read the fact snapshot for a subject", ["facts:read"], False),
    ("qualify_lead", "Evidence-grounded ICP qualification from stored facts",
     ["qualification:run"], False),
    ("get_research_status", "Research job progress, counters and budgets",
     ["jobs:read"], False),
    ("ask_user", "Ask the user a blocking question (job goes WAITING_FOR_USER)",
     ["interaction:write"], False),
    # ---- Code-aware tools: trace the codebase, then repair behind approval ----
    ("list_code", "List workspace source files (secrets/vendor excluded)",
     ["code:read"], False),
    ("read_code", "Read a workspace source file or a line window",
     ["code:read"], False),
    ("search_code", "Regex search across the workspace source tree",
     ["code:read"], False),
    ("git_history", "Recent commits (optionally scoped to one path)",
     ["code:read"], False),
    ("git_show", "Full diff of a single commit", ["code:read"], False),
    ("run_tests", "Run the project's own test suite (pytest / ruff / typecheck)",
     ["code:read", "tests:run"], False),
    ("propose_patch", "Propose a code patch behind an approval gate (writes nothing)",
     ["code:write"], False),
]


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
        # existing databases, but never touch `enabled` — an operator may
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


def reclaim_stale_runs(db, stale_hours: int = 24) -> int:
    """Mark RUNNING agent runs as FAILED when they have not updated within the
    stale window: the worker that owned them is gone (a serverless request
    killed mid-run), and nothing will ever call finish_run. This is the
    /agents zombie fix (gap register FRONT-03); reaped runs keep their error
    so the dashboard shows why the run died instead of lying "جاري".
    """
    stale_hours = int(stale_hours)
    if getattr(db, "dialect", "sqlite") == "postgres":
        stale = f"updated_at < now() - interval '{stale_hours} hours'"
    else:
        stale = (f"updated_at < strftime('%Y-%m-%dT%H:%M:%SZ','now',"
                 f"'-{stale_hours * 60} minutes')")
    cur = db.execute(
        "UPDATE agent_runs SET status='FAILED', error=?, updated_at=?"
        f" WHERE status='RUNNING' AND {stale}",
        (f"stale run reaped: no update for {stale_hours}h (worker died)",
         utcnow()))
    return getattr(cur, "rowcount", 0)


class AgentRegistry:
    """Reads and writes agents, tools, connections and runs. Pure constructor:
    schema and seed data are bootstrap concerns (see `ensure_seeded`)."""

    def __init__(self, db):
        self.db = db

    def agents(self):
        return self.db.query("SELECT * FROM agents ORDER BY name")

    def versions(self, slug):
        return self.db.query(
            "SELECT v.* FROM agent_versions v JOIN agents a ON a.agent_id=v.agent_id"
            " WHERE a.slug=? ORDER BY v.created_at DESC", (slug,))

    def create_run(self, slug, input_data, version=None):
        agent = self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))
        if not agent:
            raise ValueError("agent not found")
        version = version or agent["current_version"]
        run_id = f"run_{uuid.uuid4().hex}"
        now = utcnow()
        self.db.execute(
            "INSERT INTO agent_runs (run_id, organization_id, agent_id, version, status, input_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (run_id, getattr(self.db, "org_id", None), agent["agent_id"], version, "RUNNING",
             json.dumps(input_data, ensure_ascii=False), now, now),
        )
        return run_id

    def finish_run(self, run_id, status, output=None, error=None, usage=None):
        usage = usage or {}
        self.db.execute(
            "UPDATE agent_runs SET status=?, output_json=?, error=?, cost_usd=?, prompt_tokens=?, completion_tokens=?, updated_at=? WHERE run_id=?",
            (status, json.dumps(output, ensure_ascii=False, default=str) if output is not None else None,
             error, usage.get("cost_usd", 0), usage.get("prompt_tokens", 0),
             usage.get("completion_tokens", 0), utcnow(), run_id),
        )

    def start_step(self, run_id, step_name, step_type="pipeline", input_data=None):
        cur = self.db.execute(
            "INSERT INTO agent_steps (run_id, step_name, step_type, status, input_json, started_at)"
            " VALUES (?,?,?,?,?,?)",
            (run_id, step_name, step_type, "RUNNING",
             json.dumps(input_data, ensure_ascii=False) if input_data is not None else None, utcnow()),
        )
        return cur.lastrowid

    def finish_step(self, step_id, status, output=None, error=None, provider=None, latency_ms=None):
        self.db.execute(
            "UPDATE agent_steps SET status=?, output_json=?, error=?, provider=?, latency_ms=?, finished_at=? WHERE id=?",
            (status, json.dumps(output, ensure_ascii=False, default=str) if output is not None else None,
             error, provider, latency_ms, utcnow(), step_id),
        )

    def runs(self, limit=50):
        org_id = getattr(self.db, "org_id", None)
        clause = " AND r.organization_id = ?" if org_id else ""
        params = [limit]
        if org_id:
            params.insert(0, org_id)
        return self.db.query(
            "SELECT r.*, a.slug, a.name FROM agent_runs r JOIN agents a ON a.agent_id=r.agent_id"
            f" WHERE 1=1{clause} ORDER BY r.created_at DESC LIMIT ?", tuple(params))

    def run(self, run_id):
        org_id = getattr(self.db, "org_id", None)
        clause = " AND organization_id = ?" if org_id else ""
        params = [run_id]
        if org_id:
            params.append(org_id)
        row = self.db.one(f"SELECT * FROM agent_runs WHERE run_id=?{clause}", tuple(params))
        if not row:
            return None
        row["steps"] = self.db.query("SELECT * FROM agent_steps WHERE run_id=? ORDER BY id", (run_id,))
        approval_clause = " AND organization_id = ?" if org_id else ""
        approval_params = [run_id]
        if org_id:
            approval_params.append(org_id)
        row["approvals"] = self.db.query(
            f"SELECT * FROM approvals WHERE run_id=?{approval_clause} ORDER BY requested_at",
            tuple(approval_params),
        )
        return row

    def tools(self):
        return self.db.query("SELECT * FROM tools WHERE enabled=1 ORDER BY name")

    def connections(self):
        return self.db.query("SELECT * FROM connections ORDER BY provider")

    def approvals(self, status="PENDING"):
        org_id = getattr(self.db, "org_id", None)
        clause = " AND organization_id = ?" if org_id else ""
        params = [status]
        if org_id:
            params.append(org_id)
        return self.db.query(
            f"SELECT * FROM approvals WHERE status=?{clause} ORDER BY requested_at",
            tuple(params),
        )

    def check_connection(self, provider):
        row = self.db.one("SELECT * FROM providers WHERE name=? ORDER BY priority LIMIT 1", (provider,))
        if not row:
            return None
        has_key = row["env_key"] is None or bool(os.environ.get(row["env_key"]))
        status = "configured" if has_key else "missing_key"
        http_status = None
        if has_key and row.get("base_url"):
            try:
                response = requests.head(row["base_url"], timeout=5, allow_redirects=True)
                http_status = response.status_code
                status = "healthy" if response.status_code < 500 else "unhealthy"
            except requests.RequestException:
                status = "unreachable"
        self.db.execute(
            "UPDATE connections SET status=?, base_url=?, last_checked_at=? WHERE provider=?",
            (status, row.get("base_url"), utcnow(), provider),
        )
        return {"provider": provider, "status": status, "has_key": has_key,
                "base_url": row.get("base_url"), "http_status": http_status,
                "checked_at": utcnow()}

    def request_approval(self, run_id, action, payload):
        approval_id = f"approval_{uuid.uuid4().hex}"
        self.db.execute(
            "INSERT INTO approvals (approval_id, run_id, action, payload_json, status, requested_at)"
            " VALUES (?,?,?,?,?,?)",
            (approval_id, run_id, action, json.dumps(payload, ensure_ascii=False), "PENDING", utcnow()),
        )
        return approval_id

    def approval(self, approval_id):
        return self.db.one("SELECT * FROM approvals WHERE approval_id=?", (approval_id,))

    def resolve_approval(self, approval_id, status):
        cur = self.db.execute(
            "UPDATE approvals SET status=?, resolved_at=? WHERE approval_id=? AND status='PENDING'",
            (status, utcnow(), approval_id),
        )
        return cur.rowcount > 0

    # ---------- Dynamic CRUD (UI-driven, multi-domain) ----------

    def create_agent(self, slug, name, description="", status="draft"):
        """Create a new agent row. Returns the agent dict (slug is unique).
        Raises ValueError on duplicate slug."""
        existing = self.db.one("SELECT slug FROM agents WHERE slug=?", (slug,))
        if existing:
            raise ValueError(f"agent slug '{slug}' already exists")
        # Org-scoped id: same slug can exist per tenant without PK collisions.
        agent_id = f"agent:{getattr(self.db, 'org_id', None) or 'platform'}:{slug}"
        now = utcnow()
        self.db.execute(
            "INSERT INTO agents (agent_id, slug, name, description, status, current_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (agent_id, slug, name, description, status, None, now, now),
        )
        return self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))

    def update_agent(self, slug, fields):
        """Update mutable agent fields. Allowed: name, description, status."""
        allowed = {"name", "description", "status"}
        sets, params = [], []
        for key in allowed:
            if key in fields:
                sets.append(f"{key}=?")
                params.append(fields[key])
        if not sets:
            return self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))
        sets.append("updated_at=?")
        params.append(utcnow())
        params.append(slug)
        self.db.execute(f"UPDATE agents SET {', '.join(sets)} WHERE slug=?", params)
        return self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))

    def archive_agent(self, slug):
        """Soft-delete: set status=archived. Keeps versions + runs for audit."""
        return self.update_agent(slug, {"status": "archived"}) is not None

    def create_version(
        self, slug, version, instructions=None,
        model_provider="router", model_name=None, thinking_effort=None,
        tool_policy=None, output_schema=None, status="draft",
    ):
        """Create a new version row for an existing agent. Validates the slug exists."""
        agent = self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))
        if not agent:
            raise ValueError(f"agent '{slug}' not found")
        existing = self.db.one(
            "SELECT version FROM agent_versions WHERE agent_id=? AND version=?",
            (agent["agent_id"], version),
        )
        if existing:
            raise ValueError(f"version '{version}' already exists for '{slug}'")
        self.db.execute(
            "INSERT INTO agent_versions (agent_id, version, instructions, model_policy, model_provider, model_name, thinking_effort, tool_policy, output_schema, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (agent["agent_id"], version, instructions,
             json.dumps({"task": "reasoning", "fallback": model_provider}) if model_provider else None,
             model_provider, model_name, thinking_effort,
             json.dumps(tool_policy) if tool_policy else None,
             json.dumps(output_schema) if output_schema else None,
             status, utcnow()),
        )
        return self.db.one(
            "SELECT * FROM agent_versions WHERE agent_id=? AND version=?",
            (agent["agent_id"], version),
        )

    def set_active_version(self, slug, version):
        """Point the agent's current_version pointer to an existing version."""
        agent = self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))
        if not agent:
            raise ValueError(f"agent '{slug}' not found")
        v = self.db.one(
            "SELECT version FROM agent_versions WHERE agent_id=? AND version=?",
            (agent["agent_id"], version),
        )
        if not v:
            raise ValueError(f"version '{version}' not found for '{slug}'")
        self.db.execute(
            "UPDATE agents SET current_version=?, updated_at=? WHERE slug=?",
            (version, utcnow(), slug),
        )
        return self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))

    def get_active_version(self, slug):
        """Return the agent + its active version row in one dict (used by the chat)."""
        agent = self.db.one("SELECT * FROM agents WHERE slug=?", (slug,))
        if not agent or not agent.get("current_version"):
            return None
        version = self.db.one(
            "SELECT * FROM agent_versions WHERE agent_id=? AND version=?",
            (agent["agent_id"], agent["current_version"]),
        )
        if not version:
            return None
        # Parse JSON fields back to dicts for the chat layer
        for json_field in ("model_policy", "tool_policy", "output_schema"):
            raw = version.get(json_field)
            if raw:
                try:
                    version[json_field] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass
        return {"agent": agent, "version": version}

    def register_tool(self, name, description, input_schema=None, output_schema=None, scopes=None, requires_approval=False, enabled=True):
        """Upsert a tool definition. Lets the UI register new tools without code changes."""
        self.db.execute(
            "INSERT INTO tools (name, description, input_schema, output_schema, scopes, requires_approval, enabled, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET"
            "   description=excluded.description,"
            "   input_schema=excluded.input_schema,"
            "   output_schema=excluded.output_schema,"
            "   scopes=excluded.scopes,"
            "   requires_approval=excluded.requires_approval,"
            "   enabled=excluded.enabled",
            (name, description,
             json.dumps(input_schema) if input_schema else None,
             json.dumps(output_schema) if output_schema else None,
             json.dumps(scopes) if scopes else None,
             int(bool(requires_approval)),
             int(bool(enabled)),
             utcnow()),
        )
        return self.db.one("SELECT * FROM tools WHERE name=?", (name,))

    def register_connection(self, connection_id, provider, kind="custom", base_url=None, status="configured", metadata=None):
        """Upsert a generic platform connection (LinkedIn, Google Maps, WhatsApp, custom HTTP...)."""
        self.db.execute(
            "INSERT INTO connections (connection_id, provider, kind, base_url, status, metadata_json, created_at, last_checked_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(connection_id) DO UPDATE SET"
            "   provider=excluded.provider,"
            "   kind=excluded.kind,"
            "   base_url=excluded.base_url,"
            "   status=excluded.status,"
            "   metadata_json=excluded.metadata_json,"
            "   last_checked_at=excluded.last_checked_at",
            (connection_id, provider, kind, base_url, status,
             json.dumps(metadata, ensure_ascii=False) if metadata else None,
             utcnow(), utcnow()),
        )
        return self.db.one("SELECT * FROM connections WHERE connection_id=?", (connection_id,))
