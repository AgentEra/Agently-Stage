# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import threading
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

from .StageException import StageClosedError, StageSettlementError

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, Task
    from collections.abc import Awaitable, Callable

    from .Stage import Stage

T = TypeVar("T")
_CallbackKind = Literal["success", "error", "finally"]
_OwnedTaskPhase = Literal["body", "settlement"]


@dataclass(frozen=True)
class _Callback:
    kind: _CallbackKind
    function: Callable[..., object | Awaitable[object]]
    context: contextvars.Context


class StageHandle(Generic[T]):
    """Loop-neutral access to a Stage body outcome and settlement barrier."""

    def __init__(self, stage: Stage):
        self._stage = stage
        self._body_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self._state_lock = threading.RLock()
        self._pending_work = 0
        self._settlement_future: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._settlement_future.set_result(None)
        self._settlement_errors: list[BaseException] = []
        self._stage_error_cursor = 0
        self._generation_id: int | None = None
        self._owner_loop: AbstractEventLoop | None = None
        self._owner_task: Task[object] | None = None
        self._owned_body_tasks: set[Task[object]] = set()
        self._owned_settlement_tasks: set[Task[object]] = set()
        self._cancel_requested = False
        self._body_completed = False
        self._body_result: T | None = None
        self._body_error: BaseException | None = None
        self._callbacks: deque[_Callback] = deque()
        self._callback_drain_active = False

    @property
    def generation_id(self) -> int:
        with self._state_lock:
            if self._generation_id is None:
                raise RuntimeError("Stage work has not been admitted to a generation")
            return self._generation_id

    def _set_generation_id(self, generation_id: int) -> None:
        with self._state_lock:
            if self._generation_id is None:
                self._generation_id = generation_id

    def _retain_work(self) -> None:
        with self._state_lock:
            if self._pending_work == 0:
                self._settlement_future = concurrent.futures.Future()
            self._pending_work += 1

    def _release_work(self) -> None:
        became_quiescent = False
        with self._state_lock:
            if self._pending_work <= 0:
                raise RuntimeError("StageHandle work reservation underflow")
            self._pending_work -= 1
            if self._pending_work == 0:
                became_quiescent = True
                if not self._settlement_future.done():
                    self._settlement_future.set_result(None)
        if became_quiescent:
            self._stage._handle_quiescent(self)

    def _record_settlement_error(self, error: BaseException) -> None:
        with self._state_lock:
            self._settlement_errors.append(error)

    def _register_owned_task(self, task: Task[object], *, phase: _OwnedTaskPhase) -> bool:
        with self._state_lock:
            if phase == "body":
                self._owned_body_tasks.add(task)
                return self._cancel_requested
            self._owned_settlement_tasks.add(task)
            return False

    def _unregister_owned_task(self, task: Task[object]) -> None:
        with self._state_lock:
            self._owned_body_tasks.discard(task)
            self._owned_settlement_tasks.discard(task)

    def _take_unreported_stage_errors(self) -> tuple[BaseException, ...]:
        with self._state_lock:
            errors = tuple(self._settlement_errors[self._stage_error_cursor :])
            self._stage_error_cursor = len(self._settlement_errors)
            return errors

    def _set_body_result(self, result: T) -> bool:
        with self._state_lock:
            if self._body_completed:
                return False
            self._body_completed = True
            self._body_result = result
            self._body_future.set_result(result)
            return self._activate_callback_drain_locked()

    def _set_body_exception(self, error: BaseException, *, ignored: bool = False) -> bool:
        with self._state_lock:
            if self._body_completed:
                return False
            self._body_completed = True
            self._body_error = error
            if ignored:
                self._body_future.set_result(None)  # type: ignore[arg-type]
            else:
                self._body_future.set_exception(error)
            return self._activate_callback_drain_locked()

    def _set_body_cancelled(self, error: asyncio.CancelledError | None = None) -> bool:
        with self._state_lock:
            if self._body_completed:
                return False
            self._body_completed = True
            self._body_error = error or asyncio.CancelledError()
            self._body_future.cancel()
            return self._activate_callback_drain_locked()

    def _register_initial_callback(
        self,
        kind: _CallbackKind,
        callback: Callable[..., object | Awaitable[object]],
    ) -> None:
        with self._state_lock:
            self._callbacks.append(_Callback(kind, callback, contextvars.copy_context()))

    def _activate_callback_drain_locked(self) -> bool:
        if self._callbacks and not self._callback_drain_active:
            self._callback_drain_active = True
            return True
        return False

    def _register_callback(
        self,
        kind: _CallbackKind,
        callback: Callable[..., object | Awaitable[object]],
    ) -> StageHandle[T]:
        callback_context = contextvars.copy_context()
        with self._stage._scope_lock:
            if self._stage._closed:
                raise StageClosedError("Cannot register a callback after Stage scope close")
            with self._state_lock:
                self._callbacks.append(_Callback(kind, callback, callback_context))
                should_start = self._body_completed and self._activate_callback_drain_locked()
            if should_start:
                self._stage._submit_callback_drain_locked(self)
        return self

    def on_success(
        self,
        callback: Callable[[T], object | Awaitable[object]],
    ) -> StageHandle[T]:
        return self._register_callback("success", callback)

    def on_error(
        self,
        callback: Callable[[BaseException], object | Awaitable[object]],
    ) -> StageHandle[T]:
        return self._register_callback("error", callback)

    def on_finally(
        self,
        callback: Callable[[], object | Awaitable[object]],
    ) -> StageHandle[T]:
        return self._register_callback("finally", callback)

    async def _drain_callbacks(self) -> None:
        while True:
            with self._state_lock:
                if not self._callbacks:
                    self._callback_drain_active = False
                    return
                callback = self._callbacks.popleft()
                body_error = self._body_error
                body_result = self._body_result

            if callback.kind == "success" and body_error is None:
                callback_args = (body_result,)
            elif callback.kind == "error" and body_error is not None:
                callback_args = (body_error,)
            elif callback.kind == "finally":
                callback_args = ()
            else:
                continue

            try:
                await self._stage._execute_callback(
                    callback.function,
                    callback_args,
                    callback.context,
                )
            except BaseException as error:
                self._record_settlement_error(error)

    def _set_owner_task(self, loop: AbstractEventLoop, task: Task[object]) -> None:
        with self._state_lock:
            self._owner_loop = loop
            self._owner_task = task
            should_cancel = self._cancel_requested
        if should_cancel:
            task.cancel()

    @staticmethod
    def _cancel_tasks(owner_task: Task[object] | None, body_tasks: tuple[Task[object], ...]) -> None:
        if owner_task is not None and not owner_task.done():
            owner_task.cancel()
        for task in body_tasks:
            if not task.done():
                task.cancel()

    def is_ready(self) -> bool:
        return self._body_future.done()

    def get(self, timeout: float | None = None) -> T:
        return self._body_future.result(timeout=timeout)

    async def async_get(self, timeout: float | None = None) -> T:
        reader = asyncio.wrap_future(self._body_future)
        if timeout is None:
            return await asyncio.shield(reader)
        return await asyncio.wait_for(asyncio.shield(reader), timeout)

    def wait_settled(self, timeout: float | None = None) -> None:
        with self._stage._scope_lock, self._state_lock:
            barrier = self._settlement_future
        barrier.result(timeout=timeout)
        with self._state_lock:
            errors = self._settlement_errors.copy()
        if errors:
            raise StageSettlementError(errors)

    async def async_wait_settled(self, timeout: float | None = None) -> None:
        with self._stage._scope_lock, self._state_lock:
            barrier = self._settlement_future
        reader = asyncio.wrap_future(barrier)
        if timeout is None:
            await asyncio.shield(reader)
        else:
            await asyncio.wait_for(asyncio.shield(reader), timeout)
        with self._state_lock:
            errors = self._settlement_errors.copy()
        if errors:
            raise StageSettlementError(errors)

    def cancel(self, timeout: float | None = None) -> bool:
        with self._state_lock:
            if self._body_future.done() and not self._owned_body_tasks:
                return False
            self._cancel_requested = True
            loop = self._owner_loop
            owner_task = self._owner_task
            body_tasks = tuple(self._owned_body_tasks)
        if loop is not None:
            loop.call_soon_threadsafe(self._cancel_tasks, owner_task, body_tasks)
        try:
            self._body_future.result(timeout=timeout)
        except (asyncio.CancelledError, concurrent.futures.CancelledError):
            return True
        except BaseException:
            return True
        return True
