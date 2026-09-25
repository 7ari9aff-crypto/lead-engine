"""The agentic research orchestrator (R3).

Chat -> Agent -> Intent -> Research Plan -> Tool Calls -> Observations ->
Replanning -> Evidence Collection -> Verification -> Qualification -> Review
(directive §36).

Design:
- The loop is STATELESS between iterations: objective, plan, counters, facts
  and the step trail live in the DB — a crashed worker restarts and resumes
  from research_context + research_facts (directive §33).
- The model proposes ACTIONS as strict JSON (portable across the whole LLM
  pool — not just native-function-calling providers); a small deterministic
  layer validates scopes and budgets before anything executes.
- Model strategy (§42): the PLANNER and the per-turn actor run on the agent
  version's pinned provider — if it is unavailable the job PAUSES
  (WAITING_FOR_CAPACITY), it never silently downgrades. Tools internally may
  use the regular pool.
- Stop logic (§41): objective satisfied (model says done AND coverage gate
  passes), diminishing returns (no new candidates for N rounds), budget
  exhausted (§40 guardrails), user stop, capacity loss. Every stop records
  stop_reason and lands the job at READY_FOR_REVIEW — never COMPLETED
  without the human gate.
- No tool named send_* exists; approval authority stays human (§31).
"""
import json
from datetime import datetime, timedelta, timezone

from ..agent_registry import AgentRegistry
from ..cache import CacheLayer
from ..config import load_cache_policy
from ..db import utcnow
from ..jobs import (
    CANCELLED, COMPLETED, FAILED, PAUSED, READY_FOR_REVIEW, RUNNING, WAITING_FOR_USER,
)
from ..router import NoProviderAvailable, Router
from ..truth import FactsStore
from .manager import ResearchJobManager
from .tools import ScopeDenied, ToolContext, execute_tool

ACTOR_SYSTEM = """أنت وكيل بحث B2B ذاتي داخل نظام Lead Engine.
هدفك تحقيق هدف البحث المعطى بأدوات حقيقية، وتحوّل كل معلومة تتعلمها إلى حقائق
موثقة بمصدرها. أنت لا ترسل أي شيء لأحد أبدًا — دورك البحث والتوثيق والتأهيل فقط.

قواعد صارمة:
- كل ملاحظة تتعلمها عن شركة تُحفظ بأداة save_fact مع مصدرها (url) — لا تعتمد
  على ذاكرتك ولا تؤجل الحفظ.
- المعلومات من مقتطفات البحث تعتبر UNVERIFIED؛ تحتاج مصدرًا ثانيًا مستقلًا
  لتصبح VERIFIED — كرر المصادر المختلفة للحقول المهمة (هاتف، إيميل، عدد فروع).
- التعميق أهم من التكرار: بعد أول بحث، راجع المرشحين وحسّن أدق حقولهم
  (فروع، صانع قرار، إشارات تسويق) بمصادر إضافية بدل جمع أسماء جديدة فقط.
- إذا تعذر التقدم بسبب نقص معلومة من المستخدم نفسه، استخدم ask_user.
- لا تخترع شركات أو أرقامًا. المصداقية أهم من الكمية.
- عند اكتمال التغطية الكافية (عدد مرشحين جيد + حقول مهمة موثقة) أعلن done=true.

أعد JSON فقط:
{"thought": "خطة الجولة الحالية بسطرين",
 "actions": [{"tool": "اسم الأداة", "args": {...}}],   // حتى 4 أدوات
 "done": false,
 "note": "سطر يشرح حالة التقدم للمستخدم"}
"""

PLANNER_PROMPT = """أنت مخطط بحث B2B. حوّل الهدف التالي إلى خطة بحث قابلة للتنفيذ
باستعلامات بحث ويب (عربي + إنجليزي). أعد JSON فقط:
{{"queries": [{{"q": "...", "city": "...", "lang": "ar|en"}}],
 "target_candidates": <عدد الشركات المستهدف>,
 "verify_fields": ["phone", "email", "branches"],
 "notes": "..."}}

الهدف: {objective}

ICP (إن وجد):
{icp}
"""

STALL_ROUNDS_LIMIT = 3
MAX_PARSE_RETRIES = 1


class OrchestratorError(RuntimeError):
    pass


class ResearchOrchestrator:
    def __init__(self, db, settings: dict, job_id: str, *,
                 router: Router | None = None):
        self.db = db
        self.settings = settings or {}
        self.job_id = job_id
        self.manager = ResearchJobManager(db, settings)
        self.store = FactsStore(db)
        self.registry = AgentRegistry(db)
        self.router = router or Router(db, CacheLayer(db, load_cache_policy()),
                                       self.settings)
        self.agent_slug = "lead-research"

    # ---------------------------------------------------------------- run
    def run(self) -> dict:
        state = self.manager.jobs.current(self.job_id)
        if state in (CANCELLED, COMPLETED, FAILED, PAUSED):
            return self._summary(state)
        if state != RUNNING:
            # QUEUED / RESUMING / WAITING_FOR_USER(answered) / a phase -> RUNNING
            self.manager.jobs.transition(self.job_id, RUNNING)
        agent_run_id = self._ensure_agent_run()
        try:
            return self._loop(agent_run_id)
        except NoProviderAvailable as exc:
            backoff = (self.settings.get("job", {}) or {}).get(
                "pause_backoff_seconds", 1800)
            resume_at = (datetime.now(timezone.utc)
                         + timedelta(seconds=backoff)).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.manager.pause_for_capacity(
                self.job_id, f"NO_CAPACITY:{exc.task}", resume_at)
            return self._summary(PAUSED, note=str(exc))

    # --------------------------------------------------------------- loop
    def _loop(self, agent_run_id: str) -> dict:
        ctx = self.manager.context(self.job_id)
        objective = ctx["objective"]
        plan = ctx.get("plan")
        if not plan:
            self.manager.set_phase(self.job_id, "DISCOVERING", "planning")
            plan = self._make_plan(objective, agent_run_id)
            self.manager.set_plan(self.job_id, plan)

        last_candidates = 0
        stall_rounds = 0
        last_actions: list = []
        stop_reason = stop_detail = None
        while True:
            current = self.manager.jobs.current(self.job_id)
            if current in (CANCELLED, PAUSED, COMPLETED, FAILED, WAITING_FOR_USER):
                return self._summary(current)
            ok, exceeded, snap = self.manager.budget_check(self.job_id)
            if not ok:
                # a budget stop does NOT skip closure: whatever was learned
                # still gets verified, qualified and presented — the user must
                # see the partial knowledge, never an empty gate (§41 + §46)
                stop_reason, stop_detail = "BUDGET_EXHAUSTED", f"{exceeded}: {snap}"
                break
            self.manager.bump_counter(self.job_id, "steps")
            turn = self._agent_turn(objective, plan, agent_run_id,
                                    last_actions=last_actions)
            self.manager.bump_counter(self.job_id, "model_calls")
            last_actions = turn.get("actions") or []
            candidates = int(self.manager.counters(self.job_id).get("candidates") or 0)
            if candidates > last_candidates:
                stall_rounds = 0
            else:
                stall_rounds += 1
            last_candidates = candidates
            if turn.get("done"):
                break
            if stall_rounds >= STALL_ROUNDS_LIMIT:
                stop_reason, stop_detail = ("DIMINISHING_RETURNS",
                                            f"no new candidates for {stall_rounds} rounds")
                break
            if self.manager.jobs.current(self.job_id) == WAITING_FOR_USER:
                return self._summary(WAITING_FOR_USER,
                                     note=turn.get("note") or "waiting for user input")

        return self._finalize(agent_run_id, stop_reason=stop_reason,
                              stop_detail=stop_detail)

    # ------------------------------------------------------ agent turn
    def _agent_turn(self, objective: str, plan: dict, agent_run_id: str,
                    last_actions: list | None = None) -> dict:
        from .tools import render_tool_docs

        ctx = self._tool_context(agent_run_id)
        progress = self.manager.progress(self.job_id)
        digest = self._facts_digest()
        step_number = int(self.manager.counters(self.job_id).get("steps") or 0)
        observations = json.dumps(last_actions or [], ensure_ascii=False,
                                  default=str)[:3500]
        prompt = (f"هدف البحث: {objective}\n\nالخطة: "
                  f"{json.dumps(plan, ensure_ascii=False)}\n\n"
                  f"التقدم الحالي: {json.dumps(progress, ensure_ascii=False, default=str)}\n\n"
                  f"نتائج أدواتك في الجولة السابقة (هذه ملاحظاتك — احفظ ما تعلمته "
                  f"بـsave_fact فورًا): {observations}\n\n"
                  f"آخر الحقائق المخزنة (مختصر): {digest}\n\n"
                  f"{render_tool_docs()}\n\n"
                  "قرر الجولة التالية: أعد JSON بالشكل المطلوب.")
        payload = {"prompt": ACTOR_SYSTEM + "\n\n" + prompt, "json_mode": True}
        prefer = self._pinned_provider()
        step_id = self.registry.start_step(agent_run_id, f"turn:{step_number}",
                                           input_data={"objective": objective})
        result, meta = self.router.route("reasoning", payload, job_id=self.job_id,
                                         use_cache=False, prefer_provider=prefer)
        self.manager.bump_counter(self.job_id, "model_calls")
        data = _parse_json(result.get("text", ""))
        if data is None:
            # one corrective retry, then treat as a stalled round
            retry_payload = {"prompt": payload["prompt"] +
                             "\n\nتنبيه: ردك السابق ليس JSON صالحًا. أعد JSON فقط.",
                             "json_mode": True}
            result, meta = self.router.route("reasoning", retry_payload,
                                             job_id=self.job_id, use_cache=False,
                                             prefer_provider=prefer)
            self.manager.bump_counter(self.job_id, "model_calls")
            data = _parse_json(result.get("text", ""))
            if data is None:
                self.registry.finish_step(step_id, "FAILED",
                                          error="model output unparseable twice")
                return {"done": False, "note": "model output unparseable",
                        "actions": []}

        executed = []
        for action in (data.get("actions") or [])[:4]:
            name = action.get("tool")
            args = action.get("args") or {}
            try:
                out = execute_tool(ctx, name, args, registry=self.registry)
                executed.append({"tool": name, "ok": "error" not in out,
                                 "summary": json.dumps(out, ensure_ascii=False,
                                                       default=str)[:220]})
            except ScopeDenied as exc:
                executed.append({"tool": name, "ok": False,
                                 "summary": f"SCOPE DENIED: {exc}"})
            except Exception as exc:
                executed.append({"tool": name, "ok": False,
                                 "summary": f"{type(exc).__name__}: {exc}"[:200]})
        self.registry.finish_step(step_id, "COMPLETED", output={
            "thought": data.get("thought"), "note": data.get("note"),
            "actions": executed, "provider": meta.get("provider")})
        return {"done": bool(data.get("done")), "note": data.get("note"),
                "actions": executed}

    # ------------------------------------------------------------- phases
    def _finalize(self, agent_run_id: str, *, stop_reason: str | None = None,
                  stop_detail: str | None = None) -> dict:
        """Verification sweep + qualification of every candidate subject, then
        materialize leads and park at the review gate. Nothing here
        re-discovers (directive §25)."""
        self.manager.set_phase(self.job_id, "VERIFYING", "verification sweep")
        self._verify_emails(agent_run_id)
        self.manager.set_phase(self.job_id, "QUALIFYING", "evidence-grounded fit")
        verdicts = self._qualify_all(agent_run_id)
        materialized = self._materialize_leads(verdicts)
        candidates = int(self.manager.counters(self.job_id).get("candidates") or 0)
        target = int((self.manager.context(self.job_id).get("plan") or {})
                     .get("target_candidates") or 0)
        if stop_reason:
            reason = stop_reason
            detail = f"{stop_detail or ''}; {materialized} leads ready for review"
        elif target and candidates >= target:
            reason, detail = "OBJECTIVE_SATISFIED", f"{candidates}/{target} candidates"
        else:
            reason, detail = "COVERAGE_ADEQUATE", f"{candidates} candidates"
        return self._gate(reason, detail, agent_run_id)

    def _verify_emails(self, agent_run_id: str) -> int:
        from ..providers.email import VerificationPipeline

        verifier = VerificationPipeline(self.router)
        verified = 0
        rows = self.db.query(
            "SELECT fact_id, subject_id, value FROM research_facts"
            " WHERE field='email' AND status IN ('UNVERIFIED','VERIFIED')"
            " AND job_id=?", (self.job_id,))
        for row in rows:
            if self.manager.jobs.current(self.job_id) in (CANCELLED, PAUSED):
                break
            verdict = verifier.verify(row["value"])
            outcome = "verified" if verdict.get("status") == "DELIVERABLE" else "refuted"
            self.store.verify_fact(
                row["fact_id"], outcome=outcome,
                confidence=verdict.get("confidence"), provider=verdict.get("via"),
                quote=json.dumps({"status": verdict.get("status"),
                                  "reason": (verdict.get("details") or {}).get("reason")},
                                 ensure_ascii=False))
            self.manager.bump_counter(self.job_id, "verifications")
            verified += 1
        return verified

    def _qualify_all(self, agent_run_id: str) -> dict:
        """Qualify every candidate subject from stored facts ONLY.
        Returns {subject_id: verdict}."""
        from .qualification import QualificationError, qualify_from_facts
        from .tools import _active_icp

        icp = _active_icp(self._tool_context(agent_run_id))
        subjects = self.db.query(
            "SELECT DISTINCT subject_id FROM research_facts"
            " WHERE job_id=? AND subject_kind='company'"
            " ORDER BY subject_id", (self.job_id,))
        verdicts = {}
        for row in subjects:
            if self.manager.jobs.current(self.job_id) in (CANCELLED, PAUSED):
                break
            step_id = self.registry.start_step(agent_run_id,
                                               f"qualify:{row['subject_id']}",
                                               input_data={})
            try:
                verdict = qualify_from_facts(self.db, self.router, "company",
                                             row["subject_id"], icp,
                                             store=self.store, job_id=self.job_id)
                self.manager.bump_counter(self.job_id, "model_calls")
                self.registry.finish_step(step_id, "COMPLETED", output={
                    "fit_score": verdict["fit_score"], "tier": verdict["tier"],
                    "why": verdict["why"][:3]})
                verdicts[row["subject_id"]] = verdict
            except QualificationError as exc:
                self.registry.finish_step(step_id, "FAILED", error=str(exc)[:300])
            self.manager.bump_counter(self.job_id, "qualifications")
        return verdicts

    def _materialize_leads(self, verdicts: dict) -> int:
        """Turn qualified subjects into lead rows so the human review layer
        (Stage 3) has something to present and decide on."""
        from ..config import load_legal_policy
        from ..pipeline.filters import Scorer
        from ..pipeline.legal_gate import LegalGate

        scorer = Scorer(self.settings)
        gate = LegalGate(load_legal_policy("default"))
        count = 0
        skipped_thin = 0
        for subject_id, verdict in verdicts.items():
            facts = self.store.facts_for_qualification("company", subject_id)
            values = facts["values"]
            # evidence threshold (stage 2 filter, deterministic): a subject the
            # research could only name — directories, aggregators, stray pages —
            # is not a lead. At least a contact field, or 2+ distinct facts.
            contact_present = any(values.get(k) for k in
                                  ("phone", "email", "decision_maker"))
            if len(values) < 2 and not contact_present:
                skipped_thin += 1
                continue
            lead_id = f"{getattr(self.db, 'org_id', None) or 'shared'}:{subject_id}"
            email = values.get("email")
            is_domain_subject = not subject_id.startswith("name:")
            lead = {
                "lead_id": lead_id,
                "job_id": self.job_id,
                "name": values.get("name") or subject_id,
                "domain": values.get("domain") or (
                    subject_id if is_domain_subject else None),
                "city": values.get("city"),
                "country": values.get("country"),
                "industry": values.get("industry"),
                "branches": int(values["branches"])
                if str(values.get("branches") or "").isdigit() else None,
                "phone": values.get("phone"),
                "email": email,
                "decision_maker": values.get("decision_maker"),
                "decision_maker_title": values.get("decision_maker_title"),
                "linkedin": values.get("linkedin"),
                "website": values.get("website") or (
                    f"https://{subject_id}" if is_domain_subject else None),
                "qualification_score": verdict["fit_score"],
                "tier": verdict["tier"],
                "processing_mode": verdict.get("processing_mode", "cloud"),
                "sources": ["research_agent"],
                "source_queries": [f"research:{self.job_id}"],
                "raw": json.dumps({"pipeline": {"qualification": verdict}},
                                  ensure_ascii=False, default=str),
            }
            lead["score"] = scorer.score(lead)
            gate_verdict = gate.evaluate(lead)
            lead["legal_decision"] = gate_verdict["decision"]
            # research leads land in REVIEW: the human gate decides from here
            lead["stage"] = "REJECTED" if not gate_verdict["storage_allowed"] \
                else "REVIEW"
            if email:
                row = self.db.one(
                    "SELECT status FROM research_facts WHERE subject_id=? AND"
                    " field='email' AND value=? ORDER BY collected_at DESC LIMIT 1",
                    (subject_id, email))
                lead["email_status"] = row["status"] if row else None
            self.db.insert_lead(lead)
            count += 1
        if skipped_thin:
            self.manager.bump_counter(self.job_id, "thin_candidates_skipped",
                                      skipped_thin)
        return count

    # ----------------------------------------------------------- planning
    def _make_plan(self, objective: str, agent_run_id: str) -> dict:
        from ..icp_store import ICPStore

        icps = ICPStore(self.db)
        ctx_row = self.manager.context(self.job_id) or {}
        icp = {}
        if ctx_row.get("icp_version_id"):
            row = icps.get(ctx_row["icp_version_id"])
            icp = row["definition"] if row else {}
        prompt = PLANNER_PROMPT.format(
            objective=objective, icp=json.dumps(icp, ensure_ascii=False)[:2000])
        result, meta = self.router.route(
            "reasoning", {"prompt": prompt, "json_mode": True},
            job_id=self.job_id, use_cache=False,
            prefer_provider=self._pinned_provider())
        self.manager.bump_counter(self.job_id, "model_calls")
        plan = _parse_json(result.get("text", "")) or {}
        plan.setdefault("queries", [])
        plan.setdefault("target_candidates", 30)
        plan.setdefault("verify_fields", ["phone", "email"])
        return plan

    # ------------------------------------------------------------- wiring
    def _tool_context(self, agent_run_id: str) -> ToolContext:
        scopes = self._agent_scopes()
        return ToolContext(db=self.db, router=self.router, store=self.store,
                           manager=self.manager, job_id=self.job_id,
                           allowed_scopes=scopes, run_id=agent_run_id)

    def _agent_scopes(self) -> set:
        payload = self.registry.get_active_version(self.agent_slug)
        scopes = ((payload or {}).get("version") or {}).get("tool_policy") or {}
        return set(scopes.get("scopes") or [])

    def _pinned_provider(self) -> str | None:
        payload = self.registry.get_active_version(self.agent_slug)
        provider = ((payload or {}).get("version") or {}).get("model_provider")
        return provider if provider and provider != "router" else None

    def _has_run_id_column(self) -> bool:
        if getattr(self, "_has_run_id_col", None) is not None:
            return self._has_run_id_col
        try:
            if getattr(self.db, "dialect", "sqlite") == "postgres":
                cols = self.db.query(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='research_context' AND column_name='run_id'"
                )
                self._has_run_id_col = bool(cols)
            else:
                existing = {row["name"] for row in self.db.conn.execute("PRAGMA table_info(research_context)")}
                self._has_run_id_col = "run_id" in existing
        except Exception:
            self._has_run_id_col = False
        return self._has_run_id_col

    def _ensure_agent_run(self) -> str:
        ctx_row = self.manager.context(self.job_id) or {}
        run_id = ctx_row.get("run_id")
        if run_id:
            row = self.db.one("SELECT status FROM agent_runs WHERE run_id=?",
                              (run_id,))
            if row and row["status"] == "RUNNING":
                return run_id
            # a finished run from a previous session (RESEARCH_MORE) -> new run
        run_id = self.registry.create_run(self.agent_slug, {
            "job_id": self.job_id, "objective": ctx_row.get("objective")})
        if self._has_run_id_column():
            self.db.execute(
                "UPDATE research_context SET run_id=?, updated_at=? WHERE job_id=?",
                (run_id, utcnow(), self.job_id))
        else:
            self.db.execute(
                "UPDATE research_context SET updated_at=? WHERE job_id=?",
                (utcnow(), self.job_id))
        return run_id

    def _facts_digest(self) -> str:
        rows = self.db.query(
            "SELECT subject_id, field, value, status FROM research_facts"
            " WHERE job_id=? ORDER BY collected_at DESC LIMIT 40", (self.job_id,))
        digest = {}
        for r in rows:
            digest.setdefault(r["subject_id"], {})[f"{r['field']}({r['status']})"] = \
                r["value"]
        return json.dumps(digest, ensure_ascii=False)[:2500]

    def _gate(self, reason: str, detail: str, agent_run_id: str) -> dict:
        self.manager.ready_for_review(self.job_id, reason, detail)
        self._finish_run(agent_run_id, "COMPLETED")
        return self._summary(READY_FOR_REVIEW, note=detail)

    def _finish_run(self, agent_run_id: str, status: str) -> None:
        progress = self.manager.progress(self.job_id)
        self.registry.finish_run(agent_run_id, status, output={
            "job_id": self.job_id, "stop_reason": progress.get("stop_reason"),
            "stats": progress.get("stats")})

    def _summary(self, state: str, note: str | None = None) -> dict:
        progress = self.manager.progress(self.job_id)
        progress["note"] = note
        return progress


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    try:
        data = json.loads(text.strip())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
