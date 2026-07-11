from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from agently_stage import EventEmitter
from agently_stage.StageException import StageClosedError


def test_concurrent_emit_invokes_once_listener_once() -> None:
    emitter = EventEmitter()
    calls = 0
    calls_lock = threading.Lock()

    @emitter.once("value")
    def listener(value: int) -> None:
        nonlocal calls
        with calls_lock:
            calls += value

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: emitter.emit("value", 1, wait=True), range(50)))

    assert calls == 1
    emitter.close()


def test_fire_and_forget_emit_returns_before_listener_completion() -> None:
    emitter = EventEmitter()
    finished = threading.Event()

    @emitter.on("value")
    def listener() -> None:
        time.sleep(0.1)
        finished.set()

    started = time.monotonic()
    handles = emitter.emit("value", wait=False)
    elapsed = time.monotonic() - started

    assert elapsed < 0.05
    assert len(handles) == 1
    assert not finished.is_set()
    emitter.close()
    assert finished.is_set()


def test_listener_failures_are_isolated_and_observable_from_handles() -> None:
    emitter = EventEmitter()

    @emitter.on("value")
    def failed_listener() -> None:
        raise ValueError("listener failed")

    @emitter.on("value")
    def successful_listener() -> str:
        return "ok"

    failed, successful = emitter.emit("value", wait=True)

    with pytest.raises(ValueError, match="listener failed"):
        failed.get()
    assert successful.get() == "ok"
    emitter.close()


def test_async_emit_waits_without_blocking_user_loop() -> None:
    async def scenario() -> None:
        emitter = EventEmitter()

        @emitter.on("value")
        async def listener(value: int) -> int:
            await asyncio.sleep(0.01)
            return value + 1

        handles = await emitter.async_emit("value", 1, wait=True)

        assert await handles[0].async_get() == 2
        await emitter.async_close()

    asyncio.run(scenario())


def test_closed_emitter_rejects_new_emit() -> None:
    emitter = EventEmitter()
    emitter.close()

    with pytest.raises(StageClosedError):
        emitter.emit("value")


def test_listener_registry_operations_are_idempotent() -> None:
    emitter = EventEmitter()

    def listener() -> None:
        return None

    emitter.on("value", listener)
    emitter.on("value", listener)
    assert emitter.listener_count("value") == 1
    emitter.off("value", listener)
    emitter.off("value", listener)
    assert emitter.listener_count("value") == 0
    emitter.close()


def test_wait_does_not_swallow_process_control_exceptions() -> None:
    emitter = EventEmitter()

    @emitter.on("value")
    def listener() -> None:
        raise KeyboardInterrupt

    try:
        with pytest.raises(KeyboardInterrupt):
            emitter.emit("value", wait=True)
    finally:
        emitter.close()
