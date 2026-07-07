from __future__ import annotations

import argparse
from datetime import date

from .workflow import run_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project health reporting agent")
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="One or more workbook paths to analyze.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/weekly_reports",
        help="Directory where the generated reports should be written.",
    )
    parser.add_argument(
        "--as-of-date",
        default=date.today().isoformat(),
        help="As-of date for schedule and overdue checks, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--deck-output",
        default="deliverables/monthly_executive_deck.pptx",
        help="Path for the monthly executive PowerPoint deck.",
    )
    parser.add_argument(
        "--skip-deck",
        action="store_true",
        help="Skip PowerPoint generation and write only the JSON and CSV monthly synthesis outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_analysis(
        input_paths=args.inputs,
        output_dir=args.output_dir,
        as_of_date=date.fromisoformat(args.as_of_date),
        deck_output=args.deck_output,
        skip_deck=args.skip_deck,
    )
    return 0
