from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agently_stage import Stage, StageCallBridge, StageLifecycleError


def test_as_sync_resolves_async_callable_with_context_and_metadata() -> None:
    marker = contextvars.ContextVar("marker", default="missing")
    marker.set("caller")
    caller_thread = threading.get_ident()

    async def read_context(value: int) -> tuple[int, str, int]:
        return value, marker.get(), threading.get_ident()

    bridged = StageCallBridge().as_sync(read_context)

    assert bridged.__name__ == "read_context"
    assert inspect.signature(bridged) == inspect.signature(read_context)
    value, observed_marker, worker_thread = bridged(3)
    assert value == 3
    assert observed_marker == "caller"
    assert worker_thread != caller_thread


def test_as_async_keeps_async_callable_on_caller_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()

        class AsyncCallable:
            async def __call__(self, value: int) -> tuple[int, asyncio.AbstractEventLoop]:
                return value, asyncio.get_running_loop()

        async_callable = AsyncCallable()
        bridged = StageCallBridge().as_async(async_callable)

        assert bridged is async_callable
        assert await bridged(4) == (4, caller_loop)

    asyncio.run(run())


def test_as_async_returns_native_coroutine_function_unchanged() -> None:
    async def work() -> int:
        return 1

    assert StageCallBridge().as_async(work) is work


def test_as_sync_resolves_awaitable_returned_by_sync_callable() -> None:
    async def result() -> int:
        return 5

    def produce_awaitable():
        return result()

    bridge = StageCallBridge()
    assert bridge.as_sync(produce_awaitable)() == 5
    bridge.close()


def test_as_sync_preserves_primary_task_error() -> None:
    async def nested() -> None:
        raise ValueError("primary")

    async def fail() -> None:
        await asyncio.create_task(nested())

    bridge = StageCallBridge()
    with pytest.raises(ValueError, match="primary"):
        bridge.as_sync(fail, managed=True)()
    bridge.close()


def test_as_async_copies_context_into_blocking_executor() -> None:
    marker = contextvars.ContextVar("marker", default="missing")
    caller_thread = threading.get_ident()

    def blocking() -> tuple[str, int]:
        return marker.get(), threading.get_ident()

    async def run() -> None:
        marker.set("caller")
        bridge = StageCallBridge()
        observed_marker, worker_thread = await bridge.as_async(blocking)()
        assert observed_marker == "caller"
        assert worker_thread != caller_thread
        await bridge.async_close()

    asyncio.run(run())


def test_bridge_rejects_non_callable_adapters() -> None:
    bridge = StageCallBridge()
    with pytest.raises(TypeError, match="callable"):
        bridge.as_sync(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="callable"):
        bridge.as_async(1)  # type: ignore[arg-type]
    bridge.close()


def test_as_async_settles_blocking_call_before_cancellation_acknowledgement() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking() -> None:
        started.set()
        release.wait(5)
        finished.set()

    async def run() -> None:
        bridged = StageCallBridge().as_async(blocking, managed=True)
        task = asyncio.create_task(bridged())

        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert finished.is_set()

    asyncio.run(run())


def test_as_async_light_bridge_does_not_wait_for_blocking_call_on_cancel() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking() -> None:
        started.set()
        release.wait(5)
        finished.set()

    async def run() -> None:
        bridged = StageCallBridge().as_async(blocking)
        task = asyncio.create_task(bridged())

        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not finished.is_set()

        release.set()
        assert await asyncio.to_thread(finished.wait, 1)

    asyncio.run(run())


def test_bridge_does_not_close_borrowed_executor() -> None:
    executor = ThreadPoolExecutor(max_workers=1)
    try:

        async def run() -> None:
            bridge = StageCallBridge(executor=executor)
            assert await bridge.as_async(lambda: "done")() == "done"
            await bridge.async_close()

        asyncio.run(run())
        assert executor.submit(lambda: "still-open").result(timeout=1) == "still-open"
    finally:
        executor.shutdown(wait=True)


def test_submit_returns_future_compatible_stage_handle() -> None:
    async def run() -> None:
        bridge = StageCallBridge()

        async def work() -> int:
            await asyncio.sleep(0)
            return 7

        handle = bridge.submit(work)
        callback_values: list[int] = []
        handle.add_done_callback(lambda completed: callback_values.append(completed.result()))

        assert not handle.done()
        assert await handle == 7
        assert handle.done()
        assert not handle.cancelled()
        assert handle.result() == 7
        assert handle.exception() is None
        assert callback_values == [7]
        await bridge.async_close()

    asyncio.run(run())


def test_removed_done_callback_is_not_invoked() -> None:
    bridge = StageCallBridge()
    release = threading.Event()

    async def work() -> str:
        await asyncio.to_thread(release.wait, 5)
        return "done"

    handle = bridge.submit(work)
    observed: list[str] = []

    def callback(_: object) -> None:
        observed.append("called")

    handle.add_done_callback(callback)
    assert handle.remove_done_callback(callback) == 1
    release.set()
    assert handle.result(timeout=1) == "done"
    assert observed == []
    bridge.close()


def test_done_callback_uses_registration_context() -> None:
    marker = contextvars.ContextVar("marker", default="missing")
    bridge = StageCallBridge()
    release = threading.Event()

    async def work() -> int:
        await asyncio.to_thread(release.wait, 5)
        return 9

    handle = bridge.submit(work)
    observed: list[str] = []
    marker.set("registered")
    handle.add_done_callback(lambda _: observed.append(marker.get()))
    marker.set("changed")
    release.set()

    assert handle.result(timeout=1) == 9
    assert observed == ["registered"]
    bridge.close()


def test_sync_bridge_reentry_on_its_carrier_fails_before_inner_submission() -> None:
    bridge = StageCallBridge()
    inner_calls = 0

    async def inner() -> str:
        nonlocal inner_calls
        inner_calls += 1
        return "inner"

    sync_inner = bridge.as_sync(inner)

    async def outer() -> None:
        with pytest.raises(StageLifecycleError, match="carrier"):
            sync_inner()

    bridge.as_sync(outer)()
    assert inner_calls == 0
    bridge.close()


def test_iter_sync_closes_async_source_on_early_consumer_close() -> None:
    finalized = threading.Event()

    async def source():
        try:
            yield 1
            await asyncio.Event().wait()
        finally:
            finalized.set()

    bridge = StageCallBridge()
    iterator = bridge.iter_sync(source())
    assert next(iterator) == 1
    iterator.close()

    assert finalized.wait(1)
    bridge.close()


def test_iter_async_closes_sync_source_on_early_consumer_close() -> None:
    finalized = threading.Event()

    def source():
        try:
            yield 1
            while True:
                yield 2
        finally:
            finalized.set()

    async def run() -> None:
        bridge = StageCallBridge()
        iterator = bridge.iter_async(source())
        assert await anext(iterator) == 1
        await iterator.aclose()

        assert await asyncio.to_thread(finalized.wait, 1)
        await bridge.async_close()

    asyncio.run(run())


def test_iter_sync_preserves_source_order_and_exception() -> None:
    async def source():
        yield 1
        yield 2
        raise ValueError("async-source")

    bridge = StageCallBridge()
    observed: list[int] = []
    with pytest.raises(ValueError, match="async-source"):
        for item in bridge.iter_sync(source()):
            observed.append(item)
    assert observed == [1, 2]
    bridge.close()


def test_iter_sync_propagates_async_source_close_error() -> None:
    class Source:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self) -> None:
            raise RuntimeError("async-close")

    bridge = StageCallBridge()
    with pytest.raises(RuntimeError, match="async-close"):
        list(bridge.iter_sync(Source()))
    bridge.close()


def test_iter_async_preserves_source_order_and_exception() -> None:
    def source():
        yield 1
        yield 2
        raise ValueError("sync-source")

    async def run() -> None:
        bridge = StageCallBridge()
        observed: list[int] = []
        with pytest.raises(ValueError, match="sync-source"):
            async for item in bridge.iter_async(source()):
                observed.append(item)
        assert observed == [1, 2]
        await bridge.async_close()

    asyncio.run(run())


def test_stream_close_can_retry_wait_after_timeout() -> None:
    started = threading.Event()
    release = threading.Event()

    def source():
        yield 1
        started.set()
        release.wait(5)
        yield 2

    stage = Stage(loop="stage")
    stream = stage.go(source())
    assert next(iter(stream)) == 1
    assert started.wait(1)

    with pytest.raises(TimeoutError) as timeout:
        stream.close(timeout=0.01)
    assert type(timeout.value) is TimeoutError

    retry = threading.Thread(target=stream.close)
    retry.start()
    assert retry.is_alive()
    release.set()
    retry.join(1)
    assert not retry.is_alive()
    stage.close()


def test_closing_lazy_stream_does_not_enter_source_body() -> None:
    source_entered = threading.Event()

    async def source():
        source_entered.set()
        yield 1

    stage = Stage(loop="stage")
    stream = stage.go(source, lazy=True)
    stream.close(timeout=1)

    assert stream.closed
    assert not source_entered.is_set()
    stage.close()


def test_bridge_close_can_retry_after_timeout() -> None:
    started = threading.Event()
    release = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    bridge = StageCallBridge(executor=executor)

    async def work() -> None:
        started.set()
        await asyncio.to_thread(release.wait, 5)

    caller = threading.Thread(target=bridge.as_sync(work))
    caller.start()
    assert started.wait(1)

    with pytest.raises(TimeoutError):
        bridge.close(timeout=0.01)

    retry = threading.Thread(target=bridge.close)
    retry.start()
    assert retry.is_alive()
    release.set()
    retry.join(1)
    caller.join(1)
    assert not retry.is_alive()
    assert not caller.is_alive()
    assert bridge._carrier_stage.snapshot().state == "closed"
    executor.shutdown(wait=True)


def test_bridge_does_not_close_borrowed_stage() -> None:
    stage = Stage()
    bridge = StageCallBridge(stage=stage)
    assert bridge.submit(lambda: "borrowed").result(timeout=1) == "borrowed"
    bridge.close()
    assert stage.get(lambda: "still-open") == "still-open"
    stage.close()


def test_stage_accepts_borrowed_executor_without_owning_shutdown() -> None:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        stage = Stage(loop="stage", executor=executor)
        assert stage.get(lambda: "stage") == "stage"
        stage.close()
        assert executor.submit(lambda: "borrowed").result(timeout=1) == "borrowed"
    finally:
        executor.shutdown(wait=True)


def test_stage_rejects_executor_and_max_workers_together() -> None:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        with pytest.raises(ValueError, match="executor"):
            Stage(executor=executor, max_workers=1)
    finally:
        executor.shutdown(wait=True)
