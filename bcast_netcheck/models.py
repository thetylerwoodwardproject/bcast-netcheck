"""Serializable data shared by checks, diagnosis and renderers."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    target: str | None = None
    value: Any = None
    unit: str | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    endpoint: str = ""
    required: bool = True
    kind: str = ""
    label: str = ""


@dataclass
class Diagnosis:
    status: str
    summary: str
    recommendations: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {"healthy": 0, "warning": 1, "failure": 2, "critical": 2, "error": 3}[self.status]


@dataclass
class DiagnosticRun:
    target: str
    site: str | None
    description: str
    timestamp: str
    version: str
    checks: list[CheckResult]
    diagnosis: Diagnosis
