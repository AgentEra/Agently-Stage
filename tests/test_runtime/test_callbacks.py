from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import pytest

from agently_stage import Stage
from agently_stage.StageException import StageClosedError, StageSettlementError

if TYPE_CHECKING:
    from agently_stage.StageHandle import StageHandle


def test_immediate_body_accepts_chain_without_grace_period() -> None:
    observed: list[str] = []

    handle = (
        Stage()
        .go(lambda: "value")
        .on_success(lambda value: observed.append(value))
        .on_finally(lambda: observed.append("finally"))
    )

    assert handle.get() == "value"
    handle.wait_settled()
    assert observed == ["value", "finally"]


def test_callbacks_are_observers_and_preserve_registration_order() -> None:
    observed: list[str] = []
    handle = Stage().go(lambda: 42)
    handle.on_success(lambda value: observed.append(f"first:{value}"))
    handle.on_success(lambda value: observed.append(f"second:{value}"))
    handle.on_error(lambda error: observed.append(f"error:{error}"))
    handle.on_finally(lambda: observed.append("finally"))

    assert handle.get() == 42
    handle.wait_settled()
    assert observed == ["first:42", "second:42", "finally"]


def test_error_callback_observes_body_error_without_recovery() -> None:
    observed: list[str] = []

    def body() -> None:
        raise ValueError("body failed")

    handle = Stage().go(body).on_error(lambda error: observed.append(str(error)))

    with pytest.raises(ValueError, match="body failed"):
        handle.get()
    handle.wait_settled()
    assert observed == ["body failed"]


def test_ignore_exception_still_selects_error_observers() -> None:
    observed: list[str] = []

    def body() -> None:
        raise ValueError("ignored")

    handle = Stage().go(body, ignore_exception=True).on_error(lambda error: observed.append(str(error)))

    assert handle.get() is None
    handle.wait_settled()
    assert observed == ["ignored"]


def test_callback_failure_does_not_rewrite_body_outcome() -> None:
    def fail_callback(value: int) -> None:
        raise RuntimeError(f"callback failed for {value}")

    handle = Stage().go(lambda: 42).on_success(fail_callback)

    assert handle.get() == 42
    with pytest.raises(StageSettlementError) as exc_info:
        handle.wait_settled()
    assert isinstance(exc_info.value.errors[0], RuntimeError)


def test_finally_runs_after_prior_callback_failure() -> None:
    finalized = threading.Event()

    def fail_callback(value: int) -> None:
        raise RuntimeError(value)

    handle = Stage().go(lambda: 42).on_success(fail_callback).on_finally(finalized.set)

    with pytest.raises(StageSettlementError):
        handle.wait_settled()
    assert finalized.is_set()


def test_async_callbacks_are_awaited_by_settlement() -> None:
    observed: list[str] = []

    async def callback(value: str) -> None:
        await asyncio.sleep(0.01)
        observed.append(value)

    handle = Stage().go(lambda: "async-callback").on_success(callback)

    handle.wait_settled()
    assert observed == ["async-callback"]


def test_late_callback_can_reopen_settlement_after_body_generation_closed() -> None:
    stage = Stage()
    observed = threading.Event()
    handle = stage.go(lambda: "done")
    assert handle.get() == "done"
    handle.wait_settled()

    handle.on_success(lambda value: observed.set())

    handle.wait_settled()
    assert observed.is_set()
    stage.close()


def test_scope_close_rejects_late_callback_registration() -> None:
    stage = Stage()
    handle = stage.go(lambda: "done")
    assert handle.get() == "done"
    stage.close()

    with pytest.raises(StageClosedError):
        handle.on_success(lambda value: value)


def test_legacy_callback_arguments_use_same_pipeline() -> None:
    observed: list[str] = []

    with Stage() as stage:
        handle = stage.go(
            lambda: "done",
            on_success=lambda value: observed.append(value),
            on_finally=lambda: observed.append("finally"),
        )

    assert handle.get() == "done"
    assert observed == ["done", "finally"]


def test_settlement_barrier_cannot_pass_partially_admitted_callback() -> None:
    admission_paused = threading.Event()
    release_admission = threading.Event()

    class PausingStage(Stage):
        def _submit_callback_drain_locked(self, handle: StageHandle[object]) -> None:
            admission_paused.set()
            release_admission.wait(timeout=1)
            super()._submit_callback_drain_locked(handle)

    stage = PausingStage()
    callback_finished = threading.Event()
    settlement_returned = threading.Event()
    handle = stage.go(lambda: "done")
    assert handle.get() == "done"
    handle.wait_settled()

    registration = threading.Thread(target=handle.on_success, args=(lambda value: callback_finished.set(),))
    registration.start()
    assert admission_paused.wait(timeout=1)

    waiter = threading.Thread(target=lambda: (handle.wait_settled(), settlement_returned.set()))
    waiter.start()
    returned_during_admission = settlement_returned.wait(timeout=0.02)
    release_admission.set()
    registration.join(timeout=1)
    waiter.join(timeout=1)

    assert not returned_during_admission
    assert callback_finished.is_set()
    assert settlement_returned.is_set()
    stage.close()
