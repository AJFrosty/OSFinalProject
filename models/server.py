from models.priorityQueue import PriorityQueue


class Server:
    def __init__(self, name, computeSpeed, queue=None, wirelessDelay=0.0, wiredDelay=0.0,
                 wirelessBandwidth=10.0, wiredBandwidth=100.0, isRemote=True):
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

    def ensureQueue(self):
        if self.queue is None:
            self.queue = PriorityQueue()

    def addTask(self, task, currentTime=0.0):
        self.ensureQueue()
        if task.dataSize < 0:
            raise ValueError("Task data size cannot be negative")
        self.queue.push(task)
        task.location = self.name
        task.transferStartTime = currentTime if self.isRemote else 0.0
        task.transferTime = self.getTransferTime(task)
        task.communicationDelay = self.getCommunicationDelay(task)
        task.transferCompletionTime = currentTime + task.communicationDelay
        task.status = "transferring" if task.communicationDelay > 0 else "ready"

    def nextTask(self, currentTime=0.0):
        self.ensureQueue()
        for task in self.queue.getTasks():
            if task.status == "transferring" and task.transferCompletionTime <= currentTime:
                task.status = "ready"
        task = self.queue.popReady(currentTime)
        if task is not None:
            task.status = "running"
        return task

    def removeTask(self, taskId):
        self.ensureQueue()
        for task in self.queue.getTasks():
            if task.id == taskId:
                self.queue.removeTask(taskId)
                task.status = "new"
                task.location = "none"
                task.transferStartTime = 0.0
                task.transferTime = 0.0
                task.communicationDelay = 0.0
                task.transferCompletionTime = 0.0
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

    def getTransferTime(self, task):
        if not self.isRemote or task.dataSize == 0:
            return 0.0
        wirelessTime = task.dataSize / self.wirelessBandwidth
        wiredTime = task.dataSize / self.wiredBandwidth if self.wiredDelay > 0 else 0.0
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
        queueTime = queuedWork / self.computeSpeed
        taskTime = task.size / self.computeSpeed
        return queueTime + self.getCommunicationDelay(task) + taskTime
