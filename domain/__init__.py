"""Lead Engine V6 domain — pure business logic.

IMPORT RULE (ADR-0003): this package imports nothing from api, application,
infrastructure or runtime. No FastAPI, no Redis, no provider SDKs, no
environment. Enforced by tests/v6/test_import_boundaries.py.
"""
