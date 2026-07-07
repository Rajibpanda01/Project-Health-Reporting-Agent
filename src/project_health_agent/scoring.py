from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .models import ProjectContext, ProjectHealthReport, SignalResult, WorkbookAnalysis


BASE_WEIGHTS = {
    "schedule": 0.27,
    "budget": 0.18,
    "milestone": 0.13,
    "execution": 0.16,
    "risk": 0.12,
    "stakeholder": 0.08,
    "resource": 0.06,
    "change": 0.03,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _score_to_status(score: float) -> str:
    if score >= 65:
        return "Red"
    if score >= 35:
        return "Amber"
    return "Green"


def _confidence_from_score(data_quality_score: float) -> str:
    if data_quality_score >= 80:
        return "High"
    if data_quality_score >= 60:
        return "Medium"
    return "Low"


def _normalize_weights(signals: list[SignalResult]) -> list[SignalResult]:
    total_weight = sum(signal.weight for signal in signals)
    if total_weight <= 0:
        return signals
    for signal in signals:
        signal.weight = signal.weight / total_weight
    return signals


def _weighted_score(signals: list[SignalResult]) -> float:
    return sum(signal.score * signal.weight for signal in signals)


def _severity_points(frame: pd.DataFrame, severity_col: str, status_col: str | None = None) -> float:
    if frame.empty:
        return 0.0
    points = {"Critical": 35, "High": 20, "Medium": 12, "Low": 5}
    working = frame.copy()
    if status_col and status_col in working.columns:
        working = working.loc[~working[status_col].isin(["Closed", "Resolved"])]
    return float(working[severity_col].map(points).fillna(0).sum())


def _priority_points(frame: pd.DataFrame, priority_col: str, status_col: str | None = None) -> float:
    if frame.empty:
        return 0.0
    points = {"P1": 25, "P2": 12, "P3": 6}
    working = frame.copy()
    if status_col and status_col in working.columns:
        working = working.loc[~working[status_col].isin(["Closed", "Resolved"])]
    return float(working[priority_col].map(points).fillna(0).sum())


def _recent_sentiment_score(frame: pd.DataFrame) -> tuple[float, list[str]]:
    if frame.empty:
        return 55.0, []
    mapping = {"Positive": 10, "Neutral": 55, "Negative": 100}
    working = frame.copy()
    if "Week" in working.columns:
        working["week_num"] = working["Week"].astype(str).str.replace("W", "", regex=False).astype(int)
        working = working.sort_values("week_num")
    recent = working.tail(2)["Sentiment"].tolist()
    score = sum(mapping[item] for item in recent) / len(recent)
    return score, recent


def _signal_summary(name: str, score: float) -> str:
    band = _score_to_status(score).lower()
    return f"{name} risk is {band} ({round(score, 1)}/100)."


def _status_from_triggers(score: float, red_triggers: list[bool], amber_triggers: list[bool]) -> str:
    if any(red_triggers) or score >= 65:
        return "Red"
    if any(amber_triggers) or score >= 35:
        return "Amber"
    return "Green"


def score_project_context(context: ProjectContext, as_of_date: date) -> ProjectHealthReport:
    if context.plan_type == "portfolio":
        return _score_portfolio_project(context, as_of_date)
    if context.plan_type == "detailed_plan":
        return _score_detailed_project(context, as_of_date)
    raise ValueError(f"Unsupported plan type {context.plan_type}")


def _score_portfolio_project(context: ProjectContext, as_of_date: date) -> ProjectHealthReport:
    summary = context.summary
    budget = context.datasets["budget"]
    milestones = context.datasets["milestones"]
    risks = context.datasets["risks"]
    issues = context.datasets["issues"]
    resources = context.datasets["resources"]
    feedback = context.datasets["feedback"]
    weekly = context.datasets["weekly"]

    progress_gap = max(0.0, float(summary["Planned_%"]) - float(summary["Progress_%"]))
    schedule_delay_days = float(summary["Schedule_Delay_Days"])
    gap_score = _clamp(progress_gap / 12 * 100)
    delay_score = _clamp(schedule_delay_days / 20 * 100)
    schedule_score = 0.6 * gap_score + 0.4 * delay_score
    schedule_signal = SignalResult(
        name="Schedule",
        score=schedule_score,
        status=_score_to_status(schedule_score),
        summary=(
            f"Progress trails plan by {progress_gap:.0f} points and the project is "
            f"{schedule_delay_days:.0f} days behind schedule."
        ),
        weight=BASE_WEIGHTS["schedule"],
        evidence={
            "progress_percent": summary["Progress_%"],
            "planned_percent": summary["Planned_%"],
            "schedule_delay_days": summary["Schedule_Delay_Days"],
        },
    )

    spend_ratio = float(summary["Actual_Spend_USD"]) / float(summary["Budget_USD"])
    burn_gap = max(0.0, spend_ratio - float(summary["Progress_%"]) / 100)
    recent_budget = budget.tail(3) if not budget.empty else budget
    recent_variance_ratio = 0.0
    if not recent_budget.empty and float(recent_budget["Planned"].sum()) > 0:
        recent_variance_ratio = max(0.0, float(recent_budget["Variance"].clip(lower=0).sum()) / float(recent_budget["Planned"].sum()))
    budget_score = _clamp((burn_gap / 0.2) * 100 + max(0.0, spend_ratio - 1) * 200 + recent_variance_ratio * 100)
    budget_signal = SignalResult(
        name="Budget",
        score=budget_score,
        status=_score_to_status(budget_score),
        summary=(
            f"The project has consumed {spend_ratio:.0%} of budget while delivering "
            f"{float(summary['Progress_%']) / 100:.0%} completion."
        ),
        weight=BASE_WEIGHTS["budget"],
        evidence={
            "budget_usd": summary["Budget_USD"],
            "actual_spend_usd": summary["Actual_Spend_USD"],
            "burn_gap": round(burn_gap, 3),
            "recent_positive_variance_ratio": round(recent_variance_ratio, 3),
        },
    )

    total_milestones = max(len(milestones), 1)
    delayed_ratio = float((milestones["Status"] == "Delayed").sum()) / total_milestones if not milestones.empty else 0.0
    overdue_ratio = 0.0
    if not milestones.empty and "Planned_Date" in milestones.columns:
        overdue_ratio = float(
            ((milestones["Planned_Date"] < pd.Timestamp(as_of_date)) & (milestones["Status"] != "Completed")).sum()
        ) / total_milestones
    milestone_score = _clamp(max(delayed_ratio, overdue_ratio) * 100)
    milestone_signal = SignalResult(
        name="Milestone",
        score=milestone_score,
        status=_score_to_status(milestone_score),
        summary=(
            f"{(delayed_ratio * 100):.0f}% of milestones are marked delayed and "
            f"{(overdue_ratio * 100):.0f}% are overdue as of {as_of_date.isoformat()}."
        ),
        weight=BASE_WEIGHTS["milestone"],
        evidence={
            "total_milestones": total_milestones,
            "delayed_ratio": round(delayed_ratio, 3),
            "overdue_ratio": round(overdue_ratio, 3),
        },
    )

    open_issue_points = _priority_points(issues, "Priority", "Status")
    execution_score = _clamp(float(summary["Critical_Blockers"]) * 30 + open_issue_points)
    execution_signal = SignalResult(
        name="Execution",
        score=execution_score,
        status=_score_to_status(execution_score),
        summary=(
            f"The project has {int(summary['Critical_Blockers'])} critical blockers and "
            f"{len(issues.loc[~issues['Status'].isin(['Resolved'])])} unresolved issues."
        ),
        weight=BASE_WEIGHTS["execution"],
        evidence={
            "critical_blockers": summary["Critical_Blockers"],
            "unresolved_issue_count": int(len(issues.loc[~issues["Status"].isin(["Resolved"])])),
            "issue_points": round(open_issue_points, 1),
        },
    )

    risk_score = _clamp(_severity_points(risks, "Severity", "Status"))
    risk_signal = SignalResult(
        name="Risk",
        score=risk_score,
        status=_score_to_status(risk_score),
        summary=(
            f"The risk register contains {len(risks.loc[~risks['Status'].isin(['Closed'])])} active items "
            "with a meaningful concentration of high and critical entries."
        ),
        weight=BASE_WEIGHTS["risk"],
        evidence={
            "active_risk_count": int(len(risks.loc[~risks["Status"].isin(["Closed"])])),
            "severity_mix": dict(Counter(risks.loc[~risks["Status"].isin(["Closed"]), "Severity"])),
        },
    )

    stakeholder_score, recent_sentiment = _recent_sentiment_score(feedback)
    stakeholder_signal = SignalResult(
        name="Stakeholder",
        score=stakeholder_score,
        status=_score_to_status(stakeholder_score),
        summary=(
            f"Recent stakeholder sentiment is {', '.join(recent_sentiment) if recent_sentiment else summary['Stakeholder_Sentiment']}."
        ),
        weight=BASE_WEIGHTS["stakeholder"],
        evidence={
            "summary_sentiment": summary["Stakeholder_Sentiment"],
            "recent_feedback": recent_sentiment,
        },
    )

    max_role_utilization = float(resources["Utilization_%"].max()) if not resources.empty else float(summary["Resource_Utilization_%"])
    summary_util = float(summary["Resource_Utilization_%"])
    resource_score = 10 if max(summary_util, max_role_utilization) <= 80 else 40 if max(summary_util, max_role_utilization) <= 90 else 80 if max(summary_util, max_role_utilization) <= 100 else 100
    resource_signal = SignalResult(
        name="Resource",
        score=resource_score,
        status=_score_to_status(resource_score),
        summary=(
            f"Resource utilization is running at {summary_util:.0f}% overall, with a peak role load of {max_role_utilization:.0f}%."
        ),
        weight=BASE_WEIGHTS["resource"],
        evidence={
            "portfolio_utilization": summary["Resource_Utilization_%"],
            "max_role_utilization": max_role_utilization,
        },
    )

    signals = _normalize_weights(
        [
            schedule_signal,
            budget_signal,
            milestone_signal,
            execution_signal,
            risk_signal,
            stakeholder_signal,
            resource_signal,
        ]
    )
    overall_score = _weighted_score(signals)

    latest_progress = None
    if not weekly.empty:
        working = weekly.copy()
        working["week_num"] = working["Week"].astype(str).str.replace("W", "", regex=False).astype(int)
        latest_progress = float(working.sort_values("week_num").iloc[-1]["Progress_%"])
    data_quality_score = 100.0
    if latest_progress is not None:
        data_quality_score -= min(20.0, abs(latest_progress - float(summary["Progress_%"])))

    rag_status = _status_from_triggers(
        overall_score,
        red_triggers=[
            float(summary["Critical_Blockers"]) >= 2,
            milestone_score >= 70,
            schedule_score >= 70 and budget_score >= 50,
            risk_score >= 70 and stakeholder_score >= 55,
        ],
        amber_triggers=[
            schedule_score >= 50,
            budget_score >= 40,
            execution_score >= 40,
            risk_score >= 40,
        ],
    )

    reasons = _top_reasons(signals, rag_status)
    recommendations = _recommendations_from_signals(signals, rag_status, data_quality_score)
    assumptions = [
        "Used the workbook's project summary row as the primary source of truth for current-state metrics.",
        f"Evaluated overdue milestones against {as_of_date.isoformat()}.",
        "Did not use the provided RAG column as an input; treated it only as an optional validation reference.",
    ]
    validation = {}
    if context.existing_rag:
        validation = {
            "provided_rag_status": context.existing_rag,
            "matches_provided_status": context.existing_rag == rag_status,
        }

    return ProjectHealthReport(
        workbook_name=context.workbook_name,
        workbook_path=context.workbook_path,
        plan_type=context.plan_type,
        project_id=context.project_id,
        project_name=context.project_name,
        rag_status=rag_status,
        overall_score=overall_score,
        confidence=_confidence_from_score(data_quality_score),
        data_quality_score=data_quality_score,
        status_summary=_status_summary_text(rag_status, signals),
        reasons=reasons,
        recommendations=recommendations,
        assumptions=assumptions,
        signals=signals,
        key_metrics={
            "progress_percent": float(summary["Progress_%"]),
            "planned_percent": float(summary["Planned_%"]),
            "progress_gap": round(progress_gap, 1),
            "schedule_delay_days": schedule_delay_days,
            "budget_burn_ratio": round(spend_ratio, 3),
            "burn_gap": round(burn_gap, 3),
            "critical_blockers": int(summary["Critical_Blockers"]),
            "open_risks": int(summary["Open_Risks"]),
            "summary_sentiment": summary["Stakeholder_Sentiment"],
            "resource_utilization": float(summary["Resource_Utilization_%"]),
        },
        validation=validation,
    )


def _score_detailed_project(context: ProjectContext, as_of_date: date) -> ProjectHealthReport:
    plan = context.datasets["plan"]
    risks = context.datasets["risks"]
    issues = context.datasets["issues"]
    resources = context.datasets["resources"]
    changes = context.datasets["changes"]
    weekly = context.datasets["weekly"]

    start_date = pd.Timestamp(context.summary["start_date"])
    finish_date = pd.Timestamp(context.summary["finish_date"])
    project_window_days = max(1, int((finish_date - start_date).days))
    elapsed_ratio = _clamp((pd.Timestamp(as_of_date) - start_date).days / project_window_days, 0, 1)
    planned_progress = elapsed_ratio * 100

    task_progress = float(pd.to_numeric(plan["%_Complete"], errors="coerce").fillna(0).mean())
    weekly_progress = float(context.summary["weekly_reported_progress"]) if context.summary["weekly_reported_progress"] is not None else None
    progress_gap_between_sources = abs(weekly_progress - task_progress) if weekly_progress is not None else 0.0
    if weekly_progress is None:
        blended_progress = task_progress
    else:
        blended_progress = (task_progress * 0.6) + (weekly_progress * 0.4)

    due_tasks = plan.loc[plan["Finish_Date"] <= pd.Timestamp(as_of_date)]
    overdue_incomplete = due_tasks.loc[~due_tasks["Status"].isin(["Completed", "Not Applicable"])]
    overdue_ratio = float(len(overdue_incomplete) / len(due_tasks)) if len(due_tasks) else 0.0
    progress_gap = max(0.0, planned_progress - blended_progress)
    schedule_score = (0.4 * _clamp(progress_gap / 15 * 100)) + (0.6 * _clamp(overdue_ratio * 100))
    schedule_signal = SignalResult(
        name="Schedule",
        score=schedule_score,
        status=_score_to_status(schedule_score),
        summary=(
            f"About {planned_progress:.0f}% of the plan duration has elapsed, while blended progress is "
            f"{blended_progress:.0f}% and {overdue_ratio:.0%} of due tasks are still incomplete."
        ),
        weight=BASE_WEIGHTS["schedule"],
        evidence={
            "planned_progress_by_date": round(planned_progress, 1),
            "task_based_progress": round(task_progress, 1),
            "weekly_reported_progress": round(weekly_progress, 1) if weekly_progress is not None else None,
            "blended_progress": round(blended_progress, 1),
            "overdue_ratio": round(overdue_ratio, 3),
        },
    )

    total_tasks = max(len(plan), 1)
    blocked_ratio = float(plan["Status"].isin(["Blocked", "On Hold"]).sum() / total_tasks)
    if "Priority" in plan.columns and not plan["Priority"].dropna().empty:
        high_priority_open = int(((plan["Priority"] == "High") & ~plan["Status"].isin(["Completed", "Not Applicable"])).sum())
    else:
        high_priority_open = int(
            ((plan.get("Schedule_Health", pd.Series("", index=plan.index)) == "Red") & ~plan["Status"].isin(["Completed", "Not Applicable"])).sum()
        )
    issue_points = _priority_points(issues, "Priority")
    execution_score = _clamp((blocked_ratio * 100 * 0.6) + min(40.0, high_priority_open / 20 * 40) + min(30.0, issue_points))
    execution_signal = SignalResult(
        name="Execution",
        score=execution_score,
        status=_score_to_status(execution_score),
        summary=(
            f"{blocked_ratio:.0%} of tasks are blocked and {high_priority_open} high-priority tasks are still open."
        ),
        weight=BASE_WEIGHTS["execution"],
        evidence={
            "blocked_ratio": round(blocked_ratio, 3),
            "blocked_tasks": int((plan["Status"] == "Blocked").sum()),
            "high_priority_open_tasks": high_priority_open,
            "open_issue_points": round(issue_points, 1),
        },
    )

    risk_score = _clamp(_severity_points(risks, "Severity"))
    risk_signal = SignalResult(
        name="Risk",
        score=risk_score,
        status=_score_to_status(risk_score),
        summary=(
            f"The plan carries {int((risks['Severity'] == 'Critical').sum())} critical risks and "
            f"{int((risks['Severity'] == 'High').sum())} high risks."
        ),
        weight=BASE_WEIGHTS["risk"],
        evidence={
            "critical_risks": int((risks["Severity"] == "Critical").sum()),
            "high_risks": int((risks["Severity"] == "High").sum()),
            "severity_mix": dict(Counter(risks["Severity"])),
        },
    )

    avg_utilization = float(resources["Utilization_%"].mean()) if not resources.empty else 0.0
    max_utilization = float(resources["Utilization_%"].max()) if not resources.empty else 0.0
    resource_score = 10 if max_utilization <= 80 else 40 if max_utilization <= 90 else 80 if max_utilization <= 100 else 100
    resource_signal = SignalResult(
        name="Resource",
        score=resource_score,
        status=_score_to_status(resource_score),
        summary=(
            f"Average resource utilization is {avg_utilization:.0f}% and the most stretched role is at {max_utilization:.0f}%."
        ),
        weight=BASE_WEIGHTS["resource"],
        evidence={
            "average_utilization": round(avg_utilization, 1),
            "max_utilization": round(max_utilization, 1),
        },
    )

    change_points = (
        (changes["Impact"] == "High").sum() * 35
        + (changes["Impact"] == "Medium").sum() * 10
        + (changes["Impact"] == "Low").sum() * 4
    )
    change_score = _clamp(change_points)
    change_signal = SignalResult(
        name="Change",
        score=change_score,
        status=_score_to_status(change_score),
        summary=(
            f"The change log contains {len(changes)} requests, including "
            f"{int((changes['Impact'] == 'High').sum())} high-impact changes."
        ),
        weight=BASE_WEIGHTS["change"],
        evidence={
            "change_request_count": int(len(changes)),
            "impact_mix": dict(Counter(changes["Impact"])),
        },
    )

    signals = _normalize_weights(
        [
            schedule_signal,
            execution_signal,
            risk_signal,
            resource_signal,
            change_signal,
        ]
    )
    overall_score = _weighted_score(signals)

    data_quality_score = 100.0
    data_quality_score -= 15.0  # No explicit budget sheet for this plan.
    data_quality_score -= 10.0  # No explicit stakeholder sentiment sheet.
    data_quality_score -= min(25.0, progress_gap_between_sources)

    rag_status = _status_from_triggers(
        overall_score,
        red_triggers=[
            overdue_ratio >= 0.5,
            blocked_ratio >= 0.2,
            int((risks["Severity"] == "Critical").sum()) >= 3,
            int((issues["Priority"] == "P1").sum()) >= 5,
        ],
        amber_triggers=[
            schedule_score >= 50,
            blocked_ratio >= 0.1,
            max_utilization >= 95,
        ],
    )

    reasons = _top_reasons(signals, rag_status)
    recommendations = _recommendations_from_signals(signals, rag_status, data_quality_score)
    assumptions = [
        f"Evaluated the plan against {as_of_date.isoformat()} because no explicit report date was stored in the workbook.",
        "Used a conservative blended progress figure when the weekly summary and task-level completion disagreed.",
        "Renormalized the overall score because budget and stakeholder sentiment data were not available in this workbook.",
    ]
    validation = {}
    if context.existing_rag:
        validation = {
            "provided_rag_status": context.existing_rag,
            "matches_provided_status": context.existing_rag == rag_status,
        }

    return ProjectHealthReport(
        workbook_name=context.workbook_name,
        workbook_path=context.workbook_path,
        plan_type=context.plan_type,
        project_id=context.project_id,
        project_name=context.project_name,
        rag_status=rag_status,
        overall_score=overall_score,
        confidence=_confidence_from_score(data_quality_score),
        data_quality_score=data_quality_score,
        status_summary=_status_summary_text(rag_status, signals),
        reasons=reasons,
        recommendations=recommendations,
        assumptions=assumptions,
        signals=signals,
        key_metrics={
            "planned_progress_by_date": round(planned_progress, 1),
            "task_based_progress": round(task_progress, 1),
            "weekly_reported_progress": round(weekly_progress, 1) if weekly_progress is not None else None,
            "progress_signal_gap": round(progress_gap_between_sources, 1),
            "overdue_ratio": round(overdue_ratio, 3),
            "blocked_ratio": round(blocked_ratio, 3),
            "critical_risks": int((risks["Severity"] == "Critical").sum()),
            "p1_issues": int((issues["Priority"] == "P1").sum()),
            "max_utilization": round(max_utilization, 1),
            "average_utilization": round(avg_utilization, 1),
        },
        validation=validation,
    )


def _top_reasons(signals: list[SignalResult], rag_status: str) -> list[str]:
    ordered = sorted(signals, key=lambda item: item.score * item.weight, reverse=True)
    lead_count = 3 if rag_status == "Red" else 2
    return [signal.summary for signal in ordered[:lead_count]]


def _recommendations_from_signals(
    signals: list[SignalResult],
    rag_status: str,
    data_quality_score: float,
) -> list[str]:
    sorted_signals = sorted(signals, key=lambda item: item.score * item.weight, reverse=True)
    recommendations: list[str] = []
    for signal in sorted_signals[:3]:
        if signal.name == "Schedule":
            recommendations.append("Re-baseline overdue work and assign owners for the next two milestone dates.")
        elif signal.name == "Budget":
            recommendations.append("Freeze non-essential spend until delivery progress catches up with the burn rate.")
        elif signal.name == "Milestone":
            recommendations.append("Turn delayed milestones into a dated recovery plan with explicit checkpoint owners.")
        elif signal.name == "Execution":
            recommendations.append("Run a daily blocker and issue review until the open execution queue drops materially.")
        elif signal.name == "Risk":
            recommendations.append("Convert critical risks into named mitigation actions with target resolution dates.")
        elif signal.name == "Stakeholder":
            recommendations.append("Schedule a sponsor checkpoint to align expectations and close sentiment gaps early.")
        elif signal.name == "Resource":
            recommendations.append("Rebalance the team or add temporary capacity to the most overloaded roles.")
        elif signal.name == "Change":
            recommendations.append("Tighten change control and defer medium-impact enhancements that are not deadline-critical.")
    if data_quality_score < 75:
        recommendations.append("Reconcile conflicting progress signals before the next weekly report to improve confidence.")
    deduped: list[str] = []
    for item in recommendations:
        if item not in deduped:
            deduped.append(item)
    return deduped[:4 if rag_status == "Red" else 3]


def _status_summary_text(rag_status: str, signals: list[SignalResult]) -> str:
    ordered = sorted(signals, key=lambda item: item.score * item.weight, reverse=True)
    leaders = ", ".join(f"{signal.name.lower()} risk" for signal in ordered[:2])
    return f"{rag_status} because {leaders} are driving the highest weighted pressure."


def summarize_workbook(
    reports: list[ProjectHealthReport],
    workbook_name: str,
    workbook_path: str,
    plan_type: str,
    as_of_date: date,
) -> WorkbookAnalysis:
    rag_counts = Counter(report.rag_status for report in reports)
    average_score = round(sum(report.overall_score for report in reports) / max(len(reports), 1), 1)
    lowest_confidence = min((report.data_quality_score for report in reports), default=100.0)
    watchlist = sorted(reports, key=lambda item: item.overall_score, reverse=True)[:5]

    executive_summary = {
        "project_count": len(reports),
        "rag_counts": dict(rag_counts),
        "average_score": average_score,
        "lowest_data_quality_score": round(lowest_confidence, 1),
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
        workbook_name=workbook_name,
        workbook_path=Path(workbook_path),
        plan_type=plan_type,
        analyzed_at=datetime.utcnow(),
        as_of_date=as_of_date,
        reports=reports,
        executive_summary=executive_summary,
    )
