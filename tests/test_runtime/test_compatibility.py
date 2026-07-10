from __future__ import annotations

import asyncio
import threading

from agently_stage import StageCallBackTask, StageDispatch, StageResponse, StageTaskProxy
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


def test_task_thread_pool_reuses_canonical_executors() -> None:
    assert TaskThreadPool.submit(lambda: "sync").result(timeout=1) == "sync"

    async def async_body() -> str:
        await asyncio.sleep(0)
        return "async"

    assert TaskThreadPool.submit(async_body).result(timeout=1) == "async"
    assert _legacy_runtime_threads() == []


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
