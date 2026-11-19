import json

from experiments.resultsPlotter import generateAllCharts
from experiments.scenarioRunner import printScenarioSummary, runAllScenarios


report = runAllScenarios()
with open("allScenarioResults.json", "w", encoding="utf-8") as resultsFile:
    json.dump(report, resultsFile, indent=2)
printScenarioSummary(report)
chartPaths = generateAllCharts(report, "graphs")
print("\nResults saved to allScenarioResults.json")
print("Generated charts:")
for chartPath in chartPaths:
    print(f"  {chartPath}")
