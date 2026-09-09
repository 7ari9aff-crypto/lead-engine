"""Vercel entrypoint — exposes the FastAPI app to the Python runtime."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lead_engine.api.app import app  # noqa: E402

handler = app
