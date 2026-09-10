"""Minimal stateless MCP (Model Context Protocol) server over streamable HTTP.

Exposes the engine's tools at POST /mcp as JSON-RPC 2.0 — the same toolset
the chat uses. Any MCP client can connect (n8n MCP Client node, Claude,
ZCode, Cursor...). Stateless: no session bookkeeping, every request is
self-contained, which is what serverless deployments can support.
"""
import json

from .chat import execute_tool

PROTOCOL_VERSION = "2025-03-26"

MCP_TOOLS = [
    {
        "name": "run_lead_generation",
        "description": "شغّل خط توليد الـleads بالكامل لمدينة سعودية: بحث حقيقي + إزالة تكرار + فلترة + تأهيل AI. يعيد الـleads مع الأرقام والإيميلات المتاحة من مقتطفات البحث.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "المدينة مثل: الرياض، جدة"},
                "industry": {"type": "string", "enum": ["dental"], "description": "افتراضي dental"},
                "dry_run": {"type": "boolean", "description": "تشغيل تجربة — افتراضي false"},
                    "approval_id": {"type": "string", "description": "معرف موافقة التشغيل الحي"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_job_status",
        "description": "حالة مهمة توليد: الحالة والأحداث والمقاييس.",
        "inputSchema": {"type": "object",
                        "properties": {"job_id": {"type": "string"}},
                        "required": ["job_id"]},
    },
    {
        "name": "list_leads",
        "description": "استعراض الـleads المخزنة مع جهات الاتصال المتاحة.",
        "inputSchema": {"type": "object", "properties": {
            "stage": {"type": "string", "enum": ["ACCEPTED", "REVIEW", "REJECTED"]},
            "job_id": {"type": "string"},
            "limit": {"type": "integer", "default": 15},
        }},
    },
    {
        "name": "verify_email",
        "description": "فحص إيميل بخمس حالات مع كشف catch-all.",
        "inputSchema": {"type": "object",
                        "properties": {"email": {"type": "string"}},
                        "required": ["email"]},
    },
    {
        "name": "system_status",
        "description": "حالة النظام: المزوّدون، المهام، الـleads، الاستهلاك.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _result(rid, payload):
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle_jsonrpc(body: dict, router, db):
    """Handle one JSON-RPC request. Returns (response_dict_or_None, http_status).
    None response = notification (HTTP 202)."""
    if not isinstance(body, dict):
        return _error(None, -32600, "invalid Request"), 400
    method = body.get("method", "")
    rid = body.get("id")

    if method == "initialize":
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "lead-engine",
                "title": "Lead Engine — quota-aware lead generation",
                "version": __import__("lead_engine", fromlist=["__version__"]).__version__,
            },
            "instructions": "أدوات تشغيل توليد leads حقيقية: run_lead_generation لتشغيل "
                            "الخط لمدينة سعودية، list_leads للنتائج، verify_email للفحص، "
                            "system_status للحالة.",
        }), 200

    if method == "server/discover":
        return _result(rid, {
            "resultType": "complete",
            "supportedVersions": [PROTOCOL_VERSION],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "lead-engine",
                "version": __import__("lead_engine", fromlist=["__version__"]).__version__,
            },
            "ttlMs": 300000,
            "cacheScope": "public",
        }), 200

    if method == "notifications/initialized":
        return None, 202
    if method == "ping":
        return _result(rid, {}), 200

    if method == "tools/list":
        return _result(rid, {"tools": MCP_TOOLS}), 200

    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            out = execute_tool(name, args, router, db)
        except Exception as exc:
            out = {"error": f"{type(exc).__name__}: {exc}"}
        is_error = "error" in out
        return _result(rid, {
            "content": [{"type": "text",
                         "text": json.dumps(out, ensure_ascii=False, default=str)}],
            "isError": is_error,
        }), 200

    if rid is not None:
        return _error(rid, -32601, f"method not found: {method}"), 200
    return None, 202
