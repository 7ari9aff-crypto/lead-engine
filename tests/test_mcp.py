"""MCP endpoint: stateless JSON-RPC over HTTP with the engine toolset."""
import json

from fastapi.testclient import TestClient

from lead_engine.api.app import app

client = TestClient(app)


def test_initialize():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {}})
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["serverInfo"]["name"] == "lead-engine"
    assert "tools" in result["capabilities"]


def test_tools_list_has_five_tools():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = r.json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"run_lead_generation", "get_job_status", "list_leads",
                     "verify_email", "system_status"}
    for t in tools:
        assert "inputSchema" in t


def test_tools_call_system_status():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": "system_status", "arguments": {}}})
    body = r.json()
    assert body["result"]["isError"] is False
    payload = json.loads(body["result"]["content"][0]["text"])
    assert "providers" in payload


def test_notification_returns_202():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202


def test_unknown_method():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "nope"})
    assert r.json()["error"]["code"] == -32601


def test_mcp_get_hint():
    r = client.get("/mcp")
    assert r.status_code == 200
    assert r.json()["usage"].startswith("POST /mcp")
