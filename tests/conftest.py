import os

# Tests run in explicit open mode: no auth backend is configured on CI/dev
# machines, and the platform now fails closed without this opt-in.
os.environ.setdefault("LEAD_ENGINE_DEV_OPEN", "1")
os.environ.pop("LEAD_ENGINE_ENV", None)
