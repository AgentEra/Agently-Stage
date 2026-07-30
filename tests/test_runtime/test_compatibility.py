from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from agently_stage import Stage, StageCallBackTask, StageDispatch, StageFunction, StageResponse, StageTaskProxy
from agently_stage.StageHandle import StageHandle
from agently_stage.TaskThreadPool import TaskThreadPool


def _legacy_runtime_threads() -> list[threading.Thread]:
    legacy_prefixes = ("AgentlyStageDispatchThread", "shutdown_monitor_thread")
    return [thread for thread in threading.enumerate() if thread.name.startswith(legacy_prefixes)]


def test_stage_response_is_the_handle_compatibility_name() -> None:
    assert StageResponse is StageHandle


def test_stage_dispatch_delegates_without_legacy_loop_threads() -> None:
    dispatch = StageDispatch(reuse_env=False)

    sync_future = dispatch.run_sync_function(lambda: 1)

    async def async_body() -> int:
        await asyncio.sleep(0)
        return 2

    async_future = dispatch.run_async_function(async_body)
    assert sync_future.result(timeout=1) == 1
    assert async_future.result(timeout=1) == 2
    dispatch.close()
    assert _legacy_runtime_threads() == []


def test_stage_dispatch_to_executor_work_is_owned_by_close_barrier() -> None:
    dispatch = StageDispatch(max_workers=1)
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    def body() -> str:
        started.set()
        release.wait()
        return "done"

    future = dispatch.to_executor(body)
    assert started.wait(timeout=1)

    close_thread = threading.Thread(target=lambda: (dispatch.close(), closed.set()))
    close_thread.start()
    close_was_blocked = not closed.wait(timeout=0.05)
    release.set()
    close_thread.join(timeout=1)
    assert close_was_blocked
    assert closed.is_set()
    assert future.result(timeout=1) == "done"


def test_stage_dispatch_future_remains_sync_readable_inside_a_running_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()
        dispatch = StageDispatch()

        async def current_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        future = dispatch.run_async_function(current_loop)
        assert future.result(timeout=1) is not caller_loop
        dispatch.close()

    asyncio.run(run())


def test_task_thread_pool_reuses_canonical_executors() -> None:
    assert TaskThreadPool.submit(lambda: "sync").result(timeout=1) == "sync"

    async def async_body() -> str:
        await asyncio.sleep(0)
        return "async"

    assert TaskThreadPool.submit(async_body).result(timeout=1) == "async"
    assert _legacy_runtime_threads() == []


def test_task_thread_pool_async_future_remains_sync_readable_inside_a_running_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()

        async def current_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        future = TaskThreadPool.submit(current_loop)
        assert future.result(timeout=1) is not caller_loop

    asyncio.run(run())


def test_stage_callback_task_uses_stage_instead_of_raw_thread() -> None:
    observed: list[str] = []
    callback = StageCallBackTask(lambda value: observed.append(value))

    handle = callback("done")

    handle.get(timeout=1)
    handle.wait_settled(timeout=1)
    assert observed == ["done"]
    assert _legacy_runtime_threads() == []


def test_stage_task_proxy_preserves_direct_sync_callback_order() -> None:
    observed: list[str] = []
    proxy = StageTaskProxy(
        lambda: "body",
        on_success=lambda value: observed.append(value),
        on_finally=lambda: observed.append("finally"),
    )

    assert proxy() == "body"
    assert observed == ["body", "finally"]


def test_stage_function_concurrent_first_call_submits_once() -> None:
    stage = Stage()
    original_go = stage.go

    def slow_go(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.03)
        return original_go(*args, **kwargs)

    cast("Any", stage).go = slow_go
    stage_function = StageFunction(stage, lambda: "done")
    start = threading.Barrier(8)

    def invoke():  # type: ignore[no-untyped-def]
        start.wait()
        return stage_function.go()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(invoke) for _ in range(8)]
        handles = [future.result(timeout=1) for future in futures]

    assert len({id(handle) for handle in handles}) == 1
    assert handles[0].get(timeout=1) == "done"
    stage.close()
