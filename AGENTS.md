# AGENTS.md — Lead Engine

## Architecture
- **Backend**: Python FastAPI app (`lead_engine/api/app.py`), SQLite persistence (`lead_engine/db.py`), runs on port 8000.
- **Frontend**: React 19 + Vite 6 SPA (`web/`), runs on port 5173 (mapped to host 3000).
- **Wiring**: Single-origin — the Vite dev server proxies all API paths (`/api`, `/providers`, `/leads`, `/jobs`, `/benchmark`, `/health`, etc.) to the backend. The browser only talks to port 3000. Cookie-based auth works because everything is same-origin through the proxy.
- **`BACKEND_URL` env var** (not `VITE_` prefixed) tells the Vite proxy where the backend is. In Docker it's `http://backend:8000`. The client uses relative URLs so the proxy stays in the path.

## Boot sequence
1. Backend: `pip install -r requirements.txt` → `python -m lead_engine init` (creates SQLite DB + seeds provider registry) → `uvicorn ... --reload`
2. Frontend: `corepack enable` → `pnpm install` → `pnpm dev` (Vite dev server with HMR)

## Auth
- `LEAD_ENGINE_ADMIN_PASSWORD` enables the login gate. If unset, auth is disabled and the dashboard is open.
- `LEAD_ENGINE_AUTH_SECRET` signs the session cookie (HMAC). Falls back to the admin password if unset.
- `LEAD_ENGINE_COOKIE_SECURE` — if set to any non-empty value, cookies get `Secure`. Leave unset for the preview (internal proxy is HTTP).
- Cookie is `HttpOnly`, `SameSite=Lax`, 12-hour TTL.

## API keys (all optional)
Missing keys → the provider is filtered out and the router falls back to the next one. The app boots and serves the dashboard with zero API keys. See `.env.example` for the full list.

## Key files
- `lead_engine/api/app.py` — FastAPI app, all routes, admin middleware
- `lead_engine/api/auth.py` — cookie session logic
- `lead_engine/db.py` — SQLite schema (providers, jobs, leads, usage_ledger, cache)
- `lead_engine/registry.py` — provider registry + seeding
- `lead_engine/router.py` — provider router (quota, rate limit, health)
- `lead_engine/pipeline/` — the lead generation pipeline stages
- `web/src/lib/api.ts` — frontend API client (relative URLs through Vite proxy)
- `web/src/pages/` — dashboard pages (Overview, Keys, Providers, Jobs, Leads, Chat, etc.)

## pnpm build scripts
pnpm 12 blocks esbuild's build scripts by default (`ERR_PNPM_IGNORED_BUILDS`). The compose sets `PNPM_CONFIG_DANGEROUSLY_ALLOW_ALL_BUILDS=true` to bypass this. The `onlyBuiltDependencies` in `pnpm-workspace.yaml` is present but insufficient on its own with pnpm 12.3.4.

## Verify the app works
```bash
docker compose -f docker-compose.base44.yml up -d --build
docker compose -f docker-compose.base44.yml ps
curl -s http://localhost:8000/health | head
curl -s http://localhost:3000 | head
```
The frontend at :3000 should show the dashboard (or login gate if `LEAD_ENGINE_ADMIN_PASSWORD` is set).

## Tests
```bash
docker compose -f docker-compose.base44.yml exec backend python -m pytest tests/ -x
```
