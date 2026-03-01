# Signal & Trigger Backend Implementation Plan

## Context

Two use cases drive this:

1. **Approval-gated agent** — machine parks at `wait_for`, user approval (e.g. WhatsApp webhook) hits ultralight listener → UDS notify → dispatcher resumes one machine. Addressed channel: `"approval/task-001"`.

2. **Quota-gated pipeline** — 10,000 machines parked waiting for API quota. Cron sends signal → dispatcher resumes N machines up to available quota. Broadcast channel: `"quota/openai"`.

**10,000 waiting machines = 10,000 rows in SQLite. Zero processes, zero memory.** Machine checkpoints with `waiting_channel`, exits. Signal arrives → trigger fires → dispatcher resumes matches.

## Deployment Matrix

| Deployment | Trigger | Who watches |
|---|---|---|
| Dev/test | `NoOpTrigger` | Your process (in-process) |
| Local durable | `FileTrigger` | launchd / systemd |
| **Local fast** | **`SocketTrigger` (UDS)** | **Dispatcher process** |
| AWS | `NoOpTrigger` | DynamoDB Streams → Lambda (implicit) |

DynamoDB = `NoOpTrigger`. Streams → Lambda is infrastructure config, not SDK code.

`SocketTrigger` uses `SOCK_DGRAM` — fire-and-forget, no connection state, payload is the channel name. Cross-platform: asyncio uses kqueue (macOS) / epoll (Linux) under the hood.

## Files

### New

| File | What |
|---|---|
| `signals.py` | `Signal`, `SignalBackend` (Protocol), `MemorySignalBackend`, `SQLiteSignalBackend`, `TriggerBackend` (Protocol), `NoOpTrigger`, `SocketTrigger`, `FileTrigger`, factories |
| `dispatcher.py` | `SignalDispatcher` — bridges signals to machine resume. UDS listener mode for `SocketTrigger`. |
| `tests/unit/test_signals.py` | Signal + trigger backend tests (parametrized Memory/SQLite) |
| `tests/unit/test_wait_for.py` | Machine-level `wait_for` integration tests |

### Edit

| File | What |
|---|---|
| `persistence.py` | `waiting_channel` field on `MachineSnapshot`. `list_execution_ids(waiting_channel=...)` filter on all three backends (Memory, LocalFile, SQLiteCheckpoint). |
| `flatmachine.py` | `WaitingForSignal` exception. `wait_for` handling in `_execute_state`. Signal/trigger backend wiring in `__init__`. Catch `WaitingForSignal` in `execute()` main loop — checkpoint with `waiting_channel`, return. Resume path: re-enter state, consume signal, continue. |
| `__init__.py` | Export new symbols |
| `tests/unit/test_backend_lifecycle.py` | Add `waiting_channel` filter tests |

## Implementation Order

1. **`signals.py`** — standalone, no deps
2. **`persistence.py`** — add `waiting_channel` to snapshot + filter
3. **`flatmachine.py`** — wire backends, `wait_for` handling
4. **`dispatcher.py`** — depends on signals + persistence
5. **`__init__.py`** — exports
6. **Tests**

## Key Design Decisions

- **`WaitingForSignal` exception** — state executor raises, main loop catches. Clean separation, same pattern as `on_error`.
- **Signal consumed on resume** — dispatcher marks executions for resume. Machine itself consumes signal when it re-executes the `wait_for` state. Signal data flows through `output.*` in `output_to_context` — no new template syntax.
- **SQLite shared path** — signals table lives in same DB as work pools and checkpoints (`sqlite_path` convention).
- **Socket is optimization, not reliability** — if dispatcher is down, signals accumulate in SQLite. Processed on next start. The UDS just says "go look now."
- **`SOCK_DGRAM`** for trigger — no connection state, channel name as payload.
