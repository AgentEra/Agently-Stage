from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time

import pytest

from agently_stage import Stage


def test_sync_and_async_body_results_are_available_from_sync_callers() -> None:
    stage = Stage()

    async def async_body() -> str:
        await asyncio.sleep(0)
        return "async"

    assert stage.get(lambda: "sync") == "sync"
    assert stage.get(async_body) == "async"
    stage.close()


def test_async_reader_does_not_conflict_with_user_event_loop() -> None:
    async def scenario() -> None:
        stage = Stage()

        async def body() -> int:
            await asyncio.sleep(0)
            return 42

        handle = stage.go(body)
        assert await handle.async_get() == 42
        await handle.async_wait_settled()
        await stage.async_close()

    asyncio.run(scenario())


def test_coroutines_remain_concurrent_on_single_control_worker() -> None:
    stage = Stage()

    async def body(value: int) -> int:
        await asyncio.sleep(0.05)
        return value

    started = time.monotonic()
    handles = [stage.go(body, value) for value in range(20)]
    assert [handle.get() for handle in handles] == list(range(20))
    elapsed = time.monotonic() - started

    assert elapsed < 0.3
    stage.close()


def test_body_exception_is_raised_without_becoming_settlement_failure() -> None:
    stage = Stage()

    def body() -> None:
        raise ValueError("body failed")

    handle = stage.go(body)
    with pytest.raises(ValueError, match="body failed"):
        handle.get()
    handle.wait_settled()
    stage.close()


def test_ignore_exception_returns_none() -> None:
    stage = Stage()

    def body() -> None:
        raise ValueError("ignored")

    handle = stage.go(body, ignore_exception=True)
    assert handle.get() is None
    handle.wait_settled()
    stage.close()


def test_cancel_hands_off_to_owner_loop_and_waits_for_acknowledgement() -> None:
    stage = Stage()
    started = threading.Event()

    async def body() -> None:
        started.set()
        await asyncio.sleep(10)

    handle = stage.go(body)
    assert started.wait(timeout=1)
    assert handle.cancel(timeout=1)
    with pytest.raises(concurrent.futures.CancelledError):
        handle.get()
    handle.wait_settled()
    stage.close()


def test_body_result_returns_before_retained_descendant_settles() -> None:
    stage = Stage()
    child_finished = threading.Event()

    async def body() -> str:
        async def child() -> None:
            await asyncio.sleep(0.05)
            child_finished.set()

        asyncio.create_task(child())
        return "ready"

    handle = stage.go(body)

    assert handle.get() == "ready"
    assert not child_finished.is_set()
    handle.wait_settled()
    assert child_finished.is_set()
    stage.close()
