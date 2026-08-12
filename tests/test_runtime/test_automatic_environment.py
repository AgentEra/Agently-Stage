from __future__ import annotations

import asyncio
import contextvars
import inspect
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from agently_stage import Stage, StageLifecycleError, StageSettlementError
from agently_stage._runtime import _runtime_snapshot


async def _current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_sync_context_inside_running_loop_uses_safe_carrier() -> None:
    async def scenario() -> tuple[str, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop]:
        caller_loop = asyncio.get_running_loop()

        async def leaf() -> tuple[str, asyncio.AbstractEventLoop]:
            await asyncio.sleep(0)
            return "ok", asyncio.get_running_loop()

        with Stage() as stage:
            value, worker_loop = stage.get(leaf)
        return value, caller_loop, worker_loop

    value, caller_loop, worker_loop = asyncio.run(scenario())

    assert value == "ok"
    assert worker_loop is not caller_loop


def test_sync_context_explains_loop_affinity_boundary() -> None:
    async def scenario() -> None:
        caller_loop = asyncio.get_running_loop()
        loop_bound = caller_loop.create_future()
        caller_loop.call_soon(loop_bound.set_result, "ok")

        with Stage() as stage:
            stage.get(lambda: loop_bound)

    with pytest.raises(StageLifecycleError, match=r"async with Stage\(\).+owner loop"):
        asyncio.run(scenario())


def test_explicit_same_loop_sync_scope_preserves_primary_error() -> None:
    observed_stages: list[Stage] = []

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        with Stage(loop=loop) as stage:
            observed_stages.append(stage)
            stage.get(asyncio.sleep, 0)

    with pytest.raises(StageLifecycleError, match=r"get\(\).+async_get\(\)"):
        asyncio.run(scenario())
    assert observed_stages[0].snapshot().state == "closed"


def test_stage_as_sync_is_a_scoped_adapter() -> None:
    marker = contextvars.ContextVar("marker", default="missing")
    caller_thread = threading.get_ident()
    child_finished = threading.Event()

    async def work(value: int) -> tuple[int, str, int]:
        async def retained_child() -> None:
            await asyncio.sleep(0.01)
            child_finished.set()

        asyncio.create_task(retained_child())
        return value, marker.get(), threading.get_ident()

    marker.set("caller")
    adapted = Stage.as_sync(work)

    assert adapted.__name__ == "work"
    assert inspect.signature(adapted) == inspect.signature(work)
    value, observed_marker, worker_thread = adapted(7)
    assert value == 7
    assert observed_marker == "caller"
    assert worker_thread != caller_thread
    assert child_finished.is_set()


def test_stage_adapters_support_decorator_form() -> None:
    @Stage.as_sync
    async def sync_view(value: int) -> int:
        return value

    @Stage.as_async
    def async_view(value: int) -> int:
        return value

    assert sync_view(1) == 1

    async def scenario() -> None:
        assert await async_view(2) == 2

    asyncio.run(scenario())


def test_stage_as_async_is_a_scoped_adapter() -> None:
    marker = contextvars.ContextVar("marker", default="missing")

    def work(value: int) -> tuple[int, str, int]:
        return value, marker.get(), threading.get_ident()

    async def scenario() -> None:
        caller_thread = threading.get_ident()
        marker.set("caller")
        adapted = Stage.as_async(work)

        assert adapted.__name__ == "work"
        assert inspect.signature(adapted) == inspect.signature(work)
        value, observed_marker, worker_thread = await adapted(7)
        assert value == 7
        assert observed_marker == "caller"
        assert worker_thread != caller_thread

    asyncio.run(scenario())


def test_sync_context_on_carrier_uses_an_escape_loop() -> None:
    outer = Stage(loop="stage")

    async def run_nested_scope() -> tuple[asyncio.AbstractEventLoop, asyncio.AbstractEventLoop]:
        outer_loop = asyncio.get_running_loop()
        with Stage() as nested:
            nested_loop = nested.get(_current_loop)
        return outer_loop, nested_loop

    outer_loop, nested_loop = outer.get(run_nested_scope)
    outer.close()

    assert nested_loop is not outer_loop
    deadline = time.monotonic() + 1
    while _runtime_snapshot().escape_loop_count and time.monotonic() < deadline:
        time.sleep(0.001)
    assert _runtime_snapshot().escape_loop_count == 0


def test_sync_context_avoids_every_transitively_blocked_carrier() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import asyncio
                import time
                from concurrent.futures import ThreadPoolExecutor

                from agently_stage import Stage
                from agently_stage._runtime import _runtime_snapshot

                loops = []

                async def sdk():
                    loops.append(asyncio.get_running_loop())
                    return "ok"

                async def action():
                    loops.append(asyncio.get_running_loop())
                    with Stage() as inner:
                        return inner.get(sdk)

                def manager():
                    with Stage() as outer:
                        return outer.get(action)

                async def chunk():
                    loops.append(asyncio.get_running_loop())
                    return manager()

                assert Stage.as_sync(chunk)() == "ok"
                assert len(set(loops)) == 3

                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(executor.map(lambda _: Stage.as_sync(chunk)(), range(24)))
                assert results == ["ok"] * 24

                deadline = time.monotonic() + 1
                while _runtime_snapshot().escape_loop_count and time.monotonic() < deadline:
                    time.sleep(0.001)
                assert _runtime_snapshot().escape_loop_count == 0
                print("transitive-carrier-ok")
                """
            ),
        ],
        check=False,
        capture_output=True,
        cwd=".",
        text=True,
        timeout=3,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["transitive-carrier-ok"]


def test_sync_context_in_worker_reuses_inherited_caller_loop() -> None:
    async def scenario() -> tuple[asyncio.AbstractEventLoop, asyncio.AbstractEventLoop]:
        caller_loop = asyncio.get_running_loop()

        def sync_middle() -> asyncio.AbstractEventLoop:
            with Stage() as nested:
                return nested.get(_current_loop)

        async with Stage() as outer:
            observed_loop = await outer.go(sync_middle).async_get()
        return caller_loop, observed_loop

    caller_loop, observed_loop = asyncio.run(scenario())

    assert observed_loop is caller_loop


def test_stage_adapters_resolve_dynamic_awaitables() -> None:
    async def resolve(value: int) -> int:
        await asyncio.sleep(0)
        return value

    def produces_awaitable(value: int):
        return resolve(value)

    assert Stage.as_sync(produces_awaitable)(3) == 3

    async def scenario() -> None:
        assert await Stage.as_async(produces_awaitable)(4) == 4

    asyncio.run(scenario())


def test_stage_adapters_preserve_callable_errors() -> None:
    async def async_failure() -> None:
        raise ValueError("async adapter failure")

    def sync_failure() -> None:
        raise LookupError("sync adapter failure")

    with pytest.raises(ValueError, match="async adapter failure"):
        Stage.as_sync(async_failure)()

    async def scenario() -> None:
        with pytest.raises(LookupError, match="sync adapter failure"):
            await Stage.as_async(sync_failure)()

    asyncio.run(scenario())


def test_async_context_nested_in_carrier_reuses_physical_loop() -> None:
    outer = Stage(loop="stage")

    async def run_nested_scope() -> tuple[asyncio.AbstractEventLoop, asyncio.AbstractEventLoop]:
        outer_loop = asyncio.get_running_loop()
        async with Stage() as nested:
            nested_loop = await nested.go(_current_loop).async_get()
        return outer_loop, nested_loop

    outer_loop, nested_loop = outer.get(run_nested_scope)
    outer.close()

    assert nested_loop is outer_loop


def test_stage_adapters_reject_non_callables_and_stream_functions() -> None:
    async def async_source():
        yield 1

    def sync_source():
        yield 1

    with pytest.raises(TypeError, match="callable"):
        Stage.as_sync(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="callable"):
        Stage.as_async(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="scalar"):
        Stage.as_sync(async_source)
    with pytest.raises(TypeError, match="scalar"):
        Stage.as_async(sync_source)


def test_stage_as_async_waits_for_blocking_settlement_before_cancellation() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking() -> None:
        started.set()
        release.wait(5)
        finished.set()

    async def scenario() -> None:
        task = asyncio.create_task(Stage.as_async(blocking)())
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert finished.is_set()

    asyncio.run(scenario())


def test_context_cleanup_error_does_not_replace_sync_body_error() -> None:
    def fail_cleanup() -> None:
        raise RuntimeError("cleanup")

    with pytest.raises(ValueError, match="body") as raised:
        with Stage() as stage:
            stage.go(lambda: 1, on_finally=fail_cleanup)
            raise ValueError("body")

    assert raised.value.__context__ is not None
    assert isinstance(raised.value.__context__, StageSettlementError)
    assert [str(error) for error in raised.value.__context__.errors] == ["cleanup"]
    assert raised.value.__context__.__context__ is None


def test_context_cleanup_error_does_not_replace_async_body_error() -> None:
    async def fail_cleanup() -> None:
        raise RuntimeError("cleanup")

    async def scenario() -> None:
        async with Stage() as stage:
            stage.go(lambda: 1, on_finally=fail_cleanup)
            raise ValueError("body")

    with pytest.raises(ValueError, match="body") as raised:
        asyncio.run(scenario())

    assert raised.value.__context__ is not None
    assert isinstance(raised.value.__context__, StageSettlementError)
    assert [str(error) for error in raised.value.__context__.errors] == ["cleanup"]
    assert raised.value.__context__.__context__ is None


def test_stage_settings_validate_without_creating_a_carrier() -> None:
    before = _runtime_snapshot()

    with pytest.raises(KeyError, match="Unknown"):
        Stage.set_settings("runtime.unknown", 1)
    with pytest.raises(TypeError, match="positive integer"):
        Stage.set_settings("runtime.carrier_loop_count", True)
    with pytest.raises(TypeError, match="positive integer"):
        Stage.set_settings("runtime.carrier_loop_count", 1.5)
    with pytest.raises(ValueError, match="greater than zero"):
        Stage.set_settings("runtime.carrier_loop_count", 0)
    assert Stage.set_settings("runtime.carrier_loop_count", 1) is Stage
    assert _runtime_snapshot() == before


def test_configured_carrier_pool_balances_active_epochs_and_freezes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import asyncio
                import threading

                from agently_stage import Stage, StageLifecycleError
                from agently_stage._runtime import _runtime_snapshot

                assert Stage.set_settings("runtime.carrier_loop_count", 2) is Stage
                release = threading.Event()
                started = [threading.Event(), threading.Event()]
                loops = []

                async def hold(marker):
                    loops.append(asyncio.get_running_loop())
                    marker.set()
                    await asyncio.to_thread(release.wait, 5)

                async def current_loop():
                    return asyncio.get_running_loop()

                stages = [Stage(loop="stage"), Stage(loop="stage")]
                handles = [stage.go(hold, marker) for stage, marker in zip(stages, started)]
                assert all(marker.wait(1) for marker in started)
                snapshot = _runtime_snapshot()
                assert snapshot.carrier_loop_count == 2
                assert snapshot.active_loop_count == 2
                assert len(set(loops)) == 2
                assert stages[0]._generation_lease is not None
                assert stages[1]._generation_lease is not None
                assert stages[0]._generation_lease.slot_id != stages[1]._generation_lease.slot_id

                release.set()
                for handle in handles:
                    handle.get(timeout=1)
                    handle.wait_settled(timeout=1)
                for stage in stages:
                    stage.close()

                rotating = Stage(loop="stage")
                first_loop = rotating.get(current_loop)
                rotating.wait_settled(timeout=1)
                second_loop = rotating.get(current_loop)
                rotating.wait_settled(timeout=1)
                rotating.close()
                assert first_loop is not second_loop

                Stage.set_settings("runtime.carrier_loop_count", 2)
                try:
                    Stage.set_settings("runtime.carrier_loop_count", 3)
                except StageLifecycleError:
                    pass
                else:
                    raise AssertionError("carrier settings did not freeze")
                print("carrier-pool-ok")
                """
            ),
        ],
        check=False,
        capture_output=True,
        cwd=".",
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["carrier-pool-ok"]
