# Task 6 adaptive green process scheduling

This contribution adds the adaptive scoring option allowed by Component 6. It
balances estimated completion time and local CPU energy, adjusts to battery and
wireless conditions, and compares against the existing static and list policies.
It is a tuned adaptive heuristic, not Q-learning or a neural network.

## How to run and read the code

From the repository root, run `python run.py` for a short demonstration,
`python testImplementation.py` for the original checks, `python testTask6.py` for
the new checks, and `python runTask6.py` for tuning and all 90 core test runs.
The simulation uses only Python's standard library. Charts additionally need
`python -m pip install -r requirements.txt`, followed by `python plotTask6.py`.
Python 3.10 or newer is recommended; the saved results were run on Python 3.12.

Read these files in order:

1. `scheduling/aiPolicy.py`: the complete adaptive policy, using the same
   `chooseServer(task, device, servers)` interface as the other policies.
2. `experiments/policyMetrics.py`: timing and persistent policy memory measurement.
3. `experiments/scenarioRunner.py`: workloads, task completion, tuning and results.
4. `testTask6.py`: examples checking the policy and the experiment runner.
5. `experiments/resultsPlotter.py`: charts from the saved CSV files.

The existing device, queue, server and scheduler code is unchanged. `main.py` and
`run.py` include an additional demonstration. Names follow the repository's
camelCase convention, except Python's required special names and library APIs.

## The policy in plain language

For each arriving task, look at all eligible execution locations and choose the
one with the lowest score. Reject local placement if the battery cannot cover
the task, including energy already promised to tasks in the local queue.

The state contains remaining battery, available battery after reservations,
local queue length, current wireless speed, and task size. Queue pressure affects
the score through the existing estimate, which sums queued task workload.
If remote servers have different wireless speeds, the state uses the slowest;
each candidate's transfer estimate still uses its own bandwidth. All servers in
these experiments share the scenario's wireless speed.

```text
localTime = task.size / device.computeSpeed
localEnergy = task.size * device.energyPerWorkUnit
timeScale = max(localTime, 1)
energyScale = max(localEnergy, 1)

score = timeWeight * estimatedFinishTime / timeScale
      + energyWeight * estimatedLocalCpuEnergy / energyScale
```

A score uses time relative to running that task locally, and energy relative to
its local CPU cost. Dividing first prevents the units of time and energy from
deciding the trade-off accidentally. A lower score is better. The scales are at
least one to avoid division by zero for zero-work tasks. Queue delays can make
the time ratio larger than one; it is a ratio, not a probability.

The starting energy weight is 0.35, selected using the separate tuning workloads:

| Condition | Energy weight | Time weight |
| --- | ---: | ---: |
| Battery at least 30% available, wireless at least 10 MB/time unit | 0.35 | 0.65 |
| Battery below 30% available, fast wireless | 0.60 | 0.40 |
| Battery at least 30% available, wireless below 10 MB/time unit | 0.20 | 0.80 |
| Battery below 30% available, slow wireless | 0.45 | 0.55 |

Low available battery adds 0.25 to the energy weight to conserve the remaining
budget. Slow wireless subtracts 0.15 to put more emphasis on delay. The battery
adjustment is larger because avoiding battery depletion matters even on a slow
connection. These thresholds and adjustments are simple design assumptions,
not values claimed by the research paper. The weights are kept between 0.10 and
0.90, and the time weight is always one minus the energy weight.

For example, a size-10 task with 10 MB of data costs 5 energy units locally and
takes 10 time units on the local CPU. On an empty edge server at speed 3,
wireless delay 5 and bandwidth 2, it takes about 13.33 time units. With high
battery and slow wireless, the local score is 1 and the edge score is about
1.07, so local wins. With low battery, the edge score becomes about 0.73, so
the policy accepts the extra delay to save local CPU energy.

Remote execution has zero **local CPU** energy in the current core simulator.
This does not mean networking or remote servers consume no energy. Task 8 must
add transmission and radio energy before interpreting the result as total
device energy savings. No carbon savings or AI execution energy are estimated.

## Tuning and testing

Tuning uses seeds 101-105, 24 tasks per workload, and all six configurations below.
It tries only three starting energy weights: 0.20, 0.35 and 0.50. Their mean tuning
objectives were 0.557403, 0.553172 and 0.555618 respectively; lower is better.

```text
tuningObjective = 0.5 * measuredMakespan / listPolicyMakespan
                + 0.5 * measuredCpuEnergy / hypotheticalAllLocalCpuEnergy
```

The list baseline uses the same tuning tasks. The hypothetical all-local energy
is a scale, not a feasible schedule when battery is low. The two ratios have
equal coefficients to consider both outcomes. This is a design preference, not
a guarantee of a globally optimal trade-off. It selects the middle candidate,
0.35, before any held-out test run. Only the starting weight is tuned; the two
adjustments and thresholds above are fixed in advance.

Tests use seeds 1-5 and 40 tasks per workload. The chosen starting weight stays
fixed during testing, while battery/network adjustments remain active. Task
lists are regenerated from the same seed for each policy so comparisons are
paired. Fresh devices, servers and tasks are created for every run. Changing
the test outcomes does not trigger retuning.

| Scenario | Battery capacity | Wireless MB/time unit | Task sizes |
| --- | ---: | ---: | --- |
| HighEnergy | 1000 | 10 | Mixed, 5-120 |
| LowEnergy | 100 | 10 | Mixed, 5-120 |
| FastWireless | 500 | 20 | Mixed, 5-120 |
| SlowWireless | 500 | 2 | Mixed, 5-120 |
| LargeTasks | 500 | 10 | 60-120 |
| SmallTasks | 500 | 10 | 5-25 |

Each adjacent pair changes one condition. Priorities range from 1 to 3; smaller
numbers execute first. Input data is 0.2-1.0 times task size in MB. The large/small
comparison therefore changes both compute workload and its associated input
data, using the same data-to-work ratio distribution. Local/edge/cloud compute
speeds are 1/3/5. Wireless fixed delay is 5, cloud wired delay is 10, wired
bandwidth is 100, and local energy costs 0.5 per unit of work.

All tasks arrive at time zero and are placed in generation order. Execution is
non-preemptive. Each CPU runs at most one task at a time; different CPUs run in
parallel. A remote task starts only after its transfer completes. The original
priority queue decides which ready task goes next. Uploads overlap, following
the existing Task 5 model; a shared upload queue belongs to Task 8.

The existing finish-time estimate is a heuristic: it adds queued workload,
communication delay and compute time, without reproducing every priority and
transfer-overlap detail. Static, list and adaptive policies retain the existing
model. Reported makespan comes from the completion simulation, not the estimate.
The batch runner avoids needing running-task estimates during later arrivals.

## Saved results

The following values are mean +/- sample standard deviation across five seeds.
Time is in simulation units; energy is in model units, not measured joules.

| Scenario | List makespan | Adaptive makespan | List CPU energy | Adaptive CPU energy |
| --- | ---: | ---: | ---: | ---: |
| HighEnergy | 305.56 +/- 22.73 | 310.83 +/- 23.82 | 132.90 +/- 22.92 | 115.80 +/- 19.00 |
| LowEnergy | 314.38 +/- 27.23 | 314.69 +/- 27.96 | 95.20 +/- 4.80 | 92.70 +/- 6.47 |
| FastWireless | 306.05 +/- 21.85 | 309.76 +/- 23.73 | 133.70 +/- 22.02 | 117.10 +/- 19.32 |
| SlowWireless | 316.23 +/- 20.72 | 309.53 +/- 22.47 | 144.40 +/- 18.59 | 128.00 +/- 19.06 |
| LargeTasks | 424.21 +/- 7.83 | 429.46 +/- 7.88 | 200.30 +/- 14.19 | 170.70 +/- 20.03 |
| SmallTasks | 79.89 +/- 3.14 | 80.53 +/- 2.92 | 35.40 +/- 1.02 | 32.90 +/- 1.29 |

The adaptive policy reduces mean local CPU energy against list scheduling in all
six cases. It increases mean makespan in five cases, by about 0.1-1.7%, and
reduces it by about 2.1% in SlowWireless. These are descriptive comparisons
across five seeds, not proof of statistical significance or universal superiority.
The static rule is slower in all six scenarios. In LargeTasks it offloads
everything to the first edge server, consuming zero local CPU energy while
producing a mean makespan of 1222.82. That highlights why energy alone is an
incomplete objective under this simplified energy model.

Adaptive decision time averages approximately 20-28 microseconds per task across
the six scenarios on this host. The per-scenario mean and standard deviation,
and every individual timing, are saved in the CSV files. These are noisy host
wall-clock measurements using `perf_counter_ns`, not simulation time. Timings
cover policy selection and the common battery fallback, excluding queue insertion,
logging, plotting and memory measurement. Policy order rotates across seeds.
The measured duration is not added to simulated makespan or converted to energy.

The adaptive policy's persistent instance data measures 567 bytes in these runs.
`policyMemoryBytes` counts the instance, its attribute dictionary, attribute names
and scalar values once per identity. It excludes shared code, Python itself,
temporary decision data and experiment logs. It is an approximate policy storage
measure, not peak process RAM. Values can differ between Python versions;
Python's dictionary sharing can also change baseline instance sizes between runs.

| File in results/task6 | Contents |
| --- | --- |
| settings.json | Frozen parameter, seeds, system conditions and execution environment |
| tuning.csv | All three candidates and their tuning objective statistics |
| runs.csv | 90 per-run records for all three policies |
| summary.csv | Mean, sample SD and valid-seed count for every scenario/policy/metric |
| tasks.csv | 3600 task records with placement, timing, waiting and decision overhead |
| queues.csv | Queue lengths at each simulation event for every run |
| charts/ | Makespan, CPU energy, queue occupancy, trade-off and overhead charts |

Queue waiting is start time minus transfer completion time. `arrivalToStart`
also includes transfer time. Queue occupancy includes tasks still transferring
to a node and excludes the currently running task. The chart samples each trace
on a shared time grid and shows five-seed means and sample SD. Energy efficiency
is completed tasks divided by local CPU energy. With zero CPU energy, that ratio
is undefined and saved blank, not reported as a finite efficiency. Empty-node
mean waiting times are also blank; `validSeeds` records the observations used.

## Requirement coverage and group integration

This contribution extends the existing repository at commit `6ffa8e0`. It adds
the Task 6 policy, experiments, tests and documentation without replacing the
core models or scheduler. Run `python runTask6.py` and `python plotTask6.py` to
generate the results locally. Generated files under `results/task6/` are ignored
by Git; the source and this recorded comparison remain reviewable in the branch.

| Task 6 requirement | Evidence |
| --- | --- |
| Third adaptive policy | AdaptiveGreenPolicy, kept separate from the existing DRL-inspired rule |
| Battery, local queue, wireless speed and task size state | getState and state/decision tests |
| Latency and energy score with justified weights | chooseServer, getWeights and explanations above |
| Separate tuning workload | 24-task tuning seeds 101-105 versus 40-task test seeds 1-5 |
| Decision time and policy memory | policyMetrics.py, per-task and summary CSVs |
| Static/list/adaptive comparison over at least five seeds | 90 completed runs, 18 scenario-policy groups |

The original 16 implementation checks and all seven new test groups pass. New
checks cover battery reservations, changing network and queue conditions, no
eligible server, zero work, upload readiness, priority, CPU serialization and
parallelism, distinct tuning/test workloads, sample SD, and complete execution.

This Task 6 contribution supplies four of the six required project chart categories,
plus an extra overhead chart. The memory/cache chart and the full computation/
transmission/idle-energy breakdown await Tasks 7 and 8. Their eight extension
scenarios are not run or populated with dummy values here. The final group still
needs all 14 scenarios x 3 policies x 5 seeds, the remaining metrics and charts,
and its joint reflection, design brief and contribution statement.

For Task 7 integration, filter candidates through memory admission and account
for state migration/service-load delays in completion estimates. Reserve the
policy's storage according to the memory model. For Task 8, include predicted
transmission/radio energy in the score, use actual upload-queue readiness and
bandwidth, and apply the combined battery budget to every policy. Re-tune and
rerun all comparisons after those model changes; the current weights and results
are evidence only for Tasks 1-6.

## Research connection

[Ribeiro et al. (2026), Sections 3.2-3.5 and 5](https://www.mdpi.com/2673-8732/6/1/17)
discuss adaptive offloading, multiple objectives, evaluation metrics and the
cost of intelligence. This implementation follows those themes through a small
time-energy policy and explicit overhead measurements. Its formula, thresholds
and numeric results are this project's design and experiment results, not a
reproduction of a specific algorithm or reported savings from the paper.
