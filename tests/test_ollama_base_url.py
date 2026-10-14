"""Ollama adapter base-URL hardening (providers/llm.py).

Reproduced on production 2026-10-14 (research job-f06f351e60): an
OLLAMA_BASE_URL env var that exists but is EMPTY made the adapter build the
relative URL "/api/chat" with no scheme — requests raised
MissingSchema and the orchestrator surfaced it as the job's pause_reason.
The fallback chain must also cover empty strings, and a schemeless value
must still produce a valid URL.
"""
import os

import pytest

from lead_engine.providers.llm import OllamaProvider


def _provider(monkeypatch, env_value, settings=None):
    monkeypatch.setenv("OLLAMA_BASE_URL", env_value)
    p = OllamaProvider(settings or {})
    # no real network: we only inspect the URL it resolves
    return p, p._base_url()


def test_empty_env_var_falls_back_to_local_default(monkeypatch):
    _p, base = _provider(monkeypatch, "")
    assert base == "http://localhost:11434"


def test_unset_env_var_falls_back_to_local_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    p = OllamaProvider({})
    assert p._base_url() == "http://localhost:11434"


def test_schemeless_host_gets_a_scheme(monkeypatch):
    _p, base = _provider(monkeypatch, "ollama.internal:11434")
    assert base == "http://ollama.internal:11434"


def test_valid_url_passes_through(monkeypatch):
    _p, base = _provider(monkeypatch, "http://10.0.0.5:11434")
    assert base == "http://10.0.0.5:11434"
