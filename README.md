# Agently Stage

Agently Stage is a Python 3.10+ runtime bridge for safely combining synchronous
callers, asyncio work, blocking functions, generators, streaming channels, and
local event listeners.

Creating a `Stage` does not create a thread, loop, or permanent loop binding.
The first admitted root in each active epoch selects its backend lazily:

- inside an async service, `Stage()` uses that service's current running loop;
- without a running loop, `Stage()` uses the process-wide Stage carrier;
- after complete settlement, a reusable automatic Stage releases the binding
  and selects again when later work arrives.

The Stage carrier uses one process-wide control worker with finite asyncio loop
generations. Retained work drains, its loop closes, and a later batch can open a
new generation. Ordinary scripts do not need a process shutdown hook.

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

print(fetch_handle.get())  # network-result
print(calculate_handle.get())  # 42
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

When automatic or explicit Stage work uses the caller's running loop, blocking
`get()`, `wait_settled()`, `close()`, a waiting `cancel()`, or synchronous
StageStream iteration on that same loop would prevent the work from advancing.
Stage detects this case and raises `StageLifecycleError`; use the corresponding
async API or `async for`. A zero-timeout `handle.cancel(timeout=0)` may still be
used to request cancellation without claiming settlement.

Stage never stops or closes a caller-owned event loop and never replaces its
task factory. Calling `asyncio.run()` before or after Stage remains valid.

Backend selection can also be explicit:

```python
async def service() -> None:
    loop = asyncio.get_running_loop()

    same_loop = Stage(loop=loop)  # pinned to this caller-owned loop
    carrier = Stage(loop="stage")  # always use the finite Stage carrier

    assert await same_loop.go(fetch).async_get() == "network-result"
    assert await carrier.go(fetch).async_get() == "network-result"

    await same_loop.async_close()
    await carrier.async_close()
```

`None`, `"new"`, and `"default"` are not loop modes. Omit `loop` for automatic
selection or use the exact `"stage"` policy.

Each `Stage.go()` admission captures the caller's `contextvars` context. The
root and initial callbacks inherit that snapshot. A callback registered later
captures its own registration-time context. Context changes made inside Stage
do not mutate the caller's context.

### Body result and settlement are different

`get()` returns the root/body outcome. `wait_settled()` additionally waits for
Stage-retained work, callbacks, and finalizers.

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
print(handle.get())  # business-result
print(drained.is_set())  # False
handle.wait_settled()
print(drained.is_set())  # True
```

Body errors are raised by `get()` and do not become settlement errors.
Callback, finalizer, or retained-descendant failures are reported by
`wait_settled()` as `StageSettlementError` without replacing the body result.
For code that consumes Future-shaped objects, `StageHandle` also provides
`done()`, `cancelled()`, `result()`, `exception()`, `add_done_callback()`,
`remove_done_callback()`, and `await handle`. These access the body outcome;
`wait_settled()` remains the explicit barrier for retained work.

`StageHandle.cancel()` fences the handle's Stage-owned body task tree, including
retained descendants and descendants created while cancellation is being
delivered. Call `wait_settled()` after `cancel()` when later Stage-owned work
must be ruled out. Cleanup callbacks and finalizers still settle. Cancellation
cannot preempt a non-cooperative blocking function or undo an external side
effect that has already committed; applications must use their own idempotency,
authorization, or compensation policy for those effects.

On the Stage-owned carrier, tasks created inside Stage work are retained by the
carrier task factory. On a caller-owned loop, Stage deliberately does not
replace the loop's task factory: settlement covers work created through
`Stage.go()`, native tasks created through `Stage.create_task()`, and existing
tasks explicitly attached with `Stage.adopt()`. An unrelated raw
`asyncio.create_task()` remains owned by the caller.

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

## Lazy epochs and scope lifetime

Automatic backend selection happens when work enters, not when `Stage()` is
constructed. A Stage created during synchronous application setup can therefore
share a service loop when its first task is submitted later:

```python
import asyncio

from agently_stage import Stage


async def current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


stage = Stage()
carrier_loop = stage.get(current_loop)
stage.wait_settled()


async def service() -> None:
    service_loop = asyncio.get_running_loop()
    selected = await stage.go(current_loop).async_get()
    assert selected is service_loop
    assert selected is not carrier_loop
    await stage.async_close()


asyncio.run(service())
```

One active epoch never spans multiple loops. Cross-thread submissions during an
active epoch are delivered to that epoch's selected loop. Complete settlement
releases an automatic binding; the next root selects again.

`with Stage()` and `async with Stage()` are lifecycle conveniences. Context exit
seals the scope and waits for its work, but context entry does not pin an
automatic Stage to a carrier generation. Use `Stage(loop="stage")` or an exact
loop object when the backend policy must be pinned. An empty context creates no
loop.

`Stage.close()` and `Stage.async_close()` are scope barriers for explicit
application lifecycles. They are not required to make an ordinary script exit:
an active non-daemon control job keeps retained work alive, then the finite loop
closes by itself.

`seal()` rejects new external roots while already accepted roots, queued work,
owned nested work, callbacks, and finalizers drain. `wait_settled()` waits
without sealing. `close()` combines seal and settlement. Async counterparts are
available for all blocking barriers.

When a settlement timeout expires, Stage raises `TimeoutError` with unresolved
origins. The scope remains sealed, and `close()` may be called again after the
outstanding work settles.

### Create or adopt caller-loop tasks

`create_task()` creates a native `asyncio.Task` on the current running caller
loop and makes Stage its lifecycle owner in one operation:

```python
import asyncio

from agently_stage import Stage


async def main() -> None:
    async def hook() -> str:
        await asyncio.sleep(0)
        return "ready"

    stage = Stage()
    task = stage.create_task(hook(), origin="event:ready-hook")

    assert isinstance(task, asyncio.Task)
    assert await task == "ready"
    await stage.async_close(timeout=1)


asyncio.run(main())
```

This surface is for frameworks that already run on an asyncio loop and require
native task identity for `gather`, cancellation, and current-task checks. It
uses the same Stage inventory, origin diagnostics, cancellation, and settlement
barrier as `adopt()`. It does not return a copied task facade.

`adopt()` attaches an already scheduled task from the selected caller loop to
Stage cancellation, origin diagnostics, and settlement:

```python
import asyncio

from agently_stage import Stage


async def main() -> None:
    async def hook() -> str:
        await asyncio.sleep(0)
        return "ready"

    stage = Stage()
    task = asyncio.create_task(hook())
    adopted = stage.adopt(task, origin="event:ready-hook")

    assert adopted is task
    assert await task == "ready"
    await stage.async_close(timeout=1)


asyncio.run(main())
```

Use `create_task()` when Stage is responsible for creating the work. Reserve
`adopt()` for a task that genuinely existed before the ownership handoff.
An adopted task has already been scheduled by its loop, so
`max_concurrency`/`max_pending` cannot honestly delay it. Those admission limits
apply to roots created by `Stage.go()`. `create_task()` and `adopt()` both
return the original native task: the task remains the body-outcome handle,
while Stage adds scope ownership, origin diagnostics, cancellation, idle
tracking, and settlement without wrapping it in a second `StageHandle`.

Adapters that need live adopted-task inventory can read `adopted_count`,
`adopted_tasks`, and `origin_for_adopted(task)`. A Stage can also receive one
synchronous completion observer:

```python
def observe(task: asyncio.Task[object], origin: str) -> None:
    error = None if task.cancelled() else task.exception()
    print(origin, task.cancelled(), error)


stage = Stage(on_adopted_done=observe)
```

The observer runs after the task leaves the live inventory and before Stage
settlement completes. It is a lightweight notification seam, not a business
outcome policy: callbacks must not block, and applications still own error
classification, retry, persistence, and side effects. Observer failures are
reported to the task loop's exception handler and do not reinterpret the task
outcome or Stage settlement.

`LocalTaskScope` remains importable in the 0.3 line only as a deprecated
compatibility facade over `Stage`. It emits `DeprecationWarning`, delegates
task creation and inventory directly to Stage, and is scheduled for removal in
0.4.0. New code should use `Stage.go()`, `Stage.create_task()`, or
`Stage.adopt()`.

### Pressure and idle budgets

`max_concurrency` bounds concurrently running external `go()` roots.
`max_pending` bounds accepted roots waiting for a permit; overflow raises
`StageBackpressureError` immediately. Owned nested Stage work does not consume a
second root permit, so `max_concurrency=1` does not deadlock parent/child cleanup
chains. `max_workers` independently bounds blocking executor workers.
Alternatively, `executor=existing_executor` borrows an application-owned
`concurrent.futures.Executor`; it is mutually exclusive with `max_workers` and
Stage never shuts it down.

`idle_timeout` applies while Stage-owned work is unresolved. Admissions,
terminal work, callbacks, and stream publication update the monotonic activity
clock. Long-running providers or tools can call `stage.tick()` to report
cooperative progress:

```python
stage = Stage(max_concurrency=8, max_pending=32, idle_timeout=30)
```

An idle timeout seals the Stage, requests cancellation of owned work, and is
reported as `StageIdleTimeoutError` after settlement. It does not claim that a
non-cooperative blocking call or external side effect has stopped.

`snapshot()` returns a bounded immutable `StageSnapshot` with scope state,
backend mode, active/pending counts, unresolved origins, activity time, idle
state, and carrier generation id. It contains no application event or workflow
types.

Stage is a task-lifetime mechanism, not an event bus, workflow runtime, tenant
boundary, provider cancellation acknowledgement, or business retry policy.

## StageCallBridge

`StageCallBridge` adapts call shape at sync/async boundaries without making
application event, retry, or workflow decisions.

```python
import asyncio

from agently_stage import StageCallBridge


bridge = StageCallBridge()


async def fetch_name(identifier: int) -> str:
    await asyncio.sleep(0)
    return f"user-{identifier}"


fetch_name_sync = bridge.as_sync(fetch_name)
assert fetch_name_sync(7) == "user-7"


async def main() -> None:
    calculate_async = bridge.as_async(lambda value: value * 2)
    assert await calculate_async(21) == 42


asyncio.run(main())
bridge.close()
```

`as_async()` directly awaits an async callable on the caller's loop. A blocking
sync callable runs in the selected executor with the caller's `contextvars`
snapshot. The default adapter is a light call-shape bridge: cancelling its
awaiting task does not wait for an already-running blocking call, because
Python cannot preempt that thread. Use `as_async(function, managed=True)` when
the caller owns the task lifetime and cancellation acknowledgement must wait
until the blocking call actually returns or raises.

`as_sync()` resolves awaitables through the finite Stage carrier and fails fast
if a synchronous wait would re-enter that same carrier. It may be called while
another loop is running in the caller thread for compatibility, but it blocks
that thread and the awaitable must not own objects bound to the caller loop;
ordinary async code should await instead. By default it returns the body
outcome without adding a settlement barrier; use
`as_sync(function, managed=True)` when the boundary owns descendant work and
must wait for it. A primary body error is never replaced by a duplicate
settlement error. `submit()` returns a loop-neutral managed `StageHandle`.
`iter_sync(async_iterator)` and `iter_async(sync_iterator)` are managed because
their source lifetime extends beyond one call: they preserve source order,
propagate source errors, and close the source in its execution context when the
consumer stops early.

The module-level `default_stage_call_bridge` is available for framework
adapters that want one shared bridge. Applications with an explicit lifecycle
can own a separate bridge and call `close()`/`async_close()`; a timeout leaves
the bridge sealed and close may be retried. A supplied Stage or executor is
borrowed and is never closed by the bridge.

StageCallBridge is intentionally not the fast path for ordinary native calls.
Directly call sync work from sync code and directly await async work from async
code when no call-shape bridge is needed.

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

print(stream.get())  # [0, 1, 2]
print(list(stream))  # [0, 1, 2] (replay)
stage.close()
```

`for` and `async for` both work. Every reader has an independent replay cursor.
Source errors are delivered after values already published. Stream callbacks
observe source completion once and receive the complete result list; they do
not transform individual items. `lazy=True` delays source start until the first
reader. The source automatically publishes EOF or failure to StageStream's
internal channel. A consumer that intentionally stops early can call
`close()`/`async_close()` to request source termination and wait for settlement;
if that wait times out, close may be called again.

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
- [Finite generations and lazy backend reselection](examples/generation_and_pinned_context.py)
- [Callbacks, errors, and cancellation](examples/callbacks_errors_and_cancellation.py)
- [Tunnel broadcast, timeout, and failure](examples/tunnel_broadcast.py)
- [StageStream lazy execution, replay, and failure](examples/stage_stream.py)
- [Call-shape bridging and early stream close](examples/call_bridge.py)
- [EventEmitter listeners without ordinary close](examples/event_emitter.py)
- [Automatic process exit after retained work](examples/automatic_process_exit.py)

## Runtime constraints

- Async callables remain concurrent on one active backend loop; the shared
  carrier control worker is not a serial task executor.
- Stage scopes share the process-wide carrier. A scope is a lifetime and
  settlement boundary, not a tenant, fault, process, or resource-isolation
  boundary.
- Blocking functions and synchronous generator stepping use a separate blocking
  executor and do not block the Stage loop.
- No daemon Stage control thread, generator bridge thread, polling thread, or
  user `atexit` scheduling is used.
- Cross-thread submission has fixed overhead. For very fine-grained work,
  submit one async root that creates many asyncio tasks, or select an explicit
  loop policy.
- Native async callers should directly await native async work when no
  sync/thread/loop-neutral bridge is needed.
- CPU-bound parallelism still belongs in a process executor or another
  application-owned execution boundary.

## Compatibility names

The preview imports `StageResponse`, `StageHybridGenerator`, `StageDispatch`,
`StageDispatchEnvironment`, `StageCallBackTask`, `StageTaskProxy`,
`TaskThreadPool`, and `StageFunction` remain available. They delegate to the
canonical Stage runtime and do not own additional event loops or bridge threads.
`StageDispatch` and the async `TaskThreadPool.submit(...)` path explicitly use
the shared Stage carrier so their returned `concurrent.futures.Future` objects
remain synchronously readable even when submitted from a running event loop.
New code should prefer `Stage`, `StageHandle`, `StageStream`, `StageCallBridge`,
`Tunnel`, and `EventEmitter`, plus `TunnelSubscription` when an independent
reader lifecycle is required. `LocalTaskScope` is compatibility-only and is not
recommended for new code.

## Development

```shell
uv sync
.venv/bin/pyright agently_stage tests examples
.venv/bin/python -m pytest -q --ignore=tests/test_api/test_Stage_benchmark.py
.venv/bin/python -m pytest -q tests/test_api/test_Stage_benchmark.py --benchmark-only
.venv/bin/pre-commit run --all-files
```
