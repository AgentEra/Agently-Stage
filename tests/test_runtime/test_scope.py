from __future__ import annotations

import asyncio
import threading
import time

import pytest

from agently_stage import Stage
from agently_stage._runtime import _runtime_snapshot
from agently_stage.StageException import StageClosedError


def test_empty_context_creates_no_generation() -> None:
    before = _runtime_snapshot()

    with Stage():
        pass

    assert _runtime_snapshot() == before


def test_pinned_context_keeps_loop_affinity_across_idle_gap() -> None:
    async def current_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    with Stage() as stage:
        first = stage.get(current_loop)
        second = stage.get(current_loop)

    assert first is second


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
