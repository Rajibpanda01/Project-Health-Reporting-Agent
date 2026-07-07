from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass
class SignalResult:
    name: str
    score: float
    status: str
    summary: str
    weight: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 1)
        payload["weight"] = round(self.weight, 3)
        return _json_safe(payload)


@dataclass
class ProjectHealthReport:
    workbook_name: str
    workbook_path: Path
    plan_type: str
    project_id: str
    project_name: str
    rag_status: str
    overall_score: float
    confidence: str
    data_quality_score: float
    status_summary: str
    reasons: list[str]
    recommendations: list[str]
    assumptions: list[str]
    signals: list[SignalResult]
    key_metrics: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workbook_path"] = str(self.workbook_path)
        payload["overall_score"] = round(self.overall_score, 1)
        payload["data_quality_score"] = round(self.data_quality_score, 1)
        payload["signals"] = [signal.to_dict() for signal in self.signals]
        return _json_safe(payload)


@dataclass
class WorkbookAnalysis:
    workbook_name: str
    workbook_path: Path
    plan_type: str
    analyzed_at: datetime
    as_of_date: date
    reports: list[ProjectHealthReport]
    executive_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "workbook_name": self.workbook_name,
                "workbook_path": str(self.workbook_path),
                "plan_type": self.plan_type,
                "analyzed_at": self.analyzed_at.isoformat(),
                "as_of_date": self.as_of_date.isoformat(),
                "reports": [report.to_dict() for report in self.reports],
                "executive_summary": self.executive_summary,
            }
        )


@dataclass
class ProjectContext:
    workbook_name: str
    workbook_path: Path
    plan_type: str
    project_id: str
    project_name: str
    summary: dict[str, Any]
    datasets: dict[str, Any]
    existing_rag: str | None = None


@dataclass
class LoadedWorkbook:
    workbook_name: str
    workbook_path: Path
    plan_type: str
    contexts: list[ProjectContext]
