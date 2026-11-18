import math
import statistics

from experiments.policyMetrics import MeasuredPolicy, policyMemoryBytes
from experiments.scenarioRunner import (coreScenarios, finishBatch, makeTasks,
                                        runSimulation, summarizeRuns, testSeeds, tuningSeeds)
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.aiPolicy import AdaptiveGreenPolicy
from scheduling.offloadStrategy import StaticRule
from scheduling.scheduler import Scheduler


def testStateAndWeights():
    device = Device(energyCapacity=100)
    edge = Server("Edge", 3, wirelessBandwidth=20)
    policy = AdaptiveGreenPolicy(0.35)
    task = Task("New", 10, 1, 5)
    state = policy.getState(task, device, [edge])
    assert state == {"remainingBattery": 100, "availableBattery": 100,
                     "localQueueLength": 0, "wirelessSpeed": 20, "taskSize": 10}
    assert math.isclose(policy.getWeights(state, device)[1], 0.35)
    device.addTask(Task("Reserved", 160, 1))
    state = policy.getState(task, device, [edge])
    assert state["remainingBattery"] == 100
    assert state["availableBattery"] == 20
    assert state["localQueueLength"] == 1
    assert math.isclose(policy.getWeights(state, device)[1], 0.60)
    edge.wirelessBandwidth = 2
    state = policy.getState(task, device, [edge])
    assert math.isclose(policy.getWeights(state, device)[1], 0.45)


def testNetworkAndBatteryChangeDecision():
    policy = AdaptiveGreenPolicy(0.35)
    task = Task("Choice", 10, 1, 10)
    device = Device(energyCapacity=100)
    edge = Server("Edge", 3, wirelessDelay=5, wirelessBandwidth=20)
    assert policy.chooseServer(task, device, [edge]) is edge
    edge.wirelessBandwidth = 2
    assert policy.chooseServer(task, device, [edge]) is device
    device.remainingEnergy = 20
    assert policy.chooseServer(task, device, [edge]) is edge


def testQueueChangesDecision():
    policy = AdaptiveGreenPolicy(0.35)
    task = Task("Choice", 10, 1, 10)
    device = Device(energyCapacity=1000)
    edge = Server("Edge", 3, wirelessDelay=5, wirelessBandwidth=2)
    assert policy.chooseServer(task, device, [edge]) is device
    device.addTask(Task("Waiting", 50, 1))
    assert policy.chooseServer(task, device, [edge]) is edge


def testEnergySafetyAndNoServer():
    policy = AdaptiveGreenPolicy()
    device = Device(energyCapacity=5)
    edge = Server("Edge", 3)
    scheduler = Scheduler(device, [edge], policy)
    task = Task("TooLarge", 20, 1)
    assert scheduler.submitTask(task) is edge
    assert device.reservedEnergy == 0
    assert policy.chooseServer(Task("Affordable", 10, 1), device, []) is device
    try:
        policy.chooseServer(task, device, [])
    except ValueError:
        pass
    else:
        raise AssertionError("An unaffordable task must be rejected")
    emptyDevice = Device(energyCapacity=0)
    assert policy.chooseServer(Task("Zero", 0, 1), emptyDevice, []) is emptyDevice


def testBatchTimingAndPriority():
    device = Device(energyCapacity=100)
    edge = Server("Edge", 2, wirelessBandwidth=10)
    scheduler = Scheduler(device, [edge], StaticRule(5))
    scheduler.submitTask(Task("Local", 4, 1))
    scheduler.submitTask(Task("SlowUpload", 10, 1, 100))
    scheduler.submitTask(Task("QuickUpload", 6, 2, 10))
    completed, history = finishBatch(scheduler)
    byId = {row["taskId"]: row for row in completed}
    assert byId["Local"]["finishTime"] == 4
    assert byId["QuickUpload"]["startTime"] == 1
    assert byId["QuickUpload"]["finishTime"] == 4
    assert byId["SlowUpload"]["startTime"] == 10
    assert byId["SlowUpload"]["finishTime"] == 15
    assert scheduler.currentTime == 15
    assert device.remainingEnergy == 98
    assert all(row["queueLength"] == 0 for row in history[-2:])

    device = Device(energyCapacity=100)
    scheduler = Scheduler(device, [], StaticRule())
    scheduler.submitTask(Task("LowPriority", 4, 3))
    scheduler.submitTask(Task("HighPriority", 2, 1))
    completed, _ = finishBatch(scheduler)
    assert [row["taskId"] for row in completed] == ["HighPriority", "LowPriority"]
    assert completed[1]["startTime"] == 2
    assert completed[1]["finishTime"] == 6
    assert completed[1]["queueWait"] == 2


def testWorkloadsAndStatistics():
    assert not set(testSeeds).intersection(tuningSeeds)
    assert makeTasks(1, "mixed") == makeTasks(1, "mixed")
    assert makeTasks(1, "mixed") != makeTasks(101, "mixed", 24)
    assert all(5 <= task.size <= 25 for task in makeTasks(1, "small"))
    assert all(60 <= task.size <= 120 for task in makeTasks(1, "large"))
    rows = []
    for scenario in coreScenarios:
        for policy in ["Static", "List", "Adaptive"]:
            for seed in testSeeds:
                rows.append({"scenario": scenario["name"], "policy": policy,
                             "seed": seed, "makespan": seed})
    summary = summarizeRuns(rows)
    assert len(summary) == 18
    assert all(row["validSeeds"] == 5 and row["mean"] == 3 for row in summary)
    assert all(row["std"] == statistics.stdev(testSeeds) for row in summary)


def testMeasurementsAndCompletedRuns():
    policy = AdaptiveGreenPolicy()
    measured = MeasuredPolicy(policy)
    measured.chooseServer(Task("One", 1, 1), Device(), [])
    assert len(measured.decisionTimes) == 1
    assert measured.decisionTimes[0] >= 0
    exhausted = Device(energyCapacity=0)
    remote = Server("Edge", 3)
    assert MeasuredPolicy(StaticRule()).chooseServer(Task("Fallback", 1, 1), exhausted, [remote]) is remote
    assert policyMemoryBytes(policy) > 0
    before = policyMemoryBytes(policy)
    for scenario in coreScenarios:
        metrics, completed, _ = runSimulation(scenario, 1, policy)
        assert metrics["completedTasks"] == 40
        assert 0 <= metrics["computationEnergy"] <= scenario["energy"]
        assert metrics["localPercent"] + metrics["offloadedPercent"] == 100
        assert len({row["taskId"] for row in completed}) == 40
        for row in completed:
            assert row["startTime"] >= row["readyTime"]
        for server in ["LocalDevice", "EdgeServer", "CloudServer"]:
            records = sorted((row for row in completed if row["server"] == server),
                             key=lambda row: row["startTime"])
            for previous, current in zip(records, records[1:]):
                assert current["startTime"] >= previous["finishTime"]
    assert policyMemoryBytes(policy) == before


if __name__ == "__main__":
    tests = [testStateAndWeights, testNetworkAndBatteryChangeDecision, testQueueChangesDecision,
             testEnergySafetyAndNoServer, testBatchTimingAndPriority, testWorkloadsAndStatistics,
             testMeasurementsAndCompletedRuns]
    for test in tests:
        test()
        print(test.__name__ + " passed")
    print("All 7 Task 6 test groups passed")
