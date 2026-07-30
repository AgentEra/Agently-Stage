from __future__ import annotations

import asyncio
import contextvars
import threading

import pytest

from agently_stage import (
    Stage,
    StageBackpressureError,
    StageClosedError,
    StageIdleTimeoutError,
    StageLifecycleError,
)


async def _current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_default_stage_uses_the_current_running_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()
        first = Stage()
        second = Stage()

        assert await first.go(_current_loop).async_get() is caller_loop
        assert await second.go(_current_loop).async_get() is caller_loop

        await first.async_close()
        await second.async_close()

    asyncio.run(run())


def test_default_stage_falls_back_to_carrier_and_re_resolves_after_quiescence() -> None:
    stage = Stage()
    carrier_loop = stage.get(_current_loop)
    stage.wait_settled(timeout=1)

    async def run() -> None:
        caller_loop = asyncio.get_running_loop()
        assert carrier_loop is not caller_loop
        assert await stage.go(_current_loop).async_get() is caller_loop
        await stage.async_close()

    asyncio.run(run())


def test_forced_stage_backend_does_not_use_the_current_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()
        stage = Stage(loop="stage")

        assert await stage.go(_current_loop).async_get() is not caller_loop
        await stage.async_close()

    asyncio.run(run())


def test_explicit_loop_accepts_cross_thread_submission_and_is_never_closed() -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        stage = Stage(loop=loop)
        submitted = threading.Event()
        handles: list[object] = []

        def submit() -> None:
            handles.append(stage.go(_current_loop))
            submitted.set()

        thread = threading.Thread(target=submit)
        thread.start()
        await asyncio.to_thread(submitted.wait, 1)
        thread.join(timeout=1)

        handle = handles[0]
        assert await handle.async_get() is loop  # type: ignore[union-attr]
        await stage.async_close()
        assert not loop.is_closed()

    asyncio.run(run())


def test_auto_stage_redirects_cross_thread_submission_to_the_active_caller_loop() -> None:
    async def run() -> None:
        caller_loop = asyncio.get_running_loop()
        stage = Stage()
        release = asyncio.Event()
        epoch_owner = stage.go(release.wait)
        submitted = threading.Event()
        handles: list[object] = []

        def submit() -> None:
            handles.append(stage.go(_current_loop))
            submitted.set()

        thread = threading.Thread(target=submit)
        thread.start()
        await asyncio.to_thread(submitted.wait, 1)
        thread.join(timeout=1)

        handle = handles[0]
        assert await handle.async_get() is caller_loop  # type: ignore[union-attr]
        release.set()
        assert await epoch_owner.async_get()
        await stage.async_close()
        assert not caller_loop.is_closed()

    asyncio.run(run())


def test_explicit_none_is_rejected() -> None:
    with pytest.raises(TypeError, match="loop"):
        Stage(loop=None)  # type: ignore[arg-type]


def test_current_loop_context_is_captured_at_admission() -> None:
    async def run() -> None:
        marker = contextvars.ContextVar("stage_scope_marker", default="missing")
        stage = Stage()

        async def read_marker() -> str:
            await asyncio.sleep(0)
            return marker.get()

        token = marker.set("caller")
        try:
            handle = stage.go(read_marker)
        finally:
            marker.reset(token)

        assert await handle.async_get() == "caller"
        await stage.async_close()

    asyncio.run(run())


def test_same_loop_sync_result_wait_fails_fast_and_async_result_still_works() -> None:
    async def run() -> None:
        stage = Stage()
        handle = stage.go(asyncio.sleep, 0, result="ready")

        with pytest.raises(StageLifecycleError, match="async_get"):
            handle.get(timeout=0.01)
        with pytest.raises(StageLifecycleError, match="async_wait_settled"):
            handle.wait_settled(timeout=0.01)

        assert await handle.async_get() == "ready"
        await handle.async_wait_settled()
        await stage.async_close()

    asyncio.run(run())


def test_same_loop_sync_scope_barriers_fail_fast_and_async_close_still_works() -> None:
    async def run() -> None:
        stage = Stage()
        release = asyncio.Event()
        handle = stage.go(release.wait)

        with pytest.raises(StageLifecycleError, match="async_wait_settled"):
            stage.wait_settled(timeout=0.01)
        with pytest.raises(StageLifecycleError, match="async_cancel_and_wait_settled"):
            stage.cancel_and_wait_settled(timeout=0.01)
        with pytest.raises(StageLifecycleError, match="async_close"):
            stage.close(timeout=0.01)

        release.set()
        assert await handle.async_get()
        await stage.async_close()

    asyncio.run(run())


def test_same_loop_blocking_handle_cancel_fails_fast_but_zero_timeout_can_request() -> None:
    async def run() -> None:
        stage = Stage()
        started = asyncio.Event()

        async def body() -> None:
            started.set()
            await asyncio.sleep(10)

        handle = stage.go(body)
        await started.wait()

        with pytest.raises(StageLifecycleError, match="async_cancel_and_wait_settled"):
            handle.cancel(timeout=0.01)

        assert not handle.cancel(timeout=0)
        with pytest.raises(asyncio.CancelledError):
            await handle.async_get()
        await stage.async_close()

    asyncio.run(run())


def test_same_loop_sync_stream_iteration_fails_fast_and_async_iteration_works() -> None:
    async def run() -> None:
        async def source():
            await asyncio.sleep(0)
            yield "ready"

        stage = Stage()
        stream = stage.go(source)

        with pytest.raises(StageLifecycleError, match="async for"):
            list(stream)

        assert [item async for item in stream] == ["ready"]
        await stage.async_close()

    asyncio.run(run())


def test_late_callback_cannot_reopen_an_old_handle_across_backend_epochs() -> None:
    stage = Stage()

    async def first_epoch():
        handle = stage.go(asyncio.sleep, 0, result="first")
        assert await handle.async_get() == "first"
        await handle.async_wait_settled()
        return handle

    old_handle = asyncio.run(first_epoch())

    async def second_epoch() -> None:
        release = asyncio.Event()
        current = stage.go(release.wait)

        with pytest.raises(StageLifecycleError, match="backend epoch"):
            old_handle.on_success(lambda _: None)

        release.set()
        assert await current.async_get()
        await stage.async_close()

    asyncio.run(second_epoch())


def test_adopt_owns_task_outcome_origin_and_settlement() -> None:
    async def run() -> None:
        stage = Stage()
        release = asyncio.Event()
        task = asyncio.create_task(release.wait())
        adopted = stage.adopt(task, origin="flow:worker")

        assert adopted is task
        snapshot = stage.snapshot()
        assert snapshot.active_count == 1
        assert snapshot.unresolved_origins == ("flow:worker",)

        release.set()
        assert await adopted
        await stage.async_wait_settled(timeout=1)
        assert stage.snapshot().active_count == 0
        await stage.async_close()

    asyncio.run(run())


def test_create_task_enters_stage_inventory_with_native_task_identity_and_context() -> None:
    async def run() -> None:
        marker = contextvars.ContextVar("stage_task_marker", default="missing")
        observed: list[tuple[asyncio.Task[tuple[str, int]], str]] = []

        def observe(task: asyncio.Task[tuple[str, int]], origin: str) -> None:
            observed.append((task, origin))

        stage = Stage(on_adopted_done=observe)
        caller_loop = asyncio.get_running_loop()

        async def read_context() -> tuple[str, int]:
            await asyncio.sleep(0)
            return marker.get(), id(asyncio.get_running_loop())

        token = marker.set("caller")
        try:
            task = stage.create_task(read_context(), origin="flow:handler:read-context")
        finally:
            marker.reset(token)

        assert isinstance(task, asyncio.Task)
        assert stage.adopted_tasks == (task,)
        assert stage.origin_for_adopted(task) == "flow:handler:read-context"
        assert await task == ("caller", id(caller_loop))
        await stage.async_wait_settled(timeout=1)
        assert observed == [(task, "flow:handler:read-context")]
        await stage.async_close()

    asyncio.run(run())


def test_create_task_rejects_non_caller_backend_and_closes_coroutine() -> None:
    async def run() -> None:
        stage = Stage(loop="stage")
        coroutine = asyncio.sleep(0)

        with pytest.raises(StageLifecycleError, match="caller"):
            stage.create_task(coroutine, origin="flow:wrong-backend")

        assert coroutine.cr_frame is None
        await stage.async_close()

    asyncio.run(run())


def test_create_task_rejects_sealed_scope_without_leaking_coroutine() -> None:
    async def run() -> None:
        stage = Stage()
        stage.seal()
        coroutine = asyncio.sleep(0)

        with pytest.raises(StageClosedError):
            stage.create_task(coroutine, origin="flow:late")

        assert coroutine.cr_frame is None
        await stage.async_close()

    asyncio.run(run())


def test_adopted_inventory_and_observer_settle_as_one_stage_operation() -> None:
    async def run() -> None:
        observed: list[tuple[asyncio.Task[bool], str, int]] = []
        stage: Stage

        def observe(task: asyncio.Task[bool], origin: str) -> None:
            observed.append((task, origin, stage.adopted_count))

        stage = Stage(on_adopted_done=observe)
        release = asyncio.Event()
        task = asyncio.create_task(release.wait())
        stage.adopt(task, origin="flow:observed")

        assert stage.adopted_count == 1
        assert stage.adopted_tasks == (task,)
        assert stage.origin_for_adopted(task) == "flow:observed"

        release.set()
        await stage.async_wait_settled(timeout=1)

        assert observed == [(task, "flow:observed", 0)]
        assert stage.adopted_count == 0
        assert stage.adopted_tasks == ()
        assert stage.origin_for_adopted(task) is None
        await stage.async_close()

    asyncio.run(run())


def test_adopted_observer_failure_is_reported_without_breaking_settlement() -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        observed_contexts: list[dict[str, object]] = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: observed_contexts.append(context))

        def fail_observer(_task: asyncio.Task[object], _origin: str) -> None:
            raise RuntimeError("observer failed")

        try:
            stage = Stage(on_adopted_done=fail_observer)
            task = asyncio.create_task(asyncio.sleep(0))
            stage.adopt(task, origin="flow:observer-failure")
            await stage.async_close(timeout=1)
        finally:
            loop.set_exception_handler(previous_handler)

        assert len(observed_contexts) == 1
        assert observed_contexts[0]["message"] == "Stage adopted-task completion observer failed"
        assert isinstance(observed_contexts[0]["exception"], RuntimeError)
        assert observed_contexts[0]["task"] is task
        assert observed_contexts[0]["origin"] == "flow:observer-failure"

    asyncio.run(run())


def test_adopted_task_is_not_falsely_claimed_by_go_admission_limits() -> None:
    async def run() -> None:
        stage = Stage(max_concurrency=1, max_pending=0)
        release = asyncio.Event()
        first = stage.go(release.wait)
        already_scheduled = asyncio.create_task(asyncio.sleep(0, result="adopted"))

        adopted = stage.adopt(already_scheduled, origin="host:already-scheduled")
        assert await adopted == "adopted"

        release.set()
        assert await first.async_get()
        await stage.async_close()

    asyncio.run(run())


def test_unbounded_root_fast_path_preserves_snapshot_counts() -> None:
    async def run() -> None:
        stage = Stage()
        release = asyncio.Event()

        first = stage.go(release.wait)
        second = stage.go(release.wait)
        await asyncio.sleep(0)

        active = stage.snapshot()
        assert active.active_root_count == 2
        assert active.pending_root_count == 0

        release.set()
        await asyncio.gather(first.async_get(), second.async_get())
        await stage.async_wait_settled(timeout=1)

        settled = stage.snapshot()
        assert settled.active_root_count == 0
        assert settled.pending_root_count == 0
        await stage.async_close()

    asyncio.run(run())


def test_adopt_rejects_cross_loop_task() -> None:
    foreign_loop = asyncio.new_event_loop()
    foreign_task = foreign_loop.create_task(asyncio.sleep(0))

    async def run() -> None:
        stage = Stage()
        try:
            with pytest.raises(StageLifecycleError, match="event loop"):
                stage.adopt(foreign_task, origin="foreign")
        finally:
            await stage.async_close()

    try:
        asyncio.run(run())
    finally:
        foreign_task.cancel()
        foreign_loop.run_until_complete(asyncio.gather(foreign_task, return_exceptions=True))
        foreign_loop.close()


def test_adopted_task_cannot_wait_for_its_own_stage() -> None:
    async def run() -> None:
        stage = Stage()
        start = asyncio.Event()

        async def body() -> None:
            await start.wait()
            with pytest.raises(StageLifecycleError, match="owned by the same scope"):
                await stage.async_wait_settled(timeout=0.01)

        task = asyncio.create_task(body())
        stage.adopt(task, origin="flow:self-wait")
        start.set()
        await task
        await stage.async_close()

    asyncio.run(run())


def test_seal_rejects_new_roots_and_drains_accepted_pending_work() -> None:
    async def run() -> None:
        stage = Stage(max_concurrency=1, max_pending=1)
        first_release = asyncio.Event()
        second_started = asyncio.Event()

        first = stage.go(first_release.wait)

        async def second_body() -> str:
            second_started.set()
            return "second"

        second = stage.go(second_body)
        stage.seal()

        with pytest.raises(StageClosedError):
            stage.go(lambda: "late")

        first_release.set()
        assert await first.async_get()
        assert await second.async_get() == "second"
        assert second_started.is_set()
        await stage.async_close()

    asyncio.run(run())


def test_seal_allows_owned_nested_work_to_finish_the_accepted_chain() -> None:
    async def run() -> None:
        stage = Stage(max_concurrency=1, max_pending=0)
        root_started = asyncio.Event()
        continue_root = asyncio.Event()
        cleanup_observed = asyncio.Event()

        async def root() -> str:
            root_started.set()
            await continue_root.wait()

            async def cleanup() -> str:
                await asyncio.sleep(0)
                return "cleaned"

            child = stage.go(cleanup).on_finally(cleanup_observed.set)
            return await child.async_get()

        handle = stage.go(root)
        await root_started.wait()
        stage.seal()
        continue_root.set()

        assert await handle.async_get() == "cleaned"
        await stage.async_close()
        assert cleanup_observed.is_set()

    asyncio.run(run())


def test_root_pressure_is_bounded_and_nested_stage_work_does_not_deadlock() -> None:
    async def run() -> None:
        stage = Stage(max_concurrency=1, max_pending=0)
        release = asyncio.Event()
        first = stage.go(release.wait)

        with pytest.raises(StageBackpressureError):
            stage.go(lambda: "rejected")

        release.set()
        assert await first.async_get()
        await stage.async_wait_settled(timeout=1)

        async def parent() -> str:
            async def child_body() -> str:
                await asyncio.sleep(0)
                return "child"

            child = stage.go(child_body)
            return await child.async_get()

        assert await stage.go(parent).async_get() == "child"
        await stage.async_close()

    asyncio.run(run())


def test_root_pressure_is_bounded_for_concurrent_thread_submissions() -> None:
    stage = Stage(max_concurrency=2, max_pending=6)
    submit_barrier = threading.Barrier(9)
    counter_lock = threading.Lock()
    active = 0
    peak_active = 0
    handles: list[object] = []
    errors: list[BaseException] = []

    async def body() -> None:
        nonlocal active, peak_active
        with counter_lock:
            active += 1
            peak_active = max(peak_active, active)
        try:
            await asyncio.sleep(0.01)
        finally:
            with counter_lock:
                active -= 1

    def submit() -> None:
        submit_barrier.wait()
        try:
            handle = stage.go(body)
        except BaseException as error:
            errors.append(error)
        else:
            handles.append(handle)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for thread in threads:
        thread.start()
    submit_barrier.wait()
    for thread in threads:
        thread.join(timeout=1)

    assert errors == []
    assert len(handles) == 8
    for handle in handles:
        handle.get(timeout=1)  # type: ignore[union-attr]
    stage.close(timeout=1)

    assert peak_active == 2


def test_tick_extends_idle_budget_but_idle_timeout_cancels_unresponsive_work() -> None:
    async def run() -> None:
        ticking_stage = Stage(idle_timeout=0.03)

        async def cooperative() -> str:
            for _ in range(5):
                await asyncio.sleep(0.015)
                ticking_stage.tick()
            return "done"

        assert await ticking_stage.go(cooperative).async_get() == "done"
        await ticking_stage.async_close()

        timed_out_stage = Stage(idle_timeout=0.02)
        started = asyncio.Event()

        async def stuck() -> None:
            started.set()
            await asyncio.sleep(10)

        handle = timed_out_stage.go(stuck)
        await started.wait()
        with pytest.raises(asyncio.CancelledError):
            await handle.async_get(timeout=1)
        with pytest.raises(StageIdleTimeoutError):
            await timed_out_stage.async_close(timeout=1)

    asyncio.run(run())


def test_cancel_and_wait_settled_fences_owned_work() -> None:
    async def run() -> None:
        stage = Stage()
        started = asyncio.Event()
        late_effect = asyncio.Event()

        async def body() -> None:
            started.set()
            await asyncio.sleep(10)
            late_effect.set()

        stage.go(body)
        await started.wait()

        assert await stage.async_cancel_and_wait_settled(timeout=1)
        assert not late_effect.is_set()
        assert stage.snapshot().active_count == 0
        await stage.async_close()

    asyncio.run(run())


def test_cancel_and_wait_settled_cancels_adopted_task() -> None:
    async def run() -> None:
        stage = Stage()
        started = asyncio.Event()

        async def body() -> None:
            started.set()
            await asyncio.sleep(10)

        task = asyncio.create_task(body())
        stage.adopt(task, origin="flow:adopted")
        await started.wait()

        assert await stage.async_cancel_and_wait_settled(timeout=1)
        assert task.cancelled()
        assert stage.snapshot().active_count == 0
        await stage.async_close()

    asyncio.run(run())
