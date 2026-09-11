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
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lead_engine", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create database and seed provider registry")
    sub.add_parser("providers", help="show provider registry status + usage")

    bench = sub.add_parser("benchmark", help="run the live lead generation pipeline")
    bench.add_argument("--icp", default="v0_saudi_dental")
    bench.add_argument("--seed", help="CSV path with manually collected clinics")
    bench.add_argument("--no-report", action="store_true")

    verify = sub.add_parser("verify-email", help="run the 5-state email verification pipeline")
    verify.add_argument("--email", required=True)

    resume = sub.add_parser("resume", help="resume a PAUSED job")
    resume.add_argument("--job", required=True)

    worker = sub.add_parser("worker", help="run the job worker (platform queue mode)")
    worker.add_argument("--poll", type=int, default=5, help="seconds between polls")
    worker.add_argument("--once", action="store_true", help="process one job then exit")

    serve = sub.add_parser("serve", help="run the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    from .config import DATA_DIR, DB_PATH, load_env, load_settings
    from .db import open_db

    load_env()
    settings = load_settings()

    if args.cmd == "init":
        DATA_DIR.mkdir(exist_ok=True)
        db = open_db()
        from .registry import Registry

        Registry(db).seed_if_empty()
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

        router = Router(db, CacheLayer(db, load_cache_policy()), settings)
        result = VerificationPipeline(router).verify(args.email)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "resume":
        db = open_db()
        from .jobs import JobManager
        from .pipeline.orchestrator import PipelineOrchestrator

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

        from . import queue
        from .benchmark.run import run_benchmark

        worker_id = f"worker-{socket.gethostname()}-{os.getpid()}"
        print(f"worker {worker_id} polling every {args.poll}s")
        while True:
            queue.reclaim_expired(db)
            job = queue.lease_next(db, worker_id)
            if not job:
                if args.once:
                    print("queue empty")
                    return 0
                _time.sleep(args.poll)
                continue
            job_id, icp_id = job["job_id"], job["icp_id"]
            print(f"leased {job_id} (icp={icp_id}, attempt={job['attempts']})")
            try:
                summary, _metrics, _outputs = run_benchmark(
                    load_icp(icp_id), job_id=job_id)
                state = summary.get("state") or "COMPLETED"
                if state == "PAUSED":
                    queue.fail(db, job_id, summary.get("pause_reason") or "paused")
                else:
                    queue.complete(db, job_id)
                print(f"{job_id} -> {state}")
            except Exception as exc:
                state = queue.fail(db, job_id, f"{type(exc).__name__}: {exc}")
                print(f"{job_id} failed -> {state}: {exc}")
            if args.once:
                return 0

    if args.cmd == "serve":
        import uvicorn

        from .api.app import app

        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
