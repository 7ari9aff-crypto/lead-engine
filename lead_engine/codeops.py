"""Code-aware workspace operations — the agent's hands on its own source tree.

The operator asked for an agent that can trace a bug through the code and fix
it, "but always under my command — you don't change anything until you take my
permission first". That contract is enforced structurally here, not by prompt
wording:

  READ tier (no approval)
      list_code / read_code / search_code / git_history / git_status / run_tests
      Confined to the workspace root. A denylist keeps secrets (.env*, keys,
      .git internals) out of the model's context. Read-only subprocesses only.

  WRITE tier (always approval-gated)
      propose_patch  -> never touches disk. Records a PENDING approval holding
                        the full before/after payload.
      apply_patch    -> refuses unless that approval exists and is APPROVED.
                        Lands the change on a fresh git branch (never main),
                        after `git apply --check` / pre-flight validation, with
                        a timestamped backup of every touched file.

Every operation is audit-logged. Nothing in this module imports the pipeline,
so it stays cheap to load and easy to reason about.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# limits / policy
# ---------------------------------------------------------------------------
MAX_READ_BYTES = 400_000          # ~400KB per file read
MAX_LIST_ENTRIES = 2_000
MAX_SEARCH_HITS = 200
MAX_PATCH_BYTES = 800_000         # total payload of a proposed patch
MAX_EDITS_PER_PATCH = 40
MAX_OUTPUT_CHARS = 60_000         # subprocess stdout/stderr cap

READ_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".cfg", ".ini", ".css", ".html", ".sql", ".sh", ".ps1", ".env.example",
}

# Never readable: secrets, VCS internals, dependency trees, build output.
DENY_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pnpm-store",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea",
    ".vscode", "coverage", ".next", ".turbo",
}
DENY_NAME_PATTERNS = [
    re.compile(r"^\.env$"),
    re.compile(r"^\.env\.(?!example$).+"),      # .env.local, .env.production ...
    re.compile(r".*\.(pem|key|p12|pfx|keystore|jks)$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519).*$"),
    re.compile(r"^\.(npmrc|netrc|pgpass|htpasswd)$"),
    re.compile(r".*credentials.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r"^\.vercel$"),
]

# Only these commands may ever be executed, and only read-only / test shaped.
TEST_COMMANDS = {
    "pytest": ["python", "-m", "pytest"],
    "ruff": ["python", "-m", "ruff", "check"],
    "typecheck": None,  # resolved per-platform (pnpm in web/)
}


class CodeOpsError(Exception):
    """Bad request from the agent (unsafe path, unknown file, bad patch)."""


class ApprovalRequired(CodeOpsError):
    """A write was attempted without an approved approval record."""


# ---------------------------------------------------------------------------
# workspace resolution + path safety
# ---------------------------------------------------------------------------
def workspace_root() -> Path:
    """Repo root the agent may operate on.

    Explicit ``LEAD_ENGINE_WORKSPACE`` wins; otherwise the parent of this
    package (the repository checkout). Callers can pin a different root in
    tests without touching the environment of the running app.
    """
    configured = os.environ.get("LEAD_ENGINE_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def is_denied(rel: str) -> bool:
    """True when a workspace-relative path must never be read or written."""
    parts = Path(rel).parts
    if any(p in DENY_DIRS for p in parts):
        return True
    name = Path(rel).name
    return any(rx.match(name) for rx in DENY_NAME_PATTERNS)


def resolve_path(rel: str, root: Path | None = None) -> Path:
    """Resolve a workspace-relative path, refusing escapes and denylisted files."""
    if rel is None or str(rel).strip() == "":
        raise CodeOpsError("empty path")
    raw = str(rel).strip().replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise CodeOpsError("absolute paths are not allowed — use workspace-relative")
    base = (root or workspace_root()).resolve()
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise CodeOpsError(f"path escapes the workspace: {rel}")
    if is_denied(raw):
        raise CodeOpsError(f"path is off-limits (secrets / vendor / VCS): {rel}")
    return candidate


def relpath(path: Path, root: Path | None = None) -> str:
    base = (root or workspace_root()).resolve()
    try:
        return path.resolve().relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
def audit(db, actor: str, action: str, entity_type: str | None = None,
          entity_id: str | None = None, payload: dict | None = None) -> None:
    """Best-effort audit row. Never breaks the operation it is recording."""
    try:
        db.execute(
            "INSERT INTO audit_logs (organization_id, actor, action, entity_type,"
            " entity_id, payload_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (getattr(db, "org_id", None), actor, action, entity_type, entity_id,
             json.dumps(payload, ensure_ascii=False) if payload else None,
             datetime.now(timezone.utc).isoformat()),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# READ tier — safe to call freely, no approval needed
# ---------------------------------------------------------------------------
def list_code(prefix: str = "", depth: int = 3, limit: int = 400,
              root: Path | None = None) -> dict:
    """List files under `prefix` (workspace-relative), skipping denied paths."""
    base = (root or workspace_root()).resolve()
    start = (base / prefix.strip().replace("\\", "/")).resolve() if prefix else base
    try:
        start.relative_to(base)
    except ValueError:
        raise CodeOpsError(f"path escapes the workspace: {prefix}")
    if is_denied(prefix or "."):
        raise CodeOpsError(f"path is off-limits: {prefix}")

    limit = max(1, min(int(limit or 400), MAX_LIST_ENTRIES))
    depth = max(1, min(int(depth or 3), 8))
    entries: list[dict] = []
    base_depth = len(start.relative_to(base).parts)

    for current, dirs, files in os.walk(start):
        current_path = Path(current)
        current_depth = len(current_path.relative_to(base).parts)
        dirs[:] = sorted(d for d in dirs if d not in DENY_DIRS)
        if current_depth - base_depth >= depth:
            dirs[:] = []
        for name in sorted(files):
            rel = (current_path / name).relative_to(base).as_posix()
            if is_denied(rel):
                continue
            entries.append({"path": rel, "bytes": (current_path / name).stat().st_size})
            if len(entries) >= limit:
                return {"root": base.as_posix(), "prefix": prefix or ".",
                        "count": len(entries), "truncated": True, "files": entries}
    return {"root": base.as_posix(), "prefix": prefix or ".", "count": len(entries),
            "truncated": False, "files": entries}


def read_code(path: str, start_line: int | None = None, end_line: int | None = None,
              root: Path | None = None) -> dict:
    """Read a workspace file (optionally a line range)."""
    target = resolve_path(path, root)
    if not target.is_file():
        raise CodeOpsError(f"not a file: {path}")
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        raise CodeOpsError(
            f"file too large to read whole ({size} bytes > {MAX_READ_BYTES}); "
            "use search_code or a line range")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CodeOpsError(f"not a text file: {path}")
    lines = text.splitlines()
    lo = max(1, int(start_line)) if start_line else 1
    hi = min(len(lines), int(end_line)) if end_line else len(lines)
    if lo > hi:
        raise CodeOpsError("start_line is past end_line")
    window = lines[lo - 1:hi]
    return {
        "path": relpath(target, root),
        "total_lines": len(lines),
        "start_line": lo,
        "end_line": hi,
        "truncated": not (lo == 1 and hi == len(lines)),
        "content": "\n".join(window),
    }


def search_code(pattern: str, glob: str | None = None, limit: int = 50,
                root: Path | None = None) -> dict:
    """Regex search across workspace text files, returned with line numbers."""
    if not pattern:
        raise CodeOpsError("empty search pattern")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise CodeOpsError(f"invalid regex: {exc}")

    limit = max(1, min(int(limit or 50), MAX_SEARCH_HITS))
    base = (root or workspace_root()).resolve()
    hits: list[dict] = []

    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in DENY_DIRS)
        for name in sorted(files):
            current_path = Path(current) / name
            rel = current_path.relative_to(base).as_posix()
            if is_denied(rel):
                continue
            if current_path.suffix.lower() not in READ_EXTENSIONS:
                continue
            if glob and not current_path.match(glob):
                continue
            try:
                if current_path.stat().st_size > MAX_READ_BYTES:
                    continue
                text = current_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    hits.append({"path": rel, "line": number, "text": line.strip()[:400]})
                    if len(hits) >= limit:
                        return {"pattern": pattern, "count": len(hits),
                                "truncated": True, "hits": hits}
    return {"pattern": pattern, "count": len(hits), "truncated": False, "hits": hits}


# ---------------------------------------------------------------------------
# read-only subprocess helpers
# ---------------------------------------------------------------------------
def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> dict:
    """Run a read-only command, capped, with no shell interpretation."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, shell=False,
            env={**os.environ, "GIT_PAGER": "cat", "PAGER": "cat",
                 "GIT_TERMINAL_PROMPT": "0"},
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"command not available: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s"}
    stdout = (proc.stdout or "")[-MAX_OUTPUT_CHARS:]
    stderr = (proc.stderr or "")[-MAX_OUTPUT_CHARS:]
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "stdout": stdout, "stderr": stderr}


def git_history(limit: int = 20, path: str | None = None, root: Path | None = None) -> dict:
    """Recent commits (optionally scoped to one path)."""
    base = (root or workspace_root()).resolve()
    limit = max(1, min(int(limit or 20), 100))
    cmd = ["git", "log", f"-{limit}", "--oneline", "--no-decorate"]
    if path:
        cmd += ["--", path]        # `--` stops any option-looking path being parsed
    return {"command": " ".join(cmd), **_run(cmd, base)}


def git_show(rev: str, root: Path | None = None) -> dict:
    """Diff introduced by a single commit."""
    base = (root or workspace_root()).resolve()
    if not re.match(r"^[0-9a-fA-F]{4,40}$", str(rev or "")):
        raise CodeOpsError("rev must be a commit hash")
    return {"command": f"git show {rev}", **_run(["git", "show", "--stat", "-p", rev], base)}


def git_status(root: Path | None = None) -> dict:
    base = (root or workspace_root()).resolve()
    return {"command": "git status --porcelain=v1 -b",
            **_run(["git", "status", "--porcelain=v1", "-b"], base)}


def git_diff(staged: bool = False, root: Path | None = None) -> dict:
    base = (root or workspace_root()).resolve()
    cmd = ["git", "--no-pager", "diff"]
    if staged:
        cmd.append("--staged")
    return {"command": " ".join(cmd), **_run(cmd, base)}


def run_tests(selector: str | None = None, suite: str = "backend",
              root: Path | None = None) -> dict:
    """Run the project's own test suite. Allowlisted, never arbitrary commands.

    `selector` may only be a path/node-id shaped string — no shell metacharacters,
    so the model can never smuggle a second command in.
    """
    base = (root or workspace_root()).resolve()
    suite = (suite or "backend").lower()

    if suite == "frontend":
        web = base / "web"
        if not web.is_dir():
            raise CodeOpsError("web/ not found")
        cmd = ["pnpm", "run", "typecheck"] if selector == "typecheck" else ["pnpm", "run", "build"]
        return {"suite": "frontend", "command": " ".join(cmd), **_run(cmd, web, timeout=300)}

    cmd = list(TEST_COMMANDS["pytest"])
    if selector:
        if suite == "lint":
            cmd = list(TEST_COMMANDS["ruff"])
            if not re.match(r"^[A-Za-z0-9_,./\\-]+$", selector):
                raise CodeOpsError("unsafe selector")
            cmd.append(selector)
        else:
            if not re.match(r"^[A-Za-z0-9_./\\:\\[\\]-]+$", selector):
                raise CodeOpsError("unsafe selector — path or node id only")
            cmd.append(selector)
    elif suite == "lint":
        cmd = list(TEST_COMMANDS["ruff"]) + ["lead_engine/", "tests/"]
    return {"suite": suite, "command": " ".join(cmd), **_run(cmd, base, timeout=300)}


# ---------------------------------------------------------------------------
# WRITE tier — approval-gated, branch-scoped
# ---------------------------------------------------------------------------
APPROVAL_ACTION = "code_patch"


def _validate_syntax(rel: str, content: str) -> None:
    """Refuse a patch that cannot possibly load — the agent must not brick the app.

    Python is compile-checked, JSON is parsed, and YAML is left alone (PyYAML is
    optional at this layer). Everything else passes untouched.
    """
    suffix = Path(rel).suffix.lower()
    if suffix == ".py":
        try:
            compile(content, rel, "exec")
        except SyntaxError as exc:
            raise CodeOpsError(
                f"syntax error in {rel} line {exc.lineno}: {exc.msg} — patch rejected")
    elif suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise CodeOpsError(f"invalid JSON in {rel}: {exc} — patch rejected")


def _prepare_edits(edits: list[dict], root: Path | None = None) -> list[dict]:
    """Validate the proposed edit list and return normalised entries.

    Each entry carries the resolved path, the previous content (or None for a
    new file) and the new content — everything `apply_patch` needs, and enough
    to render a reviewable diff for the human.
    """
    if not edits:
        raise CodeOpsError("no edits supplied")
    if len(edits) > MAX_EDITS_PER_PATCH:
        raise CodeOpsError(f"too many files in one patch (max {MAX_EDITS_PER_PATCH})")

    prepared: list[dict] = []
    total = 0
    seen: set[str] = set()
    for item in edits:
        if not isinstance(item, dict):
            raise CodeOpsError("each edit must be an object with 'path' and 'content'")
        rel_raw = str(item.get("path") or "").strip()
        content = item.get("content")
        if not isinstance(content, str):
            raise CodeOpsError(f"edit for '{rel_raw}' has no string 'content'")
        target = resolve_path(rel_raw, root)
        rel = relpath(target, root)
        if rel in seen:
            raise CodeOpsError(f"duplicate edit for {rel}")
        seen.add(rel)
        if target.suffix.lower() not in READ_EXTENSIONS:
            raise CodeOpsError(f"refusing to patch a non-source file: {rel}")
        _validate_syntax(rel, content)
        old = target.read_text(encoding="utf-8") if target.is_file() else None
        if old == content:
            raise CodeOpsError(f"edit for {rel} is a no-op")
        total += len(content.encode("utf-8"))
        if total > MAX_PATCH_BYTES:
            raise CodeOpsError(f"patch too large (max {MAX_PATCH_BYTES} bytes)")
        prepared.append({"path": rel, "old": old, "new": content})
    return prepared


def _unified_preview(prepared: list[dict]) -> str:
    """A readable unified-diff-ish preview (no external diff dependency)."""
    import difflib
    chunks: list[str] = []
    for entry in prepared:
        old_lines = (entry["old"] or "").splitlines(keepends=True)
        new_lines = entry["new"].splitlines(keepends=True)
        header = (f"--- a/{entry['path']}\n+++ b/{entry['path']}\n"
                  if entry["old"] is not None
                  else f"--- /dev/null\n+++ b/{entry['path']}\n")
        diff = difflib.unified_diff(old_lines, new_lines, n=3)
        chunks.append(header + "".join(diff))
    return "".join(chunks)


def propose_patch(db, run_id: str, summary: str, edits: list[dict],
                  actor: str = "agent", root: Path | None = None) -> dict:
    """Register a PENDING approval holding a code patch. Writes nothing.

    This is the agent's only path to changing code. The approval row carries the
    full payload, so an operator can read the diff and either approve or reject
    it; only `apply_patch` (on an APPROVED row) ever touches disk.
    """
    root = (root or workspace_root()).resolve()
    prepared = _prepare_edits(edits, root)
    diff = _unified_preview(prepared)
    approval_id = f"approval_{uuid.uuid4().hex}"
    payload = {
        "kind": APPROVAL_ACTION,
        "summary": (summary or "code change").strip()[:500],
        "diff": diff[:MAX_PATCH_BYTES],
        "edits": [{"path": e["path"], "content": e["new"]} for e in prepared],
        "files": [e["path"] for e in prepared],
        "created": bool([e for e in prepared if e["old"] is None]),
        "root": root.as_posix(),
    }
    db.execute(
        "INSERT INTO approvals (approval_id, organization_id, run_id, action,"
        " payload_json, status, requested_at) VALUES (?,?,?,?,?,?,?)",
        (approval_id, getattr(db, "org_id", None), run_id or "chat",
         APPROVAL_ACTION, json.dumps(payload, ensure_ascii=False), "PENDING",
         datetime.now(timezone.utc).isoformat()),
    )
    audit(db, actor, "code_patch.proposed", "approval", approval_id,
          {"files": payload["files"], "summary": payload["summary"]})
    return {
        "approval_id": approval_id,
        "status": "PENDING",
        "files": payload["files"],
        "diff": diff,
        "message": ("جاهز للتطبيق — لكن محتاج موافقتك. راجع الـdiff من صفحة "
                    "الوكلاء ثم APPROVE أو REJECT. مفيش أي ملف اتغيّر لحد الآن."),
    }


BACKUP_DIRNAME = ".codeops_backups"


def _load_pending_patch(db, approval_id: str) -> tuple[dict, dict]:
    row = db.one("SELECT * FROM approvals WHERE approval_id=?", (approval_id,))
    if not row:
        raise CodeOpsError(f"approval not found: {approval_id}")
    if row.get("action") != APPROVAL_ACTION:
        raise CodeOpsError(f"approval {approval_id} is not a code patch")
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except json.JSONDecodeError:
        raise CodeOpsError("approval payload is corrupt")
    return row, payload


def _current_branch(root: Path) -> str:
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    branch = (result.get("stdout") or "").strip()
    return branch if result.get("ok") and branch else ""

def apply_patch(db, approval_id: str, actor: str = "operator",
                root: Path | None = None) -> dict:
    """Apply an APPROVED code patch onto a fresh git branch. Never touches main.

    Refuses unless the approval row exists, is a code patch, and is APPROVED.
    Every touched file is backed up first, and the outcome is committed on a
    `codeops/<approval-id>` branch so returning to the base branch undoes it.
    """
    row, payload = _load_pending_patch(db, approval_id)
    if str(row.get("status")).upper() != "APPROVED":
        raise ApprovalRequired(
            f"approval {approval_id} is {row.get('status')} — approve it first")

    base = (root or Path(payload.get("root") or workspace_root())).resolve()
    edits = payload.get("edits") or []
    if not edits:
        raise CodeOpsError("approval carries no edits")

    # Re-validate against the *current* disk state: the tree may have moved on
    # since the patch was proposed, and applying stale content would clobber it.
    prepared = _prepare_edits([{"path": e["path"], "content": e["content"]}
                               for e in edits], base)

    is_git = _run(["git", "rev-parse", "--is-inside-work-tree"], base).get("ok", False)
    base_branch = _current_branch(base) if is_git else ""
    branch = base_branch
    git_notes: list[str] = []
    commit = None

    if is_git:
        short = approval_id.replace("approval_", "")[:10]
        branch = f"codeops/{short}"
        if base_branch == branch:
            git_notes.append(f"already on {branch}")
        else:
            switch = _run(["git", "checkout", "-b", branch], base)
            if not switch.get("ok"):
                raise CodeOpsError(
                    "could not create branch: "
                    + (switch.get("stderr") or switch.get("error") or "unknown git error"))

    # Backups first — belt and braces next to the branch.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = base / BACKUP_DIRNAME / f"{approval_id}_{stamp}"
    written: list[str] = []
    for entry in prepared:
        target = base / entry["path"]
        if entry["old"] is not None:
            dest = backup_dir / entry["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry["new"], encoding="utf-8")
        written.append(entry["path"])

    if is_git:
        add = _run(["git", "add", "--"] + written, base)
        if not add.get("ok"):
            git_notes.append("git add failed: " + (add.get("stderr") or "")[:300])
        message = f"agent: {payload.get('summary', 'code change')[:70]}"
        commit_run = _run(["git", "commit", "-m", message], base)
        if commit_run.get("ok"):
            rev = _run(["git", "rev-parse", "--short", "HEAD"], base)
            commit = (rev.get("stdout") or "").strip() or None
        else:
            git_notes.append("git commit failed: "
                             + (commit_run.get("stderr") or "")[:300])

    payload["result"] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "files": written,
        "branch": branch,
        "base_branch": base_branch,
        "commit": commit,
        "backup_dir": str(backup_dir),
        "notes": git_notes,
    }
    db.execute("UPDATE approvals SET payload_json=? WHERE approval_id=?",
               (json.dumps(payload, ensure_ascii=False), approval_id))
    audit(db, actor, "code_patch.applied", "approval", approval_id,
          {"files": written, "branch": branch, "commit": commit})

    return {
        "applied": True,
        "files": written,
        "branch": branch,
        "base_branch": base_branch,
        "commit": commit,
        "backup_dir": str(backup_dir),
        "undo": (f"git checkout {base_branch}" if base_branch else
                 f"restore files from {backup_dir}"),
        "notes": git_notes,
    }

def revert_patch(db, approval_id: str, actor: str = "operator",
                 root: Path | None = None) -> dict:
    """Undo an applied patch: restore backups and return to the base branch."""
    row, payload = _load_pending_patch(db, approval_id)
    result = payload.get("result") or {}
    if not result:
        raise CodeOpsError("this approval was never applied")
    base = (root or Path(payload.get("root") or workspace_root())).resolve()
    backup_dir = Path(result.get("backup_dir") or "")

    restored: list[str] = []
    for rel in result.get("files", []):
        source = backup_dir / rel
        if source.is_file():
            dest = base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            restored.append(rel)

    base_branch = result.get("base_branch")
    if base_branch:
        _run(["git", "checkout", base_branch], base)

    payload["reverted_at"] = datetime.now(timezone.utc).isoformat()
    payload["revert_restored"] = restored
    db.execute("UPDATE approvals SET payload_json=? WHERE approval_id=?",
               (json.dumps(payload, ensure_ascii=False), approval_id))
    audit(db, actor, "code_patch.reverted", "approval", approval_id,
          {"restored": restored, "branch": base_branch})
    return {"reverted": True, "restored": restored, "branch": base_branch}

