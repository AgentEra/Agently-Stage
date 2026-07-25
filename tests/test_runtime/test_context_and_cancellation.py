from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import sys
import threading
import time
from typing import Any, cast

import pytest

from agently_stage import Stage


def test_cold_generation_preserves_submission_context() -> None:
    request_id = contextvars.ContextVar[str | None]("request_id", default=None)
    stage = Stage()

    async def read_request_id() -> str | None:
        return request_id.get()

    token = request_id.set("cold-request")
    try:
        handle = stage.go(read_request_id)
    finally:
        request_id.reset(token)

    assert handle.get(timeout=1) == "cold-request"
    handle.wait_settled(timeout=1)
    stage.close(timeout=1)


def test_warm_generation_preserves_independent_submission_contexts() -> None:
    request_id = contextvars.ContextVar[str | None]("request_id", default=None)

    async def read_request_id() -> str | None:
        await asyncio.sleep(0)
        return request_id.get()

    with Stage() as stage:
        assert stage.go(asyncio.sleep, 0).get(timeout=1) is None

        handles = []
        for index in range(20):
            expected = f"request-{index}"
            token = request_id.set(expected)
            try:
                handles.append((expected, stage.go(read_request_id)))
            finally:
                request_id.reset(token)

        assert [handle.get(timeout=1) for _, handle in handles] == [expected for expected, _ in handles]


def test_submission_context_mutation_does_not_leak_back_to_caller() -> None:
    request_id = contextvars.ContextVar[str | None]("request_id", default=None)
    stage = Stage()

    async def mutate_request_id() -> str | None:
        before = request_id.get()
        request_id.set("inside-stage")
        assert request_id.get() == "inside-stage"
        return before

    token = request_id.set("caller")
    try:
        assert stage.go(mutate_request_id).get(timeout=1) == "caller"
        assert request_id.get() == "caller"
    finally:
        request_id.reset(token)
        stage.close(timeout=1)


def test_initial_and_late_callbacks_use_their_registration_contexts() -> None:
    request_id = contextvars.ContextVar[str | None]("request_id", default=None)
    callback_values: list[tuple[str, str | None]] = []
    stage = Stage()

    initial_token = request_id.set("initial")
    try:
        handle = stage.go(
            lambda: "ready",
            on_success=lambda _: callback_values.append(("initial", request_id.get())),
        )
    finally:
        request_id.reset(initial_token)

    assert handle.get(timeout=1) == "ready"
    handle.wait_settled(timeout=1)

    late_token = request_id.set("late")
    try:
        handle.on_success(lambda _: callback_values.append(("late", request_id.get())))
    finally:
        request_id.reset(late_token)

    handle.wait_settled(timeout=1)
    assert callback_values == [("initial", "initial"), ("late", "late")]
    stage.close(timeout=1)


def test_cancel_fences_stage_owned_descendant_side_effect() -> None:
    stage = Stage()
    child_started = threading.Event()
    child_cancelled = threading.Event()
    late_effect = threading.Event()

    async def body() -> None:
        async def child() -> None:
            child_started.set()
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                child_cancelled.set()
                raise
            late_effect.set()

        asyncio.create_task(child())
        await asyncio.sleep(10)

    handle = stage.go(body)
    assert child_started.wait(timeout=1)
    assert handle.cancel(timeout=1)
    handle.wait_settled(timeout=1)

    time.sleep(0.1)
    assert child_cancelled.is_set()
    assert not late_effect.is_set()
    stage.close(timeout=1)


def test_cancel_fences_descendant_created_during_body_finalization() -> None:
    stage = Stage()
    body_started = threading.Event()
    late_child_effect = threading.Event()

    async def body() -> None:
        body_started.set()
        try:
            await asyncio.sleep(10)
        finally:

            async def late_child() -> None:
                late_child_effect.set()

            asyncio.create_task(late_child())

    handle = stage.go(body)
    assert body_started.wait(timeout=1)
    assert handle.cancel(timeout=1)
    handle.wait_settled(timeout=1)

    time.sleep(0.05)
    assert not late_child_effect.is_set()
    stage.close(timeout=1)


def test_cancel_after_body_result_fences_retained_descendant() -> None:
    stage = Stage()
    descendant_started = threading.Event()
    descendant_cancelled = threading.Event()
    late_effect = threading.Event()

    async def body() -> str:
        async def descendant() -> None:
            descendant_started.set()
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                descendant_cancelled.set()
                raise
            late_effect.set()

        asyncio.create_task(descendant())
        return "ready"

    handle = stage.go(body)
    assert handle.get(timeout=1) == "ready"
    assert descendant_started.wait(timeout=1)
    assert handle.cancel(timeout=1)
    handle.wait_settled(timeout=1)

    time.sleep(0.1)
    assert descendant_cancelled.is_set()
    assert not late_effect.is_set()
    stage.close(timeout=1)


def test_close_timeout_reports_unsettled_work_and_allows_retry() -> None:
    stage = Stage()
    body_started = threading.Event()
    release_body = threading.Event()

    async def body() -> None:
        body_started.set()
        while not release_body.is_set():
            await asyncio.sleep(0.01)

    stage.go(body)
    assert body_started.wait(timeout=1)

    try:
        with pytest.raises(TimeoutError, match="1 unsettled handle"):
            stage.close(timeout=0.02)

        assert stage.is_closing
        assert not stage.is_available
    finally:
        release_body.set()
        stage.close(timeout=1)


def test_cancel_timeout_is_not_reported_as_acknowledged() -> None:
    stage = Stage()
    body_started = threading.Event()
    release_body = threading.Event()

    async def suppress_cancel_until_released() -> str:
        body_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            while not release_body.is_set():
                await asyncio.sleep(0.01)
        return "released"

    handle = stage.go(suppress_cancel_until_released)
    assert body_started.wait(timeout=1)

    try:
        assert handle.cancel(timeout=0.01) is False
    finally:
        release_body.set()

    assert handle.get(timeout=1) == "released"
    handle.wait_settled(timeout=1)
    stage.close(timeout=1)


def test_blocking_callable_does_not_settle_before_late_effect_finishes() -> None:
    stage = Stage(max_workers=1)
    body_started = threading.Event()
    release_body = threading.Event()
    late_effect = threading.Event()

    def blocking_body() -> str:
        body_started.set()
        release_body.wait()
        late_effect.set()
        return "released"

    handle = stage.go(blocking_body)
    assert body_started.wait(timeout=1)

    try:
        assert handle.cancel(timeout=0.01) is False
        with pytest.raises(concurrent.futures.TimeoutError):
            handle.wait_settled(timeout=0.01)
        assert not late_effect.is_set()
    finally:
        release_body.set()

    handle.wait_settled(timeout=1)
    assert late_effect.wait(timeout=1)
    stage.close(timeout=1)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="asyncio context= was added in Python 3.11")
def test_task_factory_accepts_explicit_context() -> None:
    marker = contextvars.ContextVar("explicit_task_context", default="missing")
    stage = Stage()

    async def root() -> str:
        context = contextvars.copy_context()
        context.run(marker.set, "explicit")

        async def child() -> str:
            await asyncio.sleep(0)
            return marker.get()

        create_task = cast(Any, asyncio.get_running_loop().create_task)
        task = create_task(
            child(),
            context=context,
        )
        return await task

    handle = stage.go(root)
    assert handle.get(timeout=1) == "explicit"
    handle.wait_settled(timeout=1)
    stage.close(timeout=1)
