# Import Path for handling file and folder paths
from pathlib import Path

# Import sys to access and modify Python's module search path
import sys


# Get the absolute path of the project's root directory
# (__file__ refers to this run.py file)
ROOT = Path(__file__).resolve().parent

# Define the path to the "src" folder
SRC = ROOT / "src"

# Check whether the src folder is already in Python's import path
# If not, add it so Python can import modules from src/
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Import the main() function from the CLI module
from project_health_agent.cli import main


# This block executes only when run.py is run directly
if __name__ == "__main__":
    # Execute the application's main() function
    # Exit the program using the returned exit code
    raise SystemExit(main())