from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .models import LoadedWorkbook, ProjectContext


def _clean_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.where(pd.notnull(frame), None).to_dict(orient="records")


def _parse_dates(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _normalize_sheet_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_rag(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    mapping = {
        "green": "Green",
        "amber": "Amber",
        "yellow": "Amber",
        "red": "Red",
    }
    return mapping.get(text, str(value).strip())


def _scale_percent(value: Any) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    numeric = float(numeric)
    if numeric <= 1.5:
        numeric *= 100
    return round(numeric, 1)


def _find_sheet(sheets: list[str], *candidates: str) -> str | None:
    normalized_map = {_normalize_sheet_name(sheet): sheet for sheet in sheets}
    for candidate in candidates:
        match = normalized_map.get(_normalize_sheet_name(candidate))
        if match:
            return match
    return None


def _read_optional_sheet(workbook_path: Path, sheet_name: str | None) -> pd.DataFrame:
    if not sheet_name:
        return pd.DataFrame()
    return pd.read_excel(workbook_path, sheet_name=sheet_name)


def _normalize_plan_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().replace("%", "Percent")
        normalized = re.sub(r"[^0-9A-Za-z]+", "_", normalized).strip("_")
        renamed[column] = normalized
    frame = frame.rename(columns=renamed)

    aliases = {
        "Percent_Complete": "%_Complete",
        "End_Date": "Finish_Date",
        "Task_Name": "Task_Name",
        "Project_Name": "Project_Name",
        "Project_Manager": "Project_Manager",
        "Schedule_Health": "Schedule_Health",
        "At_Risk": "At_Risk",
        "On_Hold": "On_Hold",
        "Assigned_To": "Assigned_To",
        "Status_Comment": "Status_Comment",
        "Critical": "Critical",
    }
    frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame.columns})

    if "Task_Name" in frame.columns:
        frame = frame.loc[frame["Task_Name"].notna()].copy()

    if "%_Complete" in frame.columns:
        percent_values = pd.to_numeric(frame["%_Complete"], errors="coerce")
        if not percent_values.dropna().empty and float(percent_values.dropna().max()) <= 1.5:
            percent_values = percent_values * 100
        frame["%_Complete"] = percent_values

    if "Status" in frame.columns:
        frame["Status"] = frame["Status"].astype(str).str.strip()

    if "Schedule_Health" in frame.columns:
        frame["Schedule_Health"] = frame["Schedule_Health"].astype(str).str.strip().str.title()

    return _parse_dates(frame, ["Start_Date", "Finish_Date", "Baseline_Start", "Baseline_Finish"])


def _summary_key_value_map(summary_frame: pd.DataFrame) -> dict[str, Any]:
    if summary_frame.empty or len(summary_frame.columns) < 2:
        return {}
    key_column = summary_frame.columns[0]
    value_column = summary_frame.columns[1]
    mapping: dict[str, Any] = {}
    for _, row in summary_frame.iterrows():
        key = row.get(key_column)
        value = row.get(value_column)
        if pd.notna(key):
            mapping[str(key).strip()] = None if pd.isna(value) else value
    return mapping


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _synthesize_risks_from_plan(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return _empty_frame(["Risk", "Severity", "Status"])

    working = plan.copy()
    status = working["Status"] if "Status" in working.columns else pd.Series("", index=working.index)
    schedule_health = (
        working["Schedule_Health"] if "Schedule_Health" in working.columns else pd.Series("", index=working.index)
    )
    at_risk = pd.to_numeric(working["At_Risk"], errors="coerce").fillna(0) if "At_Risk" in working.columns else 0
    critical_flag = (
        pd.to_numeric(working["Critical"], errors="coerce").fillna(0) if "Critical" in working.columns else 0
    )

    open_mask = ~status.isin(["Completed", "Not Applicable"])
    risk_mask = open_mask & (
        schedule_health.isin(["Red", "Yellow"]) | (pd.Series(at_risk, index=working.index) > 0) | (pd.Series(critical_flag, index=working.index) > 0)
    )
    subset = working.loc[risk_mask].copy()
    if subset.empty:
        return _empty_frame(["Risk", "Severity", "Status"])

    subset["Severity"] = "Low"
    subset.loc[subset.get("Schedule_Health", "").eq("Yellow"), "Severity"] = "Medium"
    subset.loc[subset.get("Schedule_Health", "").eq("Red"), "Severity"] = "High"
    if "At_Risk" in subset.columns:
        subset.loc[pd.to_numeric(subset["At_Risk"], errors="coerce").fillna(0) > 0, "Severity"] = "Critical"
    if "Critical" in subset.columns:
        subset.loc[pd.to_numeric(subset["Critical"], errors="coerce").fillna(0) > 0, "Severity"] = "Critical"

    subset["Risk"] = subset["Task_Name"]
    subset["Status"] = "Open"
    return subset[["Risk", "Severity", "Status"]].reset_index(drop=True)


def _synthesize_issues_from_plan(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return _empty_frame(["Issue", "Priority", "Status"])

    working = plan.copy()
    status = working["Status"] if "Status" in working.columns else pd.Series("", index=working.index)
    schedule_health = (
        working["Schedule_Health"] if "Schedule_Health" in working.columns else pd.Series("", index=working.index)
    )
    on_hold = pd.to_numeric(working["On_Hold"], errors="coerce").fillna(0) if "On_Hold" in working.columns else 0

    open_mask = ~status.isin(["Completed", "Not Applicable"])
    issue_mask = open_mask & (
        status.isin(["Blocked", "On Hold"]) | (pd.Series(on_hold, index=working.index) > 0) | schedule_health.isin(["Red", "Yellow"])
    )
    subset = working.loc[issue_mask].copy()
    if subset.empty:
        return _empty_frame(["Issue", "Priority", "Status"])

    subset["Priority"] = "P3"
    subset.loc[subset.get("Schedule_Health", "").eq("Yellow"), "Priority"] = "P2"
    subset.loc[subset.get("Schedule_Health", "").eq("Red"), "Priority"] = "P1"
    if "Status" in subset.columns:
        subset.loc[subset["Status"].isin(["Blocked", "On Hold"]), "Priority"] = "P1"
    if "On_Hold" in subset.columns:
        subset.loc[pd.to_numeric(subset["On_Hold"], errors="coerce").fillna(0) > 0, "Priority"] = "P1"

    subset["Issue"] = subset["Task_Name"]
    subset["Status"] = "Open"
    return subset[["Issue", "Priority", "Status"]].reset_index(drop=True)


def _synthesize_resources_from_plan(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty or "Assigned_To" not in plan.columns:
        return _empty_frame(["Resource", "Utilization_%"])

    active = plan.loc[~plan["Status"].isin(["Completed", "Not Applicable"])].copy() if "Status" in plan.columns else plan
    loads: dict[str, int] = {}
    for cell in active["Assigned_To"].dropna():
        for part in str(cell).split(","):
            assignee = part.strip()
            if assignee:
                loads[assignee] = loads.get(assignee, 0) + 1

    if not loads:
        return _empty_frame(["Resource", "Utilization_%"])

    average_load = sum(loads.values()) / len(loads)
    records = []
    for assignee, count in sorted(loads.items()):
        utilization = min(120.0, 40.0 + (count / max(average_load, 1.0)) * 20.0)
        records.append({"Resource": assignee, "Utilization_%": round(utilization, 1)})
    return pd.DataFrame.from_records(records)


def load_workbook(path: str | Path) -> LoadedWorkbook:
    workbook_path = Path(path)
    sheets = pd.ExcelFile(workbook_path).sheet_names

    if _find_sheet(sheets, "Project_Summary"):
        return _load_s2p_portfolio(workbook_path)
    if _find_sheet(sheets, "Project_Plan", "Project Plan"):
        return _load_detailed_project_plan(workbook_path)

    summary_sheet = _find_sheet(sheets, "Summary")
    candidate_task_sheets = [sheet for sheet in sheets if sheet not in {summary_sheet, _find_sheet(sheets, "Comments")}]
    if candidate_task_sheets:
        preview = pd.read_excel(workbook_path, sheet_name=candidate_task_sheets[0], nrows=5)
        preview = _normalize_plan_columns(preview)
        required = {"Task_Name", "Status", "Start_Date", "Finish_Date"}
        if required.issubset(set(preview.columns)):
            return _load_detailed_project_plan(workbook_path)

    raise ValueError(
        f"Unsupported workbook layout for {workbook_path.name}. "
        "Expected either the S2P sample tabs or the Project Plan tabs."
    )


def _load_s2p_portfolio(workbook_path: Path) -> LoadedWorkbook:
    summary = pd.read_excel(workbook_path, sheet_name="Project_Summary")
    budget = pd.read_excel(workbook_path, sheet_name="Budget_Tracking")
    milestones = pd.read_excel(workbook_path, sheet_name="Milestones")
    risks = pd.read_excel(workbook_path, sheet_name="Risk_Register")
    issues = pd.read_excel(workbook_path, sheet_name="Issue_Log")
    resources = pd.read_excel(workbook_path, sheet_name="Resource_Allocation")
    feedback = pd.read_excel(workbook_path, sheet_name="Stakeholder_Feedback")
    weekly = pd.read_excel(workbook_path, sheet_name="Weekly_Status")

    milestones = _parse_dates(milestones, ["Planned_Date", "Actual_Date"])
    summary = _parse_dates(summary, ["Start_Date", "Planned_End_Date"])

    contexts: list[ProjectContext] = []
    for _, row in summary.iterrows():
        project_id = row["Project_ID"]
        project_name = row["Project_Name"]
        context = ProjectContext(
            workbook_name=workbook_path.name,
            workbook_path=workbook_path,
            plan_type="portfolio",
            project_id=project_id,
            project_name=project_name,
            summary=row.where(pd.notnull(row), None).to_dict(),
            existing_rag=_normalize_rag(row.get("RAG_Status")),
            datasets={
                "budget": budget.loc[budget["Project_ID"] == project_id].copy(),
                "milestones": milestones.loc[milestones["Project_ID"] == project_id].copy(),
                "risks": risks.loc[risks["Project_ID"] == project_id].copy(),
                "issues": issues.loc[issues["Project_ID"] == project_id].copy(),
                "resources": resources.loc[resources["Project_ID"] == project_id].copy(),
                "feedback": feedback.loc[feedback["Project_ID"] == project_id].copy(),
                "weekly": weekly.loc[weekly["Project_ID"] == project_id].copy(),
            },
        )
        contexts.append(context)

    return LoadedWorkbook(
        workbook_name=workbook_path.name,
        workbook_path=workbook_path,
        plan_type="portfolio",
        contexts=contexts,
    )


def _load_detailed_project_plan(workbook_path: Path) -> LoadedWorkbook:
    sheets = pd.ExcelFile(workbook_path).sheet_names
    plan_sheet = _find_sheet(sheets, "Project_Plan", "Project Plan")
    if not plan_sheet:
        ignored = {
            _find_sheet(sheets, "Summary"),
            _find_sheet(sheets, "Comments"),
        }
        candidates = [sheet for sheet in sheets if sheet not in ignored]
        plan_sheet = candidates[0] if candidates else None
    if not plan_sheet:
        raise ValueError(f"Could not locate a project-plan worksheet in {workbook_path.name}.")

    plan = _normalize_plan_columns(pd.read_excel(workbook_path, sheet_name=plan_sheet))
    dependencies = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Dependencies"))
    risks = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Risk_Register"))
    issues = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Issue_Log"))
    resources = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Resource_Plan"))
    changes = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Change_Requests"))
    weekly = _read_optional_sheet(workbook_path, _find_sheet(sheets, "Weekly_Progress"))
    summary_sheet = _find_sheet(sheets, "Summary")
    summary_map = _summary_key_value_map(_read_optional_sheet(workbook_path, summary_sheet))

    if risks.empty:
        risks = _synthesize_risks_from_plan(plan)
    if issues.empty:
        issues = _synthesize_issues_from_plan(plan)
    if resources.empty:
        resources = _synthesize_resources_from_plan(plan)
    if changes.empty:
        changes = _empty_frame(["Impact"])
    if weekly.empty and "% Complete" in summary_map:
        weekly = pd.DataFrame(
            [
                {
                    "Week": "Summary",
                    "Overall_Progress_%": _scale_percent(summary_map.get("% Complete")),
                    "Report_Date": summary_map.get("Today's Date"),
                }
            ]
        )

    plan = _parse_dates(plan, ["Start_Date", "Finish_Date"])
    weekly = _parse_dates(weekly, ["Report_Date"])

    project_name = None
    if "Task_Name" in plan.columns and not plan.empty:
        project_name = str(plan.iloc[0]["Task_Name"]).strip()
    if not project_name:
        project_name = workbook_path.stem.replace("_", " ")

    project_id = workbook_path.stem.upper().replace(" ", "_")
    weekly_progress = None
    if "Overall_Progress_%" in weekly.columns and not weekly.empty:
        weekly_progress = _scale_percent(weekly.iloc[-1]["Overall_Progress_%"])
    if weekly_progress is None:
        weekly_progress = _scale_percent(summary_map.get("% Complete"))

    context = ProjectContext(
        workbook_name=workbook_path.name,
        workbook_path=workbook_path,
        plan_type="detailed_plan",
        project_id=project_id,
        project_name=project_name,
        summary={
            "task_count": int(len(plan)),
            "start_date": plan["Start_Date"].min() if "Start_Date" in plan.columns else None,
            "finish_date": plan["Finish_Date"].max() if "Finish_Date" in plan.columns else None,
            "weekly_reported_progress": weekly_progress,
            "project_manager": summary_map.get("Project Manager"),
            "project_status": summary_map.get("Project Status"),
            "schedule_health": _normalize_rag(summary_map.get("Schedule Health")),
            "project_stage": summary_map.get("Project Stage"),
            "summary_percent_complete": _scale_percent(summary_map.get("% Complete")),
        },
        existing_rag=_normalize_rag(summary_map.get("Schedule Health")),
        datasets={
            "plan": plan,
            "dependencies": dependencies,
            "risks": risks,
            "issues": issues,
            "resources": resources,
            "changes": changes,
            "weekly": weekly,
        },
    )
    return LoadedWorkbook(
        workbook_name=workbook_path.name,
        workbook_path=workbook_path,
        plan_type="detailed_plan",
        contexts=[context],
    )


def frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return _clean_records(frame)
