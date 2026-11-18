import random


class NetworkInterface:
    def __init__(self, policy="FCFS", radioPolicy="fixed", idleTimeout=5.0,
                 predictiveFactor=1.5, minimumTimeout=1.0, wakeDelay=1.0,
                 wakeEnergy=0.5, txPower=0.2, idlePower=0.05,
                 bandwidthVariation=0.0, randomSeed=1, device=None):
        if policy not in ("FCFS", "PRIORITY"):
            raise ValueError("Upload policy must be FCFS or PRIORITY")
        if radioPolicy not in ("fixed", "predictive"):
            raise ValueError("Radio policy must be fixed or predictive")
        if idleTimeout < 0 or predictiveFactor <= 0 or minimumTimeout < 0:
            raise ValueError("Invalid radio timeout configuration")
        if wakeDelay < 0 or wakeEnergy < 0 or txPower < 0 or idlePower < 0:
            raise ValueError("Radio energy and delay values cannot be negative")
        if bandwidthVariation < 0 or bandwidthVariation >= 1:
            raise ValueError("Bandwidth variation must be between zero and one")
        self.policy = policy
        self.radioPolicy = radioPolicy
        self.idleTimeout = idleTimeout
        self.predictiveFactor = predictiveFactor
        self.minimumTimeout = minimumTimeout
        self.wakeDelay = wakeDelay
        self.wakeEnergy = wakeEnergy
        self.txPower = txPower
        self.idlePower = idlePower
        self.bandwidthVariation = bandwidthVariation
        self.random = random.Random(randomSeed)
        self.device = device
        self.uploadQueue = []
        self.sequence = 0
        self.activeTransfer = None
        self.activeStartTime = 0.0
        self.activeWirelessEnd = 0.0
        self.state = "idle"
        self.idleSince = 0.0
        self.lastArrivalTime = None
        self.interArrivalTimes = []
        self.recentArrivals = 5
        self.currentTime = 0.0
        self.currentBandwidth = None
        self.bandwidthByServer = {}
        self.transmissionEnergy = 0.0
        self.radioIdleEnergy = 0.0
        self.wakeEnergyConsumed = 0.0
        self.energyRejected = []
        self.stateTimes = {"active": 0.0, "idle": 0.0, "sleep": 0.0}
        self.bandwidthHistory = []

    def getIdleTimeout(self):
        if self.radioPolicy == "fixed" or not self.interArrivalTimes:
            return self.idleTimeout
        recent = self.interArrivalTimes[-self.recentArrivals:]
        averageInterval = sum(recent) / len(recent)
        return max(self.minimumTimeout, averageInterval * self.predictiveFactor)

    def enqueue(self, task, server, currentTime):
        if currentTime < self.currentTime:
            raise ValueError("Network time cannot move backwards")
        self.advance(currentTime)
        if self.lastArrivalTime is not None:
            interval = currentTime - self.lastArrivalTime
            if interval >= 0:
                self.interArrivalTimes.append(interval)
        self.lastArrivalTime = currentTime
        task.uploadServer = server
        task.status = "uploadQueued"
        task.transferStartTime = 0.0
        task.transferTime = 0.0
        task.communicationDelay = 0.0
        task.transferCompletionTime = float("inf")
        self.uploadQueue.append((task.priority, self.sequence, task, server, currentTime))
        self.sequence += 1
        self._startNext(currentTime)

    def _popNext(self):
        if not self.uploadQueue:
            return None
        if self.policy == "FCFS":
            index = min(range(len(self.uploadQueue)), key=lambda i: self.uploadQueue[i][1])
        else:
            index = min(range(len(self.uploadQueue)), key=lambda i: (self.uploadQueue[i][0], self.uploadQueue[i][1]))
        return self.uploadQueue.pop(index)

    def _getBandwidth(self, server):
        base = server.wirelessBandwidth
        current = self.bandwidthByServer.get(server.name, base)
        if self.bandwidthVariation:
            change = self.random.uniform(-self.bandwidthVariation, self.bandwidthVariation)
            current = current * (1.0 + change)
            current = min(base * (1.0 + self.bandwidthVariation), current)
            current = max(base * (1.0 - self.bandwidthVariation), current)
        self.bandwidthByServer[server.name] = current
        self.currentBandwidth = current
        self.bandwidthHistory.append(current)
        return current

    def _startNext(self, startTime):
        if self.activeTransfer is not None or not self.uploadQueue:
            return
        entry = self._popNext()
        priority, sequence, task, server, arrivalTime = entry
        bandwidth = self._getBandwidth(server)
        wirelessTime = task.dataSize / bandwidth if task.dataSize else 0.0
        txEnergy = self.txPower * wirelessTime
        if self.device is not None and txEnergy > self.device.availableEnergy:
            task.status = "energyRejected"
            task.location = "none"
            self.energyRejected.append(task.id)
            server.removeTask(task.id)
            task.status = "energyRejected"
            self._startNext(startTime)
            return
        wakeTime = self.wakeDelay if self.state == "sleep" else 0.0
        if wakeTime:
            self.wakeEnergyConsumed += self.wakeEnergy
            if self.device is not None:
                if self.wakeEnergy > self.device.availableEnergy:
                    task.status = "energyRejected"
                    task.location = "none"
                    self.energyRejected.append(task.id)
                    server.removeTask(task.id)
                    task.status = "energyRejected"
                    self._startNext(startTime)
                    return
                self.device.consumeWakeEnergy(self.wakeEnergy)
        transferStart = startTime + wakeTime
        if self.device is not None and txEnergy:
            self.device.consumeTransmissionEnergy(txEnergy)
        self.transmissionEnergy += txEnergy
        task.transferStartTime = transferStart
        wiredTime = task.dataSize / server.wiredBandwidth if server.wiredDelay > 0 and task.dataSize else 0.0
        task.transferTime = wirelessTime + wiredTime
        task.communicationDelay = server.wirelessDelay + server.wiredDelay + task.transferTime + wakeTime
        task.transferCompletionTime = transferStart + wirelessTime + wiredTime + server.wirelessDelay + server.wiredDelay
        task.status = "transferring"
        self.activeTransfer = (task, server)
        self.activeStartTime = transferStart
        self.activeWirelessEnd = transferStart + wirelessTime
        if not wakeTime:
            self._setState("active", transferStart)

    def _setState(self, newState, atTime):
        if newState == self.state:
            return
        duration = max(0.0, atTime - self.currentTime)
        self.stateTimes[self.state] += duration
        if self.state == "idle":
            idleCost = duration * self.idlePower
            if self.device is not None:
                idleCost = self.device.consumeRadioEnergy(idleCost)
            self.radioIdleEnergy += idleCost
        self.state = newState
        self.currentTime = atTime
        if newState == "idle":
            self.idleSince = atTime

    def cancelTask(self, taskId):
        remaining = [entry for entry in self.uploadQueue if entry[2].id != taskId]
        changed = len(remaining) != len(self.uploadQueue)
        self.uploadQueue = remaining
        if self.activeTransfer is not None and self.activeTransfer[0].id == taskId:
            self.activeTransfer = None
            if self.state == "active":
                self._setState("idle", self.currentTime)
                self.idleSince = self.currentTime
            return True
        return changed

    def advance(self, currentTime):
        if currentTime < self.currentTime:
            raise ValueError("Network time cannot move backwards")
        if self.activeTransfer is not None and self.state == "sleep" and self.activeStartTime <= currentTime:
            self._setState("active", self.activeStartTime)
        while self.activeTransfer is not None and self.activeWirelessEnd <= currentTime:
            task, server = self.activeTransfer
            finishTime = self.activeWirelessEnd
            self._setState("idle", finishTime)
            if task.transferCompletionTime <= finishTime:
                task.status = "ready"
            else:
                task.status = "transferring"
            self.activeTransfer = None
            self._startNext(finishTime)
        if self.activeTransfer is None:
            if self.state == "idle":
                sleepAt = self.idleSince + self.getIdleTimeout()
                if currentTime >= sleepAt:
                    self._setState("sleep", sleepAt)
            if self.uploadQueue:
                self._startNext(currentTime if self.state == "sleep" else max(self.currentTime, self.idleSince))
        if self.state == "idle" and currentTime > self.currentTime:
            duration = currentTime - self.currentTime
            self.stateTimes["idle"] += duration
            idleCost = duration * self.idlePower
            if self.device is not None:
                idleCost = self.device.consumeRadioEnergy(idleCost)
            self.radioIdleEnergy += idleCost
            self.currentTime = currentTime
        elif self.state == "sleep" and currentTime > self.currentTime:
            self.stateTimes["sleep"] += currentTime - self.currentTime
            self.currentTime = currentTime
        elif self.state == "active" and currentTime > self.currentTime:
            end = min(currentTime, self.activeWirelessEnd)
            if end > self.currentTime:
                self.stateTimes["active"] += end - self.currentTime
                self.currentTime = end

    def getEnergySummary(self):
        return {
            "computationEnergy": self.device.computationEnergy if self.device is not None else 0.0,
            "transmissionEnergy": self.transmissionEnergy,
            "radioIdleEnergy": self.radioIdleEnergy,
            "wakeEnergy": self.wakeEnergyConsumed,
            "totalIoEnergy": self.transmissionEnergy + self.radioIdleEnergy + self.wakeEnergyConsumed,
            "radioStateTimes": dict(self.stateTimes),
            "energyRejected": list(self.energyRejected),
            "bandwidthHistory": list(self.bandwidthHistory)
        }
