"""Configuration: YAML settings, ICP files, legal policies, .env secrets."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "lead_engine.sqlite3"
FIXTURES_DIR = ROOT / "fixtures"
OUTPUTS_DIR = ROOT / "outputs"


def load_env(path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no overwrite)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_settings() -> dict:
    return _yaml(CONFIG_DIR / "settings.yaml") or {}


def load_cache_policy() -> dict:
    return _yaml(CONFIG_DIR / "cache_policy.yaml") or {}


def load_icp(name: str) -> dict:
    return _yaml(CONFIG_DIR / "icp" / f"{name}.yaml")


def load_legal_policy(country: str) -> dict:
    path = CONFIG_DIR / "legal_policies" / f"{country}.yaml"
    if not path.exists():
        path = CONFIG_DIR / "legal_policies" / "default.yaml"
    return _yaml(path)


def ttl_seconds(policy: dict, data_type: str) -> int:
    days = (policy.get("ttl_days") or {}).get(data_type, 7)
    return int(days) * 86400
