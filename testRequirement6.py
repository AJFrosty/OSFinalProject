from experiments.greenPolicyExperiment import (
    createWorkload,
    runRequirement6Experiment,
    runWorkload,
    tuneAdaptivePolicy
)
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.adaptiveGreenPolicy import AdaptiveGreenPolicy


def testStateContainsRequiredInputs():
    device = Device("Device", energyCapacity=100.0)
    edge = Server("Edge", 3.0, wirelessBandwidth=10.0)
    policy = AdaptiveGreenPolicy(referenceBandwidth=10.0)
    state = policy.buildState(Task("StateTask", 25, 1, dataSize=5), device, [edge])
    assert set(("remainingBattery", "localQueueLength", "wirelessSpeed", "taskSize")).issubset(state)
    assert state["remainingBattery"] == 1.0
    assert state["localQueueLength"] == 0
    assert state["wirelessSpeed"] == 10.0
    assert state["taskSize"] == 25


def testWeightsAdaptToBatteryAndNetwork():
    policy = AdaptiveGreenPolicy(referenceBandwidth=10.0)
    fullBattery = {"remainingBattery": 1.0, "wirelessSpeed": 10.0}
    lowBattery = {"remainingBattery": 0.2, "wirelessSpeed": 10.0}
    slowNetwork = {"remainingBattery": 1.0, "wirelessSpeed": 2.0}
    fullTime, fullEnergy = policy.getAdaptiveWeights(fullBattery)
    lowTime, lowEnergy = policy.getAdaptiveWeights(lowBattery)
    slowTime, slowEnergy = policy.getAdaptiveWeights(slowNetwork)
    assert lowEnergy > fullEnergy
    assert slowEnergy > fullEnergy
    assert slowTime != fullTime
    assert slowEnergy != fullEnergy
    assert abs(fullTime + fullEnergy - 1.0) < 1e-9


def testPolicySelectsAnExecutionPointAndRecordsOverhead():
    device = Device("Device", energyCapacity=100.0)
    edge = Server("Edge", 3.0, wirelessBandwidth=10.0)
    policy = AdaptiveGreenPolicy()
    selected = policy.chooseServer(Task("ChooseTask", 40, 1, dataSize=8), device, [edge])
    summary = policy.getOverheadSummary()
    assert selected in (device, edge)
    assert summary["decisionCount"] == 1
    assert summary["averageDecisionTimeNs"] >= 0
    assert summary["policyMemoryBytes"] > 0
    assert policy.lastState["taskSize"] == 40


def testTrainingAndTestingWorkloadsAreDifferent():
    training = createWorkload(41, 12, "training")
    testing = createWorkload(97, 12, "testing")
    trainingIds = {task["id"] for task in training}
    testingIds = {task["id"] for task in testing}
    assert not trainingIds.intersection(testingIds)
    assert training != testing


def testTuningUsesTrainingWorkload():
    training = createWorkload(41, 8, "training")
    tuning = tuneAdaptivePolicy(training, randomSeed=41)
    assert len(tuning["trials"]) == 24
    assert tuning["settings"] is not None
    assert tuning["objective"] >= 0


def testAdaptiveWorkloadRunCompletesAndReportsOverhead():
    workload = createWorkload(97, 12, "testing")
    result = runWorkload(workload, "adaptive", {
        "baseTimeWeight": 0.6,
        "baseEnergyWeight": 0.4,
        "batterySensitivity": 0.5,
        "networkSensitivity": 0.25,
        "networkEnergySensitivity": 0.2,
        "referenceBandwidth": 12.0
    }, randomSeed=97)
    assert result["completedTasks"] + result["rejectedTasks"] == len(workload)
    assert result["makespan"] >= 0
    assert result["totalEnergy"] >= 0
    assert result["decisionOverhead"]["decisionCount"] == len(workload)
    assert result["decisionOverhead"]["policyMemoryBytes"] > 0


def testCompleteRequirement6Comparison():
    report = runRequirement6Experiment(trainingSeed=41, testingSeed=97, taskCount=10)
    assert report["trainingSeed"] != report["testingSeed"]
    assert report["tuningTrialCount"] == 24
    assert len(report["seedResults"]) == 5
    assert len(report["statistics"]["adaptive"]["makespan"]) == 2
    assert [result["policy"] for result in report["results"]] == ["static", "list", "adaptive"]
    adaptive = report["results"][2]
    assert adaptive["decisionOverhead"]["decisionCount"] == 10


testStateContainsRequiredInputs()
testWeightsAdaptToBatteryAndNetwork()
testPolicySelectsAnExecutionPointAndRecordsOverhead()
testTrainingAndTestingWorkloadsAreDifferent()
testTuningUsesTrainingWorkload()
testAdaptiveWorkloadRunCompletesAndReportsOverhead()
testCompleteRequirement6Comparison()
print("All Requirement 6 checks passed")
