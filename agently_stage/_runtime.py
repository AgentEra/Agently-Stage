# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Any, cast

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
    carrier_loop_count: int
    escape_loop_count: int
    active_generation_ids: tuple[int, ...]


@dataclass
class _Submission:
    handle: StageHandle[Any]
    runner: Callable[[_Generation], Awaitable[None]]
    owner: bool
    context: contextvars.Context
    phase: _WorkPhase
    blocked_generation_ids: frozenset[int]


@dataclass
class _Generation:
    generation_id: int
    slot_id: int
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
    blocked_generation_ids: frozenset[int] = frozenset()


_active_execution: contextvars.ContextVar[_ExecutionContext | None] = contextvars.ContextVar(
    "agently_stage_active_execution",
    default=None,
)


class _CarrierSlot:
    """One finite carrier-loop lane owned by the process runtime."""

    def __init__(
        self,
        slot_id: int,
        allocate_generation_id: Callable[[], int],
        *,
        on_idle: Callable[[_CarrierSlot], None] | None = None,
    ) -> None:
        self.slot_id = slot_id
        self._allocate_generation_id = allocate_generation_id
        self._on_idle = on_idle
        self._admission_lock = threading.RLock()
        self._control_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"AgentlyStageControl-{slot_id}",
        )
        self._current: _Generation | None = None
        self._next: _Generation | None = None

    def submit(
        self,
        handle: StageHandle[Any],
        runner: Callable[[_Generation], Awaitable[None]],
        *,
        preferred: _Generation | None = None,
        owner: bool = True,
        phase: _WorkPhase = _WorkPhase.BODY,
        blocked_generation_ids: frozenset[int] = frozenset(),
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
                    blocked_generation_ids=blocked_generation_ids,
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

    def acquire_lease(self, preferred: _Generation | None = None) -> _Generation:
        with self._admission_lock:
            return self._reserve_locked(preferred)

    def release_lease(self, generation: _Generation) -> None:
        self._release_reservation(generation)

    def snapshot(self) -> tuple[int | None, int | None, int, int]:
        with self._admission_lock:
            current = self._current
            queued = self._next
            current_id = None if current is None or current.state is _GenerationState.CLOSED else current.generation_id
            queued_id = None if queued is None or queued.state is _GenerationState.CLOSED else queued.generation_id
            active_loop_count = sum(
                generation is not None and generation.loop is not None for generation in (current, queued)
            )
            reservations = sum(
                generation.reservations
                for generation in (current, queued)
                if generation is not None and generation.state is not _GenerationState.CLOSED
            )
        return current_id, queued_id, active_loop_count, reservations

    def owns_loop(self, loop: AbstractEventLoop) -> bool:
        with self._admission_lock:
            return any(generation is not None and generation.loop is loop for generation in (self._current, self._next))

    def owns_generation(self, generation: _Generation) -> bool:
        return generation.slot_id == self.slot_id

    def owns_any_generation_id(self, generation_ids: frozenset[int]) -> bool:
        if not generation_ids:
            return False
        with self._admission_lock:
            return any(
                generation is not None
                and generation.state is not _GenerationState.CLOSED
                and generation.generation_id in generation_ids
                for generation in (self._current, self._next)
            )

    def shutdown(self) -> None:
        self._control_executor.shutdown(wait=False)

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
        generation = _Generation(
            generation_id=self._allocate_generation_id(),
            slot_id=self.slot_id,
        )
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
                became_idle = self._current is None and self._next is None
            if became_idle and self._on_idle is not None:
                self._on_idle(self)

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
                blocked_generation_ids=submission.blocked_generation_ids,
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
        context: contextvars.Context | None = None,
    ) -> Task[Any]:
        active_execution = _active_execution.get()

        def create_task() -> Task[Any]:
            if context is None:
                return asyncio.tasks.Task(coroutine, loop=loop)
            task_constructor = cast("Any", asyncio.tasks.Task)
            return task_constructor(
                coroutine,
                loop=loop,
                context=context,
            )

        if active_execution is None or active_execution.generation is not generation:
            return create_task()

        handle = active_execution.handle
        self._retain_reservation(generation)
        handle._retain_work()
        try:
            task = create_task()
            should_cancel = handle._register_owned_task(task, phase=active_execution.phase.value)
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
        handle._stage._owned_activity()
        self._release_reservation(generation)
        handle._release_work()


class _RuntimeCarrier:
    """Process-local finite pool of lazy carrier-loop slots."""

    def __init__(self) -> None:
        self._pool_lock = threading.RLock()
        self._blocking_executor = ThreadPoolExecutor(thread_name_prefix="AgentlyStageBlocking")
        self._generation_counter = 0
        self._slot_counter = 0
        self._selection_cursor = 0
        self._carrier_loop_count = 1
        self._settings_frozen = False
        self._slots: list[_CarrierSlot] = [self._new_slot_locked()]
        self._escape_slots: dict[int, _CarrierSlot] = {}

    @property
    def blocking_executor(self) -> ThreadPoolExecutor:
        return self._blocking_executor

    def set_carrier_loop_count(self, count: int) -> None:
        retired: list[_CarrierSlot] = []
        with self._pool_lock:
            if self._settings_frozen:
                if count == self._carrier_loop_count:
                    return
                raise StageLifecycleError(
                    "runtime.carrier_loop_count is frozen after the first carrier lease; restart the process to change it"
                )
            while len(self._slots) < count:
                self._slots.append(self._new_slot_locked())
            while len(self._slots) > count:
                retired.append(self._slots.pop())
            self._carrier_loop_count = count
            self._selection_cursor %= count
        for slot in retired:
            slot.shutdown()

    def owns_current_execution(self, stage: Stage) -> bool:
        """Return whether logical execution lineage belongs to ``stage``."""

        context = _active_execution.get()
        return context is not None and context.handle._stage is stage

    def would_sync_wait_block_current_carrier(self, stage: Stage) -> bool:
        """Return whether ``stage`` would target the carrier loop now executing."""

        context = _active_execution.get()
        with stage._scope_lock:
            generation = stage._generation_lease
            active_backend = stage._active_backend
        if (
            active_backend == "stage"
            and generation is not None
            and context is not None
            and generation.generation_id in context.blocked_generation_ids
        ):
            return True

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        if active_backend == "stage" and generation is not None:
            return generation.loop is running_loop

        # An unbound carrier Stage inherits the physically active generation on
        # first lease. Context propagation into a blocking worker is harmless:
        # such a worker has no running loop and returned above.
        return active_backend is None and context is not None and context.generation.loop is running_loop

    def submit(
        self,
        handle: StageHandle[Any],
        runner: Callable[[_Generation], Awaitable[None]],
        *,
        preferred: _Generation | None = None,
        owner: bool = True,
        phase: _WorkPhase = _WorkPhase.BODY,
        blocked_generation_ids: frozenset[int] = frozenset(),
    ) -> int:
        if preferred is None:
            slot = self._select_slot(
                avoid_current_loop=False,
                blocked_generation_ids=blocked_generation_ids,
            )
        else:
            slot = self._slot_for_generation(preferred)
        return slot.submit(
            handle,
            runner,
            preferred=preferred,
            owner=owner,
            phase=phase,
            blocked_generation_ids=blocked_generation_ids,
        )

    def acquire_lease(self, *, avoid_current_loop: bool = False) -> _Generation:
        self._freeze_settings()
        inherited = _active_execution.get()
        blocked_generation_ids: frozenset[int] = frozenset() if inherited is None else inherited.blocked_generation_ids
        if (
            inherited is not None
            and inherited.generation.generation_id not in blocked_generation_ids
            and not self._generation_is_current_loop(
                inherited.generation,
                only_when=avoid_current_loop,
            )
        ):
            try:
                return self._slot_for_generation(inherited.generation).acquire_lease(inherited.generation)
            except StageLifecycleError:
                pass
        return self._select_slot(
            avoid_current_loop=avoid_current_loop,
            blocked_generation_ids=blocked_generation_ids,
        ).acquire_lease()

    def blocked_generation_ids_for_submission(
        self,
        generation: _Generation,
        *,
        synchronous_scope: bool,
    ) -> frozenset[int]:
        """Return carrier ancestors that must not receive this scope's descendants."""

        context = _active_execution.get()
        if context is None:
            return frozenset()
        blocked_generation_ids = context.blocked_generation_ids
        if synchronous_scope and generation is not context.generation:
            blocked_generation_ids = blocked_generation_ids | {
                context.generation.generation_id,
            }
        return blocked_generation_ids

    def release_lease(self, generation: _Generation) -> None:
        self._slot_for_generation(generation).release_lease(generation)

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
                blocked_generation_ids=context.blocked_generation_ids,
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

    def snapshot(self) -> _RuntimeSnapshot:
        with self._pool_lock:
            slots = tuple(self._slots)
            escape_slots = tuple(self._escape_slots.values())
            configured_count = self._carrier_loop_count
        snapshots = [slot.snapshot() for slot in (*slots, *escape_slots)]
        active_ids = tuple(current_id for current_id, _, _, _ in snapshots if current_id is not None)
        queued_ids = tuple(queued_id for _, queued_id, _, _ in snapshots if queued_id is not None)
        active_loop_count = sum(loop_count for _, _, loop_count, _ in snapshots)
        control_thread_count = sum(thread.name.startswith("AgentlyStageControl") for thread in threading.enumerate())
        return _RuntimeSnapshot(
            active_generation_id=active_ids[0] if active_ids else None,
            queued_generation_id=queued_ids[0] if queued_ids else None,
            active_loop_count=active_loop_count,
            control_thread_count=control_thread_count,
            carrier_loop_count=configured_count,
            escape_loop_count=len(escape_slots),
            active_generation_ids=active_ids,
        )

    def _freeze_settings(self) -> None:
        with self._pool_lock:
            self._settings_frozen = True

    def _allocate_generation_id(self) -> int:
        with self._pool_lock:
            self._generation_counter += 1
            return self._generation_counter

    def _new_slot_locked(self, *, escape: bool = False) -> _CarrierSlot:
        self._slot_counter += 1
        slot = _CarrierSlot(
            self._slot_counter,
            self._allocate_generation_id,
            on_idle=self._escape_slot_idle if escape else None,
        )
        if escape:
            self._escape_slots[slot.slot_id] = slot
        return slot

    def _escape_slot_idle(self, slot: _CarrierSlot) -> None:
        with self._pool_lock:
            removed = self._escape_slots.pop(slot.slot_id, None)
        if removed is not None:
            removed.shutdown()

    def _slot_for_generation(self, generation: _Generation) -> _CarrierSlot:
        with self._pool_lock:
            slots = (*self._slots, *self._escape_slots.values())
        for slot in slots:
            if slot.owns_generation(generation):
                return slot
        raise StageLifecycleError("Stage generation is no longer owned by the carrier pool")

    def _generation_is_current_loop(self, generation: _Generation, *, only_when: bool) -> bool:
        if not only_when:
            return False
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return generation.loop is running_loop

    def _select_slot(
        self,
        *,
        avoid_current_loop: bool,
        blocked_generation_ids: frozenset[int] = frozenset(),
    ) -> _CarrierSlot:
        self._freeze_settings()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        with self._pool_lock:
            slots = tuple(self._slots)
            cursor = self._selection_cursor
        candidates: list[tuple[int, int, _CarrierSlot]] = []
        for index, slot in enumerate(slots):
            if slot.owns_any_generation_id(blocked_generation_ids):
                continue
            if avoid_current_loop and running_loop is not None and slot.owns_loop(running_loop):
                continue
            _, _, _, pressure = slot.snapshot()
            distance = (index - cursor) % len(slots)
            candidates.append((pressure, distance, slot))
        if not candidates:
            with self._pool_lock:
                return self._new_slot_locked(escape=True)
        _, _, selected = min(candidates, key=lambda item: (item[0], item[1]))
        with self._pool_lock:
            selected_index = self._slots.index(selected)
            self._selection_cursor = (selected_index + 1) % len(self._slots)
        return selected


_RUNTIME_CARRIER = _RuntimeCarrier()


def _runtime_snapshot() -> _RuntimeSnapshot:  # pyright: ignore[reportUnusedFunction]
    return _RUNTIME_CARRIER.snapshot()
