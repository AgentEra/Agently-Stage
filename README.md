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
reader.

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
terminal state raise `TunnelClosedError`.

`Tunnel(timeout=seconds)` applies a reader-local wait timeout. Timing out one
reader does not close or mutate the channel.

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
emitter.close()
```

`emit(..., wait=False)` returns listener handles immediately while Stage retains
the work. `wait=True` waits without merging listener failures; each failure
remains observable from its own handle. `async_emit()` and `async_close()` are
available for async applications. Closing an emitter prevents new emits and
waits for pending listeners.

EventEmitter is generic local pub/sub. RuntimeEvent normalization, workflow
signals, matching policy, buffering, and durable event storage remain outside
its scope.

## Runtime constraints

- Async callables remain concurrent on one Stage loop; the single control
  worker is not a serial task executor.
- Blocking functions and synchronous generator stepping use a separate blocking
  executor and do not block the Stage loop.
- No daemon Stage control thread, generator bridge thread, polling thread, or
  user `atexit` scheduling is used.
- Cross-thread submission has fixed overhead. For very fine-grained work,
  submit one async root that creates many asyncio tasks, or use a pinned context.
- CPU-bound parallelism still belongs in a process executor or another
  application-owned execution boundary.

## Compatibility names

The preview imports `StageResponse`, `StageHybridGenerator`, `StageDispatch`,
`StageDispatchEnvironment`, `StageCallBackTask`, `StageTaskProxy`,
`TaskThreadPool`, and `StageFunction` remain available. They delegate to the
canonical Stage runtime and do not own additional event loops or bridge threads.
New code should prefer `Stage`, `StageHandle`, `StageStream`, `Tunnel`, and
`EventEmitter`.

## Development

```shell
uv sync
.venv/bin/pyright agently_stage tests examples
.venv/bin/python -m pytest -q
.venv/bin/pre-commit run --all-files
```

See [the runtime foundation design](docs/superpowers/specs/2026-07-11-stage-runtime-foundation-design.md)
for the standalone runtime architecture and lifecycle invariants.
