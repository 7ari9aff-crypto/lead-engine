"""Provider Router — the only way any AI/Data operation reaches the outside.

Decision inputs: quota, rate limit, task type, provider health, key
availability — all read from the Provider Registry, never from if/else.

Flow: TASK -> L1 cache -> pick provider by priority -> execute ->
on 429 read Retry-After (short retry, then switch) -> on success cache it.
If every provider is blocked the router raises NoProviderAvailable and the
job manager PAUSES the job (quota exhaustion is a resource state, not a failure).
"""
import time

from .cache import CacheLayer
from .db import utcnow
from .registry import COOLDOWN, EXHAUSTED, Registry


class ProviderError(Exception):
    """Unclassified provider error — treated as one failed attempt."""


class RateLimited(ProviderError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExhausted(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class NoProviderAvailable(Exception):
    def __init__(self, task, tried=None):
        self.task = task
        self.tried = tried or []
        super().__init__(f"no available provider for task '{task}' (tried: {self.tried})")


def build_adapters(settings: dict) -> dict:
    """Instantiate the real provider adapters from the configured pool."""
    from .providers.email import AbstractProvider, HunterProvider, LocalSMTPVerifier
    from .providers.data import ApolloProvider
    from .providers.llm import GeminiProvider, GroqProvider, OllamaProvider, OpenRouterProvider
    from .providers.search import BraveProvider, ExaProvider, TavilyProvider

    adapters = {}
    for cls in (
        TavilyProvider, BraveProvider, ExaProvider,
        GeminiProvider, GroqProvider, OpenRouterProvider, OllamaProvider,
        ApolloProvider,
        HunterProvider, AbstractProvider, LocalSMTPVerifier,
    ):
        adapters[cls.name] = cls(settings)
    return adapters


class Router:
    def __init__(self, db, cache: CacheLayer, settings: dict):
        self.db = db
        self.cache = cache
        self.settings = settings or {}
        self.registry = Registry(db)
        self.registry.seed_if_empty()
        self.adapters = build_adapters(self.settings)

    # ---------------------------------------------------------------- public
    def route(self, task: str, payload: dict, job_id=None,
              use_cache: bool = True, cache_data_type: str = None,
              prefer_provider: str = None):
        """Execute one task through the best available provider.
        prefer_provider: pin the task to one provider (chat model picker);
        raises NoProviderAvailable naming it when that provider is blocked."""
        if use_cache:
            hit = self.cache.get_request(task, payload)
            if hit is not None:
                return hit, {"provider": "cache", "cached": True, "latency_ms": 0}

        cfg = self.settings.get("router", {})
        cooldown_default = cfg.get("cooldown_default_seconds", 300)
        unavailable_cooldown = cfg.get("unavailable_cooldown_seconds", 60)
        rate_window = cfg.get("rate_window_seconds", 60)

        tried = []
        key_counts = {name: max(1, len(getattr(a, "keys", []) or []))
                      for name, a in self.adapters.items()}
        rows = self.registry.providers_for_task(task, key_counts=key_counts)
        if prefer_provider:
            rows = [r for r in rows if r["name"] == prefer_provider]
            if not rows:
                raise NoProviderAvailable(task, [f"{prefer_provider}:not_registered"])
        for row in rows:
            name = row["name"]
            adapter = self.adapters.get(name)
            if adapter is None or not getattr(adapter, "available", False):
                tried.append(f"{name}:no_key")
                continue
            if not row.get("_usable"):
                tried.append(f"{name}:{row['status'] or 'blocked'}")
                continue
            if row["rpm_limit"] and self.registry.count_recent_requests(name, rate_window) >= row["rpm_limit"]:
                self.registry.mark(name, task, COOLDOWN, "local RPM window", cooldown_seconds=rate_window)
                tried.append(f"{name}:rpm")
                continue

            configure = getattr(adapter, "configure", None)
            if configure:
                configure(row)

            # key pool: on 429/quota rotate to the next key BEFORE giving up
            # on the provider — 5 Tavily keys = 5x monthly credits.
            # Per the design: transient 5xx gets a SHORT RETRY on the same
            # provider first; only a persistent failure switches provider.
            pool = max(1, len(getattr(adapter, "keys", []) or []))
            result = None
            key_try = 0
            retry_5xx = 0
            while key_try < pool:
                started = time.time()
                try:
                    result = adapter.request(task, payload)
                    break
                except RateLimited as exc:
                    self.registry.record_usage(name, task, job_id, 0, row["quota_kind"],
                                               "rate_limited", int((time.time() - started) * 1000))
                    if adapter.rotate_key():
                        key_try += 1
                        tried.append(f"{name}:key{adapter._key_index}(429)")
                        continue
                    self.registry.mark(name, task, COOLDOWN, str(exc),
                                       cooldown_seconds=exc.retry_after or cooldown_default)
                    tried.append(f"{name}:429")
                    break
                except QuotaExhausted as exc:
                    self.registry.record_usage(name, task, job_id, 0, row["quota_kind"],
                                               "quota", int((time.time() - started) * 1000))
                    if adapter.rotate_key():
                        key_try += 1
                        tried.append(f"{name}:key{adapter._key_index}(quota)")
                        continue
                    self.registry.mark(name, task, EXHAUSTED, str(exc))
                    tried.append(f"{name}:quota")
                    break
                except ProviderUnavailable as exc:
                    if retry_5xx < 2:
                        retry_5xx += 1
                        time.sleep(2 * retry_5xx)          # short retry: 2s, then 4s
                        tried.append(f"{name}:retry5xx#{retry_5xx}")
                        continue
                    self.registry.mark(name, task, COOLDOWN, str(exc),
                                       cooldown_seconds=unavailable_cooldown)
                    tried.append(f"{name}:unavailable")
                    break
                except ProviderError as exc:
                    self.registry.record_usage(name, task, job_id, 0, row["quota_kind"], "error",
                                               int((time.time() - started) * 1000))
                    tried.append(f"{name}:error({exc})")
                    break

            if result is None:
                continue

            latency = int((time.time() - started) * 1000)
            units = float(result.get("units", 1))
            rate_info = result.pop("rate_info", None) or {}
            usage_info = result.pop("usage", None) or {}
            self.registry.record_usage(
                name, task, job_id, units, row["quota_kind"], "ok", latency,
                prompt_tokens=usage_info.get("prompt_tokens", 0),
                completion_tokens=usage_info.get("completion_tokens", 0),
                key_index=getattr(adapter, "_key_index", None))
            self.registry.add_quota_used(name, task, units, key_counts.get(name, 1))
            if "remaining_requests" in rate_info:
                self.registry.set_rpm_from_headers(name, task, rate_info["remaining_requests"])

            if use_cache:
                self.cache.put_request(task, payload, result, cache_data_type or task)
            return result, {"provider": name, "cached": False, "latency_ms": latency}

        raise NoProviderAvailable(task, tried)

    def usage_report(self):
        return self.registry.usage_summary()

    def status_report(self):
        return self.registry.status_table()
