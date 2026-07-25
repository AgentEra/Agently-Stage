from __future__ import annotations

import asyncio
import contextvars

import pytest

from agently_stage._local_tasks import _LocalTaskOutcome, _LocalTaskScope
from agently_stage.StageException import StageClosedError, StageLifecycleError


def test_spawn_runs_on_caller_loop_with_captured_context() -> None:
    async def run() -> None:
        marker = contextvars.ContextVar("local_scope_marker", default="missing")
        caller_loop = asyncio.get_running_loop()
        scope = _LocalTaskScope()

        async def read_context() -> tuple[int, str]:
            await asyncio.sleep(0)
            return id(asyncio.get_running_loop()), marker.get()

        token = marker.set("caller")
        try:
            task = scope.spawn(read_context(), origin="event:hook")
        finally:
            marker.reset(token)

        assert await task == (id(caller_loop), "caller")
        await scope.wait_settled(timeout=1)

    asyncio.run(run())


def test_nested_spawn_is_included_in_scope_settlement() -> None:
    async def run() -> None:
        scope = _LocalTaskScope()
        child_finished = asyncio.Event()

        async def child() -> None:
            await asyncio.sleep(0)
            child_finished.set()

        async def root() -> None:
            scope.spawn(child(), origin="flow:child")

        scope.spawn(root(), origin="flow:root")
        await scope.wait_settled(timeout=1)

        assert child_finished.is_set()
        assert scope.pending_count == 0

    asyncio.run(run())


def test_adopt_observes_failure_once() -> None:
    async def run() -> None:
        outcomes: list[_LocalTaskOutcome] = []
        scope = _LocalTaskScope(on_done=outcomes.append)

        async def fail() -> None:
            raise RuntimeError("expected-local-failure")

        task = asyncio.create_task(fail())
        assert scope.adopt(task, origin="flow:failure") is task
        await scope.wait_settled(timeout=1)

        assert len(outcomes) == 1
        assert outcomes[0].task is task
        assert outcomes[0].origin == "flow:failure"
        assert isinstance(outcomes[0].error, RuntimeError)
        assert str(outcomes[0].error) == "expected-local-failure"

    asyncio.run(run())


def test_cancel_and_wait_fences_managed_late_effect() -> None:
    async def run() -> None:
        scope = _LocalTaskScope()
        body_started = asyncio.Event()
        late_effect = asyncio.Event()

        async def body() -> None:
            body_started.set()
            await asyncio.sleep(10)
            late_effect.set()

        scope.spawn(body(), origin="flow:emit")
        await body_started.wait()

        assert await scope.cancel_and_wait(timeout=1)
        await asyncio.sleep(0)
        assert not late_effect.is_set()
        assert scope.pending_count == 0

    asyncio.run(run())


def test_cancel_timeout_reports_unresolved_origin_and_can_retry() -> None:
    async def run() -> None:
        scope = _LocalTaskScope()
        body_started = asyncio.Event()
        release = asyncio.Event()

        async def suppress_cancel_until_released() -> None:
            body_started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await release.wait()

        scope.spawn(suppress_cancel_until_released(), origin="event:stuck-hook")
        await body_started.wait()

        with pytest.raises(TimeoutError, match="event:stuck-hook"):
            await scope.cancel_and_wait(timeout=0.01)

        release.set()
        await scope.wait_settled(timeout=1)
        assert scope.pending_count == 0

    asyncio.run(run())


def test_close_seals_scope_against_new_work() -> None:
    async def run() -> None:
        scope = _LocalTaskScope()
        await scope.close(timeout=1)

        coroutine = asyncio.sleep(0)
        try:
            with pytest.raises(StageClosedError):
                scope.spawn(coroutine, origin="closed")
        finally:
            coroutine.close()

    asyncio.run(run())


def test_scope_rejects_a_second_running_loop() -> None:
    scope = _LocalTaskScope()

    asyncio.run(scope.wait_settled(timeout=1))

    with pytest.raises(StageLifecycleError, match="cannot cross event loops"):
        asyncio.run(scope.wait_settled(timeout=1))
