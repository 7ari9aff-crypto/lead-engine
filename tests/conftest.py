import os

# Tests run in explicit open mode: no auth backend is configured on CI/dev
# machines, and the platform now fails closed without this opt-in.
os.environ.setdefault("LEAD_ENGINE_DEV_OPEN", "1")
os.environ.pop("LEAD_ENGINE_ENV", None)

# Guardrail: the suite must NEVER touch real providers even when the local
# .env carries live keys (this machine does). Empty-string values block BOTH
# direct reads AND config.load_env() re-hydration (which only fills keys that
# are absent from os.environ). Tests script fake routers instead.
for _key in ("TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY", "EXA_API_KEY",
             "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
             "APOLLO_API_KEY", "HUNTER_API_KEY", "ABSTRACT_API_KEY",
             "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
             "SUPABASE_DB_URL", "DATABASE_URL",
             "LEAD_ENGINE_ADMIN_PASSWORD", "LEAD_ENGINE_ORG_ID"):
    os.environ[_key] = ""


def seed_control_plane(db) -> None:
    """Seed the agent control plane (agents/tools/connections/providers) into a
    fixture database.

    Seeding used to be a side effect of `AgentRegistry(db)`, which every request
    constructed; it now lives in the startup/`init` bootstrap (gap register
    LAT-01(a)), so tests that exercise agent-backed behaviour must ask for it
    explicitly. `bootstrap.run_once` is process-scoped, hence the reset: each
    fixture database gets seeded on its own terms regardless of test order.
    """
    from lead_engine.agent_registry import ensure_seeded
    from lead_engine.bootstrap import reset

    reset()
    ensure_seeded(db)
