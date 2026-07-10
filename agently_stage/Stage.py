from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import types
from collections.abc import Awaitable, Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar, cast

from ._runtime import _RUNTIME_CARRIER, _Generation
from .StageException import StageClosedError, StageSettlementError
from .StageFunction import StageFunction
from .StageHandle import StageHandle

T = TypeVar("T")


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
        self._active_handles: set[StageHandle[Any]] = set()
        self._closed = False
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
        if isinstance(task, (classmethod, staticmethod, types.MethodType)):
            return self._classify_task(task.__func__)
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
            return await asyncio.wrap_future(task)
        if inspect.isawaitable(task):
            if args or kwargs:
                raise TypeError("Arguments cannot be supplied with a coroutine object")
            return await cast(Awaitable[T], task)
        if inspect.iscoroutinefunction(task):
            return await task(*args, **kwargs)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self._blocking_executor, functools.partial(task, *args, **kwargs))
        if inspect.isawaitable(result):
            return await cast(Awaitable[T], result)
        return cast(T, result)

    async def _execute_callback(
        self,
        callback: Callable[..., object | Awaitable[object]],
        args: tuple[object, ...],
    ) -> None:
        if inspect.iscoroutinefunction(callback):
            await callback(*args)
            return
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self._blocking_executor, functools.partial(callback, *args))
        if inspect.isawaitable(result):
            await result

    def _start_callback_drain_from_owner(self, handle: StageHandle[Any]) -> None:
        asyncio.create_task(handle._drain_callbacks())

    def _submit_callback_drain_locked(self, handle: StageHandle[Any]) -> None:
        self._active_handles.add(handle)

        async def runner(generation: _Generation) -> None:
            del generation
            await handle._drain_callbacks()

        _RUNTIME_CARRIER.submit(handle, runner, preferred=self._generation_lease, owner=False)

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
    ) -> StageHandle[T]:
        del lazy, wait_interval
        task_class = self._classify_task(task)
        if task_class == "stage_func":
            return cast(StageHandle[T], task(*args, **kwargs))
        if task_class in {"async_gen_func", "async_gen", "gen_func", "gen"}:
            raise NotImplementedError("Generator execution moves to StageStream in the next refactor phase")
        if task_class is None:
            raise TypeError(f"Unsupported Stage task: {task!r}")

        with self._scope_lock:
            if self._closed:
                raise StageClosedError("Cannot submit work to a closed Stage scope")
            if self._pinned and self._generation_lease is None:
                self._generation_lease = _RUNTIME_CARRIER.acquire_lease()
            preferred = self._generation_lease
            handle: StageHandle[T] = StageHandle(self)
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

    def get(
        self,
        task: Callable[..., T] | Awaitable[T] | Future[T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        return self.go(task, *args, **kwargs).get(timeout=timeout)

    def _handle_quiescent(self, handle: StageHandle[Any]) -> None:
        with self._scope_lock:
            self._active_handles.discard(handle)

    def close(self, timeout: float | None = None) -> None:
        with self._scope_lock:
            if self._closed:
                return
            self._closed = True
            handles = tuple(self._active_handles)
            lease = self._generation_lease
            self._generation_lease = None
        if lease is not None:
            _RUNTIME_CARRIER.release_lease(lease)

        errors: list[BaseException] = []
        for handle in handles:
            try:
                handle.wait_settled(timeout=timeout)
            except StageSettlementError as error:
                errors.extend(error.errors)
        if self._private_executor is not None:
            self._private_executor.shutdown(wait=True)
        if errors:
            raise StageSettlementError(errors)

    async def async_close(self, timeout: float | None = None) -> None:
        with self._scope_lock:
            if self._closed:
                return
            self._closed = True
            handles = tuple(self._active_handles)
            lease = self._generation_lease
            self._generation_lease = None
        if lease is not None:
            _RUNTIME_CARRIER.release_lease(lease)

        errors: list[BaseException] = []
        for handle in handles:
            try:
                await handle.async_wait_settled(timeout=timeout)
            except StageSettlementError as error:
                errors.extend(error.errors)
        if self._private_executor is not None:
            self._private_executor.shutdown(wait=True)
        if errors:
            raise StageSettlementError(errors)

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

    def func(self, task: Callable[..., T]) -> StageFunction:
        return StageFunction(self, task)
