# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import threading
import time
import types
from collections.abc import Awaitable, Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from ._runtime import _RUNTIME_CARRIER, _Generation, _WorkPhase
from .StageException import StageClosedError, StageLifecycleError, StageSettlementError
from .StageFunction import StageFunction
from .StageHandle import StageHandle

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from .StageStream import StageStream

T = TypeVar("T")
StreamT = TypeVar("StreamT")


class Stage:
    """A logical scope for sync and async work hosted by the shared carrier."""

    def __init__(
        self,
        reuse_env: bool = False,
        exception_handler: Callable[[BaseException], object] | None = None,
        max_workers: int | None = None,
        auto_close: bool = False,
    ) -> None:
        self._scope_lock = threading.RLock()
        self._close_operation_lock = threading.Lock()
        self._active_handles: set[StageHandle[Any]] = set()
        self._scope_settlement_errors: list[BaseException] = []
        self._closed = False
        self._close_completed = False
        self._pinned = False
        self._entered = False
        self._generation_lease: _Generation | None = None
        self._exception_handler = exception_handler
        self._private_executor = (
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AgentlyStageScopeBlocking")
            if max_workers is not None
            else None
        )
        self._blocking_executor = self._private_executor or _RUNTIME_CARRIER.blocking_executor
        self._compatibility_reuse_env = reuse_env
        self._compatibility_auto_close = auto_close

    def _classify_task(self, task: object) -> str | None:
        if isinstance(task, StageFunction):
            return "stage_func"
        if isinstance(task, functools.partial):
            return self._classify_task(task.func)
        if isinstance(task, classmethod | staticmethod | types.MethodType):
            return self._classify_task(cast(Any, task).__func__)
        if inspect.isasyncgenfunction(task):
            return "async_gen_func"
        if inspect.isasyncgen(task):
            return "async_gen"
        if inspect.isgeneratorfunction(task):
            return "gen_func"
        if inspect.isgenerator(task):
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

    async def _execute_scalar(
        self,
        task: Callable[..., T] | Awaitable[T] | Future[T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        if isinstance(task, Future):
            return await asyncio.wrap_future(cast(Future[T], task))
        if inspect.isawaitable(task):
            if args or kwargs:
                raise TypeError("Arguments cannot be supplied with a coroutine object")
            return await cast(Awaitable[T], task)
        if inspect.iscoroutinefunction(task):
            return await task(*args, **kwargs)

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
            return await cast(Awaitable[T], result)
        return cast(T, result)

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

    def _start_callback_drain_from_owner(self, handle: StageHandle[Any]) -> None:
        _RUNTIME_CARRIER.create_settlement_task(handle._drain_callbacks())

    def _submit_callback_drain_locked(self, handle: StageHandle[Any]) -> None:
        self._active_handles.add(handle)

        async def runner(generation: _Generation) -> None:
            del generation
            await handle._drain_callbacks()

        _RUNTIME_CARRIER.submit(
            handle,
            runner,
            preferred=self._generation_lease,
            owner=False,
            phase=_WorkPhase.SETTLEMENT,
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
            return cast(StageFunction[Any], task)(*args, **kwargs)
        if task_class in {"async_gen_func", "async_gen", "gen_func", "gen"}:
            return self._go_stream(
                task,
                task_class,
                args,
                kwargs,
                lazy=lazy,
                on_success=cast(Any, on_success),
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
            )
        if task_class is None:
            raise TypeError(f"Unsupported Stage task: {task!r}")

        with self._scope_lock:
            if self._closed:
                raise StageClosedError("Cannot submit work to a closed Stage scope")
            if self._pinned and self._generation_lease is None:
                self._generation_lease = _RUNTIME_CARRIER.acquire_lease()
            preferred = self._generation_lease
            handle: StageHandle[Any] = StageHandle(self)
            self._active_handles.add(handle)
            if on_success is not None:
                handle._register_initial_callback("success", on_success)
            if on_error is not None:
                handle._register_initial_callback("error", on_error)
            if on_finally is not None:
                handle._register_initial_callback("finally", on_finally)

            async def runner(generation: _Generation) -> None:
                del generation
                try:
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

            _RUNTIME_CARRIER.submit(handle, runner, preferred=preferred)
        return handle

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

        if task_class in {"async_gen_func", "async_gen"}:

            async def consume_async_source() -> object:
                source = task(*args, **kwargs) if task_class == "async_gen_func" else task
                try:
                    async for item in source:
                        tunnel.put(item)
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
                    for item in source:
                        tunnel.put(item)
                except BaseException as error:
                    tunnel.fail(error)
                    raise
                tunnel.close()
                return tunnel._retained_items_reference()

            consume_source = consume_sync_source

        stream_success_callback = on_success
        wrapped_on_success_callback: Callable[[object], object | Awaitable[object]] | None = None
        if stream_success_callback is not None:

            def adapt_success_result(values: object) -> object | Awaitable[object]:
                return stream_success_callback(list(cast(Any, values)))

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

        return StageStream(start, tunnel, lazy=lazy)

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

    def get(
        self,
        task: Any,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        response = cast("StageHandle[Any] | StageStream[Any]", self.go(task, *args, **kwargs))
        return cast(Any, response.get(timeout=timeout))

    def _handle_quiescent(self, handle: StageHandle[Any]) -> None:
        errors = handle._take_unreported_stage_errors()
        with self._scope_lock:
            self._scope_settlement_errors.extend(errors)
            self._active_handles.discard(handle)

    def _collect_handle_errors(self, handle: StageHandle[Any]) -> None:
        errors = handle._take_unreported_stage_errors()
        if errors:
            with self._scope_lock:
                self._scope_settlement_errors.extend(errors)

    def close(self, timeout: float | None = None) -> None:
        if _RUNTIME_CARRIER.owns_current_execution(self):
            raise StageLifecycleError("Cannot close a Stage from work owned by the same scope")
        with self._close_operation_lock:
            with self._scope_lock:
                if self._close_completed:
                    errors = self._scope_settlement_errors.copy()
                    if errors:
                        raise StageSettlementError(errors)
                    return
                self._closed = True
                handles = tuple(self._active_handles)
                lease = self._generation_lease
                self._generation_lease = None
            if lease is not None:
                _RUNTIME_CARRIER.release_lease(lease)

            deadline = None if timeout is None else time.monotonic() + timeout
            for handle in handles:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                try:
                    handle.wait_settled(timeout=remaining)
                except (TimeoutError, FutureTimeoutError):
                    with self._scope_lock:
                        unsettled_count = len(self._active_handles)
                    raise TimeoutError(f"Stage close timed out with {unsettled_count} unsettled handle(s)") from None
                except StageSettlementError:
                    pass
                finally:
                    self._collect_handle_errors(handle)
            if self._private_executor is not None:
                self._private_executor.shutdown(wait=True)
            with self._scope_lock:
                self._close_completed = True
                errors = self._scope_settlement_errors.copy()
            if errors:
                raise StageSettlementError(errors)

    async def async_close(self, timeout: float | None = None) -> None:
        if _RUNTIME_CARRIER.owns_current_execution(self):
            raise StageLifecycleError("Cannot close a Stage from work owned by the same scope")
        await asyncio.to_thread(self.close, timeout)

    @property
    def is_closing(self) -> bool:
        return self._closed

    @property
    def is_available(self) -> bool:
        return not self._closed

    def __enter__(self) -> Stage:  # noqa: PYI034 -- typing.Self is unavailable on Python 3.10.
        with self._scope_lock:
            if self._closed:
                raise StageClosedError("Cannot enter a closed Stage scope")
            self._pinned = True
            self._entered = True
        return self

    def __exit__(self, exc_type: object, value: BaseException | None, traceback: object) -> None:
        self.close()

    async def __aenter__(self) -> Stage:  # noqa: PYI034 -- typing.Self is unavailable on Python 3.10.
        return self.__enter__()

    async def __aexit__(self, exc_type: object, value: BaseException | None, traceback: object) -> None:
        await self.async_close()

    def func(self, task: Callable[..., T]) -> StageFunction[T]:
        return StageFunction(self, task)
