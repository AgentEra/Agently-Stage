# Runtime Examples Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagent execution is unavailable because repository instructions prohibit delegation.

**Goal:** Restore the original low-friction Tunnel and EventEmitter lifecycle posture and add independently runnable examples for every common standalone Stage runtime scenario.

**Architecture:** Keep every example self-contained and built only on canonical public APIs. Tunnel retains explicit producer EOF while its constructor default returns to a 10-second reader-local inactivity timeout; EventEmitter retains optional close APIs but ordinary examples rely on finite Stage settlement and require no manual emitter shutdown. A subprocess harness derives expected output directly from each example's recorded comment block.

**Tech Stack:** Python 3.10+, asyncio, threading, pytest, Pyright, Ruff/pre-commit, Jupyter nbconvert.

## Global Constraints

- Work only in the standalone Agently-Stage repository and do not import or encode Agently main-repository semantics.
- Use canonical `Stage`, `StageHandle`, `StageStream`, `Tunnel`, and `EventEmitter` APIs in recommended examples.
- Every example includes an `Expected key output from a real local run` block and prints only deterministic semantic facts.
- Sleeps may simulate asynchronous work but may not serve as lifecycle correctness grace periods.
- `Tunnel.close()` means producer EOF, not resource cleanup.
- `EventEmitter.close()` is an optional lifecycle seal, not an ordinary-script shutdown requirement.
- Runtime behavior changes follow test-driven development.

---

### Task 1: Restore Tunnel's Documented Default Safety Timeout

**Files:**
- Modify: `tests/test_runtime/test_tunnel_races.py`
- Modify: `agently_stage/Tunnel.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Tunnel(timeout: float | None = 10)`, independent `_TunnelIterator` and `_TunnelAsyncIterator` cursors.
- Produces: `Tunnel(timeout=10)` as the default, while `close()`/`fail()` remain the only channel terminal transitions.

- [ ] **Step 1: Add failing default and reader-isolation tests**

```python
import inspect


def test_default_timeout_preserves_original_ten_second_safety_posture() -> None:
    timeout = inspect.signature(Tunnel).parameters["timeout"].default
    assert timeout == 10


def test_timed_out_reader_does_not_close_tunnel() -> None:
    tunnel: Tunnel[int] = Tunnel(timeout=0.01)
    assert list(tunnel) == []
    tunnel.put(1)
    tunnel.close()
    assert list(tunnel) == [1]
```

- [ ] **Step 2: Run the focused tests and verify the default test fails**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_tunnel_races.py -q`

Expected: the new default assertion fails with `None != 10`; existing reader-isolation behavior passes.

- [ ] **Step 3: Change only the public constructor default**

```python
class Tunnel(Generic[T]):
    def __init__(
        self,
        wait_interval: float = 0.1,
        timeout: float | None = 10,
        timeout_after_start: bool = True,
    ) -> None:
        self._timeout = timeout
```

Do not add timer threads, mutate `_closed` on timeout, or restore the old shared queue/generator implementation.

- [ ] **Step 4: Update README lifecycle wording**

Document that producer `close()` publishes EOF, the default 10-second inactivity timeout ends only the waiting reader, and `timeout=None` opts into indefinite waiting. Remove wording that implies a timeout automatically closes the Tunnel.

- [ ] **Step 5: Run focused verification**

Run: `.venv/bin/python -m pytest tests/test_runtime/test_tunnel_races.py tests/test_api/test_Tunnel.py -q`

Expected: all Tunnel tests pass without warnings.

- [ ] **Step 6: Commit**

```bash
git add agently_stage/Tunnel.py tests/test_runtime/test_tunnel_races.py README.md
git commit -m "fix: restore Tunnel default reader timeout"
```

---

### Task 2: Add Core Stage Lifecycle Examples

**Files:**
- Create: `examples/basic_sync_async.py`
- Create: `examples/body_result_and_background_drain.py`
- Create: `examples/generation_and_pinned_context.py`
- Create: `examples/callbacks_errors_and_cancellation.py`

**Interfaces:**
- Consumes: `Stage.go`, `Stage.get`, `StageHandle.get`, `async_get`, `wait_settled`, `cancel`, callback observers, context-managed Stage.
- Produces: four directly runnable scripts with these exact output contracts.

```text
basic_sync_async.py
sync_result=42
async_result=ready
concurrent_results=['first', 'second']

body_result_and_background_drain.py
body=ready
settled_before_wait=False
settled_after_wait=True

generation_and_pinned_context.py
plain_generation_reopened=True
pinned_loop_reused=True

callbacks_errors_and_cancellation.py
callbacks=['success:42', 'finally']
body_error=ValueError
settlement_error=RuntimeError
cancelled=True
```

- [ ] **Step 1: Write each script with its expected-output comment before executable code**

Use this exact comment format so the later subprocess harness can parse it:

```python
# Expected key output from a real local run:
# sync_result=42
# async_result=ready
# concurrent_results=['first', 'second']
```

- [ ] **Step 2: Implement deterministic synchronization**

For background settlement, have the retained child signal `child_started`, wait on an application-owned release event through `asyncio.to_thread`, return the body result, then release it only after recording `settled_before_wait=False`. For cancellation, wait for the coroutine's started event before calling `handle.cancel(timeout=1)`. Do not infer ordering from elapsed time.

- [ ] **Step 3: Use public lifecycle evidence only**

For plain generations, call `first.wait_settled()` before the second submission and compare `first.generation_id != second.generation_id`. For pinned affinity, return `asyncio.get_running_loop()` from two calls inside one `with Stage()` block and compare object identity.

- [ ] **Step 4: Run all four scripts and copy the observed output into their comments**

Run:

```bash
for file in \
  examples/basic_sync_async.py \
  examples/body_result_and_background_drain.py \
  examples/generation_and_pinned_context.py \
  examples/callbacks_errors_and_cancellation.py; do
  .venv/bin/python "$file"
done
```

Expected: each output exactly matches its declared block and exits normally.

- [ ] **Step 5: Run Pyright on the new scripts**

Run: `.venv/bin/pyright examples/basic_sync_async.py examples/body_result_and_background_drain.py examples/generation_and_pinned_context.py examples/callbacks_errors_and_cancellation.py`

Expected: zero errors and zero warnings.

- [ ] **Step 6: Commit**

```bash
git add examples/basic_sync_async.py examples/body_result_and_background_drain.py examples/generation_and_pinned_context.py examples/callbacks_errors_and_cancellation.py
git commit -m "docs: add core Stage lifecycle examples"
```

---

### Task 3: Add Tunnel, StageStream, And EventEmitter Examples

**Files:**
- Create: `examples/tunnel_broadcast.py`
- Create: `examples/stage_stream.py`
- Create: `examples/event_emitter.py`

**Interfaces:**
- Consumes: writable `Tunnel`, read-only `StageStream`, `EventEmitter.emit`/`async_emit`, returned handles, optional emitter close.
- Produces: three directly runnable scripts with these exact output contracts.

```text
tunnel_broadcast.py
sync_replay=[1, 2]
async_replay=[1, 2]
timeout_reader=[]
later_reader=[3]
failure_values=[4]
failure_type=ValueError

stage_stream.py
started_before_read=False
lazy_result=[0, 1, 2]
sync_replay=[0, 1, 2]
async_replay=[0, 1, 2]
failure_values=[3]
failure_type=ValueError

event_emitter.py
listener_results=['sync:ready', 'async:ready']
once_calls=1
wait_false_ready=False
isolated_error=ValueError
ordinary_close_required=False
```

- [ ] **Step 1: Implement Tunnel as transport, not lifecycle owner**

Use explicit `close()` for the replay channel, a separate `Tunnel(timeout=0.01)` to prove one timed-out reader leaves later publication valid, and `fail(ValueError("source failed"))` after one accepted value to prove values precede the terminal error.

- [ ] **Step 2: Implement StageStream with read-only replay**

Create the stream with `lazy=True`, record the source-start flag before reading, call `get()`, then replay through both `list(stream)` and an `async for` collector. Use a separate failing generator to capture the accepted prefix and typed source error.

- [ ] **Step 3: Implement EventEmitter without ordinary close**

Register one sync and one async listener, verify one `once` listener fires once, use an application-owned release event to show a `wait=False` handle is initially not ready, and read a failing listener's `ValueError` from its own handle. Do not call `emitter.close()` in the ordinary path; print `ordinary_close_required=False` only after all returned handles have settled.

- [ ] **Step 4: Run all three scripts and copy observed output into their comments**

Run:

```bash
for file in examples/tunnel_broadcast.py examples/stage_stream.py examples/event_emitter.py; do
  .venv/bin/python "$file"
done
```

Expected: each output exactly matches its declared block and exits normally.

- [ ] **Step 5: Run Pyright on the scripts**

Run: `.venv/bin/pyright examples/tunnel_broadcast.py examples/stage_stream.py examples/event_emitter.py`

Expected: zero errors and zero warnings.

- [ ] **Step 6: Commit**

```bash
git add examples/tunnel_broadcast.py examples/stage_stream.py examples/event_emitter.py
git commit -m "docs: add Stage transport and event examples"
```

---

### Task 4: Prove Automatic Exit And Continuously Verify Every Example

**Files:**
- Create: `examples/automatic_process_exit.py`
- Create: `tests/test_examples.py`
- Modify: `examples/runtime_foundation.py`
- Modify: `examples/readme_examples.ipynb`
- Modify: `README.md`

**Interfaces:**
- Consumes: finite Stage generation retention, all public example scripts and their expected-output blocks.
- Produces: one no-close process-exit example, an examples index, a compact standalone quickstart, and a subprocess acceptance harness.

- [ ] **Step 1: Write the no-close process-exit example**

Use this exact output contract:

```python
# Expected key output from a real local run:
# body=ready
# background_finished=True
```

The root coroutine creates a retained child, returns `"ready"`, and the script prints the body before the child prints `background_finished=True`. Do not call `Stage.close()`, register `atexit`, or create raw threads.

- [ ] **Step 2: Add the subprocess harness**

Create `tests/test_examples.py` with an explicit list of every `.py` example. Parse contiguous `# ` lines after `# Expected key output from a real local run:` and compare them to stdout:

```python
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.stem)
def test_example_matches_recorded_key_output(example: Path) -> None:
    expected = read_expected_output(example)
    result = subprocess.run(
        [sys.executable, str(example)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == expected
```

The explicit `EXAMPLES` list contains `runtime_foundation.py` plus all eight new scripts so an accidental utility file is not treated as public documentation.

- [ ] **Step 3: Align the existing quickstart artifacts**

Rename `transport_drain` to `background_cleanup` in `runtime_foundation.py` and the notebook. Remove ordinary `emitter.close()` calls from both. Keep their existing four-line expected output unchanged.

- [ ] **Step 4: Add a README examples index and lifecycle wording**

Link every script by scenario. State that ordinary Stage and EventEmitter usage does not need a shutdown call, EventEmitter close is an optional seal, Tunnel close is EOF, and StageStream terminates its internal channel automatically.

- [ ] **Step 5: Run example acceptance and notebook execution**

Run: `.venv/bin/python -m pytest tests/test_examples.py -q`

Expected: nine parametrized example cases pass.

Run: `jupyter nbconvert --to notebook --execute examples/readme_examples.ipynb --output-dir=/tmp --output=agently-stage-readme-examples-verified.ipynb`

Expected: execution succeeds without warnings.

- [ ] **Step 6: Commit**

```bash
git add README.md examples tests/test_examples.py
git commit -m "docs: complete standalone runtime example suite"
```

---

### Task 5: Final Acceptance And Evidence Reconciliation

**Files:**
- Modify: `docs/superpowers/specs/2026-07-11-runtime-examples-design.md`
- Modify: `docs/superpowers/plans/2026-07-11-runtime-examples.md`

**Interfaces:**
- Consumes: all implemented examples and verification output.
- Produces: an implementation evidence section and a fully checked plan.

- [ ] **Step 1: Run complete static and behavioral verification**

Run:

```bash
.venv/bin/pre-commit run --all-files
.venv/bin/pyright agently_stage tests examples
.venv/bin/python -m pytest -q
```

Expected: all hooks pass, Pyright reports zero errors/warnings, and the full suite passes without lifecycle warnings.

- [ ] **Step 2: Scan standalone ownership boundaries**

Run:

```bash
rg -n -i "provider|ModelRequest|TriggerFlow|EventCenter|FunctionShifter|business abort|Agently integration" README.md examples tests/test_examples.py docs/superpowers/specs/2026-07-11-runtime-examples-design.md
```

Expected: no matches. Product/package name `Agently Stage` is allowed; downstream main-repository concepts are not.

- [ ] **Step 3: Record real evidence and check completed boxes**

Record the Python version, exact full-suite count, example subprocess count, notebook command, Pyright result, and pre-commit result in the design spec. Change its status to `implemented and verified` only after all evidence exists.

- [ ] **Step 4: Commit final evidence**

```bash
git add docs/superpowers/specs/2026-07-11-runtime-examples-design.md docs/superpowers/plans/2026-07-11-runtime-examples.md
git commit -m "docs: verify runtime examples coverage"
```
