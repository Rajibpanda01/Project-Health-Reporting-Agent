from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from project_health_agent.workflow import run_analysis


APP_RUNS_DIR = ROOT / "outputs" / "streamlit_runs"
APP_DELIVERABLES_DIR = ROOT / "deliverables"
DEFAULT_WORKBOOKS = [
    ROOT / "S2P_Project.xlsx",
    ROOT / "Project_Plan_B.xlsx",
]


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]


def _prepare_run_dirs(run_id: str) -> tuple[Path, Path, Path]:
    input_dir = APP_RUNS_DIR / run_id / "inputs"
    output_dir = APP_RUNS_DIR / run_id / "weekly_reports"
    deliverables_dir = APP_DELIVERABLES_DIR / "streamlit_runs" / run_id
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    deliverables_dir.mkdir(parents=True, exist_ok=True)
    return input_dir, output_dir, deliverables_dir


def _save_uploaded_files(uploaded_files, input_dir: Path) -> list[Path]:
    saved_paths: list[Path] = []
    for uploaded_file in uploaded_files:
        path = input_dir / uploaded_file.name
        path.write_bytes(uploaded_file.getbuffer())
        saved_paths.append(path)
    return saved_paths


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _zip_run_bytes(output_dir: Path, deliverables_dir: Path) -> bytes:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        for base_dir, prefix in [(output_dir, "outputs/weekly_reports"), (deliverables_dir, "deliverables")]:
            if not base_dir.exists():
                continue
            for file_path in base_dir.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, arcname=f"{prefix}/{file_path.relative_to(base_dir)}")
    memory.seek(0)
    return memory.getvalue()


def _display_run_outputs(result: dict) -> None:
    run_summary = _read_json(result["run_summary_path"])
    deck_data = _read_json(result["monthly_deck_data_path"])
    workbook_rows = pd.DataFrame(run_summary["workbooks"])
    critical_projects = pd.DataFrame(deck_data.get("critical_projects", []))

    rag_counts = run_summary["overall_rag_counts"]
    total_projects = run_summary["total_projects"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Projects", total_projects)
    col2.metric("Red", rag_counts.get("Red", 0))
    col3.metric("Amber", rag_counts.get("Amber", 0))
    col4.metric("Green", rag_counts.get("Green", 0))

    score_col, validation_col, confidence_col = st.columns(3)
    score_col.metric("Average Score", f'{deck_data["overall"]["average_score"]}/100')
    validation = deck_data["portfolio"].get("validation_accuracy")
    validation_col.metric("Validation Accuracy", "N/A" if validation is None else f"{round(validation * 100)}%")
    confidence_col.metric("Lead Drivers", ", ".join(deck_data["overall"].get("lead_driver_counts", {}).keys()) or "N/A")

    st.subheader("Portfolio Snapshot")
    st.dataframe(workbook_rows, use_container_width=True, hide_index=True)

    if not critical_projects.empty:
        st.subheader("Critical Projects")
        st.dataframe(critical_projects, use_container_width=True, hide_index=True)

    st.subheader("Downloads")
    output_dir = Path(result["output_dir"])
    deliverables_dir = Path(result["deck_output"]).parent if result.get("deck_output") else APP_DELIVERABLES_DIR

    st.download_button(
        "Download run summary JSON",
        data=Path(result["run_summary_path"]).read_bytes(),
        file_name="run_summary.json",
        mime="application/json",
    )
    st.download_button(
        "Download monthly synthesis CSV",
        data=Path(result["monthly_synthesis_input_path"]).read_bytes(),
        file_name="monthly_synthesis_input.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download monthly deck data JSON",
        data=Path(result["monthly_deck_data_path"]).read_bytes(),
        file_name="monthly_deck_data.json",
        mime="application/json",
    )
    if result.get("deck_output") and Path(result["deck_output"]).exists():
        st.download_button(
            "Download PowerPoint deck",
            data=Path(result["deck_output"]).read_bytes(),
            file_name=Path(result["deck_output"]).name,
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    st.download_button(
        "Download full run ZIP",
        data=_zip_run_bytes(output_dir, deliverables_dir),
        file_name="project_health_outputs.zip",
        mime="application/zip",
    )

    st.subheader("Workbook Reports")
    tabs = st.tabs([row["workbook_name"] for row in run_summary["workbooks"]])
    for tab, row in zip(tabs, run_summary["workbooks"], strict=False):
        with tab:
            weekly_report_path = Path(row["output_dir"]) / "weekly_health_report.md"
            st.markdown(_read_text(weekly_report_path))


def main() -> None:
    st.set_page_config(
        page_title="Project Health Reporting Agent",
        page_icon="📊",
        layout="wide",
    )
    st.title("Project Health Reporting Agent")
    st.caption("Upload project-plan workbooks or use the local Excel files to generate weekly reports and a monthly executive deck.")

    with st.sidebar:
        st.header("Run Options")
        as_of_date = st.date_input("As-of date", value=date.today())
        generate_deck = st.checkbox("Generate monthly PowerPoint deck", value=True)
        source_mode = st.radio(
            "Workbook source",
            options=["Use local project files", "Upload Excel files"],
            index=0,
        )
        uploaded_files = []
        if source_mode == "Upload Excel files":
            uploaded_files = st.file_uploader(
                "Upload one or more .xlsx files",
                type=["xlsx"],
                accept_multiple_files=True,
            )
        run_clicked = st.button("Run analysis", type="primary", use_container_width=True)

    st.markdown(
        f"Local default files: `{DEFAULT_WORKBOOKS[0].name}` and `{DEFAULT_WORKBOOKS[1].name}`"
    )

    if run_clicked:
        if source_mode == "Upload Excel files" and not uploaded_files:
            st.error("Upload at least one Excel workbook to continue.")
            return

        run_id = _run_id()
        input_dir, output_dir, deliverables_dir = _prepare_run_dirs(run_id)

        if source_mode == "Upload Excel files":
            input_paths = _save_uploaded_files(uploaded_files, input_dir)
        else:
            missing = [path.name for path in DEFAULT_WORKBOOKS if not path.exists()]
            if missing:
                st.error(f"Missing local workbook(s): {', '.join(missing)}")
                return
            input_paths = DEFAULT_WORKBOOKS

        deck_output = deliverables_dir / "monthly_executive_deck.pptx"

        with st.spinner("Analyzing workbooks and generating outputs..."):
            result = run_analysis(
                input_paths=input_paths,
                output_dir=output_dir,
                as_of_date=as_of_date,
                deck_output=deck_output,
                skip_deck=not generate_deck,
            )
        st.session_state["last_run_result"] = result.to_dict()
        st.success("Analysis completed.")

    last_run_result = st.session_state.get("last_run_result")
    if last_run_result:
        _display_run_outputs(last_run_result)
    else:
        st.info("Choose your workbook source from the sidebar, then click Run analysis.")


if __name__ == "__main__":
    main()
