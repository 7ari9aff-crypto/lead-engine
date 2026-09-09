"""Pipeline orchestrator: wires every stage together and owns the job state.

Stage order follows the design:
discovery -> normalize -> dedup -> hard filter -> qualification ->
enrichment -> verification -> scoring -> legal gate -> lead store.

Quota exhaustion never fails the job: the orchestrator PAUSES it with a
reason and resume_at, and the scheduler retries later.
"""
from datetime import datetime, timedelta, timezone

from ..cache import CacheLayer
from ..config import load_cache_policy, load_legal_policy
from ..db import utcnow
from ..jobs import COMPLETED, DEGRADED, JobManager, PAUSED, RUNNING
from ..router import NoProviderAvailable, Router
from .dedup import DedupEngine
from .discovery import Discovery
from .enrichment import Enrichment
from .filters import HardFilter, Scorer
from .legal_gate import LegalGate
from .qualification import Qualifier

ACCEPT_THRESHOLD = 60.0


class PipelineOrchestrator:
    def __init__(self, db, settings: dict, dry_run: bool = False, legal_country: str = None):
        self.db = db
        self.settings = settings
        self.legal_country = legal_country
        self.cache = CacheLayer(db, load_cache_policy())
        self.router = Router(db, self.cache, settings, dry_run=dry_run)
        self.jobs = JobManager(db)
        self.dry_run = dry_run

    def run_job(self, icp: dict, job_id=None, seed_leads=None) -> dict:
        if not job_id:
            job_id = self.jobs.create_job(icp["icp_id"])
        if self.jobs.current(job_id) not in (RUNNING, DEGRADED):
            self.jobs.transition(job_id, RUNNING)

        summary = {"job_id": job_id, "icp": icp["icp_id"], "stages": {}, "dry_run": self.dry_run}
        used_local_llm = False

        try:
            # 1) discovery
            plan = build_plan_from_icp(icp)
            candidates = Discovery(self.router).run(plan, job_id)
            if seed_leads:
                candidates.extend(seed_leads)
            summary["stages"]["discovery"] = {"raw_candidates": len(candidates)}

            # 2) normalize defaults
            for c in candidates:
                c.setdefault("country", icp.get("country"))
                c.setdefault("city", None)

            # 3) dedup (multi-stage)
            leads, dedup_stats = DedupEngine(self.settings).run(candidates)
            summary["stages"]["dedup"] = dedup_stats.__dict__

            # 4) hard filter
            hard = HardFilter(icp)
            kept = []
            dropped = 0
            for lead in leads:
                ok, reason = hard.apply(lead)
                if ok:
                    kept.append(lead)
                else:
                    lead["filter_reason"] = reason
                    dropped += 1
            summary["stages"]["hard_filter"] = {"kept": len(kept), "dropped": dropped}

            # 5) AI qualification
            qualifier = Qualifier(self.router)
            scored = 0
            skipped = 0
            for lead in kept:
                verdict = qualifier.qualify(lead, icp, job_id)
                if verdict.get("skipped"):
                    skipped += 1
                    continue
                if verdict.get("score") is not None:
                    lead["qualification_score"] = verdict["score"]
                    lead["tier"] = verdict.get("tier")
                    lead["processing_mode"] = verdict.get("processing_mode", "cloud")
                    if verdict.get("processing_mode") == "degraded_local":
                        used_local_llm = True
                if verdict.get("requires_review"):
                    lead["requires_review"] = True
                scored += 1
            summary["stages"]["qualification"] = {"scored": scored, "skipped": skipped}

            # 6) selective enrichment (budgeted)
            ordered = sorted(kept, key=lambda l: -(l.get("qualification_score") or 0))
            estats = Enrichment(self.router).run(ordered, plan, job_id)
            summary["stages"]["enrichment"] = estats

            # 7) email verification (5-state, catch-all aware)
            from ..providers.email import VerificationPipeline

            verifier = VerificationPipeline(self.router)
            verified = 0
            for lead in kept:
                if lead.get("email"):
                    verdict = verifier.verify(lead["email"])
                    lead["email_status"] = verdict.get("status")
                    lead["email_confidence"] = verdict.get("confidence")
                    verified += 1
            summary["stages"]["verification"] = {"verified": verified}

            # 8) scoring + legal gate + store
            gate = LegalGate(load_legal_policy(self.legal_country or icp.get("legal_policy") or "default"))
            scorer = Scorer(self.settings)
            for lead in kept:
                lead["score"] = scorer.score(lead)
                verdict = gate.evaluate(lead)
                lead["legal_decision"] = verdict["decision"]
                lead["retention_days"] = verdict["retention_days"]
                if verdict["requires_review"]:
                    lead["requires_review"] = True
                if not verdict["storage_allowed"]:
                    lead["stage"] = "REJECTED"
                elif lead.get("requires_review"):
                    lead["stage"] = "REVIEW"
                elif (lead.get("qualification_score") or 0) >= ACCEPT_THRESHOLD:
                    lead["stage"] = "ACCEPTED"
                else:
                    lead["stage"] = "REVIEW"
                lead["job_id"] = job_id
                self.db.insert_lead(lead)
                for url, query in zip(lead.get("source_urls") or [], lead.get("source_queries") or []):
                    self.db.add_evidence(lead.get("lead_id"), f"Listed in results for '{query}'",
                                         url, "web_search")
            summary["stages"]["legal_gate"] = {
                "accepted": sum(1 for l in kept if l.get("stage") == "ACCEPTED"),
                "review": sum(1 for l in kept if l.get("stage") == "REVIEW"),
                "rejected": sum(1 for l in kept if l.get("stage") == "REJECTED"),
            }
            summary["leads"] = kept
            summary["final_leads"] = len(kept)

            if used_local_llm:
                self.jobs.transition(job_id, DEGRADED, "local LLM used for some tasks")
            self.jobs.transition(job_id, COMPLETED)
            summary["state"] = COMPLETED
            self._store_summary(job_id, summary)
            return summary

        except NoProviderAvailable as exc:
            seconds = (self.settings.get("job", {}) or {}).get("pause_backoff_seconds", 1800)
            resume_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            self.jobs.pause(job_id, f"NO_AVAILABLE_PROVIDER:{exc.task}", resume_at)
            self._store_summary(job_id, summary)
            summary["state"] = PAUSED
            summary["pause_reason"] = str(exc)
            summary["resume_at"] = resume_at
            return summary

    def _store_summary(self, job_id: str, summary: dict):
        import json

        slim = {k: v for k, v in summary.items() if k != "leads"}
        self.db.execute("UPDATE jobs SET result=?, updated_at=? WHERE job_id=?",
                        (json.dumps(slim, ensure_ascii=False, default=str), utcnow(), job_id))


def build_plan_from_icp(icp: dict) -> dict:
    # imported here to avoid a circular import at module load
    from .icp import build_plan

    return build_plan(icp)
