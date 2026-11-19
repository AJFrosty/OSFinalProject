# Distributed Edge Scheduling Simulator

COMP3320 operating systems project implementation covering Requirements 1–6 and 8, plus the completed Requirement 7 memory-management extension. The code uses camelCase for user-defined filenames, variables, attributes and methods, with PascalCase for classes. Python's required special method names (such as `__init__`) are retained.

## Project Structure

```text
edgeScheduler/
    main.py
    run.py
    runRequirement6.py
    runAllExperiments.py
    allScenarioResults.json
    requirement6Results.json
    testImplementation.py
    testRequirement6.py
    testRequirement7.py
    testRequirement8.py
    testScenarioRunner.py
    models/
        task.py
        priorityQueue.py
        server.py
        device.py
    scheduling/
        offloadStrategy.py
        adaptiveGreenPolicy.py
        scheduler.py
    memoryMgmt/
        memoryManager.py
    ioMgmt/
        networkInterface.py
    experiments/
        greenPolicyExperiment.py
        scenarioRunner.py
        resultsPlotter.py
    graphs/
        makespanComparison.png
        energyImpact.png
        queueOccupancy.png
        energyMakespanTradeoff.png
        memoryAndCacheOverTime.png
        energyBreakdown.png
```

## Requirements and Run Instructions

Use Python 3.10 or newer. The simulator and tests use the Python standard library. Matplotlib is needed only to generate the charts.

```bash
python -m pip install -r requirements.txt
python run.py
```

Run all tests:

```bash
python testImplementation.py
python testRequirement6.py
python testRequirement7.py
python testRequirement8.py
python testScenarioRunner.py
```

## Requirements 1–5: Distributed Scheduling

### Distributed priority queues

The local device, edge server and cloud server each have a separate priority queue. Lower numeric priority values are treated as higher priority. Equal-priority tasks retain FIFO order. Queued tasks can migrate between nodes through the scheduler.

### Offloading policies

- `StaticRule` offloads tasks whose compute size exceeds its configured threshold.
- `DRLInspiredHeuristic` provides the logic-based offloading strategy for Requirement 2. It considers task size and queue pressure; it is not a trained reinforcement-learning agent.
- `ListSchedulingHeuristic` compares estimated completion time at eligible execution points and chooses the earliest finish.

### Heterogeneous execution and communication

The local device is the slowest execution point, edge servers are faster, and the cloud is fastest. Remote execution includes wireless delay and, for the cloud, wired backhaul delay. The wireless interface uses a single upload queue. Remote tasks cannot execute before upload and communication delay have elapsed.

Requirement 7 extends the transfer payload from input data alone to `dataSize + memory`, because a migrating task must transfer its memory state as well as its input.

### Local energy budget

The device reserves energy for tasks admitted to its local queue. Local execution consumes energy on dispatch. The scheduler avoids admitting local work that would exceed the remaining battery budget and redirects tasks when another node is able to accept them.

## Requirement 6: Adaptive Green Process Scheduling

`AdaptiveGreenPolicy` implements the permitted adaptive multi-objective scoring option. It uses a state containing remaining battery, local queue length, current wireless speed and task size. It estimates completion time and device-side energy for each candidate, normalizes both measurements and applies adaptive weights.

The energy weight rises as the battery becomes depleted. Network conditions affect both latency and energy emphasis. The candidate with the lowest weighted score is selected. The policy records decision count, decision time per task and an estimate of retained policy memory.

The policy is tuned using a separate training workload. The testing workload uses different seeds and workload size/data/memory distributions. Run the dedicated comparison with:

```bash
python runRequirement6.py
```

The result is written to `requirement6Results.json`.

## Requirement 7: Memory Management Across Device, Edge and Cloud

### Finite node memory and task working sets

Every `Device` and `Server` owns a `MemoryManager` with a finite `memoryCapacity`. Every `Task` has a `memory` working-set footprint; the default is 8 MB. Capacities can be changed when constructing a node. The experiment configuration uses a 128 MB local device, a 256 MB edge server and a 1024 MB cloud node unless a scenario changes them.

Task working-set memory is reserved when a task is admitted. It remains allocated while the task is queued, transferring or running. `Scheduler.completeTask` releases it when execution finishes. `removeTask` releases it when a queued task migrates to another node.

### Admission control and rejection records

A node accepts a task only if its free memory can hold the working set. If the selected node is full, the scheduler records the rejection and tries other available nodes. If no node can admit the task, its status becomes `memoryRejected`. Every node's rejection records include the task, requested memory, available memory, simulation time and reason.

Inspect the records using `scheduler.getMemorySummary()` or `server.memoryManager.getSummary()`.

### Migration cost

A migration moves both input data and task memory state. The transfer payload is:

```text
migrationSize = task.dataSize + task.memory
transferTime = migrationSize / bandwidth
```

For a cloud server with wireless and wired segments, transfer time includes the payload transmission time on both links. The wireless transmission energy is charged by Requirement 8's interface using the wireless transfer duration.

### Edge service cache

Workloads use five service types: analytics, media, database, vision and sensor. Edge servers have a configurable service cache; the experiment system defaults to three service-image slots of 12 MB each. A cache hit adds no service-load delay. A miss adds the configured `serviceLoadDelay`, just like a page fault. Cached service images count against the edge server's finite memory.

Two replacement policies are implemented:

- `LRU`: evicts the service image that has been unused for the longest time.
- `PREDICTIVE`: uses a recent service-arrival history and a recency-weighted frequency score to estimate which cached service is least likely to be requested again.

Set `cachePolicy="LRU"` or `cachePolicy="PREDICTIVE"` when constructing an edge `Server`. Cache hit, miss, eviction, memory and hit-rate metrics are collected.

### AI scheduler memory reservation

When `Scheduler` is created, it reserves `device.schedulerMemoryReserve` on the local device for the adaptive scheduler. The default reservation is 16 MB. This memory is unavailable for task admission and is included in node utilization and peak-memory measurements. Configure `schedulerMemoryReserve` on `Device` to change it.

## Requirement 8: Energy-Aware I/O Management

`ioMgmt/networkInterface.py` models one wireless upload at a time and supports FCFS and priority-first upload scheduling. Transmission energy is charged as `txPower * wirelessTransferTime`. The radio has active, idle and sleep states; it supports fixed and predictive sleep timeouts and a wake-up delay/energy cost. A seeded random-walk bandwidth variation model supports fluctuating wireless conditions.

The I/O summary reports computation, transmission, radio-idle and wake energy separately, radio-state times, migration data volume, energy rejections and bandwidth history.

## Testing Scenarios and Required Charts

The project documentation requests six core scenarios (high/low energy, fast/slow wireless, many large/many small tasks) and eight extension scenarios (ample/constrained edge memory, LRU/predictive cache, fixed/predictive radio timeout, stable/fluctuating bandwidth). `experiments/scenarioRunner.py` defines exactly these 14 scenarios.

Every scenario runs all three policies (static, list scheduling and adaptive) over at least five independent random seeds. The default experiment uses seeds `97`, `107`, `117`, `127` and `137`. Requirement 6 is tuned on a separate training workload using seed `41`; its selected settings are held fixed during scenario testing.

Run the full experiment and create all six charts:

```bash
python runAllExperiments.py
```

This creates `allScenarioResults.json` and the six PNG charts in `graphs/`. The charts are:

1. `makespanComparison.png` — makespan comparison across scenarios, showing mean and standard deviation.
2. `energyImpact.png` — total energy comparison across scenarios.
3. `queueOccupancy.png` — average waiting-queue occupancy across scenarios.
4. `energyMakespanTradeoff.png` — one mean point per policy per scenario.
5. `memoryAndCacheOverTime.png` — edge memory utilization and service-cache hit rate over time, comparing LRU and predictive cache cases.
6. `energyBreakdown.png` — mean computation, transmission and radio-idle energy per policy.

The six charts are explicitly listed in the assignment's Required Visualizations section. The full JSON report keeps the underlying scenario, seed, policy, memory, cache and energy measurements so the charts can be regenerated or reformatted.

## Metrics Collected

The experiment runner records makespan, local computation energy, transmission energy, radio-idle energy, wake energy, offloaded/local task counts, completed and rejected tasks, average queue waiting time, queue occupancy, energy efficiency, node memory usage, peak and average memory utilization, admission rejections, service-cache hit rate, cache hits/misses/evictions, migration data volume, radio state time, radio wake-up count, offloaded/local percentages, queue waiting time by node and adaptive scheduler overhead.

## Scope and Modelling Notes

This project implements Requirements 1–8, with Requirement 7 integrated after Requirements 1–6 and 8. It is a discrete-event simulator, not an operating-system kernel or hardware benchmark. The default compute speeds, memory capacities, energy rates, bandwidths, cache image sizes and service-load delays are configurable simulation assumptions; use the measured results from the selected configuration when writing the reflection and design brief.
