import csv
from bisect import bisect_right as bisectRight
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


policyNames = ["Static", "List", "Adaptive"]
colors = ["#8B93A6", "#276CB5", "#16856B"]
scenarioNames = ["HighEnergy", "LowEnergy", "FastWireless", "SlowWireless", "LargeTasks", "SmallTasks"]
scenarioLabels = ["High\nenergy", "Low\nenergy", "Fast\nwireless", "Slow\nwireless", "Large\ntasks", "Small\ntasks"]


def readCsv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def findMetric(summary, scenario, policy, metric):
    return next(row for row in summary if row["scenario"] == scenario
                and row["policy"] == policy and row["metric"] == metric)


def saveFigure(figure, directory, name):
    figure.savefig(directory / (name + ".png"), dpi=170, bbox_inches="tight")
    figure.savefig(directory / (name + ".svg"), bbox_inches="tight")
    plt.close(figure)


def comparisonChart(summary, directory, metric, title, label, filename):
    figure, axis = plt.subplots(figsize=(11, 5))
    for index, policy in enumerate(policyNames):
        values = [findMetric(summary, scenario, policy, metric) for scenario in scenarioNames]
        positions = [position + (index - 1) * 0.25 for position in range(6)]
        axis.bar(positions, [float(row["mean"]) for row in values], width=0.24,
                 yerr=[float(row["std"]) for row in values], capsize=3,
                 color=colors[index], label=policy)
    axis.set_xticks(range(6), scenarioLabels)
    axis.set_ylabel(label)
    axis.set_title(title + "\nMean and sample standard deviation across 5 seeds", loc="left")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)
    axis.set_axisbelow(True)
    figure.tight_layout()
    saveFigure(figure, directory, filename)


def tradeoffChart(summary, directory):
    figure, axis = plt.subplots(figsize=(10, 6))
    markers = ["o", "s", "^", "v", "D", "P"]
    for index, policy in enumerate(policyNames):
        for number, scenario in enumerate(scenarioNames):
            time = findMetric(summary, scenario, policy, "makespan")
            energy = findMetric(summary, scenario, policy, "computationEnergy")
            axis.errorbar(float(time["mean"]), float(energy["mean"]),
                          xerr=float(time["std"]), yerr=float(energy["std"]),
                          marker=markers[number], color=colors[index], capsize=2,
                          markersize=7, linestyle="none", alpha=0.85)
    for index, policy in enumerate(policyNames):
        axis.plot([], [], color=colors[index], label=policy, linewidth=3)
    for number, scenario in enumerate(scenarioNames):
        axis.plot([], [], color="#333333", marker=markers[number], linestyle="none", label=scenario)
    axis.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    axis.set_xlabel("Makespan (simulation time units)")
    axis.set_ylabel("Local CPU energy (model units)")
    axis.set_title("Energy and makespan trade-off\nOne mean point per policy and scenario; error bars show sample SD", loc="left")
    axis.grid(alpha=0.2)
    figure.tight_layout()
    saveFigure(figure, directory, "energyMakespan")


def queueChart(queueRows, directory):
    nodes = ["LocalDevice", "EdgeServer", "CloudServer"]
    nodeColors = ["#7452A1", "#C57929", "#217D95"]
    groups = {}
    for row in queueRows:
        key = (row["scenario"], row["policy"], int(row["seed"]), row["server"])
        groups.setdefault(key, []).append((float(row["time"]), int(row["queueLength"])))
    figure, axes = plt.subplots(6, 3, figsize=(14, 18), sharey=True)
    queueLimit = max(int(row["queueLength"]) for row in queueRows) + 2
    for number, scenario in enumerate(scenarioNames):
        endTime = max(float(row["time"]) for row in queueRows if row["scenario"] == scenario)
        times = [endTime * index / 160 for index in range(161)]
        for index, policy in enumerate(policyNames):
            axis = axes[number][index]
            for nodeIndex, node in enumerate(nodes):
                samples = []
                for seed in range(1, 6):
                    trace = groups[(scenario, policy, seed, node)]
                    eventTimes = [entry[0] for entry in trace]
                    samples.append([trace[bisectRight(eventTimes, time) - 1][1] for time in times])
                means = [statistics.mean(values) for values in zip(*samples)]
                deviations = [statistics.stdev(values) for values in zip(*samples)]
                axis.step(times, means, where="post", color=nodeColors[nodeIndex], label=node)
                axis.fill_between(times, [max(0, value - spread) for value, spread in zip(means, deviations)],
                                  [value + spread for value, spread in zip(means, deviations)],
                                  step="post", color=nodeColors[nodeIndex], alpha=0.10)
            axis.set_title(scenario + " / " + policy, fontsize=10)
            axis.grid(alpha=0.15)
            axis.set_ylim(0, queueLimit)
            if index == 0:
                axis.set_ylabel("Queued tasks")
            if number == 5:
                axis.set_xlabel("Simulation time units")
    handles, labels = axes[0][0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.965), frameon=False)
    figure.suptitle("Queue occupancy over time\nMean across 5 seeds; shading is sample SD. Includes uploads waiting at each node; excludes running tasks.", y=0.995, fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    saveFigure(figure, directory, "queueOccupancy")


def createCharts(resultsDirectory):
    resultsDirectory = Path(resultsDirectory)
    directory = resultsDirectory / "charts"
    directory.mkdir(parents=True, exist_ok=True)
    summary = readCsv(resultsDirectory / "summary.csv")
    comparisonChart(summary, directory, "makespan", "Makespan comparison",
                    "Simulation time units", "makespan")
    comparisonChart(summary, directory, "computationEnergy", "Energy impact: local CPU only",
                    "Computation energy (model units)", "energyImpact")
    comparisonChart(summary, directory, "decisionMicroseconds", "Scheduler decision overhead",
                    "Microseconds per task (host measurement)", "decisionOverhead")
    tradeoffChart(summary, directory)
    queueChart(readCsv(resultsDirectory / "queues.csv"), directory)
    print(f"Saved five charts as PNG and SVG in {directory}")
