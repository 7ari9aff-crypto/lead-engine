# ADR-0010 — Config-driven provider and model registry

Status: accepted (extends ADR-0009)

## Context

ADR-0009 put every vendor behind a capability contract, but the *wiring* stayed
in code: `infrastructure/providers/bootstrap.py` hardcodes which adapters exist.
Adding a search tool or a model therefore meant writing an adapter, editing
`bootstrap.py`, and shipping a PR. The operator will use several models (GLM,
Gemini, Qwen, ...) and several tools (Exa, Tavily, Apollo, OpenManus, ...) and
will change them often. That should be a configuration change.

## Decision

`config/providers.yaml` declares extra tools (`providers:`) and models
(`models:`). `infrastructure/providers/registry.py` registers each entry that is
enabled and whose `env_key` holds a value.

Three entry kinds:

- `builtin`: an adapter that already ships in `real.py`.
- `rest_search`: any JSON-over-HTTP search API, described declaratively (url,
  method, auth style, body template, `results_path`, field mapping). No code.
- `openai_compat`: any OpenAI-compatible chat-completions model. No code.

Rules:

1. **Additive.** The file adds to the built-in set; it never removes or
   replaces it. No file means today's behavior exactly.
2. **Secrets stay in the environment / credential store.** The file names an
   `env_key`; values are never in the file, the report, or the logs.
3. **Key pools.** `env_key` may hold a comma-separated list; the adapter rotates
   to the next key on 401/403/429. Exhausting every key is a classified
   `RATE_LIMIT`, so the gateway falls through to the next tool.
4. **Fail loud.** A malformed file raises at boot with the offending id.
5. **Capability checks.** Tools use the `Capability` enum; models use their own
   names (`reasoning`, `planning`, ...), matching `ModelGateway`.

## Not covered (deliberately)

Long-running agent platforms such as Manus or OpenManus are *asynchronous*
(minutes per task, credit-metered). They must not be registered as synchronous
`search_companies` adapters: that would hold a Postgres transaction open for the
whole task. They need a separate async discovery stage, designed next.

## Consequences

- New tool or model: add a YAML block and set a key. No code, no deploy of
  adapters.
- A new *kind* of integration (different protocol) still needs code, but only
  once, as a new `kind`.
- Per-key credit awareness (rotate at N credits left) is out of scope here.
