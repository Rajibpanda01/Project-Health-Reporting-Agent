from __future__ import annotations

# Import argparse to read command-line arguments
import argparse

# Import date to handle today's date and date conversion
from datetime import date

# Import the main workflow function
from .workflow import run_analysis


# Function to define and parse command-line arguments
def parse_args() -> argparse.Namespace:

    # Create the argument parser
    parser = argparse.ArgumentParser(
        description="Project Health Reporting Agent"
    )

    # Input Excel workbook(s)
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="One or more workbook paths to analyze.",
    )

    # Folder where reports will be generated
    parser.add_argument(
        "--output-dir",
        default="outputs/weekly_reports",
        help="Directory where the generated reports should be written.",
    )

    # Report generation date
    parser.add_argument(
        "--as-of-date",
        default=date.today().isoformat(),
        help="As-of date for schedule and overdue checks (YYYY-MM-DD).",
    )

    # Output path for the monthly PowerPoint presentation
    parser.add_argument(
        "--deck-output",
        default="deliverables/monthly_executive_deck.pptx",
        help="Path for the monthly executive PowerPoint deck.",
    )

    # Skip PowerPoint generation if this option is used
    parser.add_argument(
        "--skip-deck",
        action="store_true",
        help="Generate reports only (skip PowerPoint deck).",
    )

    # Return all parsed arguments
    return parser.parse_args()


# Main function of the CLI
def main() -> int:

    # Read command-line arguments
    args = parse_args()

    # Execute the complete project health analysis workflow
    run_analysis(
        input_paths=args.inputs,
        output_dir=args.output_dir,
        as_of_date=date.fromisoformat(args.as_of_date),
        deck_output=args.deck_output,
        skip_deck=args.skip_deck,
    )

    # Return success status
    return 0