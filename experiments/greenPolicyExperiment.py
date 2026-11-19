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


serviceTypes = ("analytics", "media", "database", "vision", "sensor")
servicePattern = ("analytics", "database", "media", "analytics", "analytics", "database",
                  "analytics", "analytics", "vision", "analytics", "sensor", "analytics")
cacheServicePattern = ("analytics", "database", "analytics", "analytics", "analytics", "database",
                       "vision", "analytics", "sensor", "media", "analytics", "database")


def createWorkload(seed, taskCount=24, profile="training"):
    generator = random.Random(seed)
    tasks = []
    for index in range(taskCount):
        if profile == "training":
            size = generator.randint(12, 90)
            dataSize = generator.randint(4, 24)
            memory = generator.randint(8, 36)
        elif profile == "testing":
            size = generator.randint(18, 115)
            dataSize = generator.randint(2, 34)
            memory = generator.randint(6, 42)
        elif profile == "large":
            size = generator.randint(65, 150)
            dataSize = generator.randint(12, 42)
            memory = generator.randint(20, 52)
        elif profile == "small":
            size = generator.randint(5, 30)
            dataSize = generator.randint(1, 12)
            memory = generator.randint(4, 20)
        elif profile == "cache":
            size = generator.randint(65, 110)
            dataSize = generator.randint(2, 12)
            memory = generator.randint(4, 8)
        else:
            raise ValueError("Unknown workload profile")
        tasks.append({
            "id": f"{profile.title()}Task{index + 1}",
            "size": float(size),
            "priority": generator.randint(1, 4),
            "dataSize": float(dataSize),
            "memory": float(memory),
            "service": (
                cacheServicePattern[index % len(cacheServicePattern)]
                if profile == "cache" else servicePattern[index % len(servicePattern)]
            )
        })
    return tasks


def createTasks(taskSpecs):
    return [
        Task(
            spec["id"], spec["size"], spec["priority"],
            dataSize=spec["dataSize"],
            memory=spec.get("memory", 8.0),
            service=spec.get("service", "analytics")
        )
        for spec in taskSpecs
    ]


def createSystem(strategy, randomSeed=1, scenarioConfig=None):
    config = scenarioConfig or {}
    device = Device(
        "LocalDevice",
        computeSpeed=1.0,
        energyCapacity=config.get("energyCapacity", 360.0),
        energyPerWorkUnit=0.45,
        memoryCapacity=config.get("deviceMemoryCapacity", 128.0),
        schedulerMemoryReserve=config.get("schedulerMemoryReserve", 16.0)
    )
    edge = Server(
        "EdgeServer",
        computeSpeed=3.0,
        wirelessDelay=2.0,
        wirelessBandwidth=config.get("wirelessBandwidth", 12.0),
        memoryCapacity=config.get("edgeMemoryCapacity", 256.0),
        cacheSlots=config.get("cacheSlots", 2),
        cachePolicy=config.get("cachePolicy", "LRU"),
        serviceImageSize=config.get("serviceImageSize", 12.0),
        serviceLoadDelay=config.get("serviceLoadDelay", 2.0)
    )
    cloud = Server(
        "CloudServer",
        computeSpeed=5.0,
        wirelessDelay=2.0,
        wiredDelay=3.0,
        wirelessBandwidth=config.get("cloudWirelessBandwidth", config.get("wirelessBandwidth", 10.0)),
        wiredBandwidth=100.0,
        memoryCapacity=config.get("cloudMemoryCapacity", 1024.0)
    )
    network = NetworkInterface(
        policy="FCFS",
        radioPolicy=config.get("radioPolicy", "fixed"),
        idleTimeout=8.0,
        wakeDelay=0.5,
        wakeEnergy=0.25,
        txPower=0.35,
        idlePower=0.02,
        bandwidthVariation=config.get("bandwidthVariation", 0.08),
        randomSeed=randomSeed,
        device=device
    )
    scheduler = Scheduler(device, [edge, cloud], strategy, networkInterface=network)
    return device, [edge, cloud], network, scheduler


def runWorkload(taskSpecs, policyName, policySettings=None, randomSeed=1, scenarioConfig=None):
    settings = policySettings or {}
    if policyName == "static":
        strategy = StaticRule(largeTaskThreshold=50.0)
    elif policyName == "list":
        strategy = ListSchedulingHeuristic()
    elif policyName == "adaptive":
        strategy = AdaptiveGreenPolicy(**settings)
    else:
        raise ValueError("Policy must be static, list or adaptive")

    device, servers, network, scheduler = createSystem(strategy, randomSeed, scenarioConfig)
    tasks = createTasks(taskSpecs)
    assignments = {}
    for task in tasks:
        server = scheduler.submitTask(task, currentTime=0.0)
        assignments[task.id] = server.name if server is not None else "rejected"

    allServers = [device] + servers
    serverCurrentTask = {}
    serverAvailable = {server.name: 0.0 for server in allServers}
    taskStartTimes = {}
    taskCompletionTimes = {}
    queueWaitingTimesByNode = {server.name: [] for server in allServers}
    taskArrivalTimes = {task.id: 0.0 for task in tasks}
    queueSamples = []
    eventCount = 0
    maximumEvents = max(2000, len(tasks) * 200)

    def hasActiveWork():
        return (
            any(server.queueLength() or server.runningTasks for server in allServers)
            or network.activeTransfer is not None
            or bool(network.uploadQueue)
        )

    while hasActiveWork():
        eventTimes = []
        if network.activeTransfer is not None:
            eventTimes.append(network.activeWirelessEnd)
        for server in allServers:
            if server.name in serverCurrentTask:
                eventTimes.append(serverAvailable[server.name])
            readyTimes = [
                task.transferCompletionTime
                for task in server.getQueueTasks()
                if task.status != "uploadQueued" and task.transferCompletionTime < float("inf")
            ]
            if readyTimes:
                eventTimes.append(max(serverAvailable[server.name], min(readyTimes)))
        if not eventTimes:
            raise RuntimeError("Simulation stalled with queued or running work")

        currentTime = max(scheduler.currentTime, min(eventTimes))
        scheduler.updateTime(currentTime)

        for server in allServers:
            currentTask = serverCurrentTask.get(server.name)
            if currentTask is not None and serverAvailable[server.name] <= currentTime:
                scheduler.completeTask(server.name, currentTask.id)
                serverCurrentTask.pop(server.name, None)

        dispatched = False
        for server in allServers:
            if server.name in serverCurrentTask or serverAvailable[server.name] > currentTime:
                continue
            task = scheduler.dispatchTask(server.name, currentTime=currentTime)
            if task is None:
                continue
            completionTime = currentTime + task.size / server.computeSpeed
            serverAvailable[server.name] = completionTime
            serverCurrentTask[server.name] = task
            taskStartTimes[task.id] = currentTime
            taskCompletionTimes[task.id] = completionTime
            queueWaitingTimesByNode[server.name].append(currentTime - taskArrivalTimes[task.id])
            dispatched = True

        queueSamples.append({
            "time": currentTime,
            "queues": {server.name: server.queueLength() for server in allServers},
            "running": {server.name: len(server.runningTasks) for server in allServers}
        })
        for server in allServers:
            server.memoryManager.sample(currentTime)

        eventCount += 1
        if eventCount > maximumEvents:
            raise RuntimeError("Simulation exceeded the event limit")
        if not dispatched and not eventTimes:
            raise RuntimeError("Simulation could not advance")

    makespan = max(taskCompletionTimes.values(), default=0.0)
    scheduler.updateTime(max(scheduler.currentTime, makespan))
    for server in allServers:
        server.memoryManager.sample(scheduler.currentTime)

    completedCount = sum(1 for task in tasks if task.status == "completed")
    rejectedTasks = [
        task for task in tasks
        if task.status in ("energyRejected", "memoryRejected", "rejected")
    ]
    memorySummary = scheduler.getMemorySummary()
    rejectionCount = sum(node["rejectionCount"] for node in memorySummary.values())
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
    objective = (
        0.5 * (makespan / timeScale)
        + 0.5 * (totalEnergy / energyScale)
        + len(rejectedTasks) / max(1, len(tasks))
    )
    overhead = strategy.getOverheadSummary() if isinstance(strategy, AdaptiveGreenPolicy) else {}
    memorySamples = []
    for nodeName, summary in memorySummary.items():
        for sample in summary["samples"]:
            memorySamples.append({"node": nodeName, **sample})

    queueWaitValues = [
        taskStartTimes[taskId] - taskArrivalTimes[taskId]
        for taskId in taskStartTimes
    ]
    cacheHits = sum(node["cacheHits"] for node in memorySummary.values())
    cacheMisses = sum(node["cacheMisses"] for node in memorySummary.values())
    aggregateCacheHitRate = cacheHits / (cacheHits + cacheMisses) if cacheHits + cacheMisses else 0.0
    peakMemoryUtilization = max(
        (node["peakUsedMemoryMb"] / node["capacityMb"] for node in memorySummary.values()),
        default=0.0
    )
    averageMemoryUtilization = mean(
        node["averageUtilization"] for node in memorySummary.values()
    ) if memorySummary else 0.0

    return {
        "policy": policyName,
        "makespan": makespan,
        "totalEnergy": totalEnergy,
        "computationEnergy": device.computationEnergy,
        "transmissionEnergy": network.transmissionEnergy,
        "radioIdleEnergy": network.radioIdleEnergy,
        "wakeEnergy": network.wakeEnergyConsumed,
        "completedTasks": completedCount,
        "rejectedTasks": len(rejectedTasks),
        "rejectedTaskIds": [task.id for task in rejectedTasks],
        "memoryRejectedTasks": sum(1 for task in tasks if task.status == "memoryRejected"),
        "offloadedTasks": sum(1 for name in assignments.values() if name not in (device.name, "rejected")),
        "localTasks": sum(1 for name in assignments.values() if name == device.name),
        "averageQueueWaitingTime": mean(queueWaitValues) if queueWaitValues else 0.0,
        "queueWaitingTimesByNode": {
            nodeName: {
                "mean": mean(values) if values else 0.0,
                "taskCount": len(values)
            }
            for nodeName, values in queueWaitingTimesByNode.items()
        },
        "offloadedPercent": 100.0 * sum(1 for name in assignments.values() if name not in (device.name, "rejected")) / len(tasks) if tasks else 0.0,
        "localPercent": 100.0 * sum(1 for name in assignments.values() if name == device.name) / len(tasks) if tasks else 0.0,
        "queueOccupancySamples": queueSamples,
        "energyEfficiency": completedCount / totalEnergy if totalEnergy > 0 else 0.0,
        "objective": objective,
        "assignments": assignments,
        "memory": memorySummary,
        "memorySamples": memorySamples,
        "peakMemoryUtilization": peakMemoryUtilization,
        "averageMemoryUtilization": averageMemoryUtilization,
        "serviceCacheHitRate": aggregateCacheHitRate,
        "memoryAdmissionRejections": rejectionCount,
        "migrationDataVolumeMb": network.migrationDataVolume,
        "bandwidthHistory": list(network.bandwidthHistory),
        "radioStateTimes": dict(network.stateTimes),
        "radioWakeUps": network.wakeUps,
        "energyBreakdown": {
            "computation": device.computationEnergy,
            "transmission": network.transmissionEnergy,
            "radioIdle": network.radioIdleEnergy,
            "radioWake": network.wakeEnergyConsumed
        },
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
        "makespan", "totalEnergy", "completedTasks", "rejectedTasks",
        "objective", "averageDecisionTimeNs", "policyMemoryBytes",
        "peakMemoryUtilization", "averageMemoryUtilization", "serviceCacheHitRate",
        "migrationDataVolumeMb", "memoryAdmissionRejections"
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
