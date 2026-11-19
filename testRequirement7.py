from collections import OrderedDict, deque

from memoryMgmt.memoryManager import MemoryManager
from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.offloadStrategy import StaticRule
from scheduling.scheduler import Scheduler


def testEachTaskHasMemoryFootprint():
    task = Task("DefaultMemory", 10, 1)
    assert task.memory > 0


def testLocalSchedulerMemoryIsReserved():
    device = Device("Device", memoryCapacity=64.0, schedulerMemoryReserve=16.0)
    Scheduler(device, [], StaticRule(100))
    summary = device.getMemorySummary()
    assert summary["reservedSystemMemoryMb"] == 16.0
    assert summary["capacityMb"] == 64.0


def testMemoryAdmissionRedirectsTaskToRemoteServer():
    device = Device("Device", memoryCapacity=40.0, schedulerMemoryReserve=16.0)
    edge = Server("Edge", 3.0, memoryCapacity=100.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    first = Task("LocalOccupant", 10, 1, memory=20.0)
    second = Task("Redirected", 10, 1, memory=20.0)
    assert scheduler.submitTask(first) is device
    assert scheduler.submitTask(second) is edge
    assert device.memoryManager.getSummary()["rejectionCount"] == 1
    assert second.memoryNode == "Edge"


def testMemoryAdmissionRejectionsAreRecordedOnEveryNode():
    device = Device("Device", memoryCapacity=32.0, schedulerMemoryReserve=16.0)
    edge = Server("Edge", 3.0, memoryCapacity=20.0)
    cloud = Server("Cloud", 5.0, memoryCapacity=20.0)
    scheduler = Scheduler(device, [edge, cloud], StaticRule(100))
    task = Task("TooLarge", 10, 1, memory=30.0)
    assert scheduler.submitTask(task) is None
    assert task.status == "memoryRejected"
    assert device.memoryManager.getSummary()["rejectionCount"] == 1
    assert edge.memoryManager.getSummary()["rejectionCount"] == 1
    assert cloud.memoryManager.getSummary()["rejectionCount"] == 1


def testMemoryReleasedOnlyAfterCompletion():
    device = Device("Device", memoryCapacity=128.0, schedulerMemoryReserve=16.0)
    scheduler = Scheduler(device, [], StaticRule(100))
    task = Task("Running", 10, 1, memory=24.0)
    assert scheduler.submitTask(task) is device
    assert device.memoryManager.usedTaskMemory == 24.0
    assert scheduler.dispatchTask("Device", 0.0) is task
    assert device.memoryManager.usedTaskMemory == 24.0
    assert scheduler.completeTask("Device", task.id)
    assert device.memoryManager.usedTaskMemory == 0.0


def testMigrationTransfersInputAndMemoryState():
    edge = Server("Edge", 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0)
    task = Task("Migration", 20, 1, dataSize=10.0, memory=20.0)
    assert edge.getTransferTime(task) == 3.0


def testCloudMigrationIncludesWirelessAndWiredStateTransfer():
    cloud = Server(
        "Cloud", 5.0, wirelessDelay=0.0, wiredDelay=1.0,
        wirelessBandwidth=10.0, wiredBandwidth=100.0
    )
    task = Task("CloudMigration", 20, 1, dataSize=20.0, memory=10.0)
    assert round(cloud.getTransferTime(task), 2) == 3.30


def testServiceCacheMissAndHitDelay():
    manager = MemoryManager("Edge", 128.0, cacheSlots=2, serviceImageSize=10.0, serviceLoadDelay=4.0)
    assert manager.accessService("analytics", 0.0) == 4.0
    assert manager.accessService("analytics", 1.0) == 0.0
    summary = manager.getSummary()
    assert summary["cacheHits"] == 1
    assert summary["cacheMisses"] == 1
    assert summary["cacheHitRate"] == 0.5
    assert summary["cacheMemoryMb"] == 10.0


def testLruEvictsLeastRecentlyUsedService():
    manager = MemoryManager("Edge", 128.0, cacheSlots=2, cachePolicy="LRU", serviceImageSize=10.0)
    manager.accessService("analytics", 0.0)
    manager.accessService("database", 1.0)
    manager.accessService("analytics", 2.0)
    manager.accessService("vision", 3.0)
    assert list(manager.serviceCache.keys()) == ["analytics", "vision"]
    assert manager.cacheEvictions == 1


def testPredictiveCacheUsesRecentArrivalHistory():
    manager = MemoryManager("Edge", 128.0, cacheSlots=2, cachePolicy="PREDICTIVE", serviceImageSize=10.0)
    manager.serviceCache = OrderedDict((("analytics", 1.0), ("database", 2.0)))
    manager.cacheMemoryUsed = 20.0
    manager.serviceHistory = deque(("analytics", "analytics", "analytics", "database"), maxlen=20)
    manager.accessService("vision", 3.0)
    assert "analytics" in manager.serviceCache
    assert "database" not in manager.serviceCache
    assert manager.cachePolicy == "PREDICTIVE"


def testCacheMissAddsPageLoadStyleDelayToRemoteReadiness():
    device = Device("Device", energyCapacity=1000.0)
    edge = Server(
        "Edge", 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0,
        memoryCapacity=128.0, cacheSlots=2, serviceImageSize=10.0, serviceLoadDelay=4.0
    )
    scheduler = Scheduler(device, [edge], StaticRule(0))
    task = Task("CacheMiss", 10, 1, dataSize=10.0, memory=10.0, service="analytics")
    assert scheduler.submitTask(task, 0.0) is edge
    assert task.transferCompletionTime == 6.0
    assert scheduler.dispatchTask("Edge", 5.99) is None
    assert scheduler.dispatchTask("Edge", 6.0) is task


def testMemoryAdmissionRejectsNegativeFootprints():
    manager = MemoryManager("Node", 64.0)
    task = Task("NegativeMemory", 1, 1, memory=-1.0)
    try:
        manager.canAdmit(task)
    except ValueError:
        pass
    else:
        raise AssertionError("Negative memory footprint should be rejected")


testEachTaskHasMemoryFootprint()
testLocalSchedulerMemoryIsReserved()
testMemoryAdmissionRedirectsTaskToRemoteServer()
testMemoryAdmissionRejectionsAreRecordedOnEveryNode()
testMemoryReleasedOnlyAfterCompletion()
testMigrationTransfersInputAndMemoryState()
testCloudMigrationIncludesWirelessAndWiredStateTransfer()
testServiceCacheMissAndHitDelay()
testLruEvictsLeastRecentlyUsedService()
testPredictiveCacheUsesRecentArrivalHistory()
testCacheMissAddsPageLoadStyleDelayToRemoteReadiness()
testMemoryAdmissionRejectsNegativeFootprints()
print("All Requirement 7 checks passed")
