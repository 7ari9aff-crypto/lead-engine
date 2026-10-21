"""The uploader moves secrets off a developer machine, so its safety properties
are tested directly: allow-list, no leakage in output, no blank uploads."""
from __future__ import annotations

import base64

import pytest
from scripts import push_env_to_github_secrets as m

# Fixtures are assembled at runtime from fragments so no secret-shaped literal
# sits in the repo (gitleaks must keep guarding the tree, not be allowlisted).
REAL = "tvly-" + "REALLOOKINGKEY" + "1234567890"
NOT_WIRED_VALUE = "gsk_" + "notwiredyet" + "1234567890"
MASTER_VALUE = "bWFzdGVy" * 5 + "bWFzdA=="
DB_PASSWORD = "supersecret" + "password"
ADMIN_PASSWORD = "hunter2" + "hunter2"

ENV = f"""
# comment
TAVILY_API_KEY={REAL}
export EXA_API_KEY="exa-quoted-value-123456"
GEMINI_API_KEY=
HUNTER_API_KEY=your_hunter_key
APOLLO_API_KEY=apollo-real-value-987654   # inline comment
GROQ_API_KEY={NOT_WIRED_VALUE}
SUPABASE_DB_URL=postgresql://postgres:{DB_PASSWORD}@db.host:5432/postgres
LEAD_ENGINE_V6_MASTER_KEY={MASTER_VALUE}
LEAD_ENGINE_ADMIN_PASSWORD={ADMIN_PASSWORD}
"""


def test_parse_handles_comments_quotes_export_and_inline_comments():
    e = m.parse_env(ENV)
    assert e["TAVILY_API_KEY"] == REAL
    assert e["EXA_API_KEY"] == "exa-quoted-value-123456"
    assert e["APOLLO_API_KEY"] == "apollo-real-value-987654"
    assert e["GEMINI_API_KEY"] == ""


def test_only_allow_listed_usable_keys_are_uploaded():
    p = m.plan(m.parse_env(ENV), existing=set())
    assert p["upload"] == ["TAVILY_API_KEY", "EXA_API_KEY", "APOLLO_API_KEY"]
    assert "GEMINI_API_KEY" in p["skipped_blank"]          # empty: never uploaded blank
    assert "HUNTER_API_KEY" in p["skipped_blank"]          # placeholder text
    assert p["not_wired"] == ["GROQ_API_KEY"]              # reported, not uploaded


def test_database_urls_master_keys_and_passwords_are_never_uploaded():
    p = m.plan(m.parse_env(ENV), existing=set())
    for forbidden in ("SUPABASE_DB_URL", "LEAD_ENGINE_V6_MASTER_KEY", "LEAD_ENGINE_ADMIN_PASSWORD"):
        assert forbidden not in p["upload"]
    assert p["refused_count"] == 3                         # counted, never named with values


def test_existing_secret_is_kept_unless_overwrite():
    env = m.parse_env(ENV)
    assert "TAVILY_API_KEY" in m.plan(env, {"TAVILY_API_KEY"})["skipped_existing"]
    assert "TAVILY_API_KEY" in m.plan(env, {"TAVILY_API_KEY"}, overwrite=True)["upload"]


@pytest.mark.parametrize("v", ["", "changeme", "your_key_here", "<key>", "xxxxxxxx", "short", "test"])
def test_blank_placeholder_and_tiny_values_are_unusable(v):
    assert not m.is_usable(v)


def test_dry_run_prints_names_only_and_never_a_value(tmp_path, monkeypatch, capsys):
    f = tmp_path / ".env"; f.write_text(ENV)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    calls = []
    monkeypatch.setattr(m, "_api", lambda *a, **k: calls.append(a) or {"secrets": []})
    assert m.main([str(f)]) == 0
    out = capsys.readouterr().out
    for secret in (REAL, "exa-quoted-value-123456", "apollo-real-value-987654",
                   DB_PASSWORD, ADMIN_PASSWORD, NOT_WIRED_VALUE, MASTER_VALUE):
        assert secret not in out
    assert "DRY RUN" in out
    assert all(c[0] == "GET" for c in calls)               # nothing written in dry-run


def test_apply_sends_only_encrypted_values(tmp_path, monkeypatch, capsys):
    from nacl import public
    sk = public.PrivateKey.generate()
    pub = base64.b64encode(bytes(sk.public_key)).decode()
    f = tmp_path / ".env"; f.write_text(ENV)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    sent = {}

    def fake(method, path, token, body=None):
        if method == "GET" and path.endswith("public-key"):
            return {"key": pub, "key_id": "k1"}
        if method == "GET":
            return {"secrets": []}
        sent[path] = body
        return {}
    monkeypatch.setattr(m, "_api", fake)
    assert m.main([str(f), "--apply"]) == 0
    assert set(sent) == {"actions/secrets/TAVILY_API_KEY", "actions/secrets/EXA_API_KEY",
                         "actions/secrets/APOLLO_API_KEY"}
    body = sent["actions/secrets/TAVILY_API_KEY"]
    assert REAL not in str(body)                            # ciphertext, not plaintext
    assert public.SealedBox(sk).decrypt(base64.b64decode(body["encrypted_value"])).decode() == REAL
    assert REAL not in capsys.readouterr().out
