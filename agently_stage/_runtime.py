# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Any

from .StageException import StageLifecycleError

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, Task
    from collections.abc import Awaitable, Callable

    from .Stage import Stage
    from .StageHandle import StageHandle


class _GenerationState(Enum):
    QUEUED = "queued"
    STARTING = "starting"
    OPEN = "open"
    SEALING = "sealing"
    DRAINING = "draining"
    CLOSED = "closed"


class _WorkPhase(Enum):
    BODY = "body"
    SETTLEMENT = "settlement"


@dataclass(frozen=True)
class _RuntimeSnapshot:
    active_generation_id: int | None
    queued_generation_id: int | None
    active_loop_count: int
    control_thread_count: int


@dataclass
class _Submission:
    handle: StageHandle[Any]
    runner: Callable[[_Generation], Awaitable[None]]
    owner: bool
    context: contextvars.Context
    phase: _WorkPhase


@dataclass
class _Generation:
    generation_id: int
    state: _GenerationState = _GenerationState.QUEUED
    reservations: int = 0
    loop: AbstractEventLoop | None = None
    seal_event: asyncio.Event | None = None
    pending_submissions: list[_Submission] = field(default_factory=list[_Submission])


@dataclass(frozen=True)
class _ExecutionContext:
    generation: _Generation
    handle: StageHandle[Any]
    phase: _WorkPhase


_active_execution: contextvars.ContextVar[_ExecutionContext | None] = contextvars.ContextVar(
    "agently_stage_active_execution",
    default=None,
)


class _RuntimeCarrier:
    """Process-local owner of finite Stage event-loop generations."""

    def __init__(self) -> None:
        self._admission_lock = threading.RLock()
        self._control_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="AgentlyStageControl")
        self._blocking_executor = ThreadPoolExecutor(thread_name_prefix="AgentlyStageBlocking")
        self._current: _Generation | None = None
        self._next: _Generation | None = None
        self._generation_counter = 0

    @property
    def blocking_executor(self) -> ThreadPoolExecutor:
        return self._blocking_executor

    def owns_current_execution(self, stage: Stage) -> bool:
        """Return whether the caller is executing work retained by ``stage``."""

        context = _active_execution.get()
        return context is not None and context.handle._stage is stage

    def submit(
        self,
        handle: StageHandle[Any],
        runner: Callable[[_Generation], Awaitable[None]],
        *,
        preferred: _Generation | None = None,
        owner: bool = True,
        phase: _WorkPhase = _WorkPhase.BODY,
    ) -> int:
        submission_context = contextvars.copy_context()
        handle._retain_work()
        try:
            with self._admission_lock:
                generation = self._reserve_locked(preferred)
                handle._set_generation_id(generation.generation_id)
                submission = _Submission(
                    handle=handle,
                    runner=runner,
                    owner=owner,
                    context=submission_context,
                    phase=phase,
                )
                loop = generation.loop
                if loop is None:
                    generation.pending_submissions.append(submission)
                else:
                    loop.call_soon_threadsafe(self._start_submission, generation, submission)
                return generation.generation_id
        except BaseException:
            handle._release_work()
            raise

    def acquire_lease(self) -> _Generation:
        with self._admission_lock:
            return self._reserve_locked(None)

    def release_lease(self, generation: _Generation) -> None:
        self._release_reservation(generation)

    def snapshot(self) -> _RuntimeSnapshot:
        with self._admission_lock:
            current = self._current
            queued = self._next
            current_id = None if current is None or current.state is _GenerationState.CLOSED else current.generation_id
            queued_id = None if queued is None or queued.state is _GenerationState.CLOSED else queued.generation_id
            active_loop_count = sum(
                generation is not None and generation.loop is not None for generation in (current, queued)
            )
        control_thread_count = sum(thread.name.startswith("AgentlyStageControl") for thread in threading.enumerate())
        return _RuntimeSnapshot(
            active_generation_id=current_id,
            queued_generation_id=queued_id,
            active_loop_count=active_loop_count,
            control_thread_count=control_thread_count,
        )

    def create_settlement_task(self, coroutine: Any) -> Task[Any]:
        """Create one retained task in the active handle's settlement phase."""

        context = _active_execution.get()
        if context is None:
            raise StageLifecycleError("Settlement task requires active Stage execution")
        token = _active_execution.set(
            _ExecutionContext(
                generation=context.generation,
                handle=context.handle,
                phase=_WorkPhase.SETTLEMENT,
            )
        )
        try:
            return asyncio.create_task(coroutine)
        finally:
            _active_execution.reset(token)

    def bind_current_execution(self, context: contextvars.Context) -> contextvars.Context:
        """Overlay the active private Stage lineage on a user context snapshot."""

        bound_context = context.copy()
        execution = _active_execution.get()
        if execution is not None:
            bound_context.run(_active_execution.set, execution)
        return bound_context

    def _reserve_locked(self, preferred: _Generation | None) -> _Generation:
        if preferred is not None:
            if preferred not in (self._current, self._next):
                raise StageLifecycleError("Pinned Stage generation is no longer owned by the carrier")
            if preferred.state not in {
                _GenerationState.QUEUED,
                _GenerationState.STARTING,
                _GenerationState.OPEN,
            }:
                raise StageLifecycleError("Pinned Stage generation is already sealing")
            generation = preferred
        elif self._current is None:
            generation = self._create_generation_locked(as_next=False)
        elif self._current.state in {
            _GenerationState.QUEUED,
            _GenerationState.STARTING,
            _GenerationState.OPEN,
        }:
            generation = self._current
        elif self._next is not None:
            generation = self._next
        else:
            generation = self._create_generation_locked(as_next=True)
        generation.reservations += 1
        return generation

    def _create_generation_locked(self, *, as_next: bool) -> _Generation:
        self._generation_counter += 1
        generation = _Generation(self._generation_counter)
        if as_next:
            self._next = generation
        else:
            self._current = generation
        try:
            self._control_executor.submit(self._run_generation, generation)
        except RuntimeError as error:
            if as_next:
                self._next = None
            else:
                self._current = None
            raise StageLifecycleError("Stage control executor cannot accept a generation") from error
        return generation

    def _retain_reservation(self, generation: _Generation) -> None:
        with self._admission_lock:
            if generation.state not in {_GenerationState.STARTING, _GenerationState.OPEN}:
                raise StageLifecycleError("Cannot retain work after generation sealing")
            generation.reservations += 1

    def _release_reservation(self, generation: _Generation) -> None:
        loop: AbstractEventLoop | None = None
        seal_event: asyncio.Event | None = None
        with self._admission_lock:
            if generation.reservations <= 0:
                raise StageLifecycleError("Stage generation reservation underflow")
            generation.reservations -= 1
            if generation.reservations == 0:
                if generation.state in {
                    _GenerationState.QUEUED,
                    _GenerationState.STARTING,
                    _GenerationState.OPEN,
                }:
                    generation.state = _GenerationState.SEALING
                loop = generation.loop
                seal_event = generation.seal_event
        if loop is not None and seal_event is not None:
            loop.call_soon_threadsafe(seal_event.set)

    def _run_generation(self, generation: _Generation) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_task_factory(partial(self._task_factory, generation))
        seal_event = asyncio.Event()

        with self._admission_lock:
            generation.loop = loop
            generation.seal_event = seal_event
            if generation.reservations == 0:
                generation.state = _GenerationState.SEALING
            else:
                generation.state = _GenerationState.OPEN
            submissions = generation.pending_submissions.copy()
            generation.pending_submissions.clear()
            should_seal = generation.reservations == 0

        for submission in submissions:
            loop.call_soon(self._start_submission, generation, submission)
        if should_seal:
            loop.call_soon(seal_event.set)

        try:
            loop.run_until_complete(seal_event.wait())
            with self._admission_lock:
                generation.state = _GenerationState.DRAINING
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
            with self._admission_lock:
                generation.loop = None
                generation.seal_event = None
                generation.state = _GenerationState.CLOSED
                if self._current is generation:
                    self._current = self._next
                    self._next = None

    def _start_submission(self, generation: _Generation, submission: _Submission) -> None:
        loop = generation.loop
        if loop is None:
            submission.handle._set_body_exception(StageLifecycleError("Stage generation loop is unavailable"))
            self._release_reservation(generation)
            submission.handle._release_work()
            return
        submission.context.run(
            loop.create_task,
            self._run_submission(generation, submission),
        )

    async def _run_submission(self, generation: _Generation, submission: _Submission) -> None:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        if task is None:
            raise StageLifecycleError("Stage submission has no owner task")
        if submission.owner:
            submission.handle._set_owner_task(loop, task)
        token = _active_execution.set(
            _ExecutionContext(
                generation=generation,
                handle=submission.handle,
                phase=submission.phase,
            )
        )
        try:
            await submission.runner(generation)
        finally:
            _active_execution.reset(token)
            self._release_reservation(generation)
            submission.handle._release_work()

    def _task_factory(
        self,
        generation: _Generation,
        loop: AbstractEventLoop,
        coroutine: Any,
    ) -> Task[Any]:
        context = _active_execution.get()
        if context is None or context.generation is not generation:
            return asyncio.tasks.Task(coroutine, loop=loop)

        handle = context.handle
        self._retain_reservation(generation)
        handle._retain_work()
        try:
            task = asyncio.tasks.Task(coroutine, loop=loop)
            should_cancel = handle._register_owned_task(task, phase=context.phase.value)
        except BaseException:
            self._release_reservation(generation)
            handle._release_work()
            raise
        task.add_done_callback(partial(self._descendant_done, generation, handle))
        if should_cancel:
            task.cancel()
        return task

    def _descendant_done(
        self,
        generation: _Generation,
        handle: StageHandle[Any],
        task: Task[Any],
    ) -> None:
        handle._unregister_owned_task(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                handle._record_settlement_error(error)
        self._release_reservation(generation)
        handle._release_work()


_RUNTIME_CARRIER = _RuntimeCarrier()


def _runtime_snapshot() -> _RuntimeSnapshot:  # pyright: ignore[reportUnusedFunction]
    return _RUNTIME_CARRIER.snapshot()
