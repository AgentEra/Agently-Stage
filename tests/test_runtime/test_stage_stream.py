from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import threading

import pytest

from agently_stage import Stage, StageHybridGenerator, StageStream


def test_sync_generator_returns_read_only_replayable_stage_stream() -> None:
    def source():
        yield from range(3)

    stream = Stage().go(source)

    assert isinstance(stream, StageStream)
    assert stream.get() == [0, 1, 2]
    assert list(stream) == [0, 1, 2]
    assert not hasattr(stream, "put")
    stream.wait_settled()


def test_stream_uses_one_canonical_growing_buffer_and_returns_a_safe_list() -> None:
    def source():
        yield from range(5)

    stream = Stage().go(source)
    result = stream.get()
    internal_result = stream._ensure_started().get()

    assert internal_result is stream._tunnel._items
    result.append(99)
    assert list(stream) == [0, 1, 2, 3, 4]


def test_async_generator_can_be_consumed_from_user_loop() -> None:
    async def scenario() -> None:
        async def source():
            for item in range(3):
                await asyncio.sleep(0)
                yield item

        stream = Stage().go(source)

        assert [item async for item in stream] == [0, 1, 2]
        assert await stream.async_get() == [0, 1, 2]
        await stream.async_wait_settled()

    asyncio.run(scenario())


def test_sync_and_async_subscribers_each_receive_the_full_stream() -> None:
    async def scenario() -> None:
        async def source():
            for item in range(5):
                await asyncio.sleep(0)
                yield item

        stream = Stage().go(source)

        async_reader = asyncio.create_task(_collect_async(stream))
        sync_values = await asyncio.to_thread(list, stream)
        assert sync_values == list(range(5))
        assert await async_reader == list(range(5))

    asyncio.run(scenario())


async def _collect_async(stream: StageStream[int]) -> list[int]:
    return [item async for item in stream]


def test_source_failure_is_delivered_after_published_values() -> None:
    def source():
        yield 1
        raise ValueError("source failed")

    stream = Stage().go(source)
    iterator = iter(stream)

    assert next(iterator) == 1
    with pytest.raises(ValueError, match="source failed"):
        next(iterator)
    with pytest.raises(ValueError, match="source failed"):
        stream.get()
    stream.wait_settled()


def test_stream_callbacks_observe_source_completion_once() -> None:
    observed: list[list[int]] = []

    def source():
        yield from range(3)

    stream = Stage().go(source).on_success(observed.append)

    assert stream.get() == [0, 1, 2]
    stream.wait_settled()
    assert observed == [[0, 1, 2]]


def test_lazy_stream_starts_on_first_reader() -> None:
    started = threading.Event()

    def source():
        started.set()
        yield 1

    stream = Stage().go(source, lazy=True)
    assert not started.is_set()

    assert stream.get() == [1]
    assert started.is_set()


def test_lazy_stream_callback_preserves_registration_context() -> None:
    request_id = contextvars.ContextVar[str | None]("request_id", default=None)
    observed: list[str | None] = []

    def source():
        yield 1

    registration_token = request_id.set("registration")
    try:
        stream = Stage().go(source, lazy=True).on_success(lambda _: observed.append(request_id.get()))
    finally:
        request_id.reset(registration_token)

    start_token = request_id.set("start")
    try:
        assert stream.get() == [1]
        stream.wait_settled()
    finally:
        request_id.reset(start_token)

    assert observed == ["registration"]


def test_stream_cancellation_reaches_source_finalizer() -> None:
    started = threading.Event()
    finalized = threading.Event()

    async def source():
        started.set()
        try:
            while True:
                await asyncio.sleep(1)
                yield 1
        finally:
            finalized.set()

    stream = Stage().go(source)
    assert started.wait(timeout=1)
    assert stream.cancel(timeout=1)
    with pytest.raises(concurrent.futures.CancelledError):
        stream.get()
    stream.wait_settled()
    assert finalized.wait(timeout=1)


def test_hybrid_generator_name_is_a_stage_stream_compatibility_type() -> None:
    assert issubclass(StageHybridGenerator, StageStream)
