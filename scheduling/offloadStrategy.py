from dataclasses import dataclass


@dataclass
class StaticRule:
    largeTaskThreshold: float = 50.0

    def chooseServer(self, task, device, servers):
        if task.size > self.largeTaskThreshold and servers:
            return servers[0]
        return device


@dataclass
class DRLInspiredHeuristic:
    largeTaskThreshold: float = 50.0
    localQueueLimit: int = 4
    remoteQueueLimit: int = 4
    localWorkLimit: float = 100.0

    def chooseServer(self, task, device, servers):
        if not servers:
            return device

        eligibleServers = [
            server for server in servers
            if server.queueLength() < self.remoteQueueLimit
            and server.computeSpeed > device.computeSpeed
        ]
        if not eligibleServers:
            return device

        bestRemote = min(
            eligibleServers,
            key=lambda server: (
                server.queueWork() / server.computeSpeed,
                server.queueLength()
            )
        )

        localBusy = (
            device.queueLength() >= self.localQueueLimit
            or device.queueWork() >= self.localWorkLimit
        )
        remoteLoad = bestRemote.queueWork() / bestRemote.computeSpeed
        localLoad = device.queueWork() / device.computeSpeed

        if task.size > self.largeTaskThreshold:
            return bestRemote
        if localBusy and remoteLoad < localLoad:
            return bestRemote
        return device


class ListSchedulingHeuristic:
    def chooseServer(self, task, device, servers):
        candidates = [server for server in servers]
        if device.canReserveTask(task):
            candidates.append(device)
        if not candidates:
            raise ValueError(f"No execution point can accept task {task.id}")
        return min(candidates, key=lambda server: server.estimateFinishTime(task))
