from pathlib import Path
from experiments.scenarioRunner import runExperiments


if __name__ == "__main__":
    runExperiments(Path(__file__).resolve().parent / "results" / "task6")
