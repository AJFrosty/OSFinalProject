import sys
from time import perf_counter_ns as performanceCounter


class MeasuredPolicy:
    def __init__(self, policy):
        self.policy = policy
        self.decisionTimes = []

    def chooseServer(self, task, device, servers):
        start = performanceCounter()
        chosenServer = self.policy.chooseServer(task, device, servers)
        # Include the same energy fallback used by Scheduler in every timing.
        if chosenServer is device and not device.canReserveTask(task):
            if not servers:
                raise ValueError(f"No execution point can accept task {task.id}")
            chosenServer = min(servers, key=lambda server: server.estimateFinishTime(task))
        elapsed = performanceCounter() - start
        self.decisionTimes.append(elapsed / 1000.0)
        return chosenServer


def policyMemoryBytes(policy):
    # Count persistent instance data once; exclude shared code and test logs.
    seen = set()
    total = 0
    objects = [policy, vars(policy)]
    objects.extend(vars(policy).keys())
    objects.extend(vars(policy).values())
    for item in objects:
        if id(item) not in seen:
            seen.add(id(item))
            total += sys.getsizeof(item)
    return total
