# Agently Stage

Agently Stage is a Python 3.10+ runtime bridge for safely combining synchronous
callers, asyncio work, blocking functions, generators, streaming channels, and
local event listeners.

It uses one process-wide control worker with finite asyncio loop generations.
Creating a `Stage` does not create a thread or loop. Work opens a generation
lazily; retained work drains, the loop closes, and a later batch can open a new
generation. Ordinary scripts do not need a process shutdown hook.

## Install

```shell
pip install agently-stage
```

## Stage and StageHandle

`Stage.go()` starts a synchronous or asynchronous callable and returns a
loop-neutral `StageHandle`.

```python
import asyncio
import time

from agently_stage import Stage


async def fetch() -> str:
    await asyncio.sleep(0.05)
    return "network-result"


def calculate() -> int:
    time.sleep(0.05)
    return 6 * 7


stage = Stage()
fetch_handle = stage.go(fetch)
calculate_handle = stage.go(calculate)

print(fetch_handle.get())       # network-result
print(calculate_handle.get())   # 42
```

Async services can read the same handles without blocking their own event loop:

```python
async def main() -> None:
    stage = Stage()
    handle = stage.go(fetch)
    print(await handle.async_get())
    await stage.async_close()


asyncio.run(main())
```

The user's event loop is never reused or replaced. Calling `asyncio.run()`
before or after Stage remains valid.

Each `Stage.go()` admission captures the caller's `contextvars` context. The
root task, its retained descendants, and initial callbacks inherit that
snapshot. A callback registered later captures its own registration-time
context. Context changes made inside Stage do not mutate the caller's context.

### Body result and settlement are different

`get()` returns the root/body outcome. `wait_settled()` additionally waits for
Stage-retained descendants, callbacks, and finalizers.

```python
import asyncio
import threading

from agently_stage import Stage

drained = threading.Event()


async def request() -> str:
    async def background_cleanup() -> None:
        await asyncio.sleep(0.05)
        drained.set()

    asyncio.create_task(background_cleanup())
    return "business-result"


handle = Stage().go(request)
print(handle.get())              # business-result
print(drained.is_set())          # False
handle.wait_settled()
print(drained.is_set())          # True
```

Body errors are raised by `get()` and do not become settlement errors.
Callback, finalizer, or retained-descendant failures are reported by
`wait_settled()` as `StageSettlementError` without replacing the body result.

`StageHandle.cancel()` fences the handle's Stage-owned body task tree, including
retained descendants and descendants created while cancellation is being
delivered. Call `wait_settled()` after `cancel()` when later Stage-owned work
must be ruled out. Cleanup callbacks and finalizers still settle. Cancellation
cannot preempt a non-cooperative blocking function or undo an external side
effect that has already committed; applications must use their own idempotency,
authorization, or compensation policy for those effects.

### Callback observers

Callbacks are ordered observers, not Promise-style result transformations.

```python
handle = (
    Stage()
    .go(lambda: 42)
    .on_success(lambda value: print("success", value))
    .on_error(lambda error: print("error", error))
    .on_finally(lambda: print("finished"))
)

assert handle.get() == 42
handle.wait_settled()
```

Callbacks can be sync or async. A callback registered after the body finishes
still observes the cached outcome while the Stage scope remains open. Registering
after scope close raises `StageClosedError`.

## Plain Stage or context-managed Stage?

A plain Stage is unpinned. It remains reusable after an idle loop generation
closes, so later `go()` calls may run in a new generation.

Use `with Stage()` or `async with Stage()` when several calls need the same
loop-affine resource:

```python
import asyncio

from agently_stage import Stage


async def current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


with Stage() as stage:
    first_loop = stage.get(current_loop)
    second_loop = stage.get(current_loop)
    assert first_loop is second_loop
```

The first submission lazily acquires a generation lease. Context exit seals
that Stage scope and waits for its work, without waiting for unrelated Stage
scopes. An empty context creates no loop.

`Stage.close()` and `Stage.async_close()` are scope barriers for explicit
application lifecycles. They are not required to make an ordinary script exit:
an active non-daemon control job keeps retained work alive, then the finite loop
closes by itself.

When a close timeout expires, Stage raises `TimeoutError` with the number of
unsettled handles. The scope remains closed to new submissions, and `close()`
may be called again after the outstanding work settles.

## LocalTaskScope

`LocalTaskScope` is the same-loop counterpart to `Stage.go()`. Use it only when
an async component already owns its event loop and needs explicit long-lived
task membership, origin diagnostics, cancellation, and settlement without
crossing into Stage's loop-neutral carrier.

```python
import asyncio

from agently_stage import LocalTaskOutcome, LocalTaskScope


async def main() -> None:
    outcomes: list[LocalTaskOutcome] = []
    scope = LocalTaskScope(on_done=outcomes.append)

    async def hook() -> str:
        await asyncio.sleep(0)
        return "ready"

    task = scope.spawn(hook(), origin="event:ready-hook")
    assert await task == "ready"
    await scope.close(timeout=1)

    assert scope.pending_count == 0
    assert outcomes[0].origin == "event:ready-hook"


asyncio.run(main())
```

The first operation binds the scope to the current running loop. `spawn()`
creates a new task from a coroutine and captures the caller's current
`contextvars`; `adopt()` accepts an existing task only from the same loop.
Admission is explicit: the scope does not install a task factory or discover
unrelated tasks.

`pending_tasks` and sorted `pending_origins` are immutable snapshots.
`wait_settled()` waits for all currently and transitively admitted work.
`cancel_and_wait()` cancels owned work and does not acknowledge success before
that work settles. `close()` seals admission and may either wait naturally or
cancel first. A timeout raises `TimeoutError` and leaves the scope sealed but
retryable; `pending_origins` identifies the unresolved owners.

This is a task-lifetime mechanism, not an event bus, workflow runtime, tenant
boundary, provider cancellation acknowledgement, or business retry policy.
Use direct `await` or `asyncio.TaskGroup` for ordinary lexical async work that
does not need this longer-lived membership contract.

## StageStream

Running a sync or async generator returns a read-only `StageStream`.

```python
import asyncio

from agently_stage import Stage


async def source():
    for item in range(3):
        await asyncio.sleep(0)
        yield item


stage = Stage()
stream = stage.go(source)

print(stream.get())   # [0, 1, 2]
print(list(stream))   # [0, 1, 2] (replay)
stage.close()
```

`for` and `async for` both work. Every reader has an independent replay cursor.
Source errors are delivered after values already published. Stream callbacks
observe source completion once and receive the complete result list; they do
not transform individual items. `lazy=True` delays source start until the first
reader. The source automatically publishes EOF or failure to StageStream's
internal channel; callers do not close a StageStream.

StageStream's complete-result and complete-replay contract is intentionally
unbounded. The source writes into one canonical growing replay buffer;
`get()`/`async_get()` and success callbacks receive safe list copies so caller
mutation cannot corrupt replay. For a bounded local channel without a complete
result-list promise, use `Tunnel(max_history=...)` directly.

`StageHybridGenerator` remains an import-compatible StageStream subtype for the
preview line. New code should use the `StageStream` name.

## Tunnel

`Tunnel` is an independently writable replay channel. It is not a Stage task
and is not renamed to StageStream.

```python
from agently_stage import Tunnel

tunnel: Tunnel[int] = Tunnel()
tunnel.put(1)
tunnel.put(2)
tunnel.close()

assert list(tunnel) == [1, 2]
assert list(tunnel) == [1, 2]
assert tunnel.get() == [1, 2]
```

Multiple threads or coroutines may publish. Accepted values have one total
order, and every sync/async subscriber receives that same sequence from its own
cursor. `close()` is idempotent; `put_stop()` is its compatibility alias.
`fail(error)` publishes a terminal error after accepted values. Writes after a
terminal state raise `TunnelClosedError`. Here `close()` means that the
producer publishes EOF; it is not a runtime-resource cleanup operation.

The default `Tunnel(timeout=10)` applies a reader-local inactivity timeout while
waiting for the next value, providing a safety exit if a producer forgets EOF.
Timing out one reader does not close or mutate the channel, and later readers
can still receive subsequent values. Use `timeout=None` when a reader should
wait indefinitely for explicit `close()` or `fail()`.

Complete replay is unbounded by default. Set `max_history` to retain only a
fixed suffix:

```python
from agently_stage import Tunnel, TunnelLagError

bounded: Tunnel[int] = Tunnel(max_history=2)
slow_reader = iter(bounded)

bounded.put(0)
assert next(slow_reader) == 0
for item in range(1, 5):
    bounded.put(item)

try:
    next(slow_reader)
except TunnelLagError as error:
    assert error.missed_count == 2
    assert error.expected_sequence == 1
    assert error.available_from == 3

bounded.close()
assert list(bounded) == [3, 4]  # a late reader starts at retained history
```

Bounded history never hides loss: a reader that falls behind receives
`TunnelLagError` with its expected and earliest available absolute sequences.
New readers replay the retained suffix. `max_history` bounds replay retention;
it does not provide producer backpressure, durable acknowledgement, retry, or
exactly-once delivery.

For an explicit reader lifecycle, use `subscribe()`:

```python
channel: Tunnel[int] = Tunnel(max_history=128)
channel.put(10)

replay = channel.subscribe(start="earliest", timeout=None)
live = channel.subscribe(start="latest", timeout=None)
checkpoint = channel.subscribe(start=0, timeout=None)

channel.put(11)
channel.close()

assert list(replay) == [10, 11]
assert list(live) == [11]
assert list(checkpoint) == [10, 11]
assert channel.retained_range == (0, 2)
```

`retained_range` is the half-open absolute sequence range
`(earliest_retained, next_sequence)`. An absolute subscription start may be
inside that range or equal to `next_sequence`. A stale checkpoint raises
`TunnelLagError` on read; a future checkpoint is rejected. Each
`TunnelSubscription` has its own inactivity timeout, `next_sequence`, and
idempotent `close()` / `async_close()`. Reader close, timeout, or cancellation
does not close the producer or another reader.

Legacy `iter(tunnel)`, `aiter(tunnel)`, and `get()` remain earliest-retained
readers using the Tunnel's configured default timeout.

## EventEmitter

EventEmitter owns one reusable Stage scope for all listener work.

```python
from agently_stage import EventEmitter

emitter = EventEmitter()


@emitter.once("ready")
async def ready_listener(value: str) -> str:
    return value.upper()


handles = emitter.emit("ready", "ok", wait=False)
assert handles[0].get() == "OK"

# The once listener was removed atomically before invocation.
assert emitter.emit("ready", "again", wait=True) == []
```

`emit(..., wait=False)` returns listener handles immediately while Stage retains
the work. `wait=True` waits without merging listener failures; each failure
remains observable from its own handle. Ordinary scripts do not need to close
an emitter: listener work settles through the finite Stage runtime. `close()`
and `async_close()` are optional component-lifecycle seals that prevent new
registration or emits and wait for pending listener settlement during explicit
service teardown.

EventEmitter owns generic process-local listener registration and invocation.
Remote delivery, durable storage, message matching, and application event
policy remain outside its scope.

## Runnable examples

Each example runs independently and records stable key output from a real local
run:

- [Runtime foundation overview](examples/runtime_foundation.py)
- [Sync, async, and concurrent calls](examples/basic_sync_async.py)
- [Body result and retained background settlement](examples/body_result_and_background_drain.py)
- [Finite generations and pinned loop affinity](examples/generation_and_pinned_context.py)
- [Callbacks, errors, and cancellation](examples/callbacks_errors_and_cancellation.py)
- [Same-loop task ownership and settlement](examples/local_task_scope.py)
- [Tunnel broadcast, timeout, and failure](examples/tunnel_broadcast.py)
- [StageStream lazy execution, replay, and failure](examples/stage_stream.py)
- [EventEmitter listeners without ordinary close](examples/event_emitter.py)
- [Automatic process exit after retained work](examples/automatic_process_exit.py)

## Runtime constraints

- Async callables remain concurrent on one Stage loop; the single control
  worker is not a serial task executor.
- Stage scopes share the process-wide carrier. A scope is a lifetime and
  settlement boundary, not a tenant, fault, process, or resource-isolation
  boundary.
- Blocking functions and synchronous generator stepping use a separate blocking
  executor and do not block the Stage loop.
- No daemon Stage control thread, generator bridge thread, polling thread, or
  user `atexit` scheduling is used.
- Cross-thread submission has fixed overhead. For very fine-grained work,
  submit one async root that creates many asyncio tasks, or use a pinned context.
- Native async callers should directly await native async work when no
  sync/thread/loop-neutral bridge is needed.
- CPU-bound parallelism still belongs in a process executor or another
  application-owned execution boundary.

## Compatibility names

The preview imports `StageResponse`, `StageHybridGenerator`, `StageDispatch`,
`StageDispatchEnvironment`, `StageCallBackTask`, `StageTaskProxy`,
`TaskThreadPool`, and `StageFunction` remain available. They delegate to the
canonical Stage runtime and do not own additional event loops or bridge threads.
New code should prefer `Stage`, `StageHandle`, `StageStream`, `Tunnel`, and
`EventEmitter`, plus `LocalTaskScope` and `TunnelSubscription` when their
explicit same-loop or reader-lifecycle contracts are required.

## Development

```shell
uv sync
.venv/bin/pyright agently_stage tests examples
.venv/bin/python -m pytest -q --ignore=tests/test_api/test_Stage_benchmark.py
.venv/bin/python -m pytest -q tests/test_api/test_Stage_benchmark.py --benchmark-only
.venv/bin/pre-commit run --all-files
```
