from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import ProjectHealthReport, WorkbookAnalysis


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def write_workbook_outputs(analysis: WorkbookAnalysis, base_output_dir: Path) -> Path:
    workbook_dir = base_output_dir / slugify(Path(analysis.workbook_name).stem)
    ensure_dir(workbook_dir)
    ensure_dir(workbook_dir / "project_reports")

    with (workbook_dir / "weekly_health_report.json").open("w", encoding="utf-8") as handle:
        json.dump(analysis.to_dict(), handle, indent=2)

    (workbook_dir / "weekly_health_report.md").write_text(
        render_workbook_markdown(analysis),
        encoding="utf-8",
    )
    write_project_summary_csv(analysis.reports, workbook_dir / "project_summary.csv")

    for report in analysis.reports:
        report_path = workbook_dir / "project_reports" / f"{slugify(report.project_id)}.md"
        report_path.write_text(render_project_markdown(report), encoding="utf-8")
        with report_path.with_suffix(".json").open("w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2)

    return workbook_dir


def write_project_summary_csv(reports: Iterable[ProjectHealthReport], path: Path) -> None:
    rows = [
        {
            "project_id": report.project_id,
            "project_name": report.project_name,
            "rag_status": report.rag_status,
            "overall_score": round(report.overall_score, 1),
            "confidence": report.confidence,
            "data_quality_score": round(report.data_quality_score, 1),
            "top_reason_1": report.reasons[0] if len(report.reasons) > 0 else "",
            "top_reason_2": report.reasons[1] if len(report.reasons) > 1 else "",
        }
        for report in reports
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def render_workbook_markdown(analysis: WorkbookAnalysis) -> str:
    lines = [
        f"# Weekly Health Report: {Path(analysis.workbook_name).stem.replace('_', ' ')}",
        "",
        f"- As of date: `{analysis.as_of_date.isoformat()}`",
        f"- Workbook type: `{analysis.plan_type}`",
        f"- Project count: `{analysis.executive_summary['project_count']}`",
        f"- RAG mix: `{analysis.executive_summary['rag_counts']}`",
        f"- Average health score: `{analysis.executive_summary['average_score']}`",
        "",
        "## Executive Summary",
        "",
    ]
    for report in analysis.reports[: min(5, len(analysis.reports))]:
        lines.append(
            f"- `{report.project_id}` is **{report.rag_status}** at `{report.overall_score:.1f}/100` because {', '.join(reason.rstrip('.') for reason in report.reasons[:2]).lower()}."
        )
    lines.extend(
        [
            "",
            "## Watchlist",
            "",
        ]
    )
    for item in analysis.executive_summary["watchlist"]:
        lines.append(
            f"- `{item['project_id']}` `{item['project_name']}`: `{item['rag_status']}` at `{item['overall_score']}`"
        )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `project_summary.csv` contains the flat report view.",
            "- `project_reports/` contains one Markdown and one JSON report per analyzed project.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_project_markdown(report: ProjectHealthReport) -> str:
    lines = [
        f"# {report.project_name}",
        "",
        f"- Project ID: `{report.project_id}`",
        f"- RAG Status: **{report.rag_status}**",
        f"- Overall Score: `{report.overall_score:.1f}/100`",
        f"- Confidence: `{report.confidence}`",
        f"- Data Quality Score: `{report.data_quality_score:.1f}/100`",
        "",
        report.status_summary,
        "",
        "## Why This Status",
        "",
    ]
    for reason in report.reasons:
        lines.append(f"- {reason}")
    lines.extend(
        [
            "",
            "## Signal Breakdown",
            "",
        ]
    )
    for signal in report.signals:
        lines.append(
            f"- **{signal.name}**: `{signal.status}` at `{signal.score:.1f}/100` weighted `{signal.weight:.2f}`. {signal.summary}"
        )
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
        ]
    )
    for item in report.recommendations:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Assumptions",
            "",
        ]
    )
    for item in report.assumptions:
        lines.append(f"- {item}")
    if report.validation:
        lines.extend(
            [
                "",
                "## Validation",
                "",
                f"- Provided RAG in workbook: `{report.validation.get('provided_rag_status')}`",
                f"- Matches provided status: `{report.validation.get('matches_provided_status')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_monthly_synthesis_inputs(reports: list[ProjectHealthReport], path: Path) -> None:
    rows = []
    for report in reports:
        top_signal = sorted(report.signals, key=lambda signal: signal.score * signal.weight, reverse=True)[0]
        rows.append(
            {
                "workbook_name": report.workbook_name,
                "project_id": report.project_id,
                "project_name": report.project_name,
                "rag_status": report.rag_status,
                "overall_score": round(report.overall_score, 1),
                "confidence": report.confidence,
                "top_risk_driver": top_signal.name,
                "top_risk_score": round(top_signal.score, 1),
                "reason_1": report.reasons[0] if report.reasons else "",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
