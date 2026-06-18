# Sprint 3 Master Negotiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sprint 3 Master-to-Master negotiation, temporary Worker redirection, and Worker return behavior.

**Architecture:** Keep the existing two-file Python socket project. `server.py` owns Master state, peer negotiation, temporary Worker registry, and task dispatch. `client.py` owns Worker connection state and follows redirect/release commands.

**Tech Stack:** Python 3 standard library, TCP sockets, JSON lines, `threading`, `unittest`.

---

## File Structure

- Modify `server.py`: Master-to-Master protocol, peer configuration, load thresholds, temporary Worker state, redirect/release commands.
- Modify `client.py`: redirect/release handling, temporary registration, dynamic Master target.
- Create `tests/test_sprint3.py`: unit tests for protocol and state transitions.
- Modify `README.md`: document Sprint 3 execution examples and environment variables.

## Tasks

### Task 1: Protocol Tests

- [ ] Write `tests/test_sprint3.py` with failing tests for peer parsing, Master message validation, negotiation responses, temporary registration, redirect commands, release commands, and Worker target switching.
- [ ] Run `python3 -m unittest tests.test_sprint3 -v` and confirm the tests fail because Sprint 3 helpers do not exist yet.

### Task 2: Master Sprint 3 Support

- [ ] Add peer parsing, envelope validation, load helpers, temporary Worker registry, redirect/release queues, and Master-to-Master handlers to `server.py`.
- [ ] Preserve Sprint 2 behavior for `WORKER` and `STATUS` messages.
- [ ] Run `python3 -m unittest tests.test_sprint3 -v` and confirm tests pass.

### Task 3: Worker Sprint 3 Support

- [ ] Add dynamic Master target state and handlers for `command_redirect` and `command_release` to `client.py`.
- [ ] Add `register_temporary_worker` before the borrowed Worker starts Sprint 2 task polling on the new Master.
- [ ] Run `python3 -m unittest tests.test_sprint3 -v` and confirm tests pass.

### Task 4: Documentation and Verification

- [ ] Update `README.md` with Sprint 3 behavior and local execution examples for two Masters and Workers.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `python3 -m py_compile server.py client.py tests/test_sprint3.py`.

### Task 5: Task Board and Requeue on Worker Exit

- [ ] Extend `tests/test_sprint3.py` with failing tests for task movement across pending, in-progress, and done lists.
- [ ] Extend `tests/test_sprint3.py` with a failing test proving a task assigned to a disconnected Worker returns to pending.
- [ ] Add task board state to `server.py` and make dispatch/status/disconnect update that state.
- [ ] Update `README.md` with the task lifecycle.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py`.

### Task 6: Autonomous Saturation Monitor

- [ ] Extend `tests/test_sprint3.py` with a failing test proving a saturated Master asks a peer for help without a Worker presentation.
- [ ] Add a saturation monitor loop in `server.py` that periodically calls the negotiation flow.
- [ ] Track accepted help requests to avoid repeated `request_help` messages before borrowed Workers register.
- [ ] Update `README.md` with the autonomous monitor behavior.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py`.

### Task 7: Borrowed Worker Interoperability

- [ ] Extend `tests/test_sprint3.py` with failing tests proving `command_redirect` includes `original_master_id`, the Worker prefers that value for `SERVER_UUID`, and falls back to the original address when no id is provided.
- [ ] Extend `tests/test_sprint3.py` with a failing test proving a missing, timed out, closed, or non-standard `register_temporary_worker` ACK does not prevent the Worker from continuing to the next Sprint 2 presentation.
- [ ] Update `server.py` so `command_redirect` payloads keep `new_master_address` and `original_master_address`, and also include optional `original_master_id`.
- [ ] Update `client.py` so redirect handling records `origin_server_uuid` from `original_master_id` first, then configured `SERVER_UUID`, then `original_master_address`.
- [ ] Update `client.py` so temporary registration sends the official `register_temporary_worker` payload but treats ACK parsing as best-effort logging only.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py`.
- [ ] Run a local two-Master simulation and confirm the redirected Worker receives `TASK: QUERY` and sends `STATUS`.

### Task 8: Protocol Alias Adapter

- [ ] Extend `tests/test_sprint3.py` with failing tests proving `request_help`, `register_temporary_worker`, `notify_worker_returned`, `notify_worker_dead`, `command_redirect`, and `command_release` accept uppercase aliases used by external teams.
- [ ] Add edge helpers in `server.py` to read canonical lowercase fields first and uppercase aliases second.
- [ ] Add edge helpers in `client.py` so Workers understand `NEW_MASTER_ADDRESS`, `ORIGINAL_MASTER_ADDRESS`, and `ORIGINAL_MASTER_ID` while keeping lowercase as the internal standard.
- [ ] Include uppercase aliases in accepted `response_accepted` payloads and `command_redirect` payloads without removing the lowercase fields.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py tests/test_sprint4.py`.

### Task 9: Borrowed Worker Classification and Release Fix

- [ ] Add failing tests proving heartbeat with `SERVER_UUID` records the Worker as borrowed, removes it from local Workers, and makes the Sprint 4 payload report received borrowed Workers with direction `down`.
- [ ] Add a failing test proving `register_temporary_worker` replaces a prior heartbeat-only origin id with the real `original_master_address` used for return notification.
- [ ] Add a failing test proving an idle borrowed Worker receives `command_release` in the same presentation where the Master notices load is below `RELEASE_THRESHOLD`.
- [ ] Update `server.py` so any heartbeat or presentation with origin server information calls a single borrowed-worker registration path that discards the Worker from `local_workers`.
- [ ] Update `server.py` so release queuing runs before dispatch and re-checks the current Worker's pending release before assigning a task.
- [ ] Update Sprint 4 farm-state payload direction labels to `up` for lent Workers and `down` for received Workers.
- [ ] Add explicit `worker_uuid`, `status`, `parent_uuid`, `parent_hostname`, and `current_master_uuid` fields to borrowed-worker metric entries so the supervisor does not infer the parent from the reporting Master.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py tests/test_sprint4.py`.

### Task 10: Lent Worker Heartbeat Ownership Fix

- [ ] Add a failing test proving the Master of origin does not expire a Worker in `lent_workers` when that Worker's local heartbeat timestamp becomes stale.
- [ ] Add a heartbeat-expiration helper in `server.py` that ignores Workers currently listed in `lent_workers`.
- [ ] Update `monitor_workers_loop()` to use the helper before calling `cleanup_dead_worker()`.
- [ ] Run `python3 -m unittest tests.test_sprint3 -v`.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py tests/test_sprint4.py`.

### Task 11: Returned Borrowed Worker Cleanup Fix

- [ ] Add a failing test proving that after `command_release`, the Master receptor removes the returned Worker from `borrowed_workers` and `worker_heartbeats`.
- [ ] Add a failing test proving a returned borrowed Worker cannot later be collected as expired by the receptor heartbeat monitor.
- [ ] Update `server.py` release handling to clean the returned Worker lifecycle state before it can be considered dead.
- [ ] Add lifecycle logs that distinguish `LOCAL`, `BORROWED`, `RELEASE`, and `WORKER DEAD`.
- [ ] Run `python3 -m unittest tests.test_sprint3 -v`.
- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint3 python3 -m py_compile server.py client.py tests/test_sprint3.py tests/test_sprint4.py`.
