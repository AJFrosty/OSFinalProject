from statistics import mean, stdev

from experiments.greenPolicyExperiment import (
    createWorkload,
    getPolicyStatistics,
    runWorkload,
    tuneAdaptivePolicy
)


def getScenarios():
    return [
        {"name": "energyHigh", "profile": "testing", "settings": {"energyCapacity": 600.0}},
        {"name": "energyLow", "profile": "testing", "settings": {"energyCapacity": 120.0}},
        {"name": "wirelessFast", "profile": "testing", "settings": {"wirelessBandwidth": 24.0, "cloudWirelessBandwidth": 24.0}},
        {"name": "wirelessSlow", "profile": "testing", "settings": {"wirelessBandwidth": 3.0, "cloudWirelessBandwidth": 3.0}},
        {"name": "manyLargeTasks", "profile": "large", "settings": {}},
        {"name": "manySmallTasks", "profile": "small", "settings": {}},
        {"name": "edgeMemoryAmple", "profile": "testing", "settings": {"edgeMemoryCapacity": 512.0}},
        {"name": "edgeMemoryConstrained", "profile": "testing", "settings": {"edgeMemoryCapacity": 64.0}},
        {"name": "serviceCacheLRU", "profile": "cache", "settings": {"cachePolicy": "LRU", "edgeMemoryCapacity": 1024.0}},
        {"name": "serviceCachePredictive", "profile": "cache", "settings": {"cachePolicy": "PREDICTIVE", "edgeMemoryCapacity": 1024.0}},
        {"name": "radioFixed", "profile": "testing", "settings": {"radioPolicy": "fixed"}},
        {"name": "radioPredictive", "profile": "testing", "settings": {"radioPolicy": "predictive"}},
        {"name": "bandwidthStable", "profile": "testing", "settings": {"bandwidthVariation": 0.0}},
        {"name": "bandwidthFluctuating", "profile": "testing", "settings": {"bandwidthVariation": 0.25}}
    ]


def summarizeScenario(seedResults):
    policyNames = ("static", "list", "adaptive")
    metricNames = (
        "makespan", "totalEnergy", "completedTasks", "rejectedTasks",
        "memoryRejectedTasks", "peakMemoryUtilization", "averageMemoryUtilization",
        "serviceCacheHitRate", "migrationDataVolumeMb", "memoryAdmissionRejections"
    )
    summary = {}
    for policyName in policyNames:
        policyResults = [
            next(result for result in seedRun["results"] if result["policy"] == policyName)
            for seedRun in seedResults
        ]
        summary[policyName] = {}
        for metricName in metricNames:
            values = [result[metricName] for result in policyResults]
            summary[policyName][metricName] = {
                "mean": mean(values),
                "standardDeviation": stdev(values) if len(values) > 1 else 0.0
            }
    return summary


def runAllScenarios(trainingSeed=41, testSeeds=None, taskCount=24):
    if testSeeds is None:
        testSeeds = [97, 107, 117, 127, 137]
    if len(testSeeds) < 5:
        raise ValueError("At least five testing seeds are required")
    if trainingSeed in testSeeds:
        raise ValueError("Training seed must differ from testing seeds")

    trainingWorkload = createWorkload(trainingSeed, taskCount, "training")
    tuning = tuneAdaptivePolicy(trainingWorkload, randomSeed=trainingSeed)
    allResults = []

    for scenario in getScenarios():
        seedResults = []
        for testSeed in testSeeds:
            workload = createWorkload(testSeed, taskCount, scenario["profile"])
            results = [
                runWorkload(workload, "static", randomSeed=testSeed, scenarioConfig=scenario["settings"]),
                runWorkload(workload, "list", randomSeed=testSeed, scenarioConfig=scenario["settings"]),
                runWorkload(
                    workload,
                    "adaptive",
                    tuning["settings"],
                    randomSeed=testSeed,
                    scenarioConfig=scenario["settings"]
                )
            ]
            seedResults.append({"seed": testSeed, "results": results})

        allResults.append({
            "name": scenario["name"],
            "profile": scenario["profile"],
            "settings": scenario["settings"],
            "seedResults": seedResults,
            "statistics": summarizeScenario(seedResults)
        })

    return {
        "trainingSeed": trainingSeed,
        "testingSeeds": list(testSeeds),
        "taskCount": taskCount,
        "tuningTrialCount": len(tuning["trials"]),
        "tunedSettings": tuning["settings"],
        "scenarios": allResults
    }


def printScenarioSummary(report):
    print("COMP3320 Distributed Edge Scheduling Experiments")
    print(f"Scenarios: {len(report['scenarios'])} | Testing seeds: {report['testingSeeds']}")
    print("Each scenario runs static, list and adaptive policies over every seed.")
    for scenario in report["scenarios"]:
        print(f"\n{scenario['name']}")
        for policyName, metrics in scenario["statistics"].items():
            makespan = metrics["makespan"]
            energy = metrics["totalEnergy"]
            completed = metrics["completedTasks"]
            print(
                f"  {policyName:>8} | makespan {makespan['mean']:.2f} +/- "
                f"{makespan['standardDeviation']:.2f} | energy {energy['mean']:.2f} +/- "
                f"{energy['standardDeviation']:.2f} | completed {completed['mean']:.1f}"
            )
