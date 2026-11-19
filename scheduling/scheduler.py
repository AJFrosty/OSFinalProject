from dataclasses import dataclass
from ioMgmt.networkInterface import NetworkInterface


@dataclass
class Scheduler:
    device: object
    servers: list
    strategy: object
    currentTime: float = 0.0
    networkInterface: object = None

    def __post_init__(self):
        if self.networkInterface is None:
            self.networkInterface = NetworkInterface(device=self.device)
        elif self.networkInterface.device is None:
            self.networkInterface.device = self.device
        self.device.memoryManager.reserveSystemMemory(
            "adaptiveScheduler", self.device.schedulerMemoryReserve
        )
        if hasattr(self.strategy, "setNetworkInterface"):
            self.strategy.setNetworkInterface(self.networkInterface)

    def findServer(self, serverName):
        if self.device.name == serverName:
            return self.device
        for server in self.servers:
            if server.name == serverName:
                return server
        return None

    def updateTime(self, currentTime):
        if currentTime is None:
            return self.currentTime
        if currentTime < self.currentTime:
            raise ValueError("Simulation time cannot move backwards")
        self.currentTime = currentTime
        self.networkInterface.advance(currentTime)
        return self.currentTime

    def submitTask(self, task, currentTime=None):
        now = self.updateTime(currentTime)
        if task.status == "running":
            raise ValueError(f"Task {task.id} is already running")

        if task.status in ("ready", "transferring", "uploadQueued"):
            currentServer = self.findServer(task.location)
            if currentServer is None or not currentServer.removeTask(task.id):
                raise ValueError(f"Task {task.id} could not be found in its current queue")
            self.networkInterface.cancelTask(task.id)
        elif task.status not in ("new", "waiting"):
            raise ValueError(f"Task {task.id} cannot be scheduled from status {task.status}")

        preferredServer = self.strategy.chooseServer(task, self.device, self.servers)
        allServers = [self.device] + list(self.servers)
        remainingServers = [server for server in allServers if server is not preferredServer]
        remainingServers.sort(key=lambda server: server.estimateFinishTime(task))
        candidates = ([preferredServer] if preferredServer in allServers else []) + remainingServers
        memoryRejected = False
        energyRejected = False

        for targetServer in candidates:
            if targetServer is self.device and not self.device.canReserveTask(task):
                energyRejected = True
                continue
            if not targetServer.memoryManager.canAdmit(task):
                targetServer.memoryManager.recordRejection(task, now)
                memoryRejected = True
                continue
            added = targetServer.addTask(task, now)
            if not added:
                memoryRejected = True
                continue
            if targetServer.isRemote:
                self.networkInterface.enqueue(task, targetServer, now)
            return targetServer

        task.location = "none"
        task.memoryNode = "none"
        if memoryRejected:
            task.status = "memoryRejected"
        elif energyRejected:
            task.status = "new"
            raise ValueError(f"Insufficient local energy and no remote server can admit task {task.id}")
        else:
            task.status = "rejected"
        return None

    def dispatchTask(self, serverName, currentTime=None):
        now = self.updateTime(currentTime)
        server = self.findServer(serverName)
        if server is None:
            raise ValueError(f"Unknown server: {serverName}")
        return server.nextTask(now)

    def completeTask(self, serverName, taskId):
        server = self.findServer(serverName)
        if server is None:
            raise ValueError(f"Unknown server: {serverName}")
        return server.completeTask(taskId)

    def getQueueSummary(self):
        summary = {}
        summary[self.device.name] = [task.id for task in self.device.getQueueTasks()]
        for server in self.servers:
            summary[server.name] = [task.id for task in server.getQueueTasks()]
        return summary

    def getMemorySummary(self):
        summary = {self.device.name: self.device.getMemorySummary()}
        for server in self.servers:
            summary[server.name] = server.getMemorySummary()
        return summary
