"""Lead Engine CLI.

  python -m lead_engine init
  python -m lead_engine benchmark                 # live run (needs API keys in .env)
  python -m lead_engine providers
  python -m lead_engine verify-email --email x@y.com
  python -m lead_engine resume --job JOB_ID
  python -m lead_engine serve --port 8000
"""
import argparse
import json
import os
import sys


def _bootstrap_control_plane(db=None) -> None:
    """Run the startup data steps, optionally on an already-open handle.

    `worker`, `benchmark`, `resume` and `verify-email` all read the provider
    registry and the agent/tool tables. They only ever worked on a fresh
    database because `Router.__init__` seeded providers as a side effect - and
    that side effect never covered agents/tools, so an operator who started the
    worker before `init` got silent empties. Same `run_once`-guarded,
    never-fatal steps the API lifespan runs; `init` stays the authoritative
    retry path.
    """
    from .bootstrap import run_data_bootstrap
    from .db import open_db

    owns = db is None
    if owns:
        db = open_db()
    try:
        run_data_bootstrap(db)
    except Exception as exc:  # pragma: no cover - defensive: boot regardless
        print(f"warning: startup bootstrap failed ({type(exc).__name__}: {exc})"
              f" - run `python -m lead_engine init`")
    finally:
        if owns:
            db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lead_engine", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create database and seed provider registry")
    sub.add_parser("providers", help="show provider registry status + usage")

    bench = sub.add_parser("benchmark", help="run the live lead generation pipeline")
    bench.add_argument("--icp", default="v0")
    bench.add_argument("--seed", help="CSV path with manually collected clinics")
    bench.add_argument("--no-report", action="store_true")

    verify = sub.add_parser("verify-email", help="run the 5-state email verification pipeline")
    verify.add_argument("--email", required=True)

    resume = sub.add_parser("resume", help="resume a PAUSED job")
    resume.add_argument("--job", required=True)

    evw = sub.add_parser("event-worker", help="dispatch outbox events (webhooks/notifications)")
    evw.add_argument("--once", action="store_true")

    worker = sub.add_parser("worker", help="run the job worker (platform queue mode)")
    worker.add_argument("--poll", type=int, default=5, help="seconds between polls")
    worker.add_argument("--once", action="store_true", help="process one job then exit")

    serve = sub.add_parser("serve", help="run the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    from .config import DATA_DIR, load_env, load_settings
    from .db import open_db

    load_env()
    settings = load_settings()

    if args.cmd == "init":
        DATA_DIR.mkdir(exist_ok=True)
        db = open_db()
        from .registry import Registry

        Registry(db).seed_if_empty()
        # Authoritative schema+seed path: the request path never does this work.
        from .activity.store import ensure_schema as _ensure_activity_schema
        try:
            _ensure_activity_schema(db)
        except Exception as exc:
            # Postgres: migrations own DDL and the app role has no CREATE
            # privilege on `engine`, so this statement can never succeed there
            # - the table arrives via a migration. Not fatal: seeding follows.
            print(f"note: activity schema skipped "
                  f"({type(exc).__name__}: {exc})")
        from .agent_registry import ensure_seeded as _seed_agents
        _seed_agents(db)
        print(f"database ready ({getattr(db, 'dialect', 'sqlite')} backend)")
        return 0

    if args.cmd == "providers":
        db = open_db()
        from .registry import Registry

        Registry(db).seed_if_empty()
        rows = Registry(db).status_table()
        for r in rows:
            key_state = "local" if r["env_key"] is None else (
                "key:set" if r.get("env_key") else "key:MISSING")
            print(f"{r['task']:<14} #{r['priority']} {r['name']:<12} {r['status']:<10} "
                  f"{key_state:<11} used={r['quota_used']}/{r['quota_limit']} {r['period'] or ''}")
        return 0

    if args.cmd == "benchmark":
        from .benchmark.run import run_benchmark

        # run_benchmark opens its own handle, so seed on a throwaway one.
        _bootstrap_control_plane()
        summary, metrics, outputs = run_benchmark(
            args.icp, seed_csv=args.seed, write=not args.no_report)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print(f"\nstate: {summary.get('state')}")
        if outputs:
            print(f"report: {outputs.get('report')}\ncsv: {outputs.get('csv')}")
        return 0

    if args.cmd == "verify-email":
        db = open_db()
        from .cache import CacheLayer
        from .config import load_cache_policy
        from .providers.email import VerificationPipeline
        from .router import Router

        _bootstrap_control_plane(db)
        router = Router(db, CacheLayer(db, load_cache_policy()), settings)
        result = VerificationPipeline(router).verify(args.email)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "resume":
        db = open_db()
        from .jobs import JobManager
        from .pipeline.orchestrator import PipelineOrchestrator

        _bootstrap_control_plane(db)
        jobs = JobManager(db)
        jobs.resume(args.job)
        row = db.one("SELECT icp_id FROM jobs WHERE job_id=?", (args.job,))
        from .config import load_icp

        orchestrator = PipelineOrchestrator(db, settings)
        summary = orchestrator.run_job(load_icp(row["icp_id"]), job_id=args.job)
        print(json.dumps({k: v for k, v in summary.items() if k != "leads"},
                         ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "worker":
        import socket
        import time as _time

        from .config import load_settings
        from .worker import run_worker_tick

        worker_id = f"worker-{socket.gethostname()}-{os.getpid()}"
        # A worker started before `init` used to lease jobs against an empty
        # control plane and produce silent nothing. Startup now seeds here too.
        _bootstrap_control_plane()
        print(f"worker {worker_id} polling every {args.poll}s")
        while True:
            # fresh connection per iteration: poolers/servers drop long-held
            # sessions and a job run takes minutes between queue operations
            db = open_db()
            result = run_worker_tick(db, worker_id, settings=load_settings())
            if not result["leased"]:
                if args.once:
                    print("queue empty")
                    return 0
                _time.sleep(args.poll)
                continue
            if result["error"]:
                print(f"{result['job_id']} failed -> "
                      f"{result['state']}: {result['error']}")
            else:
                print(f"{result['job_id']} -> {result['state']}")
            if args.once:
                return 0

    if args.cmd == "event-worker":
        import time as _time

        from .events import dispatch_pending

        db = open_db()
        while True:
            counts = dispatch_pending(db)
            if args.once or not counts.get("retried"):
                print(f"event dispatch: {counts}")
                return 0
            _time.sleep(2)

    if args.cmd == "serve":
        import uvicorn

        from .api.app import app

        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
