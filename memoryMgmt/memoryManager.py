from collections import OrderedDict, defaultdict
import sys


class MemoryManager:
    def __init__(self, capacityMb, cacheSlots=3, schedulerMemoryMb=0.0,
                 cachePolicy="LRU", serviceHistory=5):
        if capacityMb < 0 or schedulerMemoryMb < 0 or schedulerMemoryMb > capacityMb:
            raise ValueError("Invalid memory capacity or scheduler reservation")
        if cacheSlots < 0 or cachePolicy not in ("LRU", "PREDICTIVE"):
            raise ValueError("Invalid cache configuration")
        self.capacityMb = float(capacityMb)
        self.schedulerMemoryMb = float(schedulerMemoryMb)
        self.cacheCapacity = int(cacheSlots)
        self.cachePolicy = cachePolicy
        self.serviceHistory = max(1, int(serviceHistory))
        self.reservedMemory = 0.0
        self.taskMemory = {}
        self.rejections = []
        self.cache = OrderedDict()
        self.serviceArrivals = defaultdict(int)
        self.recentServices = []
        self.cacheHits = 0
        self.cacheMisses = 0
        self.cacheLoads = 0
        self.peakUsedMemory = self.schedulerMemoryMb
        self.memorySamples = []
        self.migrationDataMb = 0.0

    @property
    def availableMemory(self):
        return max(0.0, self.capacityMb - self.schedulerMemoryMb - self.reservedMemory)

    @property
    def usedMemory(self):
        return self.schedulerMemoryMb + self.reservedMemory

    def canAdmit(self, task):
        return task.memory >= 0 and task.memory <= self.availableMemory

    def admitTask(self, task):
        if task.id in self.taskMemory:
            return True
        if task.memory < 0:
            raise ValueError("Task memory footprint cannot be negative")
        if not self.canAdmit(task):
            self.rejections.append(task.id)
            return False
        self.taskMemory[task.id] = float(task.memory)
        self.reservedMemory += float(task.memory)
        self.peakUsedMemory = max(self.peakUsedMemory, self.usedMemory)
        self.memorySamples.append(self.usedMemory)
        return True

    def releaseTask(self, taskId):
        amount = self.taskMemory.pop(taskId, 0.0)
        self.reservedMemory = max(0.0, self.reservedMemory - amount)
        self.memorySamples.append(self.usedMemory)
        return amount

    def getMigrationTime(self, task, bandwidth):
        if bandwidth <= 0:
            raise ValueError("Migration bandwidth must be greater than zero")
        amount = float(task.dataSize) + float(task.memory)
        self.migrationDataMb += amount
        return amount / bandwidth

    def accessService(self, service, loadTime=1.0):
        if loadTime < 0:
            raise ValueError("Service load time cannot be negative")
        self.serviceArrivals[service] += 1
        self.recentServices.append(service)
        self.recentServices = self.recentServices[-self.serviceHistory:]
        if self.cacheCapacity == 0:
            self.cacheMisses += 1
            self.cacheLoads += 1
            return loadTime
        if service in self.cache:
            self.cacheHits += 1
            self.cache.move_to_end(service)
            return 0.0
        self.cacheMisses += 1
        self.cacheLoads += 1
        if len(self.cache) >= self.cacheCapacity:
            victim = self._chooseVictim()
            self.cache.pop(victim, None)
        self.cache[service] = True
        return loadTime

    def _chooseVictim(self):
        if self.cachePolicy == "LRU":
            return next(iter(self.cache))
        recentCounts = {service: self.recentServices.count(service) for service in self.cache}
        return min(self.cache, key=lambda service: (recentCounts[service], self.cache[service]))

    def setCachePolicy(self, policy):
        if policy not in ("LRU", "PREDICTIVE"):
            raise ValueError("Cache policy must be LRU or PREDICTIVE")
        self.cachePolicy = policy

    def getSummary(self):
        sampleCount = len(self.memorySamples)
        averageUsed = sum(self.memorySamples) / sampleCount if sampleCount else self.usedMemory
        totalCacheRequests = self.cacheHits + self.cacheMisses
        return {
            "capacityMb": self.capacityMb,
            "schedulerMemoryMb": self.schedulerMemoryMb,
            "currentUsedMemoryMb": self.usedMemory,
            "peakUsedMemoryMb": self.peakUsedMemory,
            "averageUsedMemoryMb": averageUsed,
            "availableMemoryMb": self.availableMemory,
            "admissionRejections": list(self.rejections),
            "cachePolicy": self.cachePolicy,
            "cacheHits": self.cacheHits,
            "cacheMisses": self.cacheMisses,
            "cacheHitRate": self.cacheHits / totalCacheRequests if totalCacheRequests else 0.0,
            "cacheLoads": self.cacheLoads,
            "cachedServices": list(self.cache.keys()),
            "migrationDataMb": self.migrationDataMb,
            "policyMemoryBytes": sys.getsizeof(self.cache) + sys.getsizeof(self.taskMemory)
        }
