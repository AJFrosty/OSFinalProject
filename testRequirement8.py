from ioMgmt.networkInterface import NetworkInterface
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.offloadStrategy import StaticRule
from scheduling.scheduler import Scheduler


def testSerialFcfsUploads():
    device = Device("Device", 1.0, energyCapacity=100.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, txPower=0.2)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task("First", 5, 2, dataSize=20, memory=0)
    second = Task("Second", 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.submitTask(second, 0.0)
    assert first.transferStartTime == 0.0
    assert first.transferCompletionTime == 2.0
    assert second.status == "uploadQueued"
    assert scheduler.dispatchTask("Edge", 1.99) is None
    assert scheduler.dispatchTask("Edge", 2.0) is first
    assert second.transferStartTime == 2.0
    assert second.transferCompletionTime == 3.0
    assert scheduler.dispatchTask("Edge", 3.0) is second


def testPriorityUploadQueue():
    device = Device("Device", 1.0, energyCapacity=100.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(policy="PRIORITY", device=device)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task("First", 5, 3, dataSize=10, memory=0)
    second = Task("Second", 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.submitTask(second, 0.0)
    assert scheduler.dispatchTask("Edge", 1.0) is first
    assert second.transferStartTime == 1.0
    assert scheduler.dispatchTask("Edge", 2.0) is second


def testTransmissionEnergyIsCharged():
    device = Device("Device", 1.0, energyCapacity=100.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, txPower=0.5)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    task = Task("Transmit", 5, 1, dataSize=20, memory=0)
    scheduler.submitTask(task, 0.0)
    assert network.transmissionEnergy == 1.0
    assert device.remainingEnergy == 99.0
    assert network.getEnergySummary()["transmissionEnergy"] == 1.0


def testTransmissionEnergyCannotOverdrawBattery():
    device = Device("Device", 1.0, energyCapacity=1.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=1.0)
    network = NetworkInterface(device=device, txPower=2.0)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    task = Task("TooExpensive", 5, 1, dataSize=1, memory=0)
    scheduler.submitTask(task, 0.0)
    assert task.status == "energyRejected"
    assert network.energyRejected == ["TooExpensive"]
    assert device.remainingEnergy == 1.0


def testRadioSleepsAndWakes():
    device = Device("Device", 1.0, energyCapacity=100.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, idleTimeout=2.0, wakeDelay=1.0, wakeEnergy=0.5)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task("First", 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.dispatchTask("Edge", 1.0)
    scheduler.dispatchTask("Edge", 4.0)
    assert network.state == "sleep"
    second = Task("Second", 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(second, 5.0)
    assert second.transferStartTime == 6.0
    assert second.transferCompletionTime == 7.0
    assert scheduler.dispatchTask("Edge", 5.5) is None
    assert network.state == "sleep"
    assert scheduler.dispatchTask("Edge", 6.5) is None
    assert scheduler.dispatchTask("Edge", 7.0) is second
    assert network.wakeEnergyConsumed == 0.5
    assert round(network.radioIdleEnergy, 2) == 0.1


def testPredictiveTimeoutUsesRecentArrivals():
    network = NetworkInterface(radioPolicy="predictive", idleTimeout=10.0, predictiveFactor=2.0,
                               minimumTimeout=1.0)
    network.interArrivalTimes = [2.0, 4.0, 6.0]
    assert network.getIdleTimeout() == 8.0


def testBandwidthVariesWithinConfiguredRange():
    device = Device("Device", 1.0, energyCapacity=1000.0)
    edge = Server("Edge", 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, bandwidthVariation=0.2, randomSeed=7)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    for index in range(4):
        task = Task(f"Task{index}", 1, 1, dataSize=1, memory=0)
        scheduler.submitTask(task, float(index * 2))
        scheduler.dispatchTask("Edge", task.transferCompletionTime)
    values = network.bandwidthHistory
    assert len(set(values)) > 1
    assert all(8.0 <= value <= 12.0 for value in values)


testSerialFcfsUploads()
testPriorityUploadQueue()
testTransmissionEnergyIsCharged()
testTransmissionEnergyCannotOverdrawBattery()
testRadioSleepsAndWakes()
testPredictiveTimeoutUsesRecentArrivals()
testBandwidthVariesWithinConfiguredRange()
print("All Requirement 8 checks passed")
