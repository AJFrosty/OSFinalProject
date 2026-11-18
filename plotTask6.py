from pathlib import Path
from experiments.resultsPlotter import createCharts


if __name__ == "__main__":
    createCharts(Path(__file__).resolve().parent / "results" / "task6")
