"""Doctor backend protocol + the sentinel runner.

Checks are registered functions receiving (backend, settings, org). The
runner guarantees honesty: a crashing check becomes a FAIL whose cause is
the exception itself — the sentinel never fails silently.
"""
from __future__ import annotations

import traceback
from typing import Any, Callable, Protocol

from contracts.doctor import CheckStatus, DoctorCheck, DoctorReport


class DoctorBackend(Protocol):
    """SQL surface for the sentinel (implemented by infrastructure)."""

    def system_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None: ...

    def system_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]: ...

    def org_all(self, org_id: str, sql: str, params: tuple = ()) -> list[dict[str, Any]]: ...

    def org_exists(self, org_id: str) -> bool: ...

    def applied_migrations(self) -> dict[str, str]: ...

    def migration_files(self) -> dict[str, str]: ...


CheckFn = Callable[[Any, Any, str | None], DoctorCheck]


class Doctor:
    """Registry + runner. Register checks at composition time; run() returns
    the full report. org=None → system checks only."""

    def __init__(self, backend: Any):
        self.backend = backend
        self._checks: list[tuple[str, CheckFn]] = []

    def register(self, check_id: str, fn: CheckFn) -> None:
        self._checks.append((check_id, fn))

    def run(self, settings: Any, org: str | None = None) -> DoctorReport:
        results: list[DoctorCheck] = []
        for check_id, fn in self._checks:
            try:
                check = fn(self.backend, settings, org)
            except Exception as exc:  # noqa: BLE001 — the sentinel never fails silently
                results.append(DoctorCheck(
                    check_id=check_id,
                    title=f"check crashed: {check_id}",
                    status=CheckStatus.FAIL,
                    cause=f"{type(exc).__name__}: {exc}",
                    evidence={"traceback_tail": traceback.format_exc()[-800:]},
                ))
                continue
            results.append(check)
        return DoctorReport(results)
