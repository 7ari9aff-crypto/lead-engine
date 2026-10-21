"""Open (or update) one GitHub Issue per failing workflow.

Called by .github/workflows/alert.yml when a watched workflow fails. GitHub emails
the repo owner for new issues, so this alerts without any external webhook or secret.

One OPEN issue per workflow, not one per failure: a flapping job comments on the
existing issue instead of burying the inbox, and a later green run closes it.
"""
from __future__ import annotations

import json
import os
import urllib.request

LABEL = "ci-failure"


def issue_title(workflow: str) -> str:
    return f"[alert] {workflow} is failing"


def find_open(issues: list[dict], workflow: str) -> dict | None:
    want = issue_title(workflow)
    for i in issues:
        # the issues API also returns pull requests; those are never ours
        if "pull_request" not in i and i.get("title") == want:
            return i
    return None


def decide(issues: list[dict], workflow: str, conclusion: str) -> str:
    """create | comment | close | noop"""
    existing = find_open(issues, workflow)
    if conclusion == "success":
        return "close" if existing else "noop"
    if conclusion in ("failure", "timed_out", "startup_failure"):
        return "comment" if existing else "create"
    return "noop"          # cancelled / skipped / neutral are not failures


def _api(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    workflow = os.environ["WORKFLOW_NAME"]
    conclusion = os.environ["WORKFLOW_CONCLUSION"]
    url = os.environ["RUN_URL"]
    sha = os.environ.get("HEAD_SHA", "")[:7]
    issues = _api("GET", f"/repos/{repo}/issues?state=open&labels={LABEL}&per_page=100") or []
    action = decide(issues, workflow, conclusion)
    existing = find_open(issues, workflow)
    if action == "create":
        _api("POST", f"/repos/{repo}/issues", {
            "title": issue_title(workflow), "labels": [LABEL],
            "body": f"`{workflow}` {conclusion} on `{sha}`.\n\nRun: {url}\n\n"
                    "This issue closes itself on the next green run."})
    elif action == "comment":
        _api("POST", f"/repos/{repo}/issues/{existing['number']}/comments",
             {"body": f"Failed again on `{sha}`: {url}"})
    elif action == "close":
        _api("POST", f"/repos/{repo}/issues/{existing['number']}/comments",
             {"body": f"Recovered on `{sha}`: {url}"})
        _api("PATCH", f"/repos/{repo}/issues/{existing['number']}", {"state": "closed"})
    print(f"{workflow}: {conclusion} -> {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
