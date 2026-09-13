-- 20260913000004_research_context_run.sql
-- R3: link a research job to its (resumable) agent run. A finished run from a
-- previous session stays for audit; RESEARCH_MORE opens a NEW run and updates
-- this pointer.

alter table engine.research_context add column if not exists run_id text;
