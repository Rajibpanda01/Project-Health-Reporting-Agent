from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .loaders import load_workbook
from .presentation import generate_monthly_presentation
from .reporting import ensure_dir, write_monthly_synthesis_inputs, write_workbook_outputs
from .scoring import score_project_context


@dataclass
class AnalysisResult:
    as_of_date: str
    workbooks: list[dict]
    total_projects: int
    overall_rag_counts: dict[str, int]
    monthly_deck: dict | None
    output_dir: str
    deck_output: str | None
    monthly_deck_data_path: str
    monthly_synthesis_input_path: str
    run_summary_path: str

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date,
            "workbooks": self.workbooks,
            "total_projects": self.total_projects,
            "overall_rag_counts": self.overall_rag_counts,
            "monthly_deck": self.monthly_deck,
            "output_dir": self.output_dir,
            "deck_output": self.deck_output,
            "monthly_deck_data_path": self.monthly_deck_data_path,
            "monthly_synthesis_input_path": self.monthly_synthesis_input_path,
            "run_summary_path": self.run_summary_path,
        }


def run_analysis(
    input_paths: list[str | Path],
    output_dir: str | Path,
    as_of_date: date,
    deck_output: str | Path | None = None,
    skip_deck: bool = False,
) -> AnalysisResult:
    output_dir = Path(output_dir)
    ensure_dir(output_dir)

    deck_output_path = Path(deck_output) if deck_output is not None else None
    if deck_output_path is not None:
        ensure_dir(deck_output_path.parent)

    all_reports = []
    workbook_summaries = []

    for input_path in input_paths:
        workbook = load_workbook(input_path)
        reports = [score_project_context(context, as_of_date) for context in workbook.contexts]
        workbook_dir = write_workbook_outputs(
            analysis=_build_workbook_analysis(workbook, reports, as_of_date),
            base_output_dir=output_dir,
        )
        workbook_summaries.append(
            {
                "workbook_name": workbook.workbook_name,
                "workbook_path": str(workbook.workbook_path),
                "output_dir": str(workbook_dir),
                "project_count": len(reports),
                "rag_counts": _rag_counts(reports),
            }
        )
        all_reports.extend(reports)

    monthly_input_path = output_dir / "monthly_synthesis_input.csv"
    monthly_deck_data_path = output_dir / "monthly_deck_data.json"
    run_summary_path = output_dir / "run_summary.json"

    write_monthly_synthesis_inputs(all_reports, monthly_input_path)

    deck_data = _build_monthly_deck_data(all_reports)
    with monthly_deck_data_path.open("w", encoding="utf-8") as handle:
        json.dump(deck_data, handle, indent=2)

    monthly_deck = None
    if not skip_deck and deck_output_path is not None:
        monthly_deck = generate_monthly_presentation(monthly_deck_data_path, deck_output_path)

    result = AnalysisResult(
        as_of_date=as_of_date.isoformat(),
        workbooks=workbook_summaries,
        total_projects=len(all_reports),
        overall_rag_counts=_rag_counts(all_reports),
        monthly_deck=monthly_deck,
        output_dir=str(output_dir),
        deck_output=str(deck_output_path) if deck_output_path is not None else None,
        monthly_deck_data_path=str(monthly_deck_data_path),
        monthly_synthesis_input_path=str(monthly_input_path),
        run_summary_path=str(run_summary_path),
    )

    with run_summary_path.open("w", encoding="utf-8") as handle:
        json.dump(result.to_dict(), handle, indent=2)

    return result


def _rag_counts(reports) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        counts[report.rag_status] = counts.get(report.rag_status, 0) + 1
    return counts


def _build_workbook_analysis(workbook, reports, as_of_date):
    from .models import WorkbookAnalysis

    watchlist = sorted(reports, key=lambda item: item.overall_score, reverse=True)[:5]
    executive_summary = {
        "project_count": len(reports),
        "rag_counts": _rag_counts(reports),
        "average_score": round(sum(item.overall_score for item in reports) / max(len(reports), 1), 1),
        "watchlist": [
            {
                "project_id": report.project_id,
                "project_name": report.project_name,
                "rag_status": report.rag_status,
                "overall_score": round(report.overall_score, 1),
            }
            for report in watchlist
        ],
    }
    return WorkbookAnalysis(
        workbook_name=workbook.workbook_name,
        workbook_path=workbook.workbook_path,
        plan_type=workbook.plan_type,
        analyzed_at=datetime.utcnow(),
        as_of_date=as_of_date,
        reports=reports,
        executive_summary=executive_summary,
    )


def build_monthly_deck_data_from_reports(reports) -> dict:
    return _build_monthly_deck_data(reports)


def _build_monthly_deck_data(reports):
    overall_counts = _rag_counts(reports)
    driver_counts = Counter()

    for report in reports:
        ranked = sorted(report.signals, key=lambda signal: signal.score * signal.weight, reverse=True)
        if ranked:
            driver_counts[ranked[0].name] += 1

    validation_total = sum(1 for report in reports if report.validation)
    validation_matches = sum(1 for report in reports if report.validation and report.validation.get("matches_provided_status"))
    detailed_reports = [report for report in reports if report.plan_type == "detailed_plan"]

    deck_data = {
        "overall": {
            "project_count": len(reports),
            "rag_counts": overall_counts,
            "average_score": round(sum(report.overall_score for report in reports) / max(len(reports), 1), 1),
            "red_pct": round((overall_counts.get("Red", 0) / max(len(reports), 1)) * 100, 1),
            "lead_driver_counts": dict(driver_counts),
        },
        "portfolio": {
            "project_count": len(reports),
            "rag_counts": overall_counts,
            "average_score": round(sum(report.overall_score for report in reports) / max(len(reports), 1), 1),
            "delay_gt_14_days": sum(
                1
                for report in reports
                if report.key_metrics.get("schedule_delay_days", 0) > 14
                or report.key_metrics.get("overdue_ratio", 0) >= 0.2
            ),
            "burn_ahead_gt_10pts": sum(
                1
                for report in reports
                if report.key_metrics.get("burn_gap", 0) > 0.10
                or report.key_metrics.get("budget_burn_ratio", 0) > 1.0
            ),
            "critical_blocker_projects": sum(
                1
                for report in reports
                if report.key_metrics.get("critical_blockers", 0) >= 2
                or report.key_metrics.get("blocked_ratio", 0) >= 0.1
            ),
            "negative_or_neutral_sentiment": sum(
                1
                for report in reports
                if report.key_metrics.get("summary_sentiment") in {"Negative", "Neutral"} or report.confidence == "Low"
            ),
            "resource_util_gt_90": sum(
                1
                for report in reports
                if report.key_metrics.get("resource_utilization", 0) > 90
                or report.key_metrics.get("max_utilization", 0) > 90
                or report.key_metrics.get("average_utilization", 0) > 85
            ),
            "validation_accuracy": round(validation_matches / max(validation_total, 1), 3)
            if validation_total
            else None,
        },
        "critical_projects": [],
        "plan_b": {},
        "outlook": {},
    }

    deck_data["critical_projects"] = [
        {
            "project_id": report.project_id,
            "project_name": report.project_name,
            "rag_status": report.rag_status,
            "overall_score": round(report.overall_score, 1),
            "reason_1": report.reasons[0] if report.reasons else "",
            "reason_2": report.reasons[1] if len(report.reasons) > 1 else "",
        }
        for report in sorted(
            [report for report in reports if report.rag_status == "Red"] or reports,
            key=lambda item: item.overall_score,
            reverse=True,
        )[:5]
    ]

    if detailed_reports:
        plan_b = next(
            (report for report in detailed_reports if "plan_b" in report.project_id.lower() or "project_plan_b" in report.project_id.lower()),
            detailed_reports[0],
        )
        deck_data["plan_b"] = {
            "project_name": plan_b.project_name,
            "rag_status": plan_b.rag_status,
            "overall_score": round(plan_b.overall_score, 1),
            "confidence": plan_b.confidence,
            "data_quality_score": round(plan_b.data_quality_score, 1),
            "planned_progress_by_date": plan_b.key_metrics.get("planned_progress_by_date"),
            "task_based_progress": plan_b.key_metrics.get("task_based_progress"),
            "weekly_reported_progress": plan_b.key_metrics.get("weekly_reported_progress"),
            "progress_signal_gap": plan_b.key_metrics.get("progress_signal_gap"),
            "overdue_ratio": plan_b.key_metrics.get("overdue_ratio"),
            "blocked_ratio": plan_b.key_metrics.get("blocked_ratio"),
            "critical_risks": plan_b.key_metrics.get("critical_risks"),
            "p1_issues": plan_b.key_metrics.get("p1_issues"),
            "reasons": plan_b.reasons,
        }

    deck_data["outlook"] = _build_outlook(deck_data)
    return deck_data


def _build_outlook(deck_data: dict) -> dict:
    red_pct = deck_data["overall"].get("red_pct", 0)
    delay_count = deck_data.get("portfolio", {}).get("delay_gt_14_days", 0)
    burn_count = deck_data.get("portfolio", {}).get("burn_ahead_gt_10pts", 0)
    blocker_count = deck_data.get("portfolio", {}).get("critical_blocker_projects", 0)
    progress_gap = deck_data.get("plan_b", {}).get("progress_signal_gap", 0) or 0
    focus_name = deck_data.get("plan_b", {}).get("project_name", "the leading red project")

    if red_pct >= 70:
        forecast = (
            "Without intervention, the portfolio is likely to stay red-heavy next month because delay, cost, "
            "and blocker pressure are all elevated at the same time."
        )
    elif red_pct >= 40:
        forecast = (
            "The portfolio should remain mixed next month, but several amber projects could still move red if "
            "recovery plans are not enforced."
        )
    else:
        forecast = (
            "The portfolio is positioned to stay broadly stable next month if the current governance cadence is maintained."
        )

    improvements = [
        f"Re-baselining the top five red projects should slow further schedule deterioration across the {delay_count} projects already delayed by more than 14 days.",
        f"A tighter burn-versus-progress review should help contain the {burn_count} projects currently spending ahead of delivery progress.",
        f"Daily blocker escalation and better status hygiene should improve confidence on the {blocker_count} heavily blocked projects and narrow the {progress_gap:.1f}-point reporting gap in {focus_name}.",
    ]

    return {
        "forecast": forecast,
        "expected_improvements": improvements,
    }
