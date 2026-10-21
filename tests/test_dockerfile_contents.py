"""Guard: the production image must contain every top-level package that the
app imports at runtime.

lead_engine/api/app.py mounts V6 inside a try/except, so a missing package in
the image fails *silently* (the app boots without /api/v1/*). This test turns
that silent degradation into a CI failure.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PACKAGES = [
    "lead_engine", "api", "config", "v6api", "application", "domain",
    "infrastructure", "contracts", "runtime", "apps", "migrations",
]


def _copied_dirs() -> set[str]:
    text = (ROOT / "Dockerfile").read_text()
    return {m.group(1) for m in re.finditer(r"^COPY\s+([\w\-]+)/\s", text, re.M)}


def test_dockerfile_copies_all_runtime_packages():
    missing = [p for p in RUNTIME_PACKAGES if p not in _copied_dirs()]
    assert not missing, f"Dockerfile does not COPY: {missing}"


def test_runtime_packages_exist():
    for p in RUNTIME_PACKAGES:
        assert (ROOT / p).is_dir(), f"{p}/ missing from repo"


def test_prod_requirements_have_no_dev_tools():
    reqs = (ROOT / "requirements.txt").read_text().lower()
    for dev in ("pytest", "ruff", "pytest-cov"):
        assert not re.search(rf"^{dev}\b", reqs, re.M), f"{dev} leaked into runtime requirements"
