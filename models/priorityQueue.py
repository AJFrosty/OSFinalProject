import heapq
from dataclasses import dataclass


@dataclass
class PriorityQueue:
    items: list = None
    sequence: int = 0

    def ensureItems(self):
        if self.items is None:
            self.items = []

    def push(self, task):
        self.ensureItems()
        if self.hasTask(task.id):
            raise ValueError(f"Task {task.id} is already in this queue")
        entry = (task.priority, self.sequence, task)
        heapq.heappush(self.items, entry)
        self.sequence += 1

    def pop(self):
        self.ensureItems()
        if not self.items:
            return None
        return heapq.heappop(self.items)[2]

    def popReady(self, currentTime):
        self.ensureItems()
        for entry in sorted(self.items):
            task = entry[2]
            if task.transferCompletionTime <= currentTime:
                self.items.remove(entry)
                heapq.heapify(self.items)
                return task
        return None

    def peek(self):
        self.ensureItems()
        if not self.items:
            return None
        return self.items[0][2]

    def removeTask(self, taskId):
        self.ensureItems()
        remaining = [entry for entry in self.items if entry[2].id != taskId]
        if len(remaining) == len(self.items):
            return False
        self.items = remaining
        heapq.heapify(self.items)
        return True

    def hasTask(self, taskId):
        self.ensureItems()
        return any(entry[2].id == taskId for entry in self.items)

    def getTasks(self):
        self.ensureItems()
        return [entry[2] for entry in sorted(self.items)]

    def queueLength(self):
        self.ensureItems()
        return len(self.items)
