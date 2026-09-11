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
    }
}

TOOL_SEED = [
    ("run_lead_generation", "Run the lead generation pipeline", ["jobs:run"], True),
    ("get_job_status", "Read a job and its events", ["jobs:read"], False),
    ("list_leads", "Read leads with filters", ["leads:read"], False),
    ("verify_email", "Verify an email address", ["verification:run"], False),
    ("system_status", "Read providers, jobs, and usage", ["system:read"], False),
]


class AgentRegistry:
    def __init__(self, db):
        self.db = db
        self.seed()

    def seed(self):
        now = utcnow()
        from .registry import Registry
        Registry(self.db).seed_if_empty()
        for slug, item in AGENT_SEED.items():
            agent_id = f"agent:{slug}"
            self.db.execute(
                "INSERT OR IGNORE INTO agents (agent_id, slug, name, description, status, current_version, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (agent_id, slug, item["name"], item["description"], "active", item["version"], now, now),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO agent_versions (agent_id, version, instructions, model_policy, model_provider, model_name, thinking_effort, tool_policy, output_schema, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (agent_id, item["version"], item["instructions"], json.dumps(item["model_policy"]),
                 item.get("model_provider"), item.get("model_name"), item.get("thinking_effort"),
                 json.dumps(item["tool_policy"]), json.dumps(item["output_schema"]), "published", now),
            )
        for name, description, scopes, approval in TOOL_SEED:
            self.db.execute(
                "INSERT OR IGNORE INTO tools (name, description, scopes, requires_approval, enabled, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (name, description, json.dumps(scopes), int(approval), 1, now),
            )
        for row in self.db.query("SELECT name, MIN(env_key) AS env_key, MIN(base_url) AS base_url FROM providers GROUP BY name"):
            self.db.execute(
                "INSERT OR IGNORE INTO connections (connection_id, provider, kind, base_url, status, created_at) VALUES (?,?,?,?,?,?)",
                (f"provider:{row['name']}", row["name"], "provider", row.get("base_url"),
                 "configured" if row.get("env_key") is None or os.environ.get(row["env_key"]) else "missing_key", now),
            )

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
            "INSERT INTO agent_runs (run_id, agent_id, version, status, input_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (run_id, agent["agent_id"], version, "RUNNING", json.dumps(input_data, ensure_ascii=False), now, now),
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
        return self.db.query(
            "SELECT r.*, a.slug, a.name FROM agent_runs r JOIN agents a ON a.agent_id=r.agent_id"
            " ORDER BY r.created_at DESC LIMIT ?", (limit,))

    def run(self, run_id):
        row = self.db.one("SELECT * FROM agent_runs WHERE run_id=?", (run_id,))
        if not row:
            return None
        row["steps"] = self.db.query("SELECT * FROM agent_steps WHERE run_id=? ORDER BY id", (run_id,))
        row["approvals"] = self.db.query("SELECT * FROM approvals WHERE run_id=? ORDER BY requested_at", (run_id,))
        return row

    def tools(self):
        return self.db.query("SELECT * FROM tools WHERE enabled=1 ORDER BY name")

    def connections(self):
        return self.db.query("SELECT * FROM connections ORDER BY provider")

    def approvals(self, status="PENDING"):
        return self.db.query("SELECT * FROM approvals WHERE status=? ORDER BY requested_at", (status,))

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
        agent_id = f"agent:{slug}"
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
