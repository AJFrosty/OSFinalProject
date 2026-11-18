import random
from statistics import mean, stdev
from itertools import product

from ioMgmt.networkInterface import NetworkInterface
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.adaptiveGreenPolicy import AdaptiveGreenPolicy
from scheduling.offloadStrategy import ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler


def createWorkload(seed, taskCount=24, profile="training"):
    generator = random.Random(seed)
    tasks = []
    for index in range(taskCount):
        if profile == "training":
            size = generator.randint(12, 90)
            dataSize = generator.randint(4, 24)
        elif profile == "testing":
            size = generator.randint(18, 115)
            dataSize = generator.randint(2, 34)
        else:
            raise ValueError("Workload profile must be training or testing")
        tasks.append({
            "id": f"{profile.title()}Task{index + 1}",
            "size": float(size),
            "priority": generator.randint(1, 4),
            "dataSize": float(dataSize)
        })
    return tasks


def createTasks(taskSpecs):
    return [
        Task(spec["id"], spec["size"], spec["priority"], dataSize=spec["dataSize"])
        for spec in taskSpecs
    ]


def createSystem(strategy, randomSeed=1):
    device = Device("LocalDevice", computeSpeed=1.0, energyCapacity=360.0, energyPerWorkUnit=0.45)
    edge = Server("EdgeServer", computeSpeed=3.0, wirelessDelay=2.0,
                  wirelessBandwidth=12.0)
    cloud = Server("CloudServer", computeSpeed=5.0, wirelessDelay=2.0,
                   wiredDelay=3.0, wirelessBandwidth=10.0, wiredBandwidth=100.0)
    network = NetworkInterface(
        policy="FCFS",
        radioPolicy="fixed",
        idleTimeout=8.0,
        wakeDelay=0.5,
        wakeEnergy=0.25,
        txPower=0.35,
        idlePower=0.02,
        bandwidthVariation=0.08,
        randomSeed=randomSeed,
        device=device
    )
    scheduler = Scheduler(device, [edge, cloud], strategy, networkInterface=network)
    return device, [edge, cloud], network, scheduler


def runWorkload(taskSpecs, policyName, policySettings=None, randomSeed=1):
    settings = policySettings or {}
    if policyName == "static":
        strategy = StaticRule(largeTaskThreshold=50.0)
    elif policyName == "list":
        strategy = ListSchedulingHeuristic()
    elif policyName == "adaptive":
        strategy = AdaptiveGreenPolicy(**settings)
    else:
        raise ValueError("Policy must be static, list or adaptive")

    device, servers, network, scheduler = createSystem(strategy, randomSeed)
    tasks = createTasks(taskSpecs)
    assignments = {}
    for task in tasks:
        server = scheduler.submitTask(task, currentTime=0.0)
        assignments[task.id] = server.name

    allServers = [device] + servers
    serverAvailable = {server.name: 0.0 for server in allServers}
    taskStartTimes = {}
    taskCompletionTimes = {}
    eventCount = 0
    maximumEvents = max(1000, len(tasks) * 100)

    while any(server.queueLength() for server in allServers) or network.activeTransfer is not None or network.uploadQueue:
        eventTimes = []
        if network.activeTransfer is not None:
            eventTimes.append(network.activeWirelessEnd)
        for server in allServers:
            readyTimes = [
                task.transferCompletionTime
                for task in server.getQueueTasks()
                if task.status != "uploadQueued" and task.transferCompletionTime < float("inf")
            ]
            if readyTimes:
                eventTimes.append(max(serverAvailable[server.name], min(readyTimes)))
        if not eventTimes:
            raise RuntimeError("Simulation stalled with tasks still queued")

        currentTime = max(scheduler.currentTime, min(eventTimes))
        scheduler.updateTime(currentTime)
        dispatched = False
        for server in allServers:
            if serverAvailable[server.name] > currentTime:
                continue
            task = scheduler.dispatchTask(server.name, currentTime=currentTime)
            if task is None:
                continue
            startTime = currentTime
            completionTime = startTime + task.size / server.computeSpeed
            serverAvailable[server.name] = completionTime
            taskStartTimes[task.id] = startTime
            taskCompletionTimes[task.id] = completionTime
            dispatched = True

        eventCount += 1
        if eventCount > maximumEvents:
            raise RuntimeError("Simulation exceeded the event limit")
        if not dispatched and not eventTimes:
            raise RuntimeError("Simulation could not advance")

    makespan = max(taskCompletionTimes.values(), default=0.0)
    scheduler.updateTime(max(scheduler.currentTime, makespan))
    completedIds = set(taskCompletionTimes)
    rejectedIds = [task.id for task in tasks if task.status == "energyRejected"]
    completedCount = len(completedIds)
    totalEnergy = (
        device.computationEnergy
        + network.transmissionEnergy
        + network.radioIdleEnergy
        + network.wakeEnergyConsumed
    )
    totalWork = sum(spec["size"] for spec in taskSpecs)
    fastestSpeed = max(server.computeSpeed for server in allServers)
    timeScale = max(1.0, totalWork / fastestSpeed)
    energyScale = max(1.0, device.energyCapacity)
    objective = 0.5 * (makespan / timeScale) + 0.5 * (totalEnergy / energyScale)
    overhead = strategy.getOverheadSummary() if isinstance(strategy, AdaptiveGreenPolicy) else {}

    return {
        "policy": policyName,
        "makespan": makespan,
        "totalEnergy": totalEnergy,
        "computationEnergy": device.computationEnergy,
        "transmissionEnergy": network.transmissionEnergy,
        "radioIdleEnergy": network.radioIdleEnergy,
        "wakeEnergy": network.wakeEnergyConsumed,
        "completedTasks": completedCount,
        "rejectedTasks": len(rejectedIds),
        "rejectedTaskIds": rejectedIds,
        "offloadedTasks": sum(1 for name in assignments.values() if name != device.name),
        "localTasks": sum(1 for name in assignments.values() if name == device.name),
        "averageQueueWaitingTime": (
            sum(taskStartTimes.values()) / len(taskStartTimes) if taskStartTimes else 0.0
        ),
        "energyEfficiency": completedCount / totalEnergy if totalEnergy > 0 else 0.0,
        "objective": objective,
        "assignments": assignments,
        "decisionOverhead": overhead
    }


def tuneAdaptivePolicy(trainingWorkload, randomSeed=1):
    if not trainingWorkload:
        raise ValueError("Training workload cannot be empty")
    parameterOptions = product(
        (0.4, 0.5, 0.6, 0.7),
        (0.3, 0.5, 0.7),
        (0.15, 0.3)
    )
    bestSettings = None
    bestObjective = float("inf")
    trials = []
    for baseTimeWeight, batterySensitivity, networkSensitivity in parameterOptions:
        settings = {
            "baseTimeWeight": baseTimeWeight,
            "baseEnergyWeight": 1.0 - baseTimeWeight,
            "batterySensitivity": batterySensitivity,
            "networkSensitivity": networkSensitivity,
            "networkEnergySensitivity": 0.2,
            "referenceBandwidth": 12.0
        }
        result = runWorkload(trainingWorkload, "adaptive", settings, randomSeed)
        trial = {
            "settings": dict(settings),
            "objective": result["objective"],
            "makespan": result["makespan"],
            "totalEnergy": result["totalEnergy"]
        }
        trials.append(trial)
        if trial["objective"] < bestObjective:
            bestObjective = trial["objective"]
            bestSettings = dict(settings)
    return {"settings": bestSettings, "objective": bestObjective, "trials": trials}


def getPolicyStatistics(seedResults):
    metricNames = (
        "makespan",
        "totalEnergy",
        "completedTasks",
        "rejectedTasks",
        "objective",
        "averageDecisionTimeNs",
        "policyMemoryBytes"
    )
    policyNames = ("static", "list", "adaptive")
    summary = {}
    for policyName in policyNames:
        policyRuns = [
            next(result for result in seedRun["results"] if result["policy"] == policyName)
            for seedRun in seedResults
        ]
        summary[policyName] = {}
        for metricName in metricNames:
            values = []
            for result in policyRuns:
                if metricName in result:
                    values.append(result[metricName])
                elif metricName == "averageDecisionTimeNs":
                    values.append(result["decisionOverhead"].get(metricName, 0.0))
                elif metricName == "policyMemoryBytes":
                    values.append(result["decisionOverhead"].get(metricName, 0.0))
            if values:
                summary[policyName][metricName] = {
                    "mean": mean(values),
                    "standardDeviation": stdev(values) if len(values) > 1 else 0.0
                }
    return summary


def runRequirement6Experiment(trainingSeed=41, testingSeed=97, taskCount=24, testSeeds=None):
    trainingWorkload = createWorkload(trainingSeed, taskCount, "training")
    if testSeeds is None:
        testSeeds = [testingSeed + index * 10 for index in range(5)]
    if trainingSeed in testSeeds:
        raise ValueError("Training seed must differ from every testing seed")

    trainingIds = {task["id"] for task in trainingWorkload}
    seedResults = []
    for testSeed in testSeeds:
        testingWorkload = createWorkload(testSeed, taskCount, "testing")
        testingIds = {task["id"] for task in testingWorkload}
        if trainingIds.intersection(testingIds):
            raise ValueError("Training and testing workloads must be separate")
        results = [
            runWorkload(testingWorkload, "static", randomSeed=testSeed),
            runWorkload(testingWorkload, "list", randomSeed=testSeed),
        ]
        seedResults.append({"seed": testSeed, "results": results})

    tuning = tuneAdaptivePolicy(trainingWorkload, randomSeed=trainingSeed)
    for seedRun in seedResults:
        testingWorkload = createWorkload(seedRun["seed"], taskCount, "testing")
        adaptiveResult = runWorkload(
            testingWorkload, "adaptive", tuning["settings"], randomSeed=seedRun["seed"]
        )
        seedRun["results"].append(adaptiveResult)

    statistics = getPolicyStatistics(seedResults)
    return {
        "trainingSeed": trainingSeed,
        "testingSeed": testSeeds[0],
        "testingSeeds": list(testSeeds),
        "trainingTaskCount": len(trainingWorkload),
        "testingTaskCount": taskCount,
        "tuningTrialCount": len(tuning["trials"]),
        "tunedSettings": tuning["settings"],
        "trainingObjective": tuning["objective"],
        "results": seedResults[0]["results"],
        "seedResults": seedResults,
        "statistics": statistics
    }

def printRequirement6Results(report):
    print("Requirement 6: Adaptive Green Scheduling")
    print(f"Training seed: {report['trainingSeed']} | Testing seeds: {report['testingSeeds']}")
    print(f"Tuning trials: {report['tuningTrialCount']}")
    print("Tuned adaptive settings:")
    for name, value in report["tunedSettings"].items():
        print(f"  {name}: {value}")
    print("\nTesting workload results (mean +/- standard deviation):")
    for policyName, metrics in report["statistics"].items():
        makespan = metrics["makespan"]
        energy = metrics["totalEnergy"]
        completed = metrics["completedTasks"]
        print(
            f"{policyName:>8} | makespan {makespan['mean']:.2f} +/- "
            f"{makespan['standardDeviation']:.2f} | energy {energy['mean']:.2f} +/- "
            f"{energy['standardDeviation']:.2f} | completed {completed['mean']:.1f}"
        )
    adaptive = report["statistics"]["adaptive"]
    print(
        f"\nAdaptive overhead | decision {adaptive['averageDecisionTimeNs']['mean']:.0f} "
        f"ns/task | policy memory {adaptive['policyMemoryBytes']['mean']:.0f} bytes"
    )
