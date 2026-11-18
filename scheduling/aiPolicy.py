class AdaptiveGreenPolicy:
    def __init__(self, baseEnergyWeight=0.35):
        if not 0.0 <= baseEnergyWeight <= 1.0:
            raise ValueError("Energy weight must be between zero and one")
        self.baseEnergyWeight = baseEnergyWeight
        self.lowBatteryLevel = 0.30
        self.fastWirelessSpeed = 10.0
        self.batteryAdjustment = 0.25
        self.networkAdjustment = 0.15

    def getState(self, task, device, servers):
        wirelessSpeed = min(
            (server.wirelessBandwidth for server in servers), default=0.0
        )
        return {
            "remainingBattery": device.remainingEnergy,
            "availableBattery": device.availableEnergy,
            "localQueueLength": device.queueLength(),
            "wirelessSpeed": wirelessSpeed,
            "taskSize": task.size,
        }

    def getWeights(self, state, device):
        batteryFraction = 0.0
        if device.energyCapacity > 0:
            batteryFraction = state["availableBattery"] / device.energyCapacity
        energyWeight = self.baseEnergyWeight
        if batteryFraction < self.lowBatteryLevel:
            energyWeight += self.batteryAdjustment
        if state["wirelessSpeed"] < self.fastWirelessSpeed:
            energyWeight -= self.networkAdjustment
        energyWeight = max(0.10, min(0.90, energyWeight))
        return 1.0 - energyWeight, energyWeight

    def chooseServer(self, task, device, servers):
        if task.size < 0 or task.dataSize < 0:
            raise ValueError("Task size and data size cannot be negative")
        state = self.getState(task, device, servers)
        timeWeight, energyWeight = self.getWeights(state, device)
        localEnergy = device.estimateEnergy(task)
        timeScale = max(task.size / device.computeSpeed, 1.0)
        energyScale = max(localEnergy, 1.0)
        candidates = list(servers)
        if device.canReserveTask(task):
            candidates.append(device)
        if not candidates:
            raise ValueError(f"No execution point can accept task {task.id}")

        bestServer = None
        bestScore = float("inf")
        for server in candidates:
            # This estimate includes the workload waiting in the local/remote queue.
            finishTime = server.estimateFinishTime(task)
            energy = localEnergy if server is device else 0.0
            score = (timeWeight * finishTime / timeScale
                     + energyWeight * energy / energyScale)
            if score < bestScore:
                bestScore = score
                bestServer = server
        return bestServer
