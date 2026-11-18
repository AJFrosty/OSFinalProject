from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.offloadStrategy import DRLInspiredHeuristic, ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler


def testPriorityOrder():
    device = Device("LocalDevice", 1.0)
    device.addTask(Task("T1", 10, 3))
    device.addTask(Task("T2", 10, 1))
    device.addTask(Task("T3", 10, 1))
    orderedTasks = [task.id for task in device.getQueueTasks()]
    assert orderedTasks == ["T2", "T3", "T1"]


def testStaticRule():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(50))
    smallTask = Task("Small", 20, 1)
    largeTask = Task("Large", 80, 1)
    assert scheduler.submitTask(smallTask) is device
    assert scheduler.submitTask(largeTask) is edge


def testHeuristic():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], DRLInspiredHeuristic())
    largeTask = Task("Large", 80, 1)
    assert scheduler.submitTask(largeTask) is edge


def testMigration():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    task = Task("MoveMe", 80, 1)
    assert scheduler.submitTask(task) is device
    scheduler.strategy = StaticRule(50)
    assert scheduler.submitTask(task) is edge
    assert not device.queue.hasTask("MoveMe")
    assert edge.queue.hasTask("MoveMe")


def testListSchedulingChoosesEarliestFinish():
    device = Device("LocalDevice", 1.0, energyCapacity=500.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    cloud = Server("CloudServer", 5.0, wirelessDelay=5.0, wiredDelay=10.0)
    scheduler = Scheduler(device, [edge, cloud], ListSchedulingHeuristic())

    localTask = Task("LocalTask", 5, 1)
    edgeTask = Task("EdgeTask", 20, 1)
    cloudTask = Task("CloudTask", 100, 1)

    assert scheduler.submitTask(localTask) is device
    assert scheduler.submitTask(edgeTask) is edge
    assert scheduler.submitTask(cloudTask) is cloud
    assert device.estimateFinishTime(localTask) == 5.0
    assert round(edge.estimateFinishTime(edgeTask), 2) == 11.67
    assert cloud.estimateFinishTime(cloudTask) == 35.0


def testNetworkDelayIncluded():
    device = Device("LocalDevice", 1.0, energyCapacity=100.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    task = Task("SmallTask", 5, 1)
    assert device.estimateFinishTime(task) == 5.0
    assert round(edge.estimateFinishTime(task), 2) == 6.67


def testEnergyReservationPreventsOversubscription():
    device = Device("LocalDevice", 1.0, energyCapacity=30.0, energyPerWorkUnit=0.5)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    firstTask = Task("First", 40, 1)
    secondTask = Task("Second", 30, 1)

    assert scheduler.submitTask(firstTask) is device
    assert device.reservedEnergy == 20.0
    assert scheduler.submitTask(secondTask) is edge
    assert device.reservedEnergy == 20.0


def testEnergyConsumedOnLocalDispatch():
    device = Device("LocalDevice", 1.0, energyCapacity=30.0, energyPerWorkUnit=0.5)
    device.addTask(Task("LocalTask", 20, 1))
    task = device.nextTask()
    assert task.id == "LocalTask"
    assert device.remainingEnergy == 20.0
    assert device.reservedEnergy == 0.0


def testListSchedulingAvoidsUnaffordableLocalExecution():
    device = Device("LocalDevice", 1.0, energyCapacity=10.0, energyPerWorkUnit=0.5)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], ListSchedulingHeuristic())
    task = Task("TooExpensiveLocally", 40, 1)
    assert scheduler.submitTask(task) is edge


def testNoExecutionWhenEnergyInsufficientAndNoRemoteServer():
    device = Device("LocalDevice", 1.0, energyCapacity=10.0, energyPerWorkUnit=0.5)
    scheduler = Scheduler(device, [], StaticRule(100))
    task = Task("NoEnergy", 40, 1)
    try:
        scheduler.submitTask(task)
    except ValueError:
        assert task.status == "new"
    else:
        raise AssertionError("Task should not be admitted without enough energy")


def testUploadTimeUsesDataSizeAndWirelessBandwidth():
    edge = Server("EdgeServer", 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0)
    task = Task("Upload", 20, 1, dataSize=50)
    assert edge.getTransferTime(task) == 5.0
    assert edge.getCommunicationDelay(task) == 7.0


def testCloudUploadIncludesWirelessAndWiredTransferTime():
    cloud = Server("CloudServer", 5.0, wirelessDelay=2.0, wiredDelay=4.0,
                   wirelessBandwidth=10.0, wiredBandwidth=100.0)
    task = Task("CloudUpload", 20, 1, dataSize=50)
    assert cloud.getTransferTime(task) == 5.5
    assert cloud.getCommunicationDelay(task) == 11.5
    device = Device("LocalDevice", 1.0)
    scheduler = Scheduler(device, [cloud], StaticRule(0))
    assert scheduler.submitTask(task, currentTime=0.0) is cloud
    assert task.status == "transferring"
    assert task.transferCompletionTime == 11.5
    assert scheduler.dispatchTask("CloudServer", currentTime=11.49) is None
    assert scheduler.dispatchTask("CloudServer", currentTime=11.5) is task


def testRemoteTaskCannotRunBeforeUploadCompletes():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0)
    scheduler = Scheduler(device, [edge], StaticRule(0))
    task = Task("DelayedUpload", 20, 1, dataSize=50)

    assert scheduler.submitTask(task, currentTime=3.0) is edge
    assert task.status == "transferring"
    assert task.transferStartTime == 3.0
    assert task.transferCompletionTime == 10.0
    assert scheduler.dispatchTask("EdgeServer", currentTime=9.99) is None
    assert task.status == "transferring"
    assert edge.queue.hasTask(task.id)
    assert scheduler.dispatchTask("EdgeServer", currentTime=10.0) is task
    assert task.status == "running"


def testRemoteDispatchRespectsPriorityAmongTransferredTasks():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0)
    scheduler = Scheduler(device, [edge], StaticRule(0))
    slowUpload = Task("HighPrioritySlowUpload", 10, 1, dataSize=50)
    fastUpload = Task("LowPriorityFastUpload", 10, 2, dataSize=10)
    scheduler.submitTask(slowUpload, currentTime=0.0)
    scheduler.submitTask(fastUpload, currentTime=0.0)

    assert scheduler.dispatchTask("EdgeServer", currentTime=1.0) is None
    assert scheduler.dispatchTask("EdgeServer", currentTime=5.0) is slowUpload
    assert scheduler.dispatchTask("EdgeServer", currentTime=6.0) is fastUpload


def testLocalTasksDoNotRequireUpload():
    device = Device("LocalDevice", 1.0, energyCapacity=100.0)
    task = Task("LocalDataTask", 10, 1, dataSize=500)
    device.addTask(task, currentTime=4.0)
    assert task.transferTime == 0.0
    assert task.communicationDelay == 0.0
    assert task.transferCompletionTime == 4.0
    assert device.nextTask(currentTime=4.0) is task


def testBandwidthMustBePositive():
    try:
        Server("InvalidServer", 2.0, wirelessBandwidth=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("Zero network bandwidth should be rejected")


testPriorityOrder()
testStaticRule()
testHeuristic()
testMigration()
testListSchedulingChoosesEarliestFinish()
testNetworkDelayIncluded()
testEnergyReservationPreventsOversubscription()
testEnergyConsumedOnLocalDispatch()
testListSchedulingAvoidsUnaffordableLocalExecution()
testNoExecutionWhenEnergyInsufficientAndNoRemoteServer()
testUploadTimeUsesDataSizeAndWirelessBandwidth()
testCloudUploadIncludesWirelessAndWiredTransferTime()
testRemoteTaskCannotRunBeforeUploadCompletes()
testRemoteDispatchRespectsPriorityAmongTransferredTasks()
testLocalTasksDoNotRequireUpload()
testBandwidthMustBePositive()
print("All implementation checks passed")
