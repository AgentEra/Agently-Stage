# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import sys
import threading
import time
import types
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast, overload

from ._runtime import _RUNTIME_CARRIER, _Generation, _WorkPhase
from .StageException import (
    StageBackpressureError,
    StageClosedError,
    StageIdleTimeoutError,
    StageLifecycleError,
    StageSettlementError,
)
from .StageFunction import StageFunction
from .StageHandle import StageHandle

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, Task

    from .StageStream import StageStream

T = TypeVar("T")
StreamT = TypeVar("StreamT")
P = ParamSpec("P")
_BackendKind = Literal["caller", "stage"]
_ContextMode = Literal["sync", "async"]


class _AutoLoop:
    def __repr__(self) -> str:
        return "<auto>"


_AUTO_LOOP = _AutoLoop()
_active_stage: contextvars.ContextVar[Stage | None] = contextvars.ContextVar(
    "agently_stage_active_scope",
    default=None,
)


@dataclass(frozen=True)
class StageSnapshot:
    """A bounded immutable view of generic Stage scope state."""

    state: Literal["open", "sealed", "closed"]
    backend_mode: Literal["auto", "caller", "stage"]
    active_backend: _BackendKind | None
    active_count: int
    active_root_count: int
    pending_root_count: int
    unresolved_origins: tuple[str, ...]
    last_activity: float
    idle_timeout: float | None
    cancelling: bool
    idle_timed_out: bool
    carrier_generation_id: int | None


@dataclass(eq=False)
class _RootAdmission:
    gate: Future[None] | None
    granted: bool


_IMMEDIATE_ROOT_ADMISSION = _RootAdmission(gate=None, granted=True)


class Stage:
    """A structured scope whose work may use a caller loop or the Stage carrier."""

    @classmethod
    def set_settings(cls, key: str, value: object) -> type[Stage]:
        """Set one process-level Stage runtime option before carrier use."""

        if key != "runtime.carrier_loop_count":
            raise KeyError(f"Unknown Stage setting: {key}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("runtime.carrier_loop_count must be a positive integer")
        if value <= 0:
            raise ValueError("runtime.carrier_loop_count must be greater than zero")
        _RUNTIME_CARRIER.set_carrier_loop_count(value)
        return cls

    @classmethod
    def as_sync(
        cls,
        function: Callable[P, T | Awaitable[T]],
    ) -> Callable[P, T]:
        """Expose a callable through one automatically routed synchronous scope."""

        if not callable(function):
            raise TypeError(f"Expected a callable, got {type(function)}")
        if inspect.isasyncgenfunction(function) or inspect.isgeneratorfunction(function):
            raise TypeError("Stage.as_sync accepts scalar callables; use StageCallBridge.iter_sync for streams")

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with cls() as stage:
                response = stage.go(function, *args, **kwargs)
                from .StageStream import StageStream

                if isinstance(response, StageStream):
                    response.close()
                    raise TypeError("Stage.as_sync accepts scalar callables; use StageCallBridge.iter_sync for streams")
                return cast("StageHandle[T]", response).get()

        return wrapper

    @classmethod
    def as_async(
        cls,
        function: Callable[P, T | Awaitable[T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        """Expose a callable through one automatically routed asynchronous scope."""

        if not callable(function):
            raise TypeError(f"Expected a callable, got {type(function)}")
        if inspect.isasyncgenfunction(function) or inspect.isgeneratorfunction(function):
            raise TypeError("Stage.as_async accepts scalar callables; use StageCallBridge.iter_async for streams")

        @functools.wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            async with cls() as stage:
                response = stage.go(function, *args, **kwargs)
                from .StageStream import StageStream

                if isinstance(response, StageStream):
                    await response.async_close()
                    raise TypeError(
                        "Stage.as_async accepts scalar callables; use StageCallBridge.iter_async for streams"
                    )
                return await cast("StageHandle[T]", response).async_get()

        return wrapper

    @overload
    def __init__(
        self,
        *,
        max_concurrency: int | None = None,
        max_pending: int | None = None,
        idle_timeout: float | None = None,
        max_workers: int | None = None,
        executor: Executor | None = None,
        exception_handler: Callable[[BaseException], object] | None = None,
        on_adopted_done: Callable[[Task[Any], str], None] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        loop: AbstractEventLoop | Literal["stage"],
        *,
        max_concurrency: int | None = None,
        max_pending: int | None = None,
        idle_timeout: float | None = None,
        max_workers: int | None = None,
        executor: Executor | None = None,
        exception_handler: Callable[[BaseException], object] | None = None,
        on_adopted_done: Callable[[Task[Any], str], None] | None = None,
    ) -> None: ...

    def __init__(
        self,
        loop: AbstractEventLoop | Literal["stage"] | _AutoLoop | None = _AUTO_LOOP,
        *,
        max_concurrency: int | None = None,
        max_pending: int | None = None,
        idle_timeout: float | None = None,
        max_workers: int | None = None,
        executor: Executor | None = None,
        exception_handler: Callable[[BaseException], object] | None = None,
        on_adopted_done: Callable[[Task[Any], str], None] | None = None,
    ) -> None:
        if loop is None:
            raise TypeError("Stage loop must be omitted, 'stage', or an event loop; None is ambiguous")
        if max_concurrency is not None and max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")
        if max_pending is not None and max_pending < 0:
            raise ValueError("max_pending must be zero or greater")
        if max_pending is not None and max_concurrency is None:
            raise ValueError("max_pending requires max_concurrency")
        if idle_timeout is not None and idle_timeout <= 0:
            raise ValueError("idle_timeout must be greater than zero")
        if executor is not None and max_workers is not None:
            raise ValueError("executor and max_workers are mutually exclusive")

        self._scope_lock = threading.RLock()
        self._scope_condition = threading.Condition(self._scope_lock)
        self._close_operation_lock = threading.Lock()
        self._active_handles: set[StageHandle[Any]] = set()
        self._adopted_tasks: dict[Task[Any], str] = {}
        self._scope_settlement_errors: list[BaseException] = []
        self._sealed = False
        self._close_completed = False
        self._cancelling = False
        self._exception_handler = exception_handler
        self._on_adopted_done = on_adopted_done
        self._max_concurrency = max_concurrency
        self._max_pending = max_pending
        self._active_root_count = 0
        self._pending_admissions: deque[_RootAdmission] = deque()
        self._idle_timeout = idle_timeout
        self._last_activity = time.monotonic()
        self._idle_timer: threading.Timer | None = None
        self._idle_timer_token = 0
        self._idle_timeout_error: StageIdleTimeoutError | None = None
        self._private_executor = (
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AgentlyStageScopeBlocking")
            if max_workers is not None
            else None
        )
        self._blocking_executor = (
            executor if executor is not None else self._private_executor or _RUNTIME_CARRIER.blocking_executor
        )
        self._generation_lease: _Generation | None = None
        self._blocked_generation_ids: frozenset[int] = frozenset()
        self._active_backend: _BackendKind | None = None
        self._active_loop: AbstractEventLoop | None = None
        self._context_mode: _ContextMode | None = None

        if isinstance(loop, _AutoLoop):
            self._backend_mode: Literal["auto", "caller", "stage"] = "auto"
            self._configured_loop: AbstractEventLoop | None = None
        elif loop == "stage":
            self._backend_mode = "stage"
            self._configured_loop = None
        elif isinstance(cast("Any", loop), asyncio.AbstractEventLoop):
            if loop.is_closed():
                raise StageLifecycleError("Stage cannot bind a closed event loop")
            self._backend_mode = "caller"
            self._configured_loop = loop
        else:
            raise TypeError("Stage loop must be omitted, 'stage', or an event loop")

    def _classify_task(self, task: object) -> str | None:
        if isinstance(task, StageFunction):
            return "stage_func"
        if isinstance(task, functools.partial):
            return self._classify_task(task.func)
        if isinstance(task, classmethod | staticmethod | types.MethodType):
            return self._classify_task(cast("Any", task).__func__)
        if inspect.isasyncgenfunction(task):
            return "async_gen_func"
        if inspect.isasyncgen(task):
            return "async_gen"
        if isinstance(task, AsyncIterator):
            return "async_gen"
        if inspect.isgeneratorfunction(task):
            return "gen_func"
        if inspect.isgenerator(task):
            return "gen"
        if isinstance(task, Iterator):
            return "gen"
        if inspect.iscoroutinefunction(task):
            return "async_func"
        if inspect.iscoroutine(task):
            return "async_coro"
        if isinstance(task, Future):
            return "future"
        if inspect.isfunction(task) or inspect.isbuiltin(task):
            return "func"
        if callable(task):
            return self._classify_task(task.__call__)
        return None

    def _callback_registration_allowed(self) -> bool:
        return not self._sealed or _active_stage.get() is self

    @staticmethod
    def _inherited_caller_loop_for_sync() -> AbstractEventLoop | None:
        """Return a caller loop that is asynchronously waiting for this worker."""

        outer = _active_stage.get()
        if outer is None:
            return None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return None
        with outer._scope_lock:
            if outer._active_backend != "caller":
                return None
            loop = outer._active_loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return None
        return loop

    def _resolve_backend_locked(self) -> tuple[_BackendKind, AbstractEventLoop | None]:
        if self._active_backend is not None:
            return self._active_backend, self._active_loop

        if self._backend_mode == "caller":
            loop = self._configured_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                raise StageLifecycleError("The configured Stage event loop must be running")
            backend: _BackendKind = "caller"
        elif self._backend_mode == "stage":
            backend = "stage"
            loop = None
        else:
            inherited_caller_loop = self._inherited_caller_loop_for_sync()
            if self._context_mode == "sync":
                if inherited_caller_loop is None:
                    backend = "stage"
                    loop = None
                else:
                    backend = "caller"
                    loop = inherited_caller_loop
            else:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    if inherited_caller_loop is None:
                        backend = "stage"
                        loop = None
                    else:
                        backend = "caller"
                        loop = inherited_caller_loop
                else:
                    backend = "caller"

        if backend == "stage":
            self._generation_lease = _RUNTIME_CARRIER.acquire_lease(
                avoid_current_loop=self._context_mode == "sync",
            )
            self._blocked_generation_ids = _RUNTIME_CARRIER.blocked_generation_ids_for_submission(
                self._generation_lease,
                synchronous_scope=self._context_mode == "sync",
            )
        else:
            self._blocked_generation_ids = frozenset()
        self._active_backend = backend
        self._active_loop = loop
        return backend, loop

    def _new_handle_locked(
        self,
        *,
        origin: str,
        allow_sealed: bool = False,
    ) -> tuple[StageHandle[Any], _BackendKind, AbstractEventLoop | None]:
        if self._sealed and not allow_sealed:
            raise StageClosedError("Cannot submit work to a sealed Stage scope")
        backend, loop = self._resolve_backend_locked()
        handle: StageHandle[Any] = StageHandle(
            self,
            origin=origin,
            backend_kind=backend,
        )
        self._active_handles.add(handle)
        self._touch_locked()
        return handle, backend, loop

    def _admit_root_locked(self) -> _RootAdmission | None:
        if _active_stage.get() is self:
            return None
        if self._max_concurrency is None or self._active_root_count < self._max_concurrency:
            self._active_root_count += 1
            return _IMMEDIATE_ROOT_ADMISSION
        if self._max_pending is not None and len(self._pending_admissions) >= self._max_pending:
            raise StageBackpressureError(f"Stage pending root bound reached: max_pending={self._max_pending}")
        gate: Future[None] = Future()
        admission = _RootAdmission(gate=gate, granted=False)
        self._pending_admissions.append(admission)
        return admission

    async def _wait_for_admission(self, admission: _RootAdmission | None) -> None:
        if admission is not None and admission.gate is not None:
            await asyncio.shield(asyncio.wrap_future(admission.gate))

    async def _await_with_loop_affinity_guidance(self, awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except RuntimeError as error:
            message = str(error).lower()
            if self._active_backend == "stage" and (
                "attached to a different loop" in message or "bound to a different event loop" in message
            ):
                raise StageLifecycleError(
                    "This work depends on an object bound to another event loop and cannot run on the selected "
                    "Stage carrier; use 'async with Stage()' and await it on the object's owner loop"
                ) from error
            raise

    def _finish_admission(self, admission: _RootAdmission | None) -> None:
        if admission is None:
            return
        with self._scope_lock:
            if admission.granted:
                self._active_root_count -= 1
            else:
                try:
                    self._pending_admissions.remove(admission)
                except ValueError:
                    pass
            while self._pending_admissions:
                next_admission = self._pending_admissions.popleft()
                gate = next_admission.gate
                if gate is None or gate.done():
                    continue
                next_admission.granted = True
                self._active_root_count += 1
                gate.set_result(None)
                break
            self._scope_condition.notify_all()

    async def _execute_scalar(
        self,
        task: Callable[..., T] | Awaitable[T] | Future[T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        if isinstance(task, Future):
            return await self._await_with_loop_affinity_guidance(asyncio.wrap_future(cast("Future[T]", task)))
        if inspect.isawaitable(task):
            if args or kwargs:
                raise TypeError("Arguments cannot be supplied with a coroutine object")
            return await self._await_with_loop_affinity_guidance(cast("Awaitable[T]", task))
        if inspect.iscoroutinefunction(task):
            return await self._await_with_loop_affinity_guidance(task(*args, **kwargs))

        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()
        call = functools.partial(task, *args, **kwargs)
        blocking_future = loop.run_in_executor(self._blocking_executor, context.run, call)
        try:
            result = await asyncio.shield(blocking_future)
        except asyncio.CancelledError:
            await asyncio.shield(blocking_future)
            raise
        if inspect.isawaitable(result):
            return await self._await_with_loop_affinity_guidance(cast("Awaitable[T]", result))
        return cast("T", result)

    async def _execute_callback(
        self,
        callback: Callable[..., object | Awaitable[object]],
        args: tuple[object, ...],
        context: contextvars.Context,
    ) -> None:
        callback_context = _RUNTIME_CARRIER.bind_current_execution(context)
        if inspect.iscoroutinefunction(callback):
            callback_task = callback_context.run(asyncio.create_task, callback(*args))
            await callback_task
            return
        loop = asyncio.get_running_loop()
        call = functools.partial(callback, *args)
        result = await loop.run_in_executor(self._blocking_executor, callback_context.run, call)
        if inspect.isawaitable(result):
            callback_task = callback_context.run(asyncio.ensure_future, result)
            await callback_task

    def _schedule_caller_runner(
        self,
        handle: StageHandle[Any],
        loop: AbstractEventLoop,
        runner: Callable[[], Awaitable[None]],
        *,
        owner: bool,
        on_start_error: Callable[[], object] | None = None,
    ) -> None:
        submission_context = contextvars.copy_context()
        handle._retain_work()

        async def retained_runner() -> None:
            try:
                if owner:
                    await runner()
                else:
                    token = _active_stage.set(self)
                    try:
                        await runner()
                    finally:
                        _active_stage.reset(token)
            finally:
                handle._release_work()

        def start() -> None:
            coroutine = retained_runner()
            try:
                task = submission_context.run(loop.create_task, coroutine)
                if owner:
                    handle._set_owner_task(loop, cast("Task[object]", task))
            except BaseException as error:
                coroutine.close()
                if owner:
                    handle._set_body_exception(error)
                else:
                    handle._record_settlement_error(error)
                if on_start_error is not None:
                    on_start_error()
                handle._release_work()

        try:
            if loop is asyncio.get_running_loop():
                start()
            else:
                loop.call_soon_threadsafe(start)
        except RuntimeError:
            if loop.is_closed() or not loop.is_running():
                handle._release_work()
                raise StageLifecycleError("The selected caller event loop is unavailable") from None
            loop.call_soon_threadsafe(start)

    def _start_callback_drain_from_owner(self, handle: StageHandle[Any]) -> None:
        if handle._backend_kind == "stage":
            _RUNTIME_CARRIER.create_settlement_task(handle._drain_callbacks())
            return
        loop = handle._owner_loop
        if loop is None:
            handle._record_settlement_error(StageLifecycleError("Stage callback owner loop is unavailable"))
            return
        self._schedule_caller_runner(handle, loop, handle._drain_callbacks, owner=False)

    def _submit_callback_drain_locked(self, handle: StageHandle[Any]) -> None:
        handle_loop = handle._owner_loop
        if self._active_backend is None:
            if handle._backend_kind == "caller":
                if handle_loop is None or handle_loop.is_closed() or not handle_loop.is_running():
                    raise StageLifecycleError("Stage callback owner loop is unavailable")
                self._active_backend = "caller"
                self._active_loop = handle_loop
                self._blocked_generation_ids = frozenset()
            else:
                self._active_backend = "stage"
                self._active_loop = None
                self._generation_lease = _RUNTIME_CARRIER.acquire_lease()
                self._blocked_generation_ids = _RUNTIME_CARRIER.blocked_generation_ids_for_submission(
                    self._generation_lease,
                    synchronous_scope=False,
                )
        elif self._active_backend != handle._backend_kind or (
            self._active_backend == "caller" and self._active_loop is not handle_loop
        ):
            raise StageLifecycleError("A late callback cannot cross the active Stage backend epoch")
        self._active_handles.add(handle)
        if handle._backend_kind == "caller":
            loop = handle_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                raise StageLifecycleError("Stage callback owner loop is unavailable")
            self._schedule_caller_runner(handle, loop, handle._drain_callbacks, owner=False)
            return

        async def runner(generation: _Generation) -> None:
            del generation
            await handle._drain_callbacks()

        _RUNTIME_CARRIER.submit(
            handle,
            runner,
            preferred=self._generation_lease,
            owner=False,
            phase=_WorkPhase.SETTLEMENT,
            blocked_generation_ids=self._blocked_generation_ids,
        )

    @overload
    def go(  # pyright: ignore[reportOverlappingOverload]
        self,
        task: Callable[..., AsyncIterator[StreamT]] | AsyncIterator[StreamT],
        *args: Any,
        lazy: bool = False,
        on_success: Callable[[list[StreamT]], object | Awaitable[object]] | None = None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None = None,
        on_finally: Callable[[], object | Awaitable[object]] | None = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs: Any,
    ) -> StageStream[StreamT]: ...

    @overload
    def go(
        self,
        task: Callable[..., Iterator[StreamT]] | Iterator[StreamT],
        *args: Any,
        lazy: bool = False,
        on_success: Callable[[list[StreamT]], object | Awaitable[object]] | None = None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None = None,
        on_finally: Callable[[], object | Awaitable[object]] | None = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs: Any,
    ) -> StageStream[StreamT]: ...

    @overload
    def go(
        self,
        task: Callable[..., Awaitable[T]],
        *args: Any,
        lazy: bool = False,
        on_success: Callable[[T], object | Awaitable[object]] | None = None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None = None,
        on_finally: Callable[[], object | Awaitable[object]] | None = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs: Any,
    ) -> StageHandle[T]: ...

    @overload
    def go(
        self,
        task: Callable[..., T] | Awaitable[T] | Future[T],
        *args: Any,
        lazy: bool = False,
        on_success: Callable[[T], object | Awaitable[object]] | None = None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None = None,
        on_finally: Callable[[], object | Awaitable[object]] | None = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs: Any,
    ) -> StageHandle[T]: ...

    def go(
        self,
        task: Any,
        *args: Any,
        lazy: bool = False,
        on_success: Callable[[Any], object | Awaitable[object]] | None = None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None = None,
        on_finally: Callable[[], object | Awaitable[object]] | None = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs: Any,
    ) -> StageHandle[Any] | StageStream[Any]:
        del wait_interval
        task_class = self._classify_task(task)
        if task_class == "stage_func":
            return cast("StageFunction[Any]", task)(*args, **kwargs)
        if task_class in {"async_gen_func", "async_gen", "gen_func", "gen"}:
            return self._go_stream(
                task,
                task_class,
                args,
                kwargs,
                lazy=lazy,
                on_success=cast("Any", on_success),
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
            )
        if task_class is None:
            raise TypeError(f"Unsupported Stage task: {task!r}")

        origin = self._task_origin(task)
        with self._scope_lock:
            owned_nested = _active_stage.get() is self
            if self._sealed and not owned_nested:
                raise StageClosedError("Cannot submit work to a sealed Stage scope")
            admission = self._admit_root_locked()
            try:
                handle, backend, loop = self._new_handle_locked(
                    origin=origin,
                    allow_sealed=owned_nested,
                )
            except BaseException:
                self._finish_admission(admission)
                raise
            if on_success is not None:
                handle._register_initial_callback("success", on_success)
            if on_error is not None:
                handle._register_initial_callback("error", on_error)
            if on_finally is not None:
                handle._register_initial_callback("finally", on_finally)
            should_cancel = self._cancelling

        async def body(generation: _Generation | None = None) -> None:
            del generation
            token = _active_stage.set(self)
            try:
                try:
                    await self._wait_for_admission(admission)
                    result = await self._execute_scalar(task, args, kwargs)
                except asyncio.CancelledError as error:
                    should_start_callbacks = handle._set_body_cancelled(error)
                    if should_start_callbacks:
                        self._start_callback_drain_from_owner(handle)
                    raise
                except BaseException as error:
                    should_start_callbacks = handle._set_body_exception(error, ignored=ignore_exception)
                    if should_start_callbacks:
                        self._start_callback_drain_from_owner(handle)
                else:
                    should_start_callbacks = handle._set_body_result(result)
                    if should_start_callbacks:
                        self._start_callback_drain_from_owner(handle)
            finally:
                _active_stage.reset(token)
                self._finish_admission(admission)

        if backend == "stage":
            try:
                _RUNTIME_CARRIER.submit(
                    handle,
                    body,
                    preferred=self._generation_lease,
                    blocked_generation_ids=self._blocked_generation_ids,
                )
            except BaseException:
                self._finish_admission(admission)
                raise
        else:
            if loop is None:
                raise StageLifecycleError("Caller-loop Stage has no selected event loop")
            try:
                self._schedule_caller_runner(
                    handle,
                    loop,
                    body,
                    owner=True,
                    on_start_error=lambda: self._finish_admission(admission),
                )
            except BaseException:
                self._finish_admission(admission)
                raise
        if should_cancel:
            handle.cancel(timeout=0)
        return handle

    def _task_origin(self, task: object) -> str:
        function = task.func if isinstance(task, functools.partial) else task
        name = getattr(function, "__qualname__", None) or getattr(function, "__name__", None)
        return sys.intern(f"go:{name or type(function).__name__}")

    def create_task(
        self,
        coroutine: Coroutine[Any, Any, T],
        *,
        origin: str,
        name: str | None = None,
    ) -> Task[T]:
        """Create and own one native task on the active caller event loop."""

        if not inspect.iscoroutine(coroutine):
            raise TypeError("Stage.create_task requires a coroutine object")

        try:
            loop = asyncio.get_running_loop()
            with self._scope_lock:
                owned_nested = _active_stage.get() is self
                if self._sealed and not owned_nested:
                    raise StageClosedError("Cannot create a task in a sealed Stage scope")
                backend, selected_loop = self._resolve_backend_locked()
                if backend != "caller" or selected_loop is not loop:
                    lease = self._release_backend_if_quiescent_locked()
                    if lease is not None:
                        _RUNTIME_CARRIER.release_lease(lease)
                    if backend == "caller" and selected_loop is not None:
                        raise StageLifecycleError(
                            "Stage.create_task cannot move caller-loop-owned work to another event loop; "
                            "use 'async with Stage()' and await the async operation on its owner loop"
                        )
                    raise StageLifecycleError(
                        "Stage.create_task requires the current running caller event loop backend"
                    )
        except BaseException:
            coroutine.close()
            raise

        context = contextvars.copy_context()
        context.run(_active_stage.set, self)
        try:
            if name is None:
                task = context.run(loop.create_task, coroutine)
            else:
                task = context.run(loop.create_task, coroutine, name=name)
        except BaseException:
            coroutine.close()
            raise

        try:
            return self.adopt(task, origin=origin)
        except BaseException:
            task.cancel()
            raise

    def adopt(self, task: Task[T], *, origin: str) -> Task[T]:
        if not isinstance(cast("Any", task), asyncio.Task):
            raise TypeError("Stage.adopt requires an asyncio.Task")
        loop = task.get_loop()
        with self._scope_lock:
            owned_nested = _active_stage.get() is self
            if self._sealed and not owned_nested:
                raise StageClosedError("Cannot adopt work into a sealed Stage scope")
            existing = self._adopted_tasks.get(task)
            if existing is not None:
                if existing != origin:
                    raise StageLifecycleError(
                        f"A Stage task cannot be adopted with two origins: {existing!r} and {origin!r}"
                    )
                return task
            backend, selected_loop = self._resolve_backend_locked()
            if backend != "caller" or selected_loop is not loop:
                lease = self._release_backend_if_quiescent_locked()
                if lease is not None:
                    _RUNTIME_CARRIER.release_lease(lease)
                raise StageLifecycleError("Stage cannot adopt a task from a different event loop backend")
            self._adopted_tasks[task] = origin
            self._touch_locked()
            should_cancel = self._cancelling

        task.add_done_callback(self._adopted_task_done)
        if should_cancel:
            task.cancel()
        return task

    def _adopted_task_done(self, task: Task[Any]) -> None:
        if not task.cancelled():
            task.exception()
        with self._scope_lock:
            origin = self._adopted_tasks.pop(task, None)
            if origin is None:
                return
            self._touch_locked()
            observer = self._on_adopted_done
            if observer is not None:
                try:
                    observer(task, origin)
                except BaseException as error:
                    task.get_loop().call_exception_handler(
                        {
                            "message": "Stage adopted-task completion observer failed",
                            "exception": error,
                            "task": task,
                            "origin": origin,
                        }
                    )
            if self._has_active_work_locked():
                lease = None
            else:
                lease = self._release_backend_if_quiescent_locked()
                self._scope_condition.notify_all()
        if lease is not None:
            _RUNTIME_CARRIER.release_lease(lease)

    @property
    def adopted_count(self) -> int:
        with self._scope_lock:
            return len(self._adopted_tasks)

    @property
    def adopted_tasks(self) -> tuple[Task[Any], ...]:
        with self._scope_lock:
            return tuple(self._adopted_tasks)

    def origin_for_adopted(self, task: Task[Any]) -> str | None:
        with self._scope_lock:
            return self._adopted_tasks.get(task)

    def _go_stream(
        self,
        task: Any,
        task_class: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        lazy: bool,
        on_success: Callable[[list[Any]], object | Awaitable[object]] | None,
        on_error: Callable[[BaseException], object | Awaitable[object]] | None,
        on_finally: Callable[[], object | Awaitable[object]] | None,
        ignore_exception: bool,
    ) -> StageStream[Any]:
        from .StageStream import StageStream
        from .Tunnel import Tunnel

        tunnel: Tunnel[Any] = Tunnel()
        source_stop = threading.Event()

        if task_class in {"async_gen_func", "async_gen"}:

            async def consume_async_source() -> object:
                source = task(*args, **kwargs) if task_class == "async_gen_func" else task
                try:
                    if source_stop.is_set():
                        tunnel.close()
                        return tunnel._retained_items_reference()
                    async for item in source:
                        if source_stop.is_set():
                            break
                        tunnel.put(item)
                        self.tick()
                except asyncio.CancelledError:
                    tunnel.close()
                    raise
                except BaseException as error:
                    tunnel.fail(error)
                    raise
                finally:
                    close_source = getattr(source, "aclose", None)
                    if close_source is not None:
                        try:
                            close_result = close_source()
                            if inspect.isawaitable(close_result):
                                await close_result
                        except BaseException as error:
                            tunnel.fail(error)
                            raise
                tunnel.close()
                return tunnel._retained_items_reference()

            consume_source: Callable[..., Any] = consume_async_source
        else:

            def consume_sync_source() -> object:
                source = task(*args, **kwargs) if task_class == "gen_func" else task
                try:
                    if source_stop.is_set():
                        tunnel.close()
                        return tunnel._retained_items_reference()
                    iterator = iter(source)
                    while not source_stop.is_set():
                        try:
                            item = next(iterator)
                        except StopIteration:
                            break
                        tunnel.put(item)
                        self.tick()
                except BaseException as error:
                    tunnel.fail(error)
                    raise
                finally:
                    close_source = getattr(source, "close", None)
                    if close_source is not None:
                        try:
                            close_source()
                        except BaseException as error:
                            tunnel.fail(error)
                            raise
                tunnel.close()
                return tunnel._retained_items_reference()

            consume_source = consume_sync_source

        wrapped_on_success_callback: Callable[[object], object | Awaitable[object]] | None = None
        if on_success is not None:

            def adapt_success_result(values: object) -> object | Awaitable[object]:
                return on_success(list(cast("Any", values)))

            wrapped_on_success_callback = adapt_success_result

        def start() -> StageHandle[object]:
            return cast(
                "StageHandle[object]",
                self.go(
                    consume_source,
                    on_success=wrapped_on_success_callback,
                    on_error=on_error,
                    on_finally=on_finally,
                    ignore_exception=ignore_exception,
                ),
            )

        return StageStream(start, tunnel, lazy=lazy, source_stop=source_stop.set)

    @overload
    def get(
        self,
        task: Callable[..., AsyncIterator[StreamT]] | AsyncIterator[StreamT],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> list[StreamT]: ...

    @overload
    def get(
        self,
        task: Callable[..., Iterator[StreamT]] | Iterator[StreamT],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> list[StreamT]: ...

    @overload
    def get(
        self,
        task: Callable[..., Awaitable[T]],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T: ...

    @overload
    def get(
        self,
        task: Callable[..., T] | Awaitable[T] | Future[T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T: ...

    def get(self, task: Any, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
        response = cast("StageHandle[Any] | StageStream[Any]", self.go(task, *args, **kwargs))
        return cast("Any", response.get(timeout=timeout))

    def _has_active_work_locked(self) -> bool:
        return bool(self._active_handles or self._adopted_tasks)

    def _active_origins_locked(self) -> tuple[str, ...]:
        return tuple(sorted([handle.origin for handle in self._active_handles] + list(self._adopted_tasks.values())))

    def _touch_locked(self) -> None:
        self._last_activity = time.monotonic()
        if self._idle_timeout is None or not self._has_active_work_locked() or self._sealed:
            return
        if self._idle_timer is not None:
            return
        self._idle_timer_token += 1
        token = self._idle_timer_token
        self._schedule_idle_timer_locked(self._idle_timeout, token)

    def _schedule_idle_timer_locked(self, delay: float, token: int) -> None:
        timer = threading.Timer(delay, self._idle_deadline_reached, args=(token,))
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _owned_activity(self) -> None:
        with self._scope_lock:
            self._touch_locked()

    def tick(self) -> None:
        with self._scope_lock:
            if self._sealed or not self._has_active_work_locked():
                return
            self._touch_locked()

    def _idle_deadline_reached(self, token: int) -> None:
        with self._scope_lock:
            if (
                token != self._idle_timer_token
                or self._idle_timeout is None
                or self._sealed
                or not self._has_active_work_locked()
            ):
                return
            self._idle_timer = None
            elapsed = time.monotonic() - self._last_activity
            if elapsed < self._idle_timeout:
                self._schedule_idle_timer_locked(self._idle_timeout - elapsed, token)
                return
            origins = self._active_origins_locked()
            self._idle_timeout_error = StageIdleTimeoutError(
                idle_timeout=self._idle_timeout,
                unresolved_origins=origins,
            )
            self._sealed = True
            self._cancelling = True
            handles = tuple(self._active_handles)
            adopted_tasks = tuple(self._adopted_tasks)
            self._scope_condition.notify_all()
        for handle in handles:
            handle.cancel(timeout=0)
        for task in adopted_tasks:
            if not task.done():
                task.cancel()

    def _release_backend_if_quiescent_locked(self) -> _Generation | None:
        if self._has_active_work_locked():
            return None
        timer = self._idle_timer
        self._idle_timer = None
        self._idle_timer_token += 1
        if timer is not None:
            timer.cancel()
        lease = self._generation_lease
        self._generation_lease = None
        self._blocked_generation_ids = frozenset()
        self._active_backend = None
        self._active_loop = None
        self._cancelling = False
        return lease

    def _handle_quiescent(self, handle: StageHandle[Any]) -> None:
        errors = handle._take_unreported_stage_errors()
        with self._scope_lock:
            self._scope_settlement_errors.extend(errors)
            self._active_handles.discard(handle)
            if self._has_active_work_locked():
                lease = None
            else:
                lease = self._release_backend_if_quiescent_locked()
                self._scope_condition.notify_all()
        if lease is not None:
            _RUNTIME_CARRIER.release_lease(lease)

    def _collect_handle_errors(self, handle: StageHandle[Any]) -> None:
        errors = handle._take_unreported_stage_errors()
        if errors:
            with self._scope_lock:
                self._scope_settlement_errors.extend(errors)

    def seal(self) -> None:
        with self._scope_lock:
            self._sealed = True
            timer = self._idle_timer
            self._idle_timer = None
            self._idle_timer_token += 1
        if timer is not None:
            timer.cancel()

    async def async_seal(self) -> None:
        self.seal()

    def _raise_scope_errors(self) -> None:
        with self._scope_lock:
            idle_error = self._idle_timeout_error
            errors = self._scope_settlement_errors.copy()
        if idle_error is not None:
            raise idle_error
        if errors:
            raise StageSettlementError(errors)

    def _ensure_not_owned_self_wait(self) -> None:
        if _active_stage.get() is self or _RUNTIME_CARRIER.owns_current_execution(self):
            raise StageLifecycleError("Cannot wait for a Stage from work owned by the same scope")
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if current_task is not None:
            with self._scope_lock:
                if current_task in self._adopted_tasks:
                    raise StageLifecycleError("Cannot wait for a Stage from work owned by the same scope")

    def _ensure_not_same_caller_loop_sync_wait(self, *, async_operation: str) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        with self._scope_lock:
            would_block_owner_loop = (
                self._active_backend == "caller"
                and self._active_loop is running_loop
                and self._has_active_work_locked()
            )
        if would_block_owner_loop:
            raise StageLifecycleError(
                "Cannot synchronously wait for a Stage while running on its active caller-owned event loop; "
                f"use {async_operation}()"
            )

    def wait_settled(self, timeout: float | None = None) -> None:
        self._ensure_not_owned_self_wait()
        self._ensure_not_same_caller_loop_sync_wait(async_operation="async_wait_settled")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._scope_condition:
            while self._has_active_work_locked():
                if deadline is None:
                    self._scope_condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    origins = self._active_origins_locked()
                    handle_count = len(self._active_handles)
                    adopted_count = len(self._adopted_tasks)
                    if adopted_count == 0:
                        unsettled = f"{handle_count} unsettled handle(s)"
                    elif handle_count == 0:
                        unsettled = f"{adopted_count} unsettled adopted task(s)"
                    else:
                        unsettled = (
                            f"{handle_count + adopted_count} unsettled work item(s) "
                            f"({handle_count} handle(s), {adopted_count} adopted task(s))"
                        )
                    raise TimeoutError(
                        f"Stage settlement timed out with {unsettled}; unresolved origins: {list(origins)}"
                    )
                self._scope_condition.wait(remaining)
        self._raise_scope_errors()

    async def async_wait_settled(self, timeout: float | None = None) -> None:
        self._ensure_not_owned_self_wait()
        await asyncio.to_thread(self.wait_settled, timeout)

    def cancel_and_wait_settled(self, timeout: float | None = None) -> bool:
        self._ensure_not_owned_self_wait()
        self._ensure_not_same_caller_loop_sync_wait(async_operation="async_cancel_and_wait_settled")
        with self._scope_lock:
            handles = tuple(self._active_handles)
            adopted_tasks = tuple(self._adopted_tasks)
            if not handles and not adopted_tasks:
                return False
            self._cancelling = True
        for handle in handles:
            handle.cancel(timeout=0)
        for task in adopted_tasks:
            if not task.done():
                task.cancel()
        self.wait_settled(timeout=timeout)
        return True

    async def async_cancel_and_wait_settled(self, timeout: float | None = None) -> bool:
        self._ensure_not_owned_self_wait()
        return await asyncio.to_thread(self.cancel_and_wait_settled, timeout)

    def close(self, timeout: float | None = None) -> None:
        self._ensure_not_owned_self_wait()
        self._ensure_not_same_caller_loop_sync_wait(async_operation="async_close")
        with self._close_operation_lock:
            with self._scope_lock:
                if self._close_completed:
                    self._raise_scope_errors()
                    return
            self.seal()
            try:
                self.wait_settled(timeout=timeout)
            except (StageIdleTimeoutError, StageSettlementError) as error:
                terminal_error: BaseException | None = error
            else:
                terminal_error = None
            if self._private_executor is not None:
                self._private_executor.shutdown(wait=True)
            with self._scope_lock:
                self._close_completed = True
            if terminal_error is not None:
                raise terminal_error

    async def async_close(self, timeout: float | None = None) -> None:
        self._ensure_not_owned_self_wait()
        await asyncio.to_thread(self.close, timeout)

    def snapshot(self) -> StageSnapshot:
        with self._scope_lock:
            if self._close_completed:
                state: Literal["open", "sealed", "closed"] = "closed"
            elif self._sealed:
                state = "sealed"
            else:
                state = "open"
            return StageSnapshot(
                state=state,
                backend_mode=self._backend_mode,
                active_backend=self._active_backend,
                active_count=len(self._active_handles) + len(self._adopted_tasks),
                active_root_count=self._active_root_count,
                pending_root_count=len(self._pending_admissions),
                unresolved_origins=self._active_origins_locked(),
                last_activity=self._last_activity,
                idle_timeout=self._idle_timeout,
                cancelling=self._cancelling,
                idle_timed_out=self._idle_timeout_error is not None,
                carrier_generation_id=(
                    None if self._generation_lease is None else self._generation_lease.generation_id
                ),
            )

    @property
    def is_closing(self) -> bool:
        return self._sealed

    @property
    def is_available(self) -> bool:
        return not self._sealed

    def owns_current_execution(self) -> bool:
        """Return whether the current task/thread is work owned by this Stage."""

        if _active_stage.get() is self or _RUNTIME_CARRIER.owns_current_execution(self):
            return True
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            return False
        if current_task is None:
            return False
        with self._scope_lock:
            return current_task in self._adopted_tasks

    def __enter__(self) -> Stage:  # noqa: PYI034
        with self._scope_lock:
            if self._sealed:
                raise StageClosedError("Cannot enter a sealed Stage scope")
            if self._context_mode is not None:
                raise StageLifecycleError("A Stage scope cannot be entered more than once")
            self._context_mode = "sync"
        return self

    def __exit__(self, exc_type: object, value: BaseException | None, traceback: object) -> None:
        self.seal()
        if value is None:
            self.close()
            return
        try:
            self.close()
        except BaseException as cleanup_error:
            cleanup_error.__context__ = None
            value.__context__ = cleanup_error
            if isinstance(cleanup_error, StageLifecycleError):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return
                deferred_close = loop.run_in_executor(None, self.close)

                def observe_deferred_close(future: asyncio.Future[None]) -> None:
                    try:
                        future.result()
                    except BaseException as deferred_error:
                        deferred_error.__context__ = None
                        value.__context__ = deferred_error

                deferred_close.add_done_callback(observe_deferred_close)

    async def __aenter__(self) -> Stage:  # noqa: PYI034
        with self._scope_lock:
            if self._sealed:
                raise StageClosedError("Cannot enter a sealed Stage scope")
            if self._context_mode is not None:
                raise StageLifecycleError("A Stage scope cannot be entered more than once")
            self._context_mode = "async"
        return self

    async def __aexit__(self, exc_type: object, value: BaseException | None, traceback: object) -> None:
        self.seal()
        if value is None:
            await self.async_close()
            return
        try:
            await self.async_close()
        except BaseException as cleanup_error:
            cleanup_error.__context__ = None
            value.__context__ = cleanup_error

    def func(self, task: Callable[..., T]) -> StageFunction[T]:
        return StageFunction(self, task)
