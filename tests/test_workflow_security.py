"""CI hardening guard (audit F1): untrusted GitHub expressions must never be
interpolated into a `run:` script. Pass them through `env:` instead, so the
shell sees data, not code."""
import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))

# Contexts an outsider (or a dispatching user) can influence.
UNTRUSTED = re.compile(
    r"\$\{\{[^}]*\b(github\.event\.(inputs|issue|pull_request|comment|review|head_commit|"
    r"commits|pages|client_payload)|github\.head_ref|inputs)\b[^}]*\}\}"
)


def _run_steps(doc):
    for job_name, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            if "run" in step:
                yield job_name, step.get("name") or f"step {i}", step["run"]


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_untrusted_expression_in_run_script(wf):
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    bad = [(j, n, m.group(0)) for j, n, script in _run_steps(doc)
           for m in UNTRUSTED.finditer(script)]
    assert not bad, f"{wf.name}: untrusted expression interpolated into run: {bad}"


def test_scanner_detects_the_known_pattern():
    """The guard itself must catch the pattern from v6-worker.yml (pre-fix)."""
    script = 'python -m apps.worker --cycles "${{ github.event.inputs.cycles || \'80\' }}"'
    assert UNTRUSTED.search(script)
    assert not UNTRUSTED.search('python -m apps.worker --cycles "$CYCLES"')
    assert not UNTRUSTED.search('echo "${{ secrets.X }}" "${{ vars.Y }}"')


def test_v6_worker_cycles_is_validated_as_integer():
    text = (WORKFLOWS[0].parent / "v6-worker.yml").read_text(encoding="utf-8")
    assert re.search(r"\^\[0-9\]\+\$", text), "cycles must be validated as digits only"
