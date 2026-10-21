"""providers.configured: a pipeline with no real search provider is an outage.

Regression: Oct 1-21 2026 every V6 run ended PARTIAL_SUCCESS with 0 companies
and 0 provider calls. The gateway fails before booking a ledger row, so
providers.health (ledger based) said OK for three weeks."""
from application.doctor import checks
from contracts.doctor import CheckStatus
from contracts.providers import Capability


class _Real:  # name does not contain "Fake" -> counts as a real adapter
    pass


class TavilySearchAdapter(_Real):
    pass


class FakeSearchProvider:
    pass


class _Gateway:
    def __init__(self, search=()):
        self._s = list(search)

    def adapters(self, capability):
        return list(self._s) if capability == Capability.SEARCH_COMPANIES else []


def run(search, production=True):
    return checks.check_providers_configured(None, None, None, _Gateway(search),
                                             production=production)


def test_no_adapters_at_all_fails_in_production():
    r = run([])
    assert r.status == CheckStatus.FAIL
    assert "TAVILY_API_KEY" in r.cause
    assert r.evidence["search_adapters"] == []


def test_only_fakes_fails_in_production():
    assert run([FakeSearchProvider()]).status == CheckStatus.FAIL


def test_only_fakes_is_just_a_warning_in_demo_dev():
    r = run([FakeSearchProvider()], production=False)
    assert r.status == CheckStatus.WARN


def test_real_provider_is_ok_even_alongside_fakes():
    r = run([FakeSearchProvider(), TavilySearchAdapter()])
    assert r.status == CheckStatus.OK
    assert "TavilySearchAdapter" in r.evidence["search_adapters"]


def test_missing_gateway_is_a_warning_not_a_crash():
    r = checks.check_providers_configured(None, None, None, None)
    assert r.status == CheckStatus.WARN


class _Backend:
    def __init__(self, states):
        self.states = states

    def system_all(self, sql, *a):
        if "acquisition.run" in sql:
            return [{"id": f"j{i}", "state": s, "finished_at": None}
                    for i, s in enumerate(self.states)]
        return []


def zero(states):
    return checks.check_zero_candidate_runs(_Backend(states), None, None)


def test_three_empty_runs_in_a_row_is_an_outage():
    r = zero(["PARTIAL_SUCCESS"] * 13)
    assert r.status == CheckStatus.FAIL
    assert r.evidence["streak"] == 13


def test_streak_stops_at_the_last_successful_run():
    r = zero(["PARTIAL_SUCCESS", "PARTIAL_SUCCESS", "READY_FOR_REVIEW",
              "PARTIAL_SUCCESS", "PARTIAL_SUCCESS", "PARTIAL_SUCCESS"])
    assert r.status != CheckStatus.FAIL  # streak is 2, below the threshold


def test_healthy_history_is_ok():
    assert zero(["READY_FOR_REVIEW", "PARTIAL_SUCCESS"]).status == CheckStatus.OK


def test_real_bootstrap_without_keys_is_detected_end_to_end(monkeypatch):
    """The exact production shape: v6-worker sets PROVIDERS=real, the org has no
    search key. Uses the REAL bootstrap + REAL gateway, no mocks."""
    from infrastructure.doctor.registry import _real_providers_required
    from infrastructure.providers import bootstrap

    for k in ("TAVILY_API_KEY", "EXA_API_KEY", "APOLLO_API_KEY", "HUNTER_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "real")
    monkeypatch.setattr(bootstrap, "_ensure_env_loaded", lambda: None)

    gateway = bootstrap.build_gateway()
    assert gateway.adapters(Capability.SEARCH_COMPANIES) == []  # the real outage
    assert _real_providers_required() is True
    r = checks.check_providers_configured(None, None, None, gateway,
                                          production=_real_providers_required())
    assert r.status == CheckStatus.FAIL


def test_real_bootstrap_with_tavily_key_is_ok(monkeypatch):
    from infrastructure.providers import bootstrap

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("EXA_API_KEY", "")
    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "real")
    monkeypatch.setattr(bootstrap, "_ensure_env_loaded", lambda: None)
    gateway = bootstrap.build_gateway()
    r = checks.check_providers_configured(None, None, None, gateway, production=True)
    assert r.status == CheckStatus.OK


def test_demo_mode_is_not_flagged_as_outage(monkeypatch):
    from infrastructure.doctor.registry import _real_providers_required

    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "demo")
    monkeypatch.delenv("LEAD_ENGINE_ENV", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    assert _real_providers_required() is False
