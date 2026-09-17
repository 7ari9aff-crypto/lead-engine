"""Tests pinning the approval-gated code-operations contract.

The operator's rule is "the agent may trace and fix code, but never change a
thing until I approve it". These tests assert exactly that, so a future
refactor cannot quietly turn `propose_patch` into a writer or let `apply_patch`
run on an unapproved row.
"""
import json

import pytest

from lead_engine import codeops
from lead_engine.db import Database


@pytest.fixture()
def workspace(tmp_path):
    """A throwaway workspace with one source file and one secret file."""
    (tmp_path / "lead_engine").mkdir()
    (tmp_path / "lead_engine" / "sample.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_KEY=should-never-be-readable\n",
                                   encoding="utf-8")
    return tmp_path


@pytest.fixture()
def db(tmp_path):
    return Database(str(tmp_path / "codeops_test.sqlite3"))


# --------------------------- path safety ---------------------------
def test_denylist_blocks_secrets_and_vendor():
    for rel in (".env", ".env.local", "keys.pem", "node_modules/x.js", ".git/config"):
        assert codeops.is_denied(rel), rel
    for rel in (".env.example", "lead_engine/api/app.py"):
        assert not codeops.is_denied(rel), rel


def test_read_code_refuses_env_file(workspace):
    with pytest.raises(codeops.CodeOpsError):
        codeops.read_code(".env", root=workspace)


def test_read_code_refuses_absolute_and_escaping_paths(workspace):
    with pytest.raises(codeops.CodeOpsError):
        codeops.read_code("C:/Windows/system32/drivers/etc/hosts", root=workspace)
    with pytest.raises(codeops.CodeOpsError):
        codeops.read_code("../../etc/passwd", root=workspace)


def test_read_code_returns_line_window(workspace):
    out = codeops.read_code("lead_engine/sample.py", start_line=2, end_line=2,
                            root=workspace)
    assert out["content"] == "    return a + b"
    assert out["total_lines"] == 2 and out["truncated"] is True


def test_search_code_finds_definition(workspace):
    out = codeops.search_code(r"def add", root=workspace)
    assert out["count"] == 1
    assert out["hits"][0]["path"] == "lead_engine/sample.py"


def test_list_code_excludes_denied(workspace):
    out = codeops.list_code(root=workspace)
    paths = {f["path"] for f in out["files"]}
    assert "lead_engine/sample.py" in paths
    assert ".env" not in paths


# --------------------------- propose: never writes ---------------------------
def test_propose_patch_does_not_touch_disk(workspace, db):
    target = workspace / "lead_engine" / "sample.py"
    before = target.read_text(encoding="utf-8")

    result = codeops.propose_patch(
        db, "run-1", "handle subtraction",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )

    assert result["status"] == "PENDING"
    assert result["approval_id"].startswith("approval_")
    assert target.read_text(encoding="utf-8") == before, "propose must never write"
    assert "-    return a + b" in result["diff"]


def test_propose_rejects_syntax_error(workspace, db):
    with pytest.raises(codeops.CodeOpsError):
        codeops.propose_patch(
            db, "run-1", "broken",
            [{"path": "lead_engine/sample.py", "content": "def add(a, b)\n    return a+b\n"}],
            root=workspace,
        )


def test_propose_rejects_noop_and_denied_paths(workspace, db):
    same = (workspace / "lead_engine" / "sample.py").read_text(encoding="utf-8")
    with pytest.raises(codeops.CodeOpsError):
        codeops.propose_patch(db, "r", "noop",
                              [{"path": "lead_engine/sample.py", "content": same}],
                              root=workspace)
    with pytest.raises(codeops.CodeOpsError):
        codeops.propose_patch(db, "r", "secret",
                              [{"path": ".env", "content": "X=1\n"}], root=workspace)


def test_approval_payload_round_trips(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    row = db.one("SELECT * FROM approvals WHERE approval_id=?", (proposed["approval_id"],))
    payload = json.loads(row["payload_json"])
    assert payload["kind"] == codeops.APPROVAL_ACTION
    assert payload["files"] == ["lead_engine/sample.py"]
    assert payload["edits"][0]["path"] == "lead_engine/sample.py"


def test_audit_rows_written_for_propose(workspace, db):
    codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    rows = db.query("SELECT action FROM audit_logs WHERE action LIKE 'code_patch%'")
    assert [r["action"] for r in rows] == ["code_patch.proposed"]


# --------------------------- apply: approval required ---------------------------
def test_apply_refuses_when_not_approved(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    target = workspace / "lead_engine" / "sample.py"
    before = target.read_text(encoding="utf-8")

    with pytest.raises(codeops.ApprovalRequired):
        codeops.apply_patch(db, proposed["approval_id"], root=workspace)
    assert target.read_text(encoding="utf-8") == before, "unapproved apply must not write"


def test_apply_refuses_when_rejected(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    db.execute("UPDATE approvals SET status='REJECTED' WHERE approval_id=?",
               (proposed["approval_id"],))
    with pytest.raises(codeops.ApprovalRequired):
        codeops.apply_patch(db, proposed["approval_id"], root=workspace)


def test_apply_writes_and_backs_up_after_approval(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    db.execute("UPDATE approvals SET status='APPROVED' WHERE approval_id=?",
               (proposed["approval_id"],))

    result = codeops.apply_patch(db, proposed["approval_id"], root=workspace)

    assert result["applied"] is True
    assert result["files"] == ["lead_engine/sample.py"]
    assert "a - b" in (workspace / "lead_engine" / "sample.py").read_text(encoding="utf-8")
    backup = workspace / ".codeops_backups"
    assert backup.is_dir()
    assert list(backup.rglob("sample.py"))


def test_apply_creates_new_file(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "add helper",
        [{"path": "lead_engine/helper.py", "content": "VALUE = 42\n"}],
        root=workspace,
    )
    db.execute("UPDATE approvals SET status='APPROVED' WHERE approval_id=?",
               (proposed["approval_id"],))
    codeops.apply_patch(db, proposed["approval_id"], root=workspace)
    assert (workspace / "lead_engine" / "helper.py").read_text(encoding="utf-8") == "VALUE = 42\n"


def test_apply_refuses_if_tree_moved_on(workspace, db):
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    db.execute("UPDATE approvals SET status='APPROVED' WHERE approval_id=?",
               (proposed["approval_id"],))
    # Something else already produced the exact target content.
    (workspace / "lead_engine" / "sample.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8")
    with pytest.raises(codeops.CodeOpsError):
        codeops.apply_patch(db, proposed["approval_id"], root=workspace)


def test_revert_restores_backup(workspace, db):
    original = (workspace / "lead_engine" / "sample.py").read_text(encoding="utf-8")
    proposed = codeops.propose_patch(
        db, "run-1", "subtract",
        [{"path": "lead_engine/sample.py", "content": "def add(a, b):\n    return a - b\n"}],
        root=workspace,
    )
    db.execute("UPDATE approvals SET status='APPROVED' WHERE approval_id=?",
               (proposed["approval_id"],))
    codeops.apply_patch(db, proposed["approval_id"], root=workspace)

    out = codeops.revert_patch(db, proposed["approval_id"], root=workspace)
    assert out["reverted"] is True
    assert (workspace / "lead_engine" / "sample.py").read_text(encoding="utf-8") == original


def test_git_history_reports_honestly_outside_repo(workspace):
    out = codeops.git_history(limit=3, root=workspace)
    assert "ok" in out
    assert isinstance(out.get("stdout", ""), str)

