import json
from experiments.greenPolicyExperiment import printRequirement6Results, runRequirement6Experiment


report = runRequirement6Experiment()
printRequirement6Results(report)
with open("requirement6Results.json", "w", encoding="utf-8") as resultsFile:
    json.dump(report, resultsFile, indent=2)
print("\nResults saved to requirement6Results.json")
