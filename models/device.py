from models.server import Server


class Device(Server):
    def __init__(self, name="LocalDevice", computeSpeed=1.0, energyCapacity=100.0, energyPerWorkUnit=0.5):
        super().__init__(name=name, computeSpeed=computeSpeed, isRemote=False)
        if energyCapacity < 0:
            raise ValueError("Energy capacity cannot be negative")
        if energyPerWorkUnit < 0:
            raise ValueError("Energy per work unit cannot be negative")
        self.energyCapacity = energyCapacity
        self.remainingEnergy = energyCapacity
        self.energyPerWorkUnit = energyPerWorkUnit
        self.reservedEnergy = 0.0

    @property
    def availableEnergy(self):
        return max(0.0, self.remainingEnergy - self.reservedEnergy)

    def estimateEnergy(self, task):
        return task.size * self.energyPerWorkUnit

    def canReserveTask(self, task):
        return self.estimateEnergy(task) <= self.availableEnergy

    def addTask(self, task, currentTime=0.0):
        energyCost = self.estimateEnergy(task)
        if not self.canReserveTask(task):
            raise ValueError(f"Insufficient local energy for task {task.id}")
        super().addTask(task, currentTime)
        self.reservedEnergy += energyCost

    def removeTask(self, taskId):
        task = next((item for item in self.getQueueTasks() if item.id == taskId), None)
        if task is None:
            return False
        if super().removeTask(taskId):
            self.reservedEnergy = max(0.0, self.reservedEnergy - self.estimateEnergy(task))
            return True
        return False

    def consumeEnergy(self, task):
        energyCost = self.estimateEnergy(task)
        if energyCost > self.remainingEnergy:
            raise ValueError(f"Insufficient local energy to execute task {task.id}")
        self.remainingEnergy -= energyCost
        return energyCost

    def nextTask(self, currentTime=0.0):
        task = super().nextTask(currentTime)
        if task is not None:
            self.reservedEnergy = max(0.0, self.reservedEnergy - self.estimateEnergy(task))
            self.consumeEnergy(task)
        return task
