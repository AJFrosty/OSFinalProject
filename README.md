# Distributed Scheduling: Implementation Requirements 1 to 5

This implementation covers the first five implementation requirements in the COMP3320 project document.

## Included

- One priority queue for the local device and a separate queue for every remote server.
- Stable priority ordering: a lower numeric priority value is served first. Tasks with equal priority are served in arrival order.
- Task placement through a static offloading rule.
- Task placement through a state-aware, DRL-inspired heuristic. It considers task size, local queue pressure, remote queue pressure, and server speed. It is a rule-based approximation, not a trained reinforcement-learning model.
- Queue migration when a task is resubmitted while it is waiting.
- Three execution environments: a slower local device, faster edge server, and fastest cloud server.
- Configurable wireless and wired delays. The local device has no communication delay, edge servers use wireless delay, and the cloud uses wireless plus wired delay.
- A list-scheduling heuristic that selects the eligible execution point with the earliest estimated finish time.
- A local energy capacity and an energy cost per unit of task workload.
- Energy reservation when a task enters the local queue, preventing queued tasks from collectively exceeding the battery budget.
- Local computation energy is deducted when a task is dispatched for execution.
- Tasks that cannot fit within the remaining local energy budget are sent to a remote server when one is available. Otherwise, submission is rejected.
- Data upload time is calculated from task data size and the configured network bandwidth.
- Cloud uploads include both wireless and wired transfer time.
- Remote tasks remain in the transferring state and cannot be dispatched until their communication delay has elapsed.
- Dispatch checks the simulation time and starts only tasks whose transfer has completed. Priority ordering is preserved among tasks that are ready to execute.

## Project structure

```text
edgeScheduler/
    main.py
    run.py
    testImplementation.py
    models/
        task.py
        priorityQueue.py
        server.py
        device.py
    scheduling/
        offloadStrategy.py
        scheduler.py
```

User-defined filenames, variables, classes, and methods use camelCase or PascalCase, with no underscores. Python's required special method names such as `__init__` are retained where necessary.

## Run

From the `edgeScheduler` directory, run:

```bash
python run.py
```

Run the implementation checks:

```bash
python testImplementation.py
```

## Execution-time and communication model

Each server estimates a task's finish time as:

```text
(queue workload / compute speed)
+ communication delay
+ (task workload / compute speed)
```

The local device has zero communication delay. An edge server adds its wireless delay and upload time. The cloud adds its wireless and wired delays and upload times.

Upload time is calculated as:

```text
wireless upload time = task data size / wireless bandwidth
wired upload time = task data size / wired bandwidth
```

For an edge server, only wireless upload time is used. For a cloud server, wireless and wired upload times are added together. Fixed wireless and wired delays are then added to obtain the total communication delay.

`Task.dataSize` is measured in MB. `wirelessBandwidth` and `wiredBandwidth` are measured in MB per simulation time unit. All delay and completion-time values use the same simulation time unit. Bandwidth must be greater than zero.

Default sample configuration:

- Local device: compute speed 1.0, no network delay or upload.
- Edge server: compute speed 3.0, wireless delay 5.0, wireless bandwidth 10.0 MB per time unit.
- Cloud server: compute speed 5.0, wireless delay 5.0, wired delay 10.0, wireless bandwidth 10.0 MB per time unit, wired bandwidth 100.0 MB per time unit.

The numeric values are demonstration settings and can be changed for experiments. `Task.size` represents compute workload, while `Task.dataSize` represents input data size in MB.

## Transfer completion and dispatch

When a task is submitted to a remote server, the scheduler records its transfer start time, upload time, total communication delay, and transfer completion time. The task is placed in the destination queue with status `transferring`.

`Scheduler.dispatchTask(serverName, currentTime)` only dispatches a task when its transfer completion time is less than or equal to the supplied simulation time. If no queued task has completed its transfer, it returns `None` and leaves the tasks in the queue. When the transfer completes, the task becomes eligible for dispatch. Priority is applied among tasks that are eligible at that time.

The scheduler simulation clock is monotonic. A supplied `currentTime` cannot be earlier than the scheduler's current time. When `currentTime` is omitted, the scheduler uses its current simulation time.

## List scheduling

`ListSchedulingHeuristic` compares the estimated finish time on the local device, edge servers, and cloud server. It selects the eligible server with the lowest estimate. The local device is only eligible when it can reserve enough energy for the task.

## Energy model

The local device calculates a task's computation energy as:

```text
energy cost = task size * energy per work unit
```

The default energy cost is 0.5 per unit of task workload. `energyCapacity` and `energyPerWorkUnit` can be configured when creating the local device.

Energy for queued local tasks is reserved at admission. When a local task is dispatched, its reserved amount is released and deducted from `remainingEnergy`. This prevents the scheduler from assigning more local work than the available energy can support. Remote execution does not consume the local CPU computation-energy budget in this implementation.

## Current scope

Requirement 5 models data-size-dependent upload time and prevents remote execution before communication completes. It does not yet implement a shared wireless upload queue, transmission-energy accounting, radio sleep states, or variable bandwidth over time; those belong to the later I/O management requirement. Memory admission and service-cache policies are also outside the scope of requirements 1 to 5.
