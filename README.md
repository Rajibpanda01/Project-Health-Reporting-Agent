# Project Health Reporting Agent

An AI-powered Project Health Reporting Agent developed as part of the Zycus AI Engineer Intern technical assignment. The system analyzes project-plan workbooks, evaluates project health using a transparent RAG framework, generates plain-English explanations, produces weekly health reports, and automatically creates an executive PowerPoint presentation for leadership.



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




## Features

- Automated project health analysis
- RAG (Red/Amber/Green) status calculation
- Plain-English health explanations
- Weekly report generation (JSON, Markdown, CSV)
- Monthly executive PowerPoint generation
- Streamlit web interface
- Command Line Interface (CLI)
- Handles incomplete or missing project data gracefully




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




## How To Run In Terminal

Run the full assignment flow, including the monthly PowerPoint:

```bash
python3 run.py \
  --inputs S2P_Project.xlsx Project_Plan_B.xlsx \
  --output-dir outputs/weekly_reports \
  --deck-output deliverables/monthly_executive_deck.pptx
```


## What The Run Produces

After the command completes, these files are generated or refreshed:

- `outputs/weekly_reports/run_summary.json`
- `outputs/weekly_reports/monthly_synthesis_input.csv`
- `outputs/weekly_reports/monthly_deck_data.json`
- `outputs/weekly_reports/s2p_project/weekly_health_report.md`
- `outputs/weekly_reports/project_plan_b/weekly_health_report.md`
- `outputs/weekly_reports/<workbook>/project_reports/*.md`
- `deliverables/monthly_executive_deck.pptx`

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
6. `presentation.py` converts `monthly_deck_data.json` into `deliverables/monthly_executive_deck.pptx` with pure Python.
7. `streamlit_app.py` wraps the same workflow in a browser UI for uploads, summaries, and downloads.

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

## Architecture Diagram

                Excel Workbooks (.xlsx)
                        │
                        ▼
                loaders.py
                (Read & Validate Data)
                        │
                        ▼
                models.py
                (Project Context)
                        │
                        ▼
                scoring.py
                (RAG & Health Score)
                        │
                        ▼
                reporting.py
                (JSON / CSV / MD)
                        │
                        ▼
                monthly_deck_data.json
                        │
                        ▼
                presentation.py
                (python-pptx)
                        │
                        ▼
                monthly_executive_deck.pptx

## Tech Stack

Backend
- Python 3.13.5
- Pandas
- OpenPyXL

Frontend
- Streamlit

Reporting
- Markdown
- JSON
- CSV

Presentation
- python-pptx

Others
- argparse
- pathlib



## Key Design Choices

- The scoring logic does not blindly trust a workbook's existing RAG column; it uses that only as a validation signal.
- Missing or inconsistent data reduces confidence instead of breaking the run.
- The monthly deck is generated from synthesized JSON, which makes Phase 3 deterministic and repeatable.

## License

This project was developed solely for the Zycus AI Engineer Intern technical assignment and is intended for evaluation purposes.
