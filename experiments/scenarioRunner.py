import csv
import json
import random
import statistics
import platform
from pathlib import Path

from experiments.policyMetrics import MeasuredPolicy, policyMemoryBytes
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.aiPolicy import AdaptiveGreenPolicy
from scheduling.offloadStrategy import ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler


testSeeds = [1, 2, 3, 4, 5]
tuningSeeds = [101, 102, 103, 104, 105]
coreScenarios = [
    {"name": "HighEnergy", "energy": 1000, "bandwidth": 10, "workload": "mixed"},
    {"name": "LowEnergy", "energy": 100, "bandwidth": 10, "workload": "mixed"},
    {"name": "FastWireless", "energy": 500, "bandwidth": 20, "workload": "mixed"},
    {"name": "SlowWireless", "energy": 500, "bandwidth": 2, "workload": "mixed"},
    {"name": "LargeTasks", "energy": 500, "bandwidth": 10, "workload": "large"},
    {"name": "SmallTasks", "energy": 500, "bandwidth": 10, "workload": "small"},
]


def makeTasks(seed, workload, count=40):
    generator = random.Random(seed)
    tasks = []
    for index in range(count):
        if workload == "small":
            size = generator.randint(5, 25)
        elif workload == "large":
            size = generator.randint(60, 120)
        else:
            size = generator.randint(5, 120)
        dataSize = round(size * generator.uniform(0.2, 1.0), 2)
        priority = generator.randint(1, 3)
        tasks.append(Task(f"T{index + 1}", size, priority, dataSize))
    return tasks


def makeSystem(scenario, policy):
    device = Device(energyCapacity=scenario["energy"])
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0,
                  wirelessBandwidth=scenario["bandwidth"])
    cloud = Server("CloudServer", 5.0, wirelessDelay=5.0, wiredDelay=10.0,
                   wirelessBandwidth=scenario["bandwidth"])
    measured = MeasuredPolicy(policy)
    return Scheduler(device, [edge, cloud], measured)


def finishBatch(scheduler):
    nodes = [scheduler.device] + scheduler.servers
    running = {}
    completed = []
    queueHistory = []
    now = scheduler.currentTime
    while True:
        for node in nodes:
            if node.name in running:
                task, start, finish = running[node.name]
                if finish <= now:
                    task.status = "completed"
                    completed.append({
                        "taskId": task.id, "server": node.name,
                        "size": task.size, "dataSize": task.dataSize,
                        "priority": task.priority,
                        "readyTime": task.transferCompletionTime,
                        "startTime": start, "finishTime": finish,
                        "queueWait": start - task.transferCompletionTime,
                        "arrivalToStart": start,
                    })
                    del running[node.name]
            if node.name not in running:
                task = scheduler.dispatchTask(node.name, now)
                if task is not None:
                    finish = now + task.size / node.computeSpeed
                    running[node.name] = (task, now, finish)

        for node in nodes:
            queueHistory.append({"time": now, "server": node.name,
                                 "queueLength": node.queueLength()})
        if not running and all(node.queueLength() == 0 for node in nodes):
            break
        nextTimes = [entry[2] for entry in running.values()]
        for node in nodes:
            if node.name not in running:
                nextTimes.extend(task.transferCompletionTime for task in node.getQueueTasks()
                                 if task.transferCompletionTime > now)
        if not nextTimes:
            raise RuntimeError("Queued tasks cannot make progress")
        now = min(nextTimes)
    return completed, queueHistory


def runSimulation(scenario, seed, policy, taskCount=40):
    if taskCount <= 0:
        raise ValueError("Task count must be greater than zero")
    scheduler = makeSystem(scenario, policy)
    tasks = makeTasks(seed, scenario["workload"], taskCount)
    for task in tasks:
        scheduler.submitTask(task, 0.0)
    completed, queueHistory = finishBatch(scheduler)
    energy = scheduler.device.energyCapacity - scheduler.device.remainingEnergy
    localCount = sum(task.location == scheduler.device.name for task in tasks)
    metrics = {
        "makespan": max((row["finishTime"] for row in completed), default=0.0),
        "meanCompletionTime": statistics.mean(row["finishTime"] for row in completed),
        "computationEnergy": energy,
        "localPercent": 100.0 * localCount / taskCount,
        "offloadedPercent": 100.0 * (taskCount - localCount) / taskCount,
        "decisionMicroseconds": statistics.mean(scheduler.strategy.decisionTimes),
        "policyMemoryBytes": policyMemoryBytes(policy),
        "tasksPerComputationEnergy": taskCount / energy if energy > 0 else None,
        "inputTransferMB": sum(task.dataSize for task in tasks if task.location != scheduler.device.name),
        "completedTasks": len(completed),
    }
    for name in ["LocalDevice", "EdgeServer", "CloudServer"]:
        waits = [row["queueWait"] for row in completed if row["server"] == name]
        metrics[name + "MeanQueueWait"] = statistics.mean(waits) if waits else None
    for row, microseconds in zip(tasks, scheduler.strategy.decisionTimes):
        for record in completed:
            if record["taskId"] == row.id:
                record["decisionMicroseconds"] = microseconds
                break
    return metrics, completed, queueHistory


def writeCsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tunePolicy():
    candidates = [0.20, 0.35, 0.50]
    scores = {weight: [] for weight in candidates}
    for scenario in coreScenarios:
        for seed in tuningSeeds:
            baseline, _, _ = runSimulation(scenario, seed, ListSchedulingHeuristic(), 24)
            allLocalEnergy = sum(task.size * 0.5 for task in makeTasks(seed, scenario["workload"], 24))
            for weight in candidates:
                result, _, _ = runSimulation(scenario, seed, AdaptiveGreenPolicy(weight), 24)
                objective = (0.5 * result["makespan"] / baseline["makespan"]
                             + 0.5 * result["computationEnergy"] / allLocalEnergy)
                scores[weight].append(objective)
    results = [{"baseEnergyWeight": weight,
                "meanTuningObjective": statistics.mean(scores[weight]),
                "stdTuningObjective": statistics.stdev(scores[weight])}
               for weight in candidates]
    best = min(results, key=lambda row: row["meanTuningObjective"])
    return best["baseEnergyWeight"], results


def summarizeRuns(runs):
    rows = []
    metricNames = list(runs[0])[3:]
    for scenario in coreScenarios:
        for policyName in ["Static", "List", "Adaptive"]:
            group = [row for row in runs if row["scenario"] == scenario["name"]
                     and row["policy"] == policyName]
            for metric in metricNames:
                values = [row[metric] for row in group if row[metric] is not None]
                rows.append({"scenario": scenario["name"], "policy": policyName,
                             "metric": metric, "validSeeds": len(values),
                             "mean": statistics.mean(values) if values else None,
                             "std": statistics.stdev(values) if len(values) > 1 else None})
    return rows


def runExperiments(outputDirectory):
    outputDirectory = Path(outputDirectory)
    outputDirectory.mkdir(parents=True, exist_ok=True)
    chosenWeight, tuningResults = tunePolicy()
    writeCsv(outputDirectory / "tuning.csv", tuningResults)
    settings = {"baseEnergyWeight": chosenWeight, "tuningSeeds": tuningSeeds,
                "testSeeds": testSeeds, "tuningTaskCount": 24, "testTaskCount": 40,
                "scenarios": coreScenarios, "pythonVersion": platform.python_version(),
                "platform": platform.platform(), "baseCommit": "6ffa8e0",
                "lowBatteryLevel": 0.30, "fastWirelessSpeed": 10.0,
                "batteryAdjustment": 0.25, "networkAdjustment": 0.15,
                "tuningObjective": "0.5 * makespan / listMakespan + 0.5 * CPUenergy / allLocalEnergy",
                "energyScope": "Local CPU only; transmission and radio await Task 8"}
    (outputDirectory / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    runs, taskRows, queueRows = [], [], []
    for scenario in coreScenarios:
        for seed in testSeeds:
            policies = [("Static", StaticRule()), ("List", ListSchedulingHeuristic()),
                        ("Adaptive", AdaptiveGreenPolicy(chosenWeight))]
            # Rotate execution order to reduce a fixed timing-order advantage.
            offset = seed % len(policies)
            policies = policies[offset:] + policies[:offset]
            for policyName, policy in policies:
                metrics, completed, history = runSimulation(scenario, seed, policy)
                label = {"scenario": scenario["name"], "policy": policyName, "seed": seed}
                runs.append(dict(label, **metrics))
                taskRows.extend(dict(label, **row) for row in completed)
                queueRows.extend(dict(label, **row) for row in history)
    summary = summarizeRuns(runs)
    writeCsv(outputDirectory / "runs.csv", runs)
    writeCsv(outputDirectory / "summary.csv", summary)
    writeCsv(outputDirectory / "tasks.csv", taskRows)
    writeCsv(outputDirectory / "queues.csv", queueRows)
    print(f"Tuned base energy weight: {chosenWeight:.2f}")
    print(f"Completed {len(runs)} test runs; results saved in {outputDirectory}")
    for row in summary:
        if row["metric"] == "makespan":
            print(f"{row['scenario']:14} {row['policy']:8} makespan {row['mean']:.2f} +/- {row['std']:.2f}")
    return summary
