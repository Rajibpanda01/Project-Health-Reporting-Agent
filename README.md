# Project Health Reporting Agent

This repository contains a complete submission for the Zycus AI Engineer Intern technical assignment. It analyzes project-plan workbooks, assigns a transparent Red/Amber/Green status, explains the result in plain English, and automatically produces both weekly health reports and a monthly executive PowerPoint.

## Deliverables

- `deliverables/RAG_Methodology.md`: one-page RAG framework and assumptions.
- `deliverables/monthly_executive_deck.pptx`: automatically generated 6-slide executive presentation.
- `outputs/weekly_reports/`: weekly outputs, JSON summaries, Markdown reports, and monthly synthesis data.

## Installation

1. Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Make sure the input workbooks are available in the project folder:

- `S2P_Project.xlsx`
- `Project_Plan_B.xlsx`

Note:

- In Codex Desktop, the PowerPoint generation step works with the bundled presentation runtime automatically.
- If you want to override the runtime manually, you can set `PROJECT_HEALTH_NODE_BIN` and `PROJECT_HEALTH_PRESENTATION_SETUP`.

## Run With Streamlit

Launch the browser app:

```bash
streamlit run streamlit_app.py
```

What the app supports:

- use the local `S2P_Project.xlsx` and `Project_Plan_B.xlsx` files
- or upload one or more `.xlsx` workbooks directly
- generate weekly reports and the monthly PowerPoint
- download the deck, JSON, CSV, and a ZIP of the full run

## How To Run

Run the full assignment flow, including the monthly PowerPoint:

```bash
python3 run.py \
  --inputs \
  "/Users/rajibpanda/Desktop/Project 9 july/S2P_Project.xlsx" \
  "/Users/rajibpanda/Desktop/Project 9 july/Project_Plan_B.xlsx" \
  --output-dir "/Users/rajibpanda/Desktop/Project 9 july/outputs/weekly_reports" \
  --deck-output "/Users/rajibpanda/Desktop/Project 9 july/deliverables/monthly_executive_deck.pptx" \
  --as-of-date 2026-07-07
```

Optional:

- To skip Phase 3 deck generation, add `--skip-deck`.

## What The Run Produces

After the command completes, these files are generated or refreshed:

- `outputs/weekly_reports/run_summary.json`
- `outputs/weekly_reports/monthly_synthesis_input.csv`
- `outputs/weekly_reports/monthly_deck_data.json`
- `outputs/weekly_reports/s2p_project/weekly_health_report.md`
- `outputs/weekly_reports/project_plan_b/weekly_health_report.md`
- `outputs/weekly_reports/<workbook>/project_reports/*.md`
- `deliverables/monthly_executive_deck.pptx`
- `deliverables/monthly_executive_deck.pptx.inspect.ndjson`

## Folder Structure

```text
.
|-- deliverables/
|   |-- RAG_Methodology.md
|   |-- monthly_executive_deck.pptx
|   `-- streamlit_runs/
|-- outputs/
|   |-- weekly_reports/
|       |-- run_summary.json
|       |-- monthly_synthesis_input.csv
|       |-- monthly_deck_data.json
|       |-- s2p_project/
|       `-- project_plan_b/
|   `-- streamlit_runs/
|-- src/
|   `-- project_health_agent/
|       |-- cli.py
|       |-- loaders.py
|       |-- models.py
|       |-- presentation.py
|       |-- monthly_deck_builder.mjs
|       |-- reporting.py
|       |-- scoring.py
|       `-- workflow.py
|-- run.py
|-- streamlit_app.py
|-- requirements.txt
|-- S2P_Project.xlsx
`-- Project_Plan_B.xlsx
```

## How The Solution Works

1. `loaders.py` reads each workbook and normalizes either the cleaned sample layout or the original exported project-plan layout into a project context.
2. `scoring.py` evaluates schedule, budget, milestone, blocker, sentiment, resource, execution, and change signals.
3. `reporting.py` writes workbook-level summaries and one plain-English report per project.
4. `workflow.py` runs the shared analysis pipeline, writes outputs, and optionally generates the deck.
5. `cli.py` exposes the workflow as a terminal command.
6. `presentation.py` prepares the presentation workspace and runs the deck builder.
7. `monthly_deck_builder.mjs` converts `monthly_deck_data.json` into `deliverables/monthly_executive_deck.pptx`.
8. `streamlit_app.py` wraps the same workflow in a browser UI for uploads, summaries, and downloads.

## Phase 3 Deck Structure

The generated PowerPoint contains 6 slides:

1. Executive Summary
2. Portfolio Health
3. Emerging Risks
4. Critical Projects
5. Recommendations
6. Next Month Outlook

## Output Snapshot From The Current Run

- Projects analyzed: `2`
- Green: `0`
- Amber: `0`
- Red: `2`
- Overall average score: `53.0/100`
- Validation accuracy against the embedded workbook health labels: `50%`

## Weekly Scheduling Bonus

You can run the weekly analysis on a schedule with cron:

```cron
0 8 * * MON cd /path/to/repo && /usr/bin/python3 run.py --inputs /path/to/S2P_Project.xlsx /path/to/Project_Plan_B.xlsx --output-dir /path/to/repo/outputs/weekly_reports --deck-output /path/to/repo/deliverables/monthly_executive_deck.pptx --as-of-date $(date +\%F)
```

## Tech Stack

- Python 3
- `pandas`
- `openpyxl`
- `streamlit`
- JavaScript ES modules
- `@oai/artifact-tool` for PowerPoint generation

## Key Design Choices

- The scoring logic does not blindly trust a workbook's existing RAG column; it uses that only as a validation signal.
- Missing or inconsistent data reduces confidence instead of breaking the run.
- The monthly deck is generated from synthesized JSON, which makes Phase 3 deterministic and repeatable.
