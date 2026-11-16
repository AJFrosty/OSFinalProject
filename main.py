from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.aiPolicy import AdaptiveGreenPolicy
from scheduling.offloadStrategy import DRLInspiredHeuristic, ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler


def showAdaptiveExample():
    device = Device(energyCapacity=100.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0, wirelessBandwidth=2.0)
    cloud = Server("CloudServer", 5.0, wirelessDelay=5.0, wiredDelay=10.0,
                   wirelessBandwidth=2.0)
    policy = AdaptiveGreenPolicy(0.35)
    scheduler = Scheduler(device, [edge, cloud], policy)
    tasks = [Task("Small", 10, 1, 10), Task("Large", 80, 2, 30), Task("Another", 25, 1, 5)]
    print("\nTask 6 adaptive green policy:")
    for task in tasks:
        state = policy.getState(task, device, [edge, cloud])
        timeWeight, energyWeight = policy.getWeights(state, device)
        target = scheduler.submitTask(task)
        print(f"{task.id}: {target.name}, time weight={timeWeight:.2f}, "
              f"energy weight={energyWeight:.2f}, available battery={state['availableBattery']:.2f}")
    print("Run python runTask6.py for the six-scenario comparison.")


def runDemo():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    cloud = Server("CloudServer", 5.0, wirelessDelay=5.0, wiredDelay=10.0)
    servers = [edge, cloud]

    tasks = [
        Task("T1", 20, 2, 5),
        Task("T2", 80, 1, 12),
        Task("T3", 45, 3, 8),
        Task("T4", 65, 2, 10),
        Task("T5", 15, 1, 3),
    ]

    scheduler = Scheduler(device, servers, DRLInspiredHeuristic())
    for task in tasks:
        targetServer = scheduler.submitTask(task)
        print(f"{task.id} assigned to {targetServer.name}")

    print("\nQueues by priority:")
    for serverName, taskIds in scheduler.getQueueSummary().items():
        print(f"{serverName}: {taskIds}")

    print("\nNext task from the edge queue:")
    edgeTasks = edge.getQueueTasks()
    if not edgeTasks:
        print("No task is waiting on the edge server")
    else:
        readyTime = min(task.transferCompletionTime for task in edgeTasks)
        nextTask = scheduler.dispatchTask("EdgeServer", currentTime=readyTime)
        if nextTask is None:
            print("No task has completed its upload")
        else:
            print(f"{nextTask.id} finished uploading and is now running at time {readyTime:.2f}")


def showStaticRuleExample():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(50))
    sampleTask = Task("StaticTask", 75, 1, 10)
    targetServer = scheduler.submitTask(sampleTask)
    print(f"Static rule assigned {sampleTask.id} to {targetServer.name}")


def showListSchedulingExample():
    device = Device("LocalDevice", 1.0, energyCapacity=500.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    cloud = Server("CloudServer", 5.0, wirelessDelay=5.0, wiredDelay=10.0)
    scheduler = Scheduler(device, [edge, cloud], ListSchedulingHeuristic())
    tasks = [
        Task("LocalCandidate", 5, 1),
        Task("EdgeCandidate", 20, 1),
        Task("CloudCandidate", 100, 1),
    ]

    print("\nList scheduling decisions:")
    for task in tasks:
        targetServer = scheduler.submitTask(task)
        finishTime = targetServer.estimateFinishTime(task)
        print(f"{task.id} assigned to {targetServer.name}, estimated finish: {finishTime:.2f}")


def showEnergyExample():
    device = Device("LocalDevice", 1.0, energyCapacity=30.0, energyPerWorkUnit=0.5)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    firstTask = Task("LocalTask", 40, 1)
    secondTask = Task("EnergyLimitedTask", 30, 1)

    firstTarget = scheduler.submitTask(firstTask)
    secondTarget = scheduler.submitTask(secondTask)
    print("\nEnergy management:")
    print(f"{firstTask.id} assigned to {firstTarget.name}")
    print(f"{secondTask.id} assigned to {secondTarget.name} because local energy is reserved")
    scheduler.dispatchTask("LocalDevice")
    print(f"Remaining local energy: {device.remainingEnergy:.2f}")


def showCommunicationExample():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0)
    edgeScheduler = Scheduler(device, [edge], StaticRule(0))
    edgeTask = Task("EdgeUpload", 30, 1, dataSize=50)
    edgeScheduler.submitTask(edgeTask, currentTime=0.0)

    cloudDevice = Device("CloudLocalDevice", 1.0)
    cloud = Server("CloudServer", 5.0, wirelessDelay=2.0, wiredDelay=4.0,
                   wirelessBandwidth=10.0, wiredBandwidth=100.0)
    cloudScheduler = Scheduler(cloudDevice, [cloud], StaticRule(0))
    cloudTask = Task("CloudUpload", 30, 1, dataSize=50)
    cloudScheduler.submitTask(cloudTask, currentTime=0.0)

    print("\nCommunication time simulation:")
    print(f"{edgeTask.id} assigned to {edgeTask.location}")
    print(f"{edgeTask.id} upload time: {edgeTask.transferTime:.2f}")
    print(f"{edgeTask.id} can start at: {edgeTask.transferCompletionTime:.2f}")
    print(f"{cloudTask.id} assigned to {cloudTask.location}")
    print(f"{cloudTask.id} upload time: {cloudTask.transferTime:.2f}")
    print(f"{cloudTask.id} can start at: {cloudTask.transferCompletionTime:.2f}")
    earlyTask = edgeScheduler.dispatchTask("EdgeServer", currentTime=6.0)
    print(f"Edge dispatch before upload completion: {earlyTask}")
    readyTask = edgeScheduler.dispatchTask("EdgeServer", currentTime=edgeTask.transferCompletionTime)
    print(f"Edge dispatch after upload completion: {readyTask.id if readyTask else None}")
