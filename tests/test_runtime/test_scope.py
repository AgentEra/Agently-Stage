from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, cast

import pytest

from agently_stage import Stage
from agently_stage._runtime import _runtime_snapshot
from agently_stage.StageException import StageClosedError, StageLifecycleError, StageSettlementError


def test_empty_context_creates_no_generation() -> None:
    before = _runtime_snapshot()

    with Stage():
        pass

    assert _runtime_snapshot() == before


def test_context_manager_does_not_pin_auto_backend_across_idle_gap() -> None:
    async def current_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    with Stage() as stage:
        first = stage.get(current_loop)
        second = stage.get(current_loop)

    assert first is not second


def test_context_close_waits_for_scope_work() -> None:
    finished = threading.Event()

    async def body() -> None:
        await asyncio.sleep(0.05)
        finished.set()

    with Stage() as stage:
        stage.go(body)

    assert finished.is_set()


def test_closing_one_scope_does_not_wait_for_unrelated_scope() -> None:
    slow_stage = Stage()
    fast_stage = Stage()
    release = threading.Event()

    slow_stage.go(release.wait)
    fast_stage.go(lambda: "done")

    started = time.monotonic()
    fast_stage.close()
    assert time.monotonic() - started < 0.2

    release.set()
    slow_stage.close()


def test_closed_scope_rejects_new_submission() -> None:
    stage = Stage()
    stage.close()

    with pytest.raises(StageClosedError):
        stage.go(lambda: None)


def test_async_context_uses_nonblocking_close_reader() -> None:
    async def scenario() -> None:
        async with Stage() as stage:
            handle = stage.go(asyncio.sleep, 0.01, result="done")
            assert await handle.async_get() == "done"

    asyncio.run(scenario())


def test_sync_task_cannot_close_its_own_stage_scope() -> None:
    stage = Stage()

    handle = stage.go(lambda: stage.close(timeout=0.05))

    with pytest.raises(StageLifecycleError, match="owned by the same scope"):
        handle.get(timeout=1)
    stage.close()


def test_async_task_cannot_close_its_own_stage_scope() -> None:
    async def scenario() -> None:
        stage = Stage()

        async def close_owner() -> None:
            await stage.async_close(timeout=0.05)

        handle = stage.go(close_owner)
        with pytest.raises(StageLifecycleError, match="owned by the same scope"):
            await handle.async_get(timeout=1)
        await stage.async_close()

    asyncio.run(scenario())


def test_async_close_does_not_block_caller_loop_during_executor_shutdown() -> None:
    shutdown_finished = threading.Event()
    shutdown_saw_heartbeat: list[bool] = []
    heartbeat = asyncio.Event()

    class SlowShutdownExecutor:
        def shutdown(self, *, wait: bool) -> None:
            assert wait
            time.sleep(0.05)
            shutdown_saw_heartbeat.append(heartbeat.is_set())
            shutdown_finished.set()

    async def scenario() -> None:
        stage = Stage()
        cast("Any", stage)._private_executor = SlowShutdownExecutor()

        async def tick() -> None:
            await asyncio.sleep(0.01)
            heartbeat.set()

        tick_task = asyncio.create_task(tick())
        await stage.async_close()
        await tick_task
        assert heartbeat.is_set()
        assert shutdown_finished.is_set()
        assert shutdown_saw_heartbeat == [True]

    asyncio.run(scenario())


def test_concurrent_close_callers_share_the_scope_barrier() -> None:
    stage = Stage()
    started = threading.Event()
    release = threading.Event()
    first_closed = threading.Event()
    second_closed = threading.Event()

    def body() -> None:
        started.set()
        release.wait()

    stage.go(body)
    assert started.wait(timeout=1)
    first = threading.Thread(target=lambda: (stage.close(), first_closed.set()))
    second = threading.Thread(target=lambda: (stage.close(), second_closed.set()))
    first.start()
    second.start()
    second_returned_before_settlement = second_closed.wait(timeout=0.02)
    release.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not second_returned_before_settlement
    assert first_closed.is_set()
    assert second_closed.is_set()


def test_scope_close_reports_already_quiescent_settlement_errors() -> None:
    stage = Stage()

    def fail_callback(value: str) -> None:
        raise RuntimeError(value)

    handle = stage.go(lambda: "settled-failure").on_success(fail_callback)
    with pytest.raises(StageSettlementError):
        handle.wait_settled(timeout=1)

    with pytest.raises(StageSettlementError) as exc_info:
        stage.close()

    assert isinstance(exc_info.value.errors[0], RuntimeError)
