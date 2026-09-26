# ADR-0008 — Deployment: API on Vercel later, worker on containers (deferred)

Status: accepted

During the V6 build phase the system runs locally only; Vercel is out of the
loop. At deployment time:

- The API is a stateless FastAPI app — it can stay on Vercel functions.
- The durable worker (leases + checkpoints, potentially minutes-long) cannot
  be a Vercel function on the Hobby plan (60 s cap). It ships as one
  `lead-engine-worker` image with per-subscription deployments
  (worker-discovery, worker-verification, worker-webhook, …) on a container
  host (Railway/Fly/VPS — final host decided at the deployment wave).
- Because the worker is one binary with different subscriptions, moving it is
  a deployment detail, not a code change.
- Legacy vercel.json keeps a 60 s cap; V6 work merges to `v6-foundation` and
  only reaches `main` at coherent wave boundaries so the GitHub→Vercel
  auto-deploy never publishes a half-migrated system.
