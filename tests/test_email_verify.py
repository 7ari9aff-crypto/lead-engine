from lead_engine.cache import CacheLayer
from lead_engine.config import load_cache_policy
from lead_engine.db import Database
from lead_engine.providers.email import VerificationPipeline
from lead_engine.router import Router


class StubAdapter:
    tasks = ("email_verify",)
    available = True

    def __init__(self, response):
        self.name = "local_smtp"
        self._response = response

    def request(self, task, payload):
        return dict(self._response)


def make_router(tmp_path, response):
    db = Database(tmp_path / "t.sqlite3")
    cache = CacheLayer(db, load_cache_policy())
    router = Router(db, cache, {}, dry_run=True)
    router.adapters = {"local_smtp": StubAdapter(response)}
    return VerificationPipeline(router)


def test_syntax_invalid(tmp_path):
    result = make_router(tmp_path, {}).verify("not-an-email")
    assert result["status"] == "INVALID"
    assert result["details"]["reason"] == "syntax"


def test_disposable_domain(tmp_path):
    result = make_router(tmp_path, {}).verify("guy@mailinator.com")
    assert result["status"] == "INVALID"
    assert result["details"]["reason"] == "disposable_domain"


def test_role_account_never_fully_deliverable(tmp_path):
    pipeline = make_router(tmp_path, {
        "provider": "local_smtp", "status": "DELIVERABLE", "confidence": 0.8,
        "details": {}, "units": 0})
    result = pipeline.verify("info@clinic.com")
    assert result["status"] == "RISKY"
    assert result["confidence"] <= 0.5


def test_catch_all_result_is_preserved(tmp_path):
    pipeline = make_router(tmp_path, {
        "provider": "local_smtp", "status": "CATCH_ALL", "confidence": 0.3,
        "details": {"reason": "catch_all_domain"}, "units": 0})
    result = pipeline.verify("someone@alzahradental.com")
    assert result["status"] == "CATCH_ALL"
    assert result["confidence"] < 0.5


def test_no_provider_leaves_unknown_not_crash(tmp_path):
    db = Database(tmp_path / "t2.sqlite3")
    cache = CacheLayer(db, load_cache_policy())
    router = Router(db, cache, {}, dry_run=True)
    router.adapters = {}  # nothing available at all
    result = VerificationPipeline(router).verify("a@b.com")
    assert result["status"] == "UNKNOWN"
