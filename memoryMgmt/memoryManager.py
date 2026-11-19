from collections import OrderedDict, deque


class MemoryManager:
    def __init__(self, nodeName, capacityMb, cacheSlots=0, cachePolicy="LRU",
                 serviceImageSize=12.0, serviceLoadDelay=2.0, historyLimit=20):
        if capacityMb <= 0:
            raise ValueError("Memory capacity must be greater than zero")
        if cacheSlots < 0 or serviceImageSize < 0 or serviceLoadDelay < 0:
            raise ValueError("Cache configuration values cannot be negative")
        if cachePolicy not in ("LRU", "PREDICTIVE"):
            raise ValueError("Cache policy must be LRU or PREDICTIVE")
        self.nodeName = nodeName
        self.capacityMb = float(capacityMb)
        self.cacheSlots = int(cacheSlots)
        self.cachePolicy = cachePolicy
        self.serviceImageSize = float(serviceImageSize)
        self.serviceLoadDelay = float(serviceLoadDelay)
        self.taskMemory = {}
        self.usedTaskMemory = 0.0
        self.systemReservations = {}
        self.serviceCache = OrderedDict()
        self.cacheMemoryUsed = 0.0
        self.serviceHistory = deque(maxlen=historyLimit)
        self.admissionRejections = []
        self.cacheHits = 0
        self.cacheMisses = 0
        self.cacheEvictions = 0
        self.peakUsedMemory = 0.0
        self.memorySamples = []

    @property
    def reservedSystemMemory(self):
        return sum(self.systemReservations.values())

    @property
    def totalUsedMemory(self):
        return self.reservedSystemMemory + self.usedTaskMemory + self.cacheMemoryUsed

    @property
    def availableMemory(self):
        return max(0.0, self.capacityMb - self.totalUsedMemory)

    @property
    def utilization(self):
        return min(1.0, self.totalUsedMemory / self.capacityMb)

    @property
    def cacheHitRate(self):
        accesses = self.cacheHits + self.cacheMisses
        return self.cacheHits / accesses if accesses else 0.0

    def reserveSystemMemory(self, owner, amountMb):
        if amountMb < 0:
            raise ValueError("System memory reservation cannot be negative")
        existing = self.systemReservations.get(owner, 0.0)
        extra = amountMb - existing
        if extra > self.availableMemory:
            raise MemoryError(
                f"{self.nodeName} cannot reserve {amountMb:.2f} MB for {owner}"
            )
        self.systemReservations[owner] = float(amountMb)
        self.updatePeak()
        return self.systemReservations[owner]

    def canAdmit(self, task):
        if task.memory < 0:
            raise ValueError("Task memory footprint cannot be negative")
        if task.id in self.taskMemory:
            return True
        return task.memory <= self.availableMemory

    def recordRejection(self, task, currentTime=0.0, reason="insufficientMemory"):
        rejection = {
            "taskId": task.id,
            "node": self.nodeName,
            "requestedMb": float(task.memory),
            "availableMb": self.availableMemory,
            "time": float(currentTime),
            "reason": reason
        }
        self.admissionRejections.append(rejection)
        return rejection

    def admit(self, task):
        if task.id in self.taskMemory:
            raise ValueError(f"Task {task.id} already holds memory on {self.nodeName}")
        if not self.canAdmit(task):
            return False
        self.taskMemory[task.id] = float(task.memory)
        self.usedTaskMemory += float(task.memory)
        self.updatePeak()
        return True

    def release(self, taskId):
        amount = self.taskMemory.pop(taskId, None)
        if amount is None:
            return False
        self.usedTaskMemory = max(0.0, self.usedTaskMemory - amount)
        return True

    def accessService(self, service, currentTime=0.0):
        if self.cacheSlots <= 0:
            return 0.0
        if not service:
            service = "default"
        self.serviceHistory.append(service)
        if service in self.serviceCache:
            self.cacheHits += 1
            self.serviceCache.move_to_end(service)
            self.serviceCache[service] = float(currentTime)
            return 0.0

        self.cacheMisses += 1
        while self.serviceCache and (
            len(self.serviceCache) >= self.cacheSlots
            or self.availableMemory < self.serviceImageSize
        ):
            self.evictService()

        if len(self.serviceCache) < self.cacheSlots and self.availableMemory >= self.serviceImageSize:
            self.serviceCache[service] = float(currentTime)
            self.cacheMemoryUsed += self.serviceImageSize
            self.updatePeak()
        return self.serviceLoadDelay

    def evictService(self):
        if not self.serviceCache:
            return None
        if self.cachePolicy == "LRU":
            service, lastAccess = self.serviceCache.popitem(last=False)
        else:
            service = min(
                self.serviceCache,
                key=lambda item: (self.predictiveScore(item), self.serviceCache[item])
            )
            lastAccess = self.serviceCache.pop(service)
        self.cacheMemoryUsed = max(0.0, self.cacheMemoryUsed - self.serviceImageSize)
        self.cacheEvictions += 1
        return service, lastAccess

    def predictiveScore(self, service):
        score = 0.0
        recent = list(self.serviceHistory)
        for age, arrival in enumerate(reversed(recent)):
            if arrival == service:
                score += 1.0 / (age + 1)
        return score

    def setCachePolicy(self, cachePolicy):
        if cachePolicy not in ("LRU", "PREDICTIVE"):
            raise ValueError("Cache policy must be LRU or PREDICTIVE")
        self.cachePolicy = cachePolicy

    def sample(self, currentTime):
        value = {
            "time": float(currentTime),
            "usedMemoryMb": self.totalUsedMemory,
            "utilization": self.utilization,
            "cacheHitRate": self.cacheHitRate,
            "cacheEntries": len(self.serviceCache)
        }
        self.memorySamples.append(value)
        self.updatePeak()
        return value

    def updatePeak(self):
        self.peakUsedMemory = max(self.peakUsedMemory, self.totalUsedMemory)

    def getSummary(self):
        averageUtilization = (
            sum(sample["utilization"] for sample in self.memorySamples) / len(self.memorySamples)
            if self.memorySamples else self.utilization
        )
        return {
            "node": self.nodeName,
            "capacityMb": self.capacityMb,
            "usedTaskMemoryMb": self.usedTaskMemory,
            "cacheMemoryMb": self.cacheMemoryUsed,
            "reservedSystemMemoryMb": self.reservedSystemMemory,
            "currentUsedMemoryMb": self.totalUsedMemory,
            "peakUsedMemoryMb": self.peakUsedMemory,
            "averageUtilization": averageUtilization,
            "currentUtilization": self.utilization,
            "admissionRejections": list(self.admissionRejections),
            "rejectionCount": len(self.admissionRejections),
            "cacheHits": self.cacheHits,
            "cacheMisses": self.cacheMisses,
            "cacheHitRate": self.cacheHitRate,
            "cacheEvictions": self.cacheEvictions,
            "cachePolicy": self.cachePolicy,
            "cacheEntries": list(self.serviceCache.keys()),
            "samples": list(self.memorySamples)
        }
