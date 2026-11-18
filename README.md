# Distributed Edge Scheduling Simulator

This project implements the COMP3320 scheduling simulator requirements 1–6 and 8. Requirement 7 is intentionally excluded. The implementation uses the same modular Python structure throughout, with camelCase filenames, variables and methods, and PascalCase class names.

## Project Structure

```text
edgeScheduler/
    main.py
    run.py
    runRequirement6.py
    testImplementation.py
    testRequirement6.py
    testRequirement8.py
    models/
        task.py
        priorityQueue.py
        server.py
        device.py
    scheduling/
        offloadStrategy.py
        adaptiveGreenPolicy.py
        scheduler.py
    ioMgmt/
        networkInterface.py
    experiments/
        greenPolicyExperiment.py
    README.md
```

## Run and Test

Use Python 3.10 or newer. No third-party packages are required.

```bash
python run.py
python testImplementation.py
python testRequirement6.py
python testRequirement8.py
python runRequirement6.py
```

`runRequirement6.py` performs the separate tuning and testing experiment, prints the policy comparison and writes `requirement6Results.json` in the current directory.

## Requirements 1–5: Distributed Scheduling

### Distributed priority queues

The local device, edge server and cloud server each have a separate priority queue. Lower numeric priority values are treated as higher priority. Equal-priority tasks retain FIFO order. Tasks can be removed from one queue and assigned to another through the scheduler.

### Offloading policies

- `StaticRule` offloads tasks whose compute size is above its configured threshold.
- `DRLInspiredHeuristic` is the logic-based offloading strategy for Requirement 2. It considers task size and queue pressure.
- `ListSchedulingHeuristic` compares the expected finish time at each eligible execution point and selects the earliest one.

### Heterogeneous execution and communication

The default demo models a slower local device, a faster edge server and the fastest cloud server. Remote execution includes communication delays. Upload time depends on task data size and bandwidth. Cloud transfer time includes wireless and wired portions. A remote task cannot be dispatched before its transfer completes.

### Local energy budget

The device reserves energy for tasks admitted to its local queue. Local execution consumes energy on dispatch. The scheduler avoids admitting local work that would exceed the remaining battery budget and can redirect work to an available remote server.

## Requirement 6: Adaptive Green Process Scheduling

`AdaptiveGreenPolicy` is the third policy. It uses an adaptive multi-objective scoring rule, which is one of the two implementation options permitted by the project. It does not require a deep-learning library or a trained neural network.

### State

Every decision records the required state inputs:

- `remainingBattery`: remaining battery as a proportion of device capacity
- `localQueueLength`: number of tasks waiting on the local device
- `wirelessSpeed`: current wireless bandwidth estimate
- `taskSize`: compute size of the task being scheduled

### Latency and energy score

For each candidate execution point, the policy estimates completion time and device-side energy cost. Local energy is estimated using the device's computation-energy rate. Remote energy includes the predicted wireless transmission energy and a wake-up cost when the radio is asleep.

The two values are normalized against the candidate set before scoring:

```text
score = timeWeight * normalizedCompletionTime
      + energyWeight * normalizedDeviceEnergy
```

The candidate with the lowest score is selected. This normalization prevents a measurement's units or numerical scale from dominating the other objective.

The weights adapt to the current conditions. Battery pressure increases as the battery level falls. Network pressure increases as wireless speed falls below the reference bandwidth.

```text
batteryPressure = 1 - remainingBattery
networkPressure = 1 - min(1, wirelessSpeed / referenceBandwidth)

timeWeight = baseTimeWeight + networkPressure * networkSensitivity
energyWeight = baseEnergyWeight
             + batteryPressure * batterySensitivity
             + networkPressure * networkEnergySensitivity
```

The raw weights are normalized so that they sum to one. When the battery is low, energy receives more weight. When the network is slow, the policy changes both latency and energy emphasis because slow transfers affect completion time and transmission energy.

### Tuning on a separate workload

The experiment tunes the adaptive policy using a training workload that is not reused for testing. The default run uses training seed `41` and a training task-size/data-size profile. It searches 24 combinations of base time weight, battery sensitivity and network sensitivity.

Each setting is evaluated using a balanced training objective:

```text
trainingObjective = 0.5 * normalizedMakespan
                  + 0.5 * normalizedTotalEnergy
```

The equal 0.5 weights are used because the policy is explicitly multi-objective: completion time and device energy are both primary goals. The metrics are normalized before combining them, so seconds do not dominate energy units simply because their numerical values are larger. The selected parameters are then held fixed during testing; only the policy's state-based weights adapt during each scheduling decision.

The default testing run uses five different seeds: `97`, `107`, `117`, `127` and `137`. The testing workload uses a different task-size/data-size profile from the training workload. Static rule, list scheduling and the tuned adaptive policy are each run against every testing workload. The report gives mean and standard deviation across the five runs.

### Scheduler overhead

The policy measures the time spent making each scheduling decision using `perf_counter_ns`. It reports the number of decisions, total decision time, average decision time per task and policy memory in bytes and kilobytes.

Policy memory is an estimate of the retained Python object sizes for the policy and its decision history. It is an in-process object-size estimate, not total operating-system resident memory.

## Requirement 8: Energy-Aware I/O Management

### Wireless upload queue

`ioMgmt/networkInterface.py` models the device wireless interface. Remote uploads enter one shared upload queue, and only one wireless transfer is active at a time. The default policy is FCFS. Set `policy="PRIORITY"` to use priority-first scheduling; lower numeric priority values are served first and equal priorities retain arrival order. An active transfer is not preempted.

### Transmission and radio energy

Transmission energy is calculated as `txPower * wirelessTransferTime` and charged to the device battery. The radio has `active`, `idle` and `sleep` states. After the configured timeout it enters sleep; waking adds a delay and energy cost. Idle radio energy is calculated using `idlePower` and the time spent idle.

Use `radioPolicy="fixed"` for a fixed sleep timeout or `radioPolicy="predictive"` to set the timeout from recent upload inter-arrival times. A seeded random-walk bandwidth model can be enabled with `bandwidthVariation` and `randomSeed`.

Call `scheduler.networkInterface.getEnergySummary()` for computation, transmission, idle-radio and wake energy, radio-state time, energy rejections and bandwidth history.

## Default Requirement 6 Demonstration

The default deterministic run on the five testing seeds produced the following sample results:

| Policy | Mean makespan | Mean total energy |
|---|---:|---:|
| Static rule | 474.26 | 126.43 |
| List scheduling | 194.15 | 80.03 |
| Adaptive green | 211.72 | 12.80 |

The adaptive policy reduced mean energy in this test workload while producing a somewhat higher mean makespan than list scheduling. These values describe this simulator configuration and seed set; they are not universal performance claims.

## Scope

Requirements 1–6 and 8 are included. Requirement 7, memory management across device, edge and cloud, is not implemented in this package.
