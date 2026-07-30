# Copyright 2024-2026 Maplemx(Mo Xin), AgentEra Ltd. Agently Team(https://Agently.tech)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from .Stage import Stage
from .StageException import StageClosedError, StageLifecycleError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

T = TypeVar("T")


@dataclass(frozen=True)
class LocalTaskOutcome:
    """Compatibility completion observation for ``LocalTaskScope``."""

    task: asyncio.Task[Any]
    origin: str
    cancelled: bool
    error: BaseException | None


class LocalTaskScope:
    """Deprecated compatibility facade over a caller-loop ``Stage`` scope."""

    def __init__(
        self,
        *,
        on_done: Callable[[LocalTaskOutcome], object] | None = None,
    ) -> None:
        warnings.warn(
            "LocalTaskScope is deprecated; use Stage.go() or Stage.adopt()",
            DeprecationWarning,
            stacklevel=2,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stage = Stage(on_adopted_done=self._task_done)
        self._on_done = on_done
        self._closed = False
        self._close_completed = False

    def _bind_running_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise StageLifecycleError("A local Stage task scope cannot cross event loops")
        return loop

    def _bound_stage(self) -> Stage:
        self._bind_running_loop()
        return self._stage

    def spawn(
        self,
        coroutine: Coroutine[Any, Any, T],
        *,
        origin: str,
    ) -> asyncio.Task[T]:
        if self._closed:
            raise StageClosedError("Cannot submit work to a closed local Stage task scope")
        self._bind_running_loop()
        return self._stage.create_task(coroutine, origin=origin)

    def adopt(
        self,
        task: asyncio.Task[T],
        *,
        origin: str,
    ) -> asyncio.Task[T]:
        if self._closed:
            raise StageClosedError("Cannot adopt work into a closed local Stage task scope")
        stage = self._bound_stage()
        if task.get_loop() is not self._loop:
            raise StageLifecycleError("A local Stage task scope cannot adopt a task from another event loop")
        return stage.adopt(task, origin=origin)

    def _task_done(self, task: asyncio.Task[Any], origin: str) -> None:
        cancelled = task.cancelled()
        error = None if cancelled else task.exception()
        if self._on_done is None:
            return
        outcome = LocalTaskOutcome(
            task=task,
            origin=origin,
            cancelled=cancelled,
            error=error,
        )
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

    async def wait_settled(self, timeout: float | None = None) -> None:
        stage = self._bound_stage()
        await stage.async_wait_settled(timeout=timeout)

    async def cancel_and_wait(self, timeout: float | None = None) -> bool:
        stage = self._bound_stage()
        return await stage.async_cancel_and_wait_settled(timeout=timeout)

    async def close(
        self,
        *,
        timeout: float | None = None,
        cancel: bool = False,
    ) -> None:
        stage = self._bound_stage()
        if self._close_completed:
            return
        self._closed = True
        if cancel:
            await stage.async_cancel_and_wait_settled(timeout=timeout)
        await stage.async_close(timeout=timeout)
        self._close_completed = True

    @property
    def pending_count(self) -> int:
        return self._stage.adopted_count

    @property
    def pending_tasks(self) -> tuple[asyncio.Task[Any], ...]:
        return self._stage.adopted_tasks

    @property
    def pending_origins(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                origin
                for task in self._stage.adopted_tasks
                if (origin := self._stage.origin_for_adopted(task)) is not None
            )
        )

    def origin_for(self, task: asyncio.Task[Any]) -> str | None:
        return self._stage.origin_for_adopted(task)
