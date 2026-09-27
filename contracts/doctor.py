"""Doctor contract: the system sentinel (anti-silent-failure layer).

Every check returns a DoctorCheck with a precise root cause. A check that
itself crashes is reported as FAIL with the exception — the doctor never
fails silently. Statuses: OK / WARN / FAIL (FAIL = needs attention now).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from contracts.events import serialize


class CheckStatus:
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class DoctorCheck:
    check_id: str
    title: str
    status: str                      # OK | WARN | FAIL
    cause: str = ""                  # precise root cause (human readable)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = serialize(self.evidence)
        return d


class DoctorReport:
    def __init__(self, checks: list[DoctorCheck]):
        self.checks = checks

    @property
    def status(self) -> str:
        if any(c.status == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.status == "WARN" for c in self.checks):
            return "WARN"
        return "OK"

    def failing(self) -> list[DoctorCheck]:
        return [c for c in self.checks if c.status == "FAIL"]

    def warned(self) -> list[DoctorCheck]:
        return [c for c in self.checks if c.status == "WARN"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "counts": {
                "total": len(self.checks),
                "ok": sum(1 for c in self.checks if c.status == "OK"),
                "warn": len(self.warned()),
                "fail": len(self.failing()),
            },
            "checks": [c.to_dict() for c in self.checks],
        }
