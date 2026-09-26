"""Import boundary enforcement (ADR-0003). Static AST scan — the layering is
a tested invariant, not a convention."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

FORBIDDEN = {
    "domain": {"api", "application", "infrastructure", "runtime", "fastapi", "psycopg", "redis"},
    "application": {"api", "fastapi"},
    "contracts": {"api", "application", "infrastructure", "runtime", "fastapi"},
}


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("layer,forbidden", FORBIDDEN.items())
def test_layer_does_not_import(layer: str, forbidden: set[str]):
    roots = [REPO / layer]
    assert roots[0].exists(), f"layer {layer} missing"
    offenders: list[str] = []
    for py in roots[0].rglob("*.py"):
        mods = _imports_of(py)
        bad = mods & forbidden
        if bad:
            offenders.append(f"{py.relative_to(REPO)} imports {sorted(bad)}")
    assert not offenders, "layering violations:\n" + "\n".join(offenders)


def test_domain_is_dependency_free():
    """domain may import only stdlib + itself."""
    allowed_prefixes = {"domain", "contracts"}
    for py in (REPO / "domain").rglob("*.py"):
        for mod in _imports_of(py):
            assert mod in allowed_prefixes or mod in __import__("sys").stdlib_module_names, \
                f"{py.name} imports non-stdlib module {mod}"
