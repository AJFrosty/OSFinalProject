from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.offloadStrategy import DRLInspiredHeuristic, ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler
from ioMgmt.networkInterface import NetworkInterface


def runDemo():
    device = Device("LocalDevice", 1.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0, memoryCapacity=256.0, cacheSlots=3)
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
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0, memoryCapacity=256.0, cacheSlots=3)
    scheduler = Scheduler(device, [edge], StaticRule(50))
    sampleTask = Task("StaticTask", 75, 1, 10)
    targetServer = scheduler.submitTask(sampleTask)
    print(f"Static rule assigned {sampleTask.id} to {targetServer.name}")


def showListSchedulingExample():
    device = Device("LocalDevice", 1.0, energyCapacity=500.0)
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0, memoryCapacity=256.0, cacheSlots=3)
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
    edge = Server("EdgeServer", 3.0, wirelessDelay=5.0, memoryCapacity=256.0, cacheSlots=3)
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
    edge = Server("EdgeServer", 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0, memoryCapacity=256.0, cacheSlots=3)
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


def showIoManagementExample():
    device = Device("IoDevice", 1.0, energyCapacity=100.0)
    edge = Server("IoEdge", 3.0, wirelessBandwidth=10.0, memoryCapacity=256.0, cacheSlots=3)
    network = NetworkInterface(policy="FCFS", radioPolicy="predictive", idleTimeout=4.0,
                               wakeDelay=1.0, wakeEnergy=0.5, txPower=0.2,
                               idlePower=0.05, bandwidthVariation=0.1, randomSeed=7,
                               device=device)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    firstTask = Task("UploadOne", 20, 2, dataSize=20)
    secondTask = Task("UploadTwo", 15, 1, dataSize=10)
    scheduler.submitTask(firstTask, currentTime=0.0)
    scheduler.submitTask(secondTask, currentTime=0.0)
    scheduler.dispatchTask("IoEdge", currentTime=firstTask.transferCompletionTime)
    scheduler.dispatchTask("IoEdge", currentTime=secondTask.transferCompletionTime)
    scheduler.dispatchTask("IoEdge", currentTime=secondTask.transferCompletionTime + 5.0)
    print("\nEnergy-aware I/O management:")
    print(f"Upload policy: {network.policy}")
    print(f"Radio policy: {network.radioPolicy}")
    print(f"Radio state: {network.state}")
    print(f"Transmission energy: {network.transmissionEnergy:.2f}")
    print(f"Radio idle energy: {network.radioIdleEnergy:.2f}")
    print(f"Remaining battery: {device.remainingEnergy:.2f}")


def showMemoryManagementExample():
    device = Device("MemoryDevice", 1.0, memoryCapacity=96.0, schedulerMemoryReserve=16.0)
    edge = Server(
        "MemoryEdge", 3.0, wirelessDelay=1.0, wirelessBandwidth=12.0,
        memoryCapacity=128.0, cacheSlots=2, cachePolicy="PREDICTIVE",
        serviceImageSize=12.0, serviceLoadDelay=2.0
    )
    scheduler = Scheduler(device, [edge], StaticRule(0))
    tasks = [
        Task("AnalyticsTask", 25, 1, dataSize=8, memory=20, service="analytics"),
        Task("DatabaseTask", 30, 2, dataSize=10, memory=24, service="database"),
        Task("AnalyticsTaskTwo", 20, 1, dataSize=6, memory=16, service="analytics")
    ]
    print("\nMemory management:")
    for task in tasks:
        target = scheduler.submitTask(task, currentTime=0.0)
        print(f"{task.id}: {target.name if target else task.status}")
    print(f"Local scheduler reservation: {device.memoryManager.reservedSystemMemory:.2f} MB")
    print(f"Edge cache policy: {edge.memoryManager.cachePolicy}")
    print(f"Edge cache misses: {edge.memoryManager.cacheMisses}")
    print(f"Edge cache hits: {edge.memoryManager.cacheHits}")
    for nodeName, summary in scheduler.getMemorySummary().items():
        print(f"{nodeName} memory usage: {summary['currentUsedMemoryMb']:.2f}/{summary['capacityMb']:.2f} MB")
