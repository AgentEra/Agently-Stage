# pyright: reportUnusedClass=false
from __future__ import annotations

import asyncio
import contextvars
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .StageException import StageClosedError, StageLifecycleError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


@dataclass(frozen=True)
class _LocalTaskOutcome:
    task: asyncio.Task[Any]
    origin: str
    cancelled: bool
    error: BaseException | None


class _LocalTaskScope(Generic[T]):
    """Own explicitly admitted tasks on one caller-managed event loop."""

    def __init__(
        self,
        *,
        on_done: Callable[[_LocalTaskOutcome], object] | None = None,
    ) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._idle: asyncio.Event | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._origins: dict[asyncio.Task[Any], str] = {}
        self._on_done = on_done
        self._closed = False
        self._close_completed = False
        self._cancelling = False

    def _bind_running_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            self._idle = asyncio.Event()
            self._idle.set()
        elif self._loop is not loop:
            raise StageLifecycleError("A local Stage task scope cannot cross event loops")
        return loop

    def _idle_event(self) -> asyncio.Event:
        self._bind_running_loop()
        if self._idle is None:
            raise StageLifecycleError("Local Stage task scope did not bind its idle event")
        return self._idle

    def spawn(
        self,
        awaitable: Awaitable[T],
        *,
        origin: str,
    ) -> asyncio.Task[T]:
        if self._closed:
            raise StageClosedError("Cannot submit work to a closed local Stage task scope")
        loop = self._bind_running_loop()
        context = contextvars.copy_context()
        task = context.run(asyncio.ensure_future, awaitable)
        if task.get_loop() is not loop:
            raise StageLifecycleError("Local Stage task admission produced a task on another event loop")
        return self.adopt(task, origin=origin)

    def adopt(
        self,
        task: asyncio.Task[T],
        *,
        origin: str,
    ) -> asyncio.Task[T]:
        if self._closed:
            raise StageClosedError("Cannot adopt work into a closed local Stage task scope")
        loop = self._bind_running_loop()
        if task.get_loop() is not loop:
            raise StageLifecycleError("A local Stage task scope cannot adopt a task from another event loop")
        if task in self._tasks:
            registered_origin = self._origins[task]
            if registered_origin != origin:
                raise StageLifecycleError(
                    f"A local Stage task cannot be adopted with two origins: {registered_origin!r} and {origin!r}"
                )
            return task

        idle = self._idle_event()
        idle.clear()
        self._tasks.add(task)
        self._origins[task] = origin
        task.add_done_callback(self._task_done)
        if self._cancelling and not task.done():
            task.cancel()
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        origin = self._origins.pop(task, "<unknown>")
        self._tasks.discard(task)
        cancelled = task.cancelled()
        error = None if cancelled else task.exception()
        outcome = _LocalTaskOutcome(
            task=task,
            origin=origin,
            cancelled=cancelled,
            error=error,
        )
        if self._on_done is not None:
            try:
                self._on_done(outcome)
            except BaseException as callback_error:
                loop = self._loop
                if loop is not None:
                    loop.call_exception_handler(
                        {
                            "message": "Local Stage task completion callback failed",
                            "exception": callback_error,
                            "task": task,
                            "origin": origin,
                        }
                    )
        if not self._tasks:
            self._cancelling = False
            idle = self._idle
            if idle is not None:
                idle.set()

    def _unresolved_origins(self) -> list[str]:
        return sorted(self._origins.get(task, "<unknown>") for task in self._tasks)

    async def wait_settled(self, timeout: float | None = None) -> None:
        idle = self._idle_event()
        if idle.is_set():
            return
        try:
            if timeout is None:
                await idle.wait()
            else:
                await asyncio.wait_for(idle.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            unresolved = self._unresolved_origins()
            raise TimeoutError(
                f"Local Stage task scope settlement timed out; unresolved origins: {unresolved}"
            ) from None

    async def cancel_and_wait(self, timeout: float | None = None) -> bool:
        self._bind_running_loop()
        tasks = tuple(self._tasks)
        if not tasks:
            return False
        self._cancelling = True
        for task in tasks:
            if not task.done():
                task.cancel()
        await self.wait_settled(timeout=timeout)
        return True

    async def close(
        self,
        *,
        timeout: float | None = None,
        cancel: bool = False,
    ) -> None:
        self._bind_running_loop()
        if self._close_completed:
            return
        self._closed = True
        if cancel:
            await self.cancel_and_wait(timeout=timeout)
        else:
            await self.wait_settled(timeout=timeout)
        self._close_completed = True

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    @property
    def pending_tasks(self) -> tuple[asyncio.Task[Any], ...]:
        return tuple(self._tasks)

    def origin_for(self, task: asyncio.Task[Any]) -> str | None:
        return self._origins.get(task)
