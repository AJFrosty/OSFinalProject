from dataclasses import dataclass


@dataclass
class Scheduler:
    device: object
    servers: list
    strategy: object
    currentTime: float = 0.0

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
        return self.currentTime

    def submitTask(self, task, currentTime=None):
        now = self.updateTime(currentTime)
        if task.status == "running":
            raise ValueError(f"Task {task.id} is already running")

        if task.status in ("ready", "transferring"):
            currentServer = self.findServer(task.location)
            if currentServer is None or not currentServer.removeTask(task.id):
                raise ValueError(f"Task {task.id} could not be found in its current queue")
        elif task.status not in ("new", "waiting"):
            raise ValueError(f"Task {task.id} cannot be scheduled from status {task.status}")

        targetServer = self.strategy.chooseServer(task, self.device, self.servers)
        if targetServer is self.device and not self.device.canReserveTask(task):
            if not self.servers:
                raise ValueError(f"Insufficient local energy and no remote server is available for task {task.id}")
            targetServer = min(self.servers, key=lambda server: server.estimateFinishTime(task))

        targetServer.addTask(task, now)
        return targetServer

    def dispatchTask(self, serverName, currentTime=None):
        now = self.updateTime(currentTime)
        server = self.findServer(serverName)
        if server is None:
            raise ValueError(f"Unknown server: {serverName}")
        return server.nextTask(now)

    def getQueueSummary(self):
        summary = {}
        summary[self.device.name] = [task.id for task in self.device.getQueueTasks()]
        for server in self.servers:
            summary[server.name] = [task.id for task in server.getQueueTasks()]
        return summary
