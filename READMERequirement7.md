# Requirement 7 Contribution: Memory Management

This contribution is provided separately. It does not replace or edit any existing project files.

## Included
- `memoryMgmt/memoryManager.py`: finite memory capacity, admission control, task memory reservations and release, migration transfer cost, LRU and predictive service cache, and scheduler memory reservation.
- `testRequirement7.py`: standalone checks for the memory manager.
- `models/task.py`: a small test-only Task class so the tests can run independently. When integrating into the group repository, use the existing `models/task.py` instead; do not replace it.

## Run the standalone tests
From this folder, run:

```bash
python testRequirement7.py
```

## Integration note
Copy only `memoryMgmt/memoryManager.py` (and `memoryMgmt/__init__.py` if the repository does not already have it) into the group project. Keep all existing files unchanged. The group's integration lead should decide how to connect the memory manager to the scheduler, servers, devices and network interface. The test-only `models/task.py` is not intended to replace the group's existing Task class.

Requirement 8 already has an implementation in the supplied project (`ioMgmt/networkInterface.py`) and its existing `testRequirement8.py`, so this contribution does not overwrite it.
