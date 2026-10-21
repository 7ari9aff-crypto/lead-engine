"""db.latency must flag a genuinely slow database, not one slow connect."""
import time

from application.doctor import checks
from contracts.doctor import CheckStatus


class _Backend:
    def __init__(self, delays):
        self.delays = list(delays)
        self.calls = 0

    def system_one(self, sql):
        time.sleep(self.delays[min(self.calls, len(self.delays) - 1)])
        self.calls += 1


def _run(delays, monkeypatch, warn_ms=None):
    if warn_ms is not None:
        monkeypatch.setenv("LEAD_ENGINE_DB_LATENCY_WARN_MS", str(warn_ms))
    else:
        monkeypatch.delenv("LEAD_ENGINE_DB_LATENCY_WARN_MS", raising=False)
    b = _Backend(delays)
    return checks.check_db_latency(b, None, None), b


def test_slow_first_probe_only_is_ok(monkeypatch):
    # cold connect (slow) then warm probes (fast): the old check would WARN
    res, b = _run([0.12, 0.001, 0.001], monkeypatch, warn_ms=50)
    assert res.status == CheckStatus.OK
    assert b.calls == checks.DB_LATENCY_PROBES


def test_consistently_slow_database_warns(monkeypatch):
    res, _ = _run([0.08, 0.08, 0.08], monkeypatch, warn_ms=50)
    assert res.status == CheckStatus.WARN
    assert res.evidence["latency_ms"] >= 50


def test_default_threshold_is_1000ms(monkeypatch):
    monkeypatch.delenv("LEAD_ENGINE_DB_LATENCY_WARN_MS", raising=False)
    assert checks._latency_threshold_ms() == 1000.0


def test_bad_env_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_DB_LATENCY_WARN_MS", "not-a-number")
    assert checks._latency_threshold_ms() == checks.DB_LATENCY_WARN_MS_DEFAULT
