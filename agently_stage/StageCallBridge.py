from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import contextvars
import functools
import inspect
import threading
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from ._runtime import _RUNTIME_CARRIER
from .Stage import Stage
from .StageException import StageLifecycleError
from .StageStream import StageStream

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Awaitable,
        Callable,
        Coroutine,
        Generator,
        Iterator,
    )
    from concurrent.futures import Executor

    from .StageHandle import StageHandle

P = ParamSpec("P")
T = TypeVar("T")


class StageCallBridge:
    """Translate sync/async scalar and stream call shapes through Stage mechanisms."""

    def __init__(
        self,
        *,
        stage: Stage | None = None,
        executor: Executor | None = None,
        managed_by_default: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._close_operation_lock = threading.RLock()
        self._closing = False
        self._closed = False
        self._executor = executor
        self._managed_by_default = managed_by_default
        self._submit_stage = stage if stage is not None else Stage(executor=executor)
        self._owns_submit_stage = stage is None
        self._carrier_stage = Stage(loop="stage", executor=executor)

    def _ensure_open(self) -> None:
        with self._lock:
            if self._closing:
                raise StageLifecycleError("StageCallBridge is closed")

    @staticmethod
    def _is_async_callable(function: object) -> bool:
        if inspect.iscoroutinefunction(function):
            return True
        return callable(function) and inspect.iscoroutinefunction(function.__call__)

    def _resolve_awaitable_sync(self, awaitable: Awaitable[T], *, managed: bool) -> T:
        if _RUNTIME_CARRIER.would_sync_wait_block_current_carrier(self._carrier_stage):
            close = getattr(awaitable, "close", None)
            if close is not None:
                close()
            raise StageLifecycleError(
                "A synchronous StageCallBridge call cannot re-enter and block its own carrier execution"
            )
        handle = self._carrier_stage.go(awaitable)
        if not managed:
            return handle.result()
        try:
            result = handle.result()
        except BaseException:
            try:
                handle.wait_settled()
            except BaseException:
                pass
            raise
        handle.wait_settled()
        return result

    def as_sync(
        self,
        function: Callable[P, T | Awaitable[T]],
        *,
        managed: bool | None = None,
    ) -> Callable[P, T]:
        if not callable(function):
            raise TypeError(f"Expected a callable, got {type(function)}")
        async_callable = self._is_async_callable(function)
        should_manage = self._managed_by_default if managed is None else managed

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            self._ensure_open()
            if async_callable and _RUNTIME_CARRIER.would_sync_wait_block_current_carrier(self._carrier_stage):
                raise StageLifecycleError(
                    "A synchronous StageCallBridge call cannot re-enter and block its own carrier execution"
                )
            result = function(*args, **kwargs)
            if inspect.isawaitable(result):
                return self._resolve_awaitable_sync(
                    cast("Awaitable[T]", result),
                    managed=should_manage,
                )
            return cast("T", result)

        return wrapper

    def as_async(
        self,
        function: Callable[P, T | Awaitable[T]],
        *,
        managed: bool | None = None,
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        if not callable(function):
            raise TypeError(f"Expected a callable, got {type(function)}")
        async_callable = self._is_async_callable(function)
        if async_callable:
            return cast("Callable[P, Coroutine[Any, Any, T]]", function)
        should_manage = self._managed_by_default if managed is None else managed

        @functools.wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            self._ensure_open()
            loop = asyncio.get_running_loop()
            context = contextvars.copy_context()
            call = functools.partial(function, *args, **kwargs)
            executor = self._executor if self._executor is not None else self._submit_stage._blocking_executor
            if not should_manage:
                result = await loop.run_in_executor(executor, context.run, call)
            else:
                concurrent_result = executor.submit(context.run, call)
                blocking = asyncio.wrap_future(concurrent_result, loop=loop)
                try:
                    result = await blocking
                except asyncio.CancelledError:
                    settlement = asyncio.wrap_future(concurrent_result, loop=loop)
                    while not settlement.done():
                        try:
                            await asyncio.shield(settlement)
                        except asyncio.CancelledError:
                            continue
                        except BaseException:
                            break
                    try:
                        settlement.result()
                    except BaseException:
                        pass
                    raise
            if inspect.isawaitable(result):
                return await cast("Awaitable[T]", result)
            return cast("T", result)

        return wrapper

    def submit(
        self,
        function: Callable[P, T | Awaitable[T]] | Awaitable[T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> StageHandle[T]:
        self._ensure_open()
        response = self._submit_stage.go(function, *args, **kwargs)
        if isinstance(response, StageStream):
            response.close()
            raise TypeError("StageCallBridge.submit accepts scalar work; use iter_sync or iter_async for streams")
        return cast("StageHandle[T]", response)

    def iter_sync(self, source: AsyncIterator[T]) -> Generator[T, None, None]:
        self._ensure_open()

        def iterator() -> Generator[T, None, None]:
            stage = Stage(loop="stage", executor=self._executor)
            stream = stage.go(source)
            try:
                yield from stream
            finally:
                try:
                    stream.close()
                finally:
                    stage.close()

        return iterator()

    def iter_async(self, source: Iterator[T]) -> AsyncGenerator[T, None]:
        self._ensure_open()

        async def iterator() -> AsyncGenerator[T, None]:
            stage = Stage(loop=asyncio.get_running_loop(), executor=self._executor)
            stream = stage.go(source)
            try:
                async for item in stream:
                    yield item
            finally:
                try:
                    await stream.async_close()
                finally:
                    await stage.async_close()

        return iterator()

    def close(self, timeout: float | None = None) -> None:
        with self._close_operation_lock:
            with self._lock:
                if self._closed:
                    return
                self._closing = True
            self._carrier_stage.close(timeout=timeout)
            if self._owns_submit_stage:
                self._submit_stage.close(timeout=timeout)
            with self._lock:
                self._closed = True

    async def async_close(self, timeout: float | None = None) -> None:
        await asyncio.to_thread(self.close, timeout)


default_stage_call_bridge = StageCallBridge()
