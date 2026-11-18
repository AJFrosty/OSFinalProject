import sys
from time import perf_counter_ns as getTimeInNanoseconds


class AdaptiveGreenPolicy:
    def __init__(self, baseTimeWeight=0.6, baseEnergyWeight=0.4,
                 batterySensitivity=0.5, networkSensitivity=0.25,
                 networkEnergySensitivity=0.2, referenceBandwidth=12.0,
                 networkInterface=None):
        if baseTimeWeight < 0 or baseEnergyWeight < 0:
            raise ValueError("Base weights cannot be negative")
        if baseTimeWeight + baseEnergyWeight == 0:
            raise ValueError("At least one base weight must be positive")
        if batterySensitivity < 0 or networkSensitivity < 0 or networkEnergySensitivity < 0:
            raise ValueError("Weight sensitivities cannot be negative")
        if referenceBandwidth <= 0:
            raise ValueError("Reference bandwidth must be greater than zero")
        weightTotal = baseTimeWeight + baseEnergyWeight
        self.baseTimeWeight = baseTimeWeight / weightTotal
        self.baseEnergyWeight = baseEnergyWeight / weightTotal
        self.batterySensitivity = batterySensitivity
        self.networkSensitivity = networkSensitivity
        self.networkEnergySensitivity = networkEnergySensitivity
        self.referenceBandwidth = referenceBandwidth
        self.networkInterface = networkInterface
        self.decisionCount = 0
        self.totalDecisionTimeNs = 0
        self.decisionHistory = []
        self.lastState = None
        self.lastWeights = None
        self.lastScores = {}

    def setNetworkInterface(self, networkInterface):
        self.networkInterface = networkInterface

    def getWirelessSpeed(self, servers):
        if self.networkInterface is not None and self.networkInterface.currentBandwidth is not None:
            return self.networkInterface.currentBandwidth
        if not servers:
            return self.referenceBandwidth
        return max(server.wirelessBandwidth for server in servers)

    def buildState(self, task, device, servers):
        batteryRatio = 0.0
        if device.energyCapacity > 0:
            batteryRatio = device.remainingEnergy / device.energyCapacity
        return {
            "remainingBattery": max(0.0, min(1.0, batteryRatio)),
            "localQueueLength": device.queueLength(),
            "wirelessSpeed": self.getWirelessSpeed(servers),
            "taskSize": task.size
        }

    def getAdaptiveWeights(self, state):
        batteryPressure = 1.0 - state["remainingBattery"]
        bandwidthRatio = min(1.0, state["wirelessSpeed"] / self.referenceBandwidth)
        networkPressure = 1.0 - bandwidthRatio
        timeWeight = self.baseTimeWeight + networkPressure * self.networkSensitivity
        energyWeight = (
            self.baseEnergyWeight
            + batteryPressure * self.batterySensitivity
            + networkPressure * self.networkEnergySensitivity
        )
        weightTotal = timeWeight + energyWeight
        return timeWeight / weightTotal, energyWeight / weightTotal

    def getUploadWait(self):
        if self.networkInterface is None:
            return 0.0
        waitTime = 0.0
        if self.networkInterface.activeTransfer is not None:
            waitTime += max(0.0, self.networkInterface.activeWirelessEnd - self.networkInterface.currentTime)
        for entry in self.networkInterface.uploadQueue:
            task = entry[2]
            server = entry[3]
            bandwidth = self.networkInterface.bandwidthByServer.get(server.name, server.wirelessBandwidth)
            waitTime += task.dataSize / bandwidth if bandwidth > 0 else 0.0
        return waitTime

    def estimateEnergy(self, task, server, device):
        if not server.isRemote:
            return device.estimateEnergy(task)
        if self.networkInterface is None:
            return 0.0
        bandwidth = server.wirelessBandwidth
        if self.networkInterface is not None:
            bandwidth = self.networkInterface.bandwidthByServer.get(server.name, bandwidth)
        transferTime = task.dataSize / bandwidth if bandwidth > 0 else 0.0
        wakeEnergy = self.networkInterface.wakeEnergy if self.networkInterface.state == "sleep" else 0.0
        return self.networkInterface.txPower * transferTime + wakeEnergy

    def chooseServer(self, task, device, servers):
        decisionStart = getTimeInNanoseconds()
        state = self.buildState(task, device, servers)
        timeWeight, energyWeight = self.getAdaptiveWeights(state)
        candidates = list(servers)
        if device.canReserveTask(task):
            candidates.append(device)
        if not candidates:
            candidates = list(servers)
        if not candidates:
            raise ValueError(f"No execution point can accept task {task.id}")

        estimates = []
        for server in candidates:
            finishTime = server.estimateFinishTime(task)
            if server.isRemote:
                finishTime += self.getUploadWait()
            energyCost = self.estimateEnergy(task, server, device)
            estimates.append((server, max(0.0, finishTime), max(0.0, energyCost)))

        timeScale = max(1.0, max(item[1] for item in estimates))
        energyScale = max(1.0, max(item[2] for item in estimates))
        scores = {}
        for server, finishTime, energyCost in estimates:
            score = timeWeight * (finishTime / timeScale) + energyWeight * (energyCost / energyScale)
            scores[server.name] = score
        selectedServer = min(candidates, key=lambda server: scores[server.name])

        elapsed = getTimeInNanoseconds() - decisionStart
        self.decisionCount += 1
        self.totalDecisionTimeNs += elapsed
        self.lastState = dict(state)
        self.lastWeights = {"timeWeight": timeWeight, "energyWeight": energyWeight}
        self.lastScores = dict(scores)
        self.decisionHistory.append({
            "taskId": task.id,
            "state": dict(state),
            "timeWeight": timeWeight,
            "energyWeight": energyWeight,
            "selectedServer": selectedServer.name,
            "decisionTimeNs": elapsed
        })
        return selectedServer

    def getOverheadSummary(self):
        averageTime = self.totalDecisionTimeNs / self.decisionCount if self.decisionCount else 0.0
        memoryBytes = self.getMemoryUsageBytes()
        return {
            "decisionCount": self.decisionCount,
            "totalDecisionTimeNs": self.totalDecisionTimeNs,
            "averageDecisionTimeNs": averageTime,
            "averageDecisionTimeMs": averageTime / 1000000.0,
            "policyMemoryBytes": memoryBytes,
            "policyMemoryKB": memoryBytes / 1024.0
        }

    def measureMemory(self, value):
        memoryBytes = sys.getsizeof(value)
        if isinstance(value, dict):
            for key, item in value.items():
                memoryBytes += sys.getsizeof(key)
                memoryBytes += self.measureMemory(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                memoryBytes += self.measureMemory(item)
        return memoryBytes

    def getMemoryUsageBytes(self):
        return sys.getsizeof(self) + self.measureMemory(self.__dict__)
