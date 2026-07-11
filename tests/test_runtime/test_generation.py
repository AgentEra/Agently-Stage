from __future__ import annotations

import asyncio
import threading
import time

from agently_stage import Stage, StageHandle
from agently_stage._runtime import _runtime_snapshot


def _wait_for_idle(timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _runtime_snapshot().active_generation_id is None:
            return True
        time.sleep(0.001)
    return False


def test_stage_creation_is_lazy() -> None:
    before = _runtime_snapshot()

    stage = Stage()

    assert _runtime_snapshot() == before
    stage.close()


def test_plain_stage_can_cross_finite_generations() -> None:
    stage = Stage()

    first = stage.go(lambda: 1)

    assert isinstance(first, StageHandle)
    assert first.get() == 1
    first.wait_settled()
    assert _wait_for_idle()

    second = stage.go(lambda: 2)

    assert second.get() == 2
    second.wait_settled()
    assert second.generation_id > first.generation_id
    assert _wait_for_idle()
    stage.close()


def test_next_generation_queues_while_previous_loop_drains() -> None:
    stage = Stage()
    finalizer_started = threading.Event()
    release_finalizer = threading.Event()
    retained_generators: list[object] = []

    async def source():
        try:
            yield 1
        finally:
            finalizer_started.set()
            while not release_finalizer.is_set():
                await asyncio.sleep(0.001)

    async def body() -> str:
        generator = source()
        assert await anext(generator) == 1
        retained_generators.append(generator)
        return "first"

    first = stage.go(body)
    assert first.get() == "first"
    first.wait_settled()
    assert finalizer_started.wait(timeout=1)

    second = stage.go(lambda: "second")
    snapshot = _runtime_snapshot()

    assert snapshot.active_loop_count == 1
    assert snapshot.queued_generation_id == second.generation_id
    release_finalizer.set()
    assert second.get(timeout=1) == "second"
    second.wait_settled(timeout=1)
    retained_generators.clear()
    stage.close()


def test_stage_threads_are_shared_and_non_daemon() -> None:
    stages = [Stage() for _ in range(20)]
    handles = [stage.go(lambda: 1) for stage in stages]
    assert [handle.get() for handle in handles] == [1] * 20
    for handle in handles:
        handle.wait_settled()

    stage_threads = [thread for thread in threading.enumerate() if thread.name.startswith("AgentlyStage")]
    control_threads = [thread for thread in stage_threads if thread.name.startswith("AgentlyStageControl")]

    assert len(control_threads) == 1
    assert all(not thread.daemon for thread in stage_threads)
    for stage in stages:
        stage.close()
