# Sprint 4 Supervisor Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic Sprint 4 performance reporting from the Master to the external supervisor over TLS/TCP.

**Architecture:** Keep the project in `server.py` and standard library only. Add pure payload-building helpers, a small TCP/TLS sender, and a daemon loop started by `iniciar_servidor()`.

**Tech Stack:** Python 3 standard library, TCP sockets, TLS via `ssl`, JSON lines, `threading`, `unittest`.

---

## File Structure

- Modify `server.py`: supervisor configuration, metrics payload builder, sender, sender loop, startup hook, worker failure counter.
- Create `tests/test_sprint4.py`: focused unit tests without real network access.
- Modify `README.md`: Sprint 4 behavior, environment variables, and execution notes.

## Tasks

### Task 1: Documentation

- [ ] Create the Sprint 4 spec in `docs/superpowers/specs/2026-06-10-sprint-4-supervisor-metrics-design.md`.
- [ ] Create this implementation plan in `docs/superpowers/plans/2026-06-10-sprint-4-supervisor-metrics.md`.

### Task 2: TDD for Payload and Sender

- [ ] Add failing tests in `tests/test_sprint4.py` for required payload fields, farm counters, task counters, neighbors, sender behavior, and disabled startup.
- [ ] Run `python3 -m unittest tests.test_sprint4 -v` and confirm failures are due to missing Sprint 4 functions.

### Task 3: Server Metrics Implementation

- [ ] Add supervisor env config constants to `server.py`.
- [ ] Add system metric helpers with standard library fallbacks.
- [ ] Add `build_supervisor_payload(state, now=None, message_id=None)` and farm summary helpers.
- [ ] Add `send_supervisor_payload(payload, host, port, use_tls=True, sni=None, connector=socket.create_connection)`.
- [ ] Add `supervisor_metrics_loop()` and `start_supervisor_metrics()`.
- [ ] Increment a worker failure counter in `cleanup_dead_worker`.

### Task 4: Startup and README

- [ ] Call `start_supervisor_metrics()` from `iniciar_servidor()`.
- [ ] Ensure `SUPERVISOR_ENABLED=0` prevents thread creation.
- [ ] Update `README.md` with Sprint 4 and supervisor environment variables.

### Task 5: Verification

- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `PYTHONPYCACHEPREFIX=/private/tmp/pycache-sprint4 python3 -m py_compile server.py client.py tests/test_sprint3.py tests/test_sprint4.py`.
