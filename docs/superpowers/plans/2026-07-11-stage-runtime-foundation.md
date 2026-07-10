# Stage Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Agently-Stage's per-instance loop and bridge-thread design with one process-wide carrier, finite loop generations, settlement-aware handles, loop-neutral channels and streams, and a Stage-backed EventEmitter.

**Architecture:** A private `_RuntimeCarrier` owns one non-daemon `ThreadPoolExecutor(max_workers=1)` control worker and creates finite asyncio loop generations. Public `Stage` scopes submit scalar or streaming work and return `StageHandle` or `StageStream`; `Tunnel` remains an independent writable broadcast channel, while compatibility modules delegate to these canonical owners without creating threads or loops of their own.

**Tech Stack:** Python 3.10+, asyncio, concurrent.futures, threading, contextvars, pytest, pytest-benchmark, Ruff, Pyright.

## Global Constraints

- Python support starts at 3.10; implementation and tests may use Python 3.10 syntax and behavior.
- Production code follows test-first red-green-refactor cycles; every behavior test must be observed failing for the intended reason before implementation.
- The control executor has exactly one worker and never executes user coroutine bodies as separate executor jobs.
- Synchronous callables and generator stepping use a distinct blocking executor.
- No daemon control thread, daemon generator bridge, polling thread, user `atexit` scheduling, or public process shutdown API may be introduced.
- Generation admission and zero-reservation sealing use one lock and no timing grace period.
- `StageHandle.get()` exposes the body outcome; settlement includes retained descendants, callbacks, and finalizers without rewriting that body outcome.
- `Tunnel` is writable and replayable; `StageStream` is read-only and task-bound.
- EventEmitter is generic local pub/sub and must not implement EventCenter RuntimeEvent or TriggerFlow SignalNet policy.
- Existing preview imports remain available as delegating compatibility facades, but undocumented per-instance loop ownership is not preserved.

---

## File Responsibility Map

| File | Responsibility |
|---|---|
| `agently_stage/_runtime.py` | Private carrier singleton, generation state, reservation admission/seal, task submission, descendant task factory, shared blocking executor |
| `agently_stage/StageHandle.py` | Typed body outcome, quiescence barrier, callback pipeline, cancellation handoff, settlement diagnostics |
| `agently_stage/Stage.py` | Public scope, task classification, pinned context lease, sync/async close, scalar and generator submission |
| `agently_stage/StageStream.py` | Read-only sync/async stream facade over Tunnel plus source StageHandle |
| `agently_stage/Tunnel.py` | Loop-neutral writable replay channel with sync and async subscriber cursors |
| `agently_stage/EventEmitter.py` | Thread-safe listener registry and Stage-backed listener fan-out |
| `agently_stage/StageException.py` | Typed closed-scope, lifecycle, channel, and settlement errors |
| `agently_stage/StageResponse.py` | StageHandle compatibility export |
| `agently_stage/StageHybridGenerator.py` | StageStream compatibility export |
| `agently_stage/StageDispatch.py` | Legacy dispatch facade over Stage, with no loop ownership |
| `agently_stage/StageTask.py` | Legacy callback/task proxy facade over canonical Stage execution |
| `agently_stage/TaskThreadPool.py` | Legacy blocking submission facade over the shared blocking executor |
| `agently_stage/__init__.py` | Canonical and compatibility public exports |

---

### Task 1: Finite Carrier Generations And Scalar Stage Handles

**Files:**
- Create: `agently_stage/_runtime.py`
- Create: `agently_stage/StageHandle.py`
- Modify: `agently_stage/Stage.py`
- Modify: `agently_stage/StageException.py`
- Modify: `agently_stage/__init__.py`
- Create: `tests/test_runtime/test_generation.py`
- Create: `tests/test_runtime/test_scalar_handle.py`
- Create: `tests/test_runtime/test_process_exit.py`

**Interfaces:**
- Produces: `Stage.go(callable, *args, **kwargs) -> StageHandle[T]`, `Stage.get(...) -> T`, `StageHandle.get(timeout=None) -> T`, `StageHandle.async_get(timeout=None) -> T`, `StageHandle.wait_settled(timeout=None) -> None`, `StageHandle.async_wait_settled(timeout=None) -> None`, and private `_RUNTIME_CARRIER`.
- Produces: `StageClosedError`, `StageLifecycleError`, and `StageSettlementError(errors)`.

- [x] **Step 1: Write failing lazy-generation and repeated-generation tests**

```python
def test_stage_is_lazy_and_repeated_batches_use_finite_generations():
    before = _runtime_snapshot()
    stage = Stage()
    assert _runtime_snapshot() == before

    first = stage.go(lambda: 1)
    assert first.get() == 1
    first.wait_settled()
    assert _wait_until(lambda: _runtime_snapshot().active_generation_id is None)

    second = stage.go(lambda: 2)
    assert second.get() == 2
    second.wait_settled()
    assert second.generation_id > first.generation_id
```

- [x] **Step 2: Run the generation test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_generation.py -q`

Expected: collection fails because `_runtime_snapshot`, `StageHandle`, and finite carrier generations do not exist.

- [x] **Step 3: Implement the private carrier state machine and scalar submission path**

```python
class _GenerationState(Enum):
    QUEUED = "queued"
    STARTING = "starting"
    OPEN = "open"
    SEALING = "sealing"
    DRAINING = "draining"
    CLOSED = "closed"


@dataclass(frozen=True)
class _RuntimeSnapshot:
    active_generation_id: int | None
    queued_generation_id: int | None
    active_loop_count: int
    control_thread_count: int


class _RuntimeCarrier:
    def submit(self, handle: StageHandle[Any], runner: Callable[[_Generation], Awaitable[None]], preferred: _Generation | None = None) -> int: ...
    def retain_descendant(self, generation: _Generation, handle: StageHandle[Any]) -> None: ...
    def release(self, generation: _Generation, handle: StageHandle[Any]) -> None: ...
    def acquire_lease(self) -> _Generation: ...
    def release_lease(self, generation: _Generation) -> None: ...
    def snapshot(self) -> _RuntimeSnapshot: ...
```

Use one admission lock for reservation and seal decisions. Queue submissions on a not-yet-started generation rather than blocking `Stage.go()` behind the prior generation's drain.

- [x] **Step 4: Implement the one-shot body result and quiescence barrier**

```python
class StageHandle(Generic[T]):
    generation_id: int

    def get(self, timeout: float | None = None) -> T: ...
    async def async_get(self, timeout: float | None = None) -> T: ...
    def wait_settled(self, timeout: float | None = None) -> None: ...
    async def async_wait_settled(self, timeout: float | None = None) -> None: ...
    def cancel(self, timeout: float | None = None) -> bool: ...
```

The body outcome uses `concurrent.futures.Future[T]`. The settlement barrier uses a condition and outstanding-work count so later legal callback admission can create a new unsettled epoch while the Stage scope is open.

- [x] **Step 5: Run scalar and generation tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_generation.py tests/test_runtime/test_scalar_handle.py -q`

Expected: all scalar and generation tests pass with no runtime warnings.

- [x] **Step 6: Write and verify subprocess exit tests RED then GREEN**

```python
def test_process_waits_for_retained_stage_work(tmp_path):
    result = _run_script(
        """
from agently_stage import Stage
import asyncio

async def root():
    async def child():
        await asyncio.sleep(0.05)
        print("child-finished")
    asyncio.create_task(child())
    return "body-finished"

print(Stage().get(root))
"""
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["body-finished", "child-finished"]
    assert "Task was destroyed" not in result.stderr
```

Run the single test before descendant tracking and confirm it fails because the child is cancelled or omitted. Then install a context-aware task factory on each private Stage loop, retain descendant tasks against the active handle and generation, and rerun until it passes.

- [x] **Step 7: Verify Task 1 and commit**

Run: `.venv/bin/python -m pytest tests/test_runtime -q`

Run: `.venv/bin/pre-commit run --all-files`

Commit: `git commit -m "refactor: add finite Stage runtime generations"`

---

### Task 2: Pinned Scopes, Callback Pipelines, And Settlement Errors

**Files:**
- Modify: `agently_stage/_runtime.py`
- Modify: `agently_stage/StageHandle.py`
- Modify: `agently_stage/Stage.py`
- Modify: `agently_stage/StageException.py`
- Create: `tests/test_runtime/test_scope.py`
- Create: `tests/test_runtime/test_callbacks.py`

**Interfaces:**
- Consumes: Task 1 carrier reservation and StageHandle quiescence primitives.
- Produces: `with Stage()`/`async with Stage()` pinned generation leases, `Stage.close()`, `Stage.async_close()`, and chainable `on_success`, `on_error`, `on_finally`.

- [x] **Step 1: Write failing pinned-scope and close-race tests**

```python
def test_pinned_context_keeps_loop_affinity_across_idle_gap():
    async def current_loop():
        return asyncio.get_running_loop()

    with Stage() as stage:
        first = stage.get(current_loop)
        second = stage.get(current_loop)
        assert first is second


def test_scope_close_rejects_late_callback_registration():
    stage = Stage()
    handle = stage.go(lambda: "ok")
    assert handle.get() == "ok"
    stage.close()
    with pytest.raises(StageClosedError):
        handle.on_success(lambda value: value)
```

- [x] **Step 2: Run scope tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_scope.py -q`

Expected: failures show context calls are not pinned and callback admission is not sealed atomically with close.

- [x] **Step 3: Implement lazy pinned leases and synchronous/asynchronous scope close**

```python
class Stage:
    def close(self, timeout: float | None = None) -> None: ...
    async def async_close(self, timeout: float | None = None) -> None: ...
    def __enter__(self) -> Stage: ...
    def __exit__(self, exc_type: object, exc: BaseException | None, traceback: object) -> None: ...
    async def __aenter__(self) -> Stage: ...
    async def __aexit__(self, exc_type: object, exc: BaseException | None, traceback: object) -> None: ...
```

An empty context creates no generation. First submission in a context acquires one lease; close atomically seals the scope, releases the lease, waits only scope-owned active handles, then shuts down a scope-private blocking executor when present.

- [x] **Step 4: Write failing callback ordering, fast-body, and settlement-isolation tests**

```python
def test_immediate_body_accepts_chain_without_grace_period():
    observed: list[str] = []
    handle = (
        Stage().go(lambda: "value")
        .on_success(lambda value: observed.append(value))
        .on_finally(lambda: observed.append("finally"))
    )
    assert handle.get() == "value"
    handle.wait_settled()
    assert observed == ["value", "finally"]


def test_callback_failure_does_not_rewrite_body_outcome():
    handle = Stage().go(lambda: 42).on_success(lambda value: 1 / 0)
    assert handle.get() == 42
    with pytest.raises(StageSettlementError) as exc_info:
        handle.wait_settled()
    assert isinstance(exc_info.value.errors[0], ZeroDivisionError)
```

- [x] **Step 5: Run callback tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_callbacks.py -q`

Expected: callback methods are absent or callbacks race with body completion.

- [x] **Step 6: Implement the ordered observer callback drain**

```python
class StageHandle(Generic[T]):
    def on_success(self, callback: Callable[[T], object | Awaitable[object]]) -> StageHandle[T]: ...
    def on_error(self, callback: Callable[[BaseException], object | Awaitable[object]]) -> StageHandle[T]: ...
    def on_finally(self, callback: Callable[[], object | Awaitable[object]]) -> StageHandle[T]: ...
```

Callback registration, Stage scope sealing, and settlement-barrier admission share the scope admission lock. A cached body outcome may schedule a callback drain in the next generation. The drain processes matching observers in registration order, records failures, continues to finalizers, and never changes the body future.

- [x] **Step 7: Verify Task 2 and commit**

Run: `.venv/bin/python -m pytest tests/test_runtime -q`

Commit: `git commit -m "feat: add Stage scope and settlement callbacks"`

---

### Task 3: Compatibility Facades Without Independent Lifecycle Owners

**Files:**
- Modify: `agently_stage/StageResponse.py`
- Modify: `agently_stage/StageDispatch.py`
- Modify: `agently_stage/StageTask.py`
- Modify: `agently_stage/TaskThreadPool.py`
- Modify: `agently_stage/StageFunction.py`
- Modify: `agently_stage/__init__.py`
- Modify: `tests/test_api/test_StageTaskProxy.py`
- Modify: `tests/test_api/test_Stage_with.py`
- Create: `tests/test_runtime/test_compatibility.py`

**Interfaces:**
- Consumes: Stage, StageHandle, and the carrier's blocking executor.
- Produces: import-compatible StageResponse, StageDispatch, StageDispatchEnvironment, StageCallBackTask, StageTaskProxy, TaskThreadPool, and StageFunction without new loop or bridge threads.

- [x] **Step 1: Write failing compatibility-owner tests**

```python
def test_legacy_facades_do_not_create_additional_control_threads():
    before = _control_thread_identities()
    response = StageDispatch(reuse_env=False).run_sync_function(lambda: 1)
    assert response.result() == 1
    assert len(_control_thread_identities() - before) <= 1
    assert not _daemon_stage_threads()
```

- [x] **Step 2: Run compatibility tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_compatibility.py -q`

Expected: current StageDispatch creates a separate event-loop thread and TaskThreadPool owns another pool.

- [x] **Step 3: Replace compatibility implementations with delegating facades**

```python
class StageResponse(StageHandle[T], Generic[T]):
    pass


class StageDispatch:
    def run_sync_function(self, func: Callable[..., T], *args: object, **kwargs: object) -> Future[T]: ...
    def run_async_function(self, func: Callable[..., Awaitable[T]], *args: object, **kwargs: object) -> Future[T]: ...
    def close(self) -> None: ...
```

`TaskThreadPool.submit()` delegates only to the shared blocking executor. `StageCallBackTask` uses its provided Stage or a plain Stage carrier submission; it never creates a raw thread or calls `asyncio.run()`.

- [x] **Step 4: Update old tests to the reviewed body-error contract**

Replace assertions that expect `StageResponse.get()` to return an exception object with `pytest.raises(...)`; retain `ignore_exception=True` returning `None` and ensure `on_error` still observes the original error.

- [x] **Step 5: Verify all scalar compatibility tests and commit**

Run: `.venv/bin/python -m pytest tests/test_api/test_Stage_with.py tests/test_api/test_StageTaskProxy.py tests/test_runtime -q`

Commit: `git commit -m "refactor: delegate legacy Stage runtime facades"`

---

### Task 4: Loop-Neutral Replayable Tunnel

**Files:**
- Modify: `agently_stage/Tunnel.py`
- Modify: `agently_stage/StageException.py`
- Replace: `tests/test_api/test_Tunnel.py`
- Create: `tests/test_runtime/test_tunnel_races.py`

**Interfaces:**
- Produces: `Tunnel[T].put`, `async_put`, `close`, `async_close`, `fail`, `put_stop`, `get`, `__iter__`, and `__aiter__`.
- Produces: `TunnelClosedError` and terminal source-error propagation.

- [x] **Step 1: Write failing replay, fan-out, failure, and concurrent publication tests**

```python
def test_each_subscriber_replays_the_full_sequence():
    tunnel: Tunnel[int] = Tunnel()
    tunnel.put(1)
    first = iter(tunnel)
    tunnel.put(2)
    tunnel.close()
    assert list(first) == [1, 2]
    assert list(tunnel) == [1, 2]


def test_async_subscribers_are_woken_without_polling():
    async def scenario():
        tunnel: Tunnel[int] = Tunnel()
        first = asyncio.create_task(_collect_async(tunnel))
        second = asyncio.create_task(_collect_async(tunnel))
        await tunnel.async_put(1)
        await tunnel.async_close()
        assert await first == [1]
        assert await second == [1]

    asyncio.run(scenario())
```

- [x] **Step 2: Run Tunnel tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_api/test_Tunnel.py tests/test_runtime/test_tunnel_races.py -q`

Expected: current shared queue consumes each item once globally, so independent subscribers do not receive full replay.

- [x] **Step 3: Implement independent cursor iterators and waiter handoff**

```python
class Tunnel(Generic[T]):
    def put(self, item: T) -> None: ...
    async def async_put(self, item: T) -> None: ...
    def close(self) -> None: ...
    async def async_close(self) -> None: ...
    def fail(self, error: BaseException) -> None: ...
    def get(self, timeout: float | None = None) -> list[T]: ...
    def __iter__(self) -> Iterator[T]: ...
    def __aiter__(self) -> AsyncIterator[T]: ...
```

Protect publication order, item history, terminal state, sync conditions, and async waiter registration with one lock. Wake async waiters using their owner loop's `call_soon_threadsafe`; remove cancelled or timed-out waiters deterministically.

- [x] **Step 4: Verify Tunnel and commit**

Run: `.venv/bin/python -m pytest tests/test_api/test_Tunnel.py tests/test_runtime/test_tunnel_races.py -q`

Commit: `git commit -m "refactor: rebuild Tunnel as replay channel"`

---

### Task 5: Read-Only StageStream And Generator Settlement

**Files:**
- Create: `agently_stage/StageStream.py`
- Modify: `agently_stage/StageHybridGenerator.py`
- Modify: `agently_stage/Stage.py`
- Modify: `agently_stage/__init__.py`
- Create: `tests/test_runtime/test_stage_stream.py`

**Interfaces:**
- Consumes: Tunnel, Stage scalar submission, StageHandle settlement.
- Produces: `StageStream[T]` with sync/async iteration, `get`, `async_get`, callback delegation, cancellation, and settlement waits.

- [ ] **Step 1: Write failing sync/async generator stream tests**

```python
def test_generator_returns_read_only_stage_stream():
    def source():
        yield from range(3)

    stream = Stage().go(source)
    assert isinstance(stream, StageStream)
    assert stream.get() == [0, 1, 2]
    assert not hasattr(stream, "put")


def test_async_generator_can_be_consumed_from_user_loop():
    async def scenario():
        async def source():
            for item in range(3):
                await asyncio.sleep(0)
                yield item

        stream = Stage().go(source)
        assert [item async for item in stream] == [0, 1, 2]
        await stream.async_wait_settled()

    asyncio.run(scenario())
```

- [ ] **Step 2: Run StageStream tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_stage_stream.py -q`

Expected: StageStream does not exist and StageHybridGenerator uses polling/shared queue behavior.

- [ ] **Step 3: Implement StageStream composition and generator consumption**

```python
class StageStream(Generic[T]):
    def get(self, timeout: float | None = None) -> list[T]: ...
    async def async_get(self, timeout: float | None = None) -> list[T]: ...
    def __iter__(self) -> Iterator[T]: ...
    def __aiter__(self) -> AsyncIterator[T]: ...
    def wait_settled(self, timeout: float | None = None) -> None: ...
    async def async_wait_settled(self, timeout: float | None = None) -> None: ...
    def cancel(self, timeout: float | None = None) -> bool: ...
```

Consume async generators on the Stage loop. Consume synchronous generators on the blocking executor. Publish every value to a private Tunnel, publish failure after prior values, close exactly once, and return the collected list as the source body result. Keep `StageHybridGenerator` importable as a StageStream subclass or alias without a polling thread.

- [ ] **Step 4: Verify generator compatibility and commit**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_stage_stream.py tests/test_api/test_Tunnel.py -q`

Commit: `git commit -m "feat: add settlement-aware StageStream"`

---

### Task 6: Stage-Backed EventEmitter

**Files:**
- Modify: `agently_stage/EventEmitter.py`
- Replace: `tests/test_api/test_EventEmitter.py`
- Modify: `tests/test_hybrid/test_Stage_EventEmitter.py`
- Create: `tests/test_runtime/test_event_emitter_races.py`

**Interfaces:**
- Consumes: Stage and StageHandle.
- Produces: thread-safe `on`, `off`, `once`, `listener_count`, `emit`, `async_emit`, `close`, and `async_close`.

- [ ] **Step 1: Write failing concurrent-once and pending-close tests**

```python
def test_concurrent_emit_invokes_once_listener_once():
    emitter = EventEmitter()
    calls = 0
    calls_lock = threading.Lock()

    @emitter.once("value")
    def listener(value: int) -> None:
        nonlocal calls
        with calls_lock:
            calls += 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: emitter.emit("value", 1, wait=True), range(50)))
    assert calls == 1


def test_close_waits_for_fire_and_forget_listeners():
    emitter = EventEmitter()
    finished = threading.Event()
    emitter.on("value", lambda: (time.sleep(0.05), finished.set()))
    emitter.emit("value", wait=False)
    emitter.close()
    assert finished.is_set()
```

- [ ] **Step 2: Run EventEmitter tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_event_emitter_races.py -q`

Expected: listener dictionaries race and current per-emit Stage contexts do not provide emitter-owned pending settlement.

- [ ] **Step 3: Implement one emitter-owned Stage scope and atomic listener snapshotting**

```python
class EventEmitter:
    def on(self, event: str, listener: Listener | None = None) -> Listener: ...
    def off(self, event: str, listener: Listener) -> None: ...
    def once(self, event: str, listener: Listener | None = None) -> Listener: ...
    def emit(self, event: str, *args: object, wait: bool = False, **kwargs: object) -> list[StageHandle[Any] | StageStream[Any]]: ...
    async def async_emit(self, event: str, *args: object, wait: bool = False, **kwargs: object) -> list[StageHandle[Any] | StageStream[Any]]: ...
    def close(self) -> None: ...
    async def async_close(self) -> None: ...
```

Remove once listeners inside the registry lock before invoking them. Snapshot ordinary listeners under the same lock. Submit listeners through one emitter-owned unpinned Stage; `wait=False` returns handles immediately, and emitter close seals admission then waits pending listener settlement.

- [ ] **Step 4: Verify EventEmitter and commit**

Run: `.venv/bin/python -m pytest tests/test_api/test_EventEmitter.py tests/test_hybrid/test_Stage_EventEmitter.py tests/test_runtime/test_event_emitter_races.py -q`

Commit: `git commit -m "refactor: rebuild EventEmitter on Stage settlement"`

---

### Task 7: Public Documentation, Typing, Performance, And Final Acceptance

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `examples/readme_examples.ipynb` only where it teaches replaced APIs
- Create: `examples/runtime_foundation.py`
- Modify: `docs/superpowers/specs/2026-07-11-stage-runtime-foundation-design.md`
- Modify: `docs/superpowers/plans/2026-07-11-stage-runtime-foundation.md`
- Modify: public modules found incomplete by Pyright or signature audit
- Create: additional regression tests required by the acceptance audit

**Interfaces:**
- Consumes: all completed runtime APIs.
- Produces: current recommended usage, runnable key-output example, Python 3.10 metadata, complete public typing, and reconciled implemented-design evidence.

- [ ] **Step 1: Update package compatibility and recommended examples**

Set `requires-python = ">=3.10"` and Ruff `target-version = "py310"`. Add a runnable example containing this stable expected-output comment:

```python
# Expected key output from a real local run:
# body=ready
# drained=True
# stream=[0, 1, 2]
# listener_calls=1
```

README must explain plain versus context-managed Stage, body result versus settlement, Tunnel versus StageStream, callback observer semantics, EventEmitter close, and the absence of a required ordinary-script shutdown hook.

- [ ] **Step 2: Run the documented example and record actual stable output**

Run: `.venv/bin/python examples/runtime_foundation.py`

Expected output contains exactly the four documented key-value lines. If observed values differ, fix implementation or update both example behavior and the recorded comment from the real run.

- [ ] **Step 3: Run typing and lint, fixing public boundaries found by the tools**

Run: `uvx pyright agently_stage tests examples/runtime_foundation.py`

Expected: zero errors. Broad `Any` is allowed only at callable payload and compatibility boundaries where the docstring states that intent.

Run: `.venv/bin/pre-commit run --all-files`

Expected: all hooks pass.

- [ ] **Step 4: Run the full test and subprocess acceptance suite**

Run: `.venv/bin/python -m pytest -q`

Expected: every tracked legacy, lifecycle, race, settlement, stream, emitter, benchmark, and subprocess test passes without RuntimeWarning, unclosed-loop warnings, destroyed-task messages, or daemon Stage bridge threads.

- [ ] **Step 5: Run a clean package installation smoke**

Run: `uv venv --python 3.10 .smoke-venv`

Run: `uv pip install --python .smoke-venv/bin/python .`

Run: `.smoke-venv/bin/python -c 'from agently_stage import EventEmitter, Stage, StageHandle, StageStream, Tunnel; print(Stage().get(lambda: "ok"))'`

Expected: `ok`, followed by normal process exit. Remove only the task-created ignored `.smoke-venv` after recording the result.

- [ ] **Step 6: Reconcile design and plan status**

Change the design status to implemented only after every acceptance criterion has direct test, typing, documentation, or smoke evidence. Check every completed plan box and record implementation commit anchors in the design document.

- [ ] **Step 7: Commit final standalone acceptance**

Run: `git diff --check`

Commit: `git commit -m "docs: complete Stage runtime foundation refactor"`

---

## Final Requirement Audit

Before declaring the branch complete, build a requirement-to-evidence table covering all 15 acceptance criteria in the design. Each row must cite a test name, command output, public file, or implementation anchor. A passing full suite alone is insufficient if it does not directly exercise interpreter exit, generation races, loop affinity, callback reopening, stream fan-out, once-listener concurrency, typing, or documentation behavior.
