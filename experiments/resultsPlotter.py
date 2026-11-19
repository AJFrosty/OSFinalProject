import os
from statistics import mean


def policyRunResults(scenario, policyName):
    return [
        next(result for result in seedRun["results"] if result["policy"] == policyName)
        for seedRun in scenario["seedResults"]
    ]


def meanMetric(scenario, policyName, metricName):
    values = [result[metricName] for result in policyRunResults(scenario, policyName)]
    return mean(values) if values else 0.0


def newPlot():
    import matplotlib.pyplot as plot
    return plot


def generateAllCharts(report, outputDirectory="graphs"):
    plot = newPlot()
    os.makedirs(outputDirectory, exist_ok=True)
    scenarios = report["scenarios"]
    scenarioNames = [scenario["name"] for scenario in scenarios]
    policyNames = ("static", "list", "adaptive")
    chartPaths = []

    plot.figure(figsize=(14, 6))
    for policyName in policyNames:
        values = [meanMetric(scenario, policyName, "makespan") for scenario in scenarios]
        errors = [scenario["statistics"][policyName]["makespan"]["standardDeviation"] for scenario in scenarios]
        plot.errorbar(scenarioNames, values, yerr=errors, marker="o", capsize=3, label=policyName)
    plot.title("Makespan Comparison Across Scenarios")
    plot.ylabel("Makespan (time units)")
    plot.xticks(rotation=45, ha="right")
    plot.legend()
    plot.tight_layout()
    path = os.path.join(outputDirectory, "makespanComparison.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    plot.figure(figsize=(14, 6))
    for policyName in policyNames:
        values = [meanMetric(scenario, policyName, "totalEnergy") for scenario in scenarios]
        errors = [scenario["statistics"][policyName]["totalEnergy"]["standardDeviation"] for scenario in scenarios]
        plot.errorbar(scenarioNames, values, yerr=errors, marker="o", capsize=3, label=policyName)
    plot.title("Energy Impact Across Scenarios")
    plot.ylabel("Total device energy")
    plot.xticks(rotation=45, ha="right")
    plot.legend()
    plot.tight_layout()
    path = os.path.join(outputDirectory, "energyImpact.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    plot.figure(figsize=(14, 6))
    for policyName in policyNames:
        values = []
        for scenario in scenarios:
            runValues = []
            for result in policyRunResults(scenario, policyName):
                samples = result["queueOccupancySamples"]
                if samples:
                    runValues.append(mean(
                        sum(sample["queues"].values())
                        for sample in samples
                    ))
            values.append(mean(runValues) if runValues else 0.0)
        plot.plot(scenarioNames, values, marker="o", label=policyName)
    plot.title("Average Queue Occupancy Across Scenarios")
    plot.ylabel("Average queued and running tasks")
    plot.xticks(rotation=45, ha="right")
    plot.legend()
    plot.tight_layout()
    path = os.path.join(outputDirectory, "queueOccupancy.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    plot.figure(figsize=(9, 7))
    for policyName in policyNames:
        xValues = []
        yValues = []
        for scenario in scenarios:
            xValues.append(scenario["statistics"][policyName]["makespan"]["mean"])
            yValues.append(scenario["statistics"][policyName]["totalEnergy"]["mean"])
        plot.scatter(xValues, yValues, alpha=0.65, label=policyName)
    plot.title("Energy–Makespan Trade-off")
    plot.xlabel("Makespan (time units)")
    plot.ylabel("Total device energy")
    plot.legend(title="Policy")
    plot.tight_layout()
    path = os.path.join(outputDirectory, "energyMakespanTradeoff.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    plot.figure(figsize=(12, 7))
    timeAxis = None
    memoryAxis = plot.gca()
    cacheAxis = memoryAxis.twinx()
    for scenarioName, policyName in (("serviceCacheLRU", "static"), ("serviceCachePredictive", "static")):
        scenario = next(item for item in scenarios if item["name"] == scenarioName)
        result = policyRunResults(scenario, policyName)[0]
        edgeSamples = [sample for sample in result["memorySamples"] if sample["node"] == "EdgeServer"]
        edgeSamples.sort(key=lambda sample: sample["time"])
        if not edgeSamples:
            continue
        timeAxis = [sample["time"] for sample in edgeSamples]
        label = f"{scenarioName} edge memory"
        memoryAxis.plot(timeAxis, [sample["utilization"] * 100 for sample in edgeSamples], label=label)
        cacheAxis.plot(
            timeAxis,
            [sample["cacheHitRate"] * 100 for sample in edgeSamples],
            linestyle="--",
            label=f"{scenarioName} cache hit rate"
        )
    memoryAxis.set_title("Memory Utilization and Service Cache Hit Rate Over Time")
    memoryAxis.set_xlabel("Simulation time")
    memoryAxis.set_ylabel("Memory utilization (%)")
    cacheAxis.set_ylabel("Cumulative cache hit rate (%)")
    linesA, labelsA = memoryAxis.get_legend_handles_labels()
    linesB, labelsB = cacheAxis.get_legend_handles_labels()
    memoryAxis.legend(linesA + linesB, labelsA + labelsB, loc="best")
    plot.tight_layout()
    path = os.path.join(outputDirectory, "memoryAndCacheOverTime.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    computationValues = []
    transmissionValues = []
    radioValues = []
    for policyName in policyNames:
        runResults = [
            result
            for scenario in scenarios
            for result in policyRunResults(scenario, policyName)
        ]
        computationValues.append(mean(result["computationEnergy"] for result in runResults))
        transmissionValues.append(mean(result["transmissionEnergy"] for result in runResults))
        radioValues.append(mean(result["radioIdleEnergy"] for result in runResults))
    plot.figure(figsize=(9, 6))
    plot.bar(policyNames, computationValues, label="Computation")
    plot.bar(policyNames, transmissionValues, bottom=computationValues, label="Transmission")
    bottoms = [computationValues[index] + transmissionValues[index] for index in range(len(policyNames))]
    plot.bar(policyNames, radioValues, bottom=bottoms, label="Radio idle")
    plot.title("Mean Energy Breakdown Per Policy")
    plot.ylabel("Mean energy across scenarios and seeds")
    plot.legend()
    plot.tight_layout()
    path = os.path.join(outputDirectory, "energyBreakdown.png")
    plot.savefig(path, dpi=180)
    plot.close()
    chartPaths.append(path)

    return chartPaths
