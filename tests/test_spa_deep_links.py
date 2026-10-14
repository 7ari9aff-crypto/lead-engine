"""SPA deep-link routing (middleware rule in app.py).

A browser navigation to ANY non-API path — including deep links like
/jobs/<id> and /leads/<id> that collide with API routes — must receive the
SPA shell (text/html), while API clients (no text/html Accept) and /api/*
paths keep their JSON contract.

Reproduced on production 2026-10-14: /jobs/job-186ba2e6ab answered
401 {"detail":"authentication required"} as raw JSON body and the browser
printed it as text with no app chrome at all — the exact-match rule only
covered /jobs, /leads, /providers bare paths.
"""
from fastapi.testclient import TestClient

from lead_engine.api.app import app

client = TestClient(app, raise_server_exceptions=False)


def _kind(resp):
    ctype = resp.headers.get("content-type", "")
    if "text/html" in ctype:
        return "html"
    if "application/json" in ctype or resp.headers.get("content-type", "").startswith("application/json"):
        return "json"
    return ctype or "empty"


def test_browser_navigation_to_deep_link_served_the_spa_shell():
    r = client.get("/jobs/job-186ba2e6ab", headers={"Accept": "text/html"})
    assert _kind(r) == "html"


def test_browser_navigation_to_bare_list_paths_served_the_spa_shell():
    for path in ("/jobs", "/leads", "/providers", "/review"):
        r = client.get(path, headers={"Accept": "text/html"})
        assert _kind(r) == "html", path


def test_api_clients_without_html_accept_keep_the_json_contract():
    r = client.get("/jobs")  # curl / n8n default Accept: */*
    assert _kind(r) == "json"


def test_api_paths_serve_json_even_to_browsers():
    r = client.get("/api/jobs", headers={"Accept": "text/html,*/*"})
    assert _kind(r) == "json"


def test_real_asset_requests_stay_static_files_not_the_spa_shell():
    # The middleware excludes asset-ish paths from the SPA fallback; FastAPI's
    # static mount answers 200 with the file itself (or 404 for a missing
    # one) — either way never the SPA shell.
    r = client.get("/assets/index-Dil35wKe.js", headers={"Accept": "text/html,*/*"})
    assert _kind(r) != "html"
    r = client.get("/favicon.svg", headers={"Accept": "text/html,*/*"})
    assert _kind(r) != "html"
