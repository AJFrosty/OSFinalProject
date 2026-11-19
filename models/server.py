from models.priorityQueue import PriorityQueue
from memoryMgmt.memoryManager import MemoryManager


class Server:
    def __init__(self, name, computeSpeed, queue=None, wirelessDelay=0.0, wiredDelay=0.0,
                 wirelessBandwidth=10.0, wiredBandwidth=100.0, isRemote=True,
                 memoryCapacity=512.0, cacheSlots=0, cachePolicy="LRU",
                 serviceImageSize=12.0, serviceLoadDelay=2.0):
        if computeSpeed <= 0:
            raise ValueError("Compute speed must be greater than zero")
        if wirelessDelay < 0 or wiredDelay < 0:
            raise ValueError("Network delays cannot be negative")
        if wirelessBandwidth <= 0 or wiredBandwidth <= 0:
            raise ValueError("Network bandwidth must be greater than zero")
        self.name = name
        self.computeSpeed = computeSpeed
        self.queue = queue
        self.wirelessDelay = wirelessDelay
        self.wiredDelay = wiredDelay
        self.wirelessBandwidth = wirelessBandwidth
        self.wiredBandwidth = wiredBandwidth
        self.isRemote = isRemote
        self.memoryManager = MemoryManager(
            name, memoryCapacity, cacheSlots, cachePolicy,
            serviceImageSize, serviceLoadDelay
        )
        self.runningTasks = {}

    def ensureQueue(self):
        if self.queue is None:
            self.queue = PriorityQueue()

    def addTask(self, task, currentTime=0.0):
        self.ensureQueue()
        if task.dataSize < 0 or task.memory < 0:
            raise ValueError("Task data size and memory footprint cannot be negative")
        if not self.memoryManager.admit(task):
            self.memoryManager.recordRejection(task, currentTime)
            return False
        try:
            task.cacheLoadDelay = self.memoryManager.accessService(task.service, currentTime)
            self.queue.push(task)
        except Exception:
            self.memoryManager.release(task.id)
            raise
        task.location = self.name
        task.memoryNode = self.name
        task.transferStartTime = currentTime if self.isRemote else 0.0
        task.transferTime = self.getTransferTime(task)
        task.communicationDelay = self.getCommunicationDelay(task) + task.cacheLoadDelay
        task.transferCompletionTime = currentTime + task.communicationDelay
        task.status = "transferring" if task.communicationDelay > 0 else "ready"
        return True

    def nextTask(self, currentTime=0.0):
        self.ensureQueue()
        for queuedTask in self.queue.getTasks():
            if queuedTask.status in ("transferring", "ready") and queuedTask.transferCompletionTime <= currentTime:
                queuedTask.status = "ready"
        task = self.queue.popReady(currentTime)
        if task is not None:
            task.status = "running"
            self.runningTasks[task.id] = task
        return task

    def completeTask(self, taskId):
        task = self.runningTasks.pop(taskId, None)
        if task is None:
            return False
        self.memoryManager.release(taskId)
        task.status = "completed"
        task.location = self.name
        return True

    def removeTask(self, taskId):
        for task in self.getQueueTasks():
            if task.id == taskId:
                self.queue.removeTask(taskId)
                self.memoryManager.release(taskId)
                task.status = "new"
                task.location = "none"
                task.memoryNode = "none"
                task.transferStartTime = 0.0
                task.transferTime = 0.0
                task.communicationDelay = 0.0
                task.transferCompletionTime = 0.0
                task.cacheLoadDelay = 0.0
                return True
        return False

    def queueWork(self):
        return sum(task.size for task in self.getQueueTasks())

    def queueLength(self):
        self.ensureQueue()
        return self.queue.queueLength()

    def getQueueTasks(self):
        self.ensureQueue()
        return self.queue.getTasks()

    def getTransferSize(self, task):
        return task.dataSize + task.memory

    def getTransferTime(self, task):
        if not self.isRemote:
            return 0.0
        transferSize = self.getTransferSize(task)
        if transferSize == 0:
            return 0.0
        wirelessTime = transferSize / self.wirelessBandwidth
        wiredTime = transferSize / self.wiredBandwidth if self.wiredDelay > 0 else 0.0
        return wirelessTime + wiredTime

    def getCommunicationDelay(self, task):
        if not self.isRemote:
            return 0.0
        return self.wirelessDelay + self.wiredDelay + self.getTransferTime(task)

    def estimateFinishTime(self, task):
        queuedWork = sum(
            queuedTask.size for queuedTask in self.getQueueTasks()
            if queuedTask.id != task.id
        )
        runningWork = sum(runningTask.size for runningTask in self.runningTasks.values())
        queueTime = (queuedWork + runningWork) / self.computeSpeed
        taskTime = task.size / self.computeSpeed
        return queueTime + self.getCommunicationDelay(task) + task.cacheLoadDelay + taskTime

    def getMemorySummary(self):
        return self.memoryManager.getSummary()
