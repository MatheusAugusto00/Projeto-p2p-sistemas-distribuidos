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
