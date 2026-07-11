from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .Stage import Stage
    from .StageHandle import StageHandle

T = TypeVar("T")


class StageCallBackTask:
    """Compatibility callback adapter using Stage instead of raw threads."""

    def __init__(self, func: Callable[..., Any], stage: Stage | None = None) -> None:
        self._func = func
        self._stage = stage

    def __call__(self, *args: Any, **kwargs: Any) -> StageHandle[Any]:
        from .Stage import Stage

        selected_stage = self._stage if self._stage is not None and self._stage.is_available else Stage()
        return cast("StageHandle[Any]", selected_stage.go(self._func, *args, **kwargs))


class StageTaskProxy(Generic[T]):
    """Compatibility callable retaining the legacy callback constructor shape."""

    def __init__(
        self,
        func: Callable[..., T] | Callable[..., Awaitable[T]],
        stage: Stage | None = None,
        on_success: Callable[[T], object] | None = None,
        on_error: Callable[[BaseException], object] | None = None,
        on_finally: Callable[[], object] | None = None,
        ignore_exception: bool = False,
        use_async: bool = False,
    ) -> None:
        self._func = func
        self._on_success = StageCallBackTask(on_success, stage) if on_success else None
        self._on_error = StageCallBackTask(on_error, stage) if on_error else None
        self._on_finally = StageCallBackTask(on_finally, stage) if on_finally else None
        self._ignore_exception = ignore_exception
        self._use_async = use_async

    def add_on_success(self, on_success: StageCallBackTask) -> StageTaskProxy[T]:
        self._on_success = on_success
        return self

    def add_on_error(self, on_error: StageCallBackTask) -> StageTaskProxy[T]:
        self._on_error = on_error
        return self

    def add_on_finally(self, on_finally: StageCallBackTask) -> StageTaskProxy[T]:
        self._on_finally = on_finally
        return self

    @staticmethod
    def _wait_callback(handle: StageHandle[Any] | None) -> None:
        if handle is None:
            return
        handle.get()
        handle.wait_settled()

    @staticmethod
    async def _async_wait_callback(handle: StageHandle[Any] | None) -> None:
        if handle is None:
            return
        await handle.async_get()
        await handle.async_wait_settled()

    async def async_run(self, *args: Any, **kwargs: Any) -> T | None:
        try:
            result = self._func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await cast(Any, result)
            else:
                result = cast(T, result)
            if self._on_success is not None:
                await self._async_wait_callback(self._on_success(result))
            return result
        except Exception as error:
            if self._on_error is not None:
                await self._async_wait_callback(self._on_error(error))
            if self._ignore_exception:
                return None
            raise
        finally:
            if self._on_finally is not None:
                await self._async_wait_callback(self._on_finally())

    def sync_run(self, *args: Any, **kwargs: Any) -> T | None:
        try:
            result = self._func(*args, **kwargs)
            if inspect.isawaitable(result):
                raise TypeError("Async StageTaskProxy call requires use_async=True")
            result = cast(T, result)
            if self._on_success is not None:
                self._wait_callback(self._on_success(result))
            return result
        except Exception as error:
            if self._on_error is not None:
                self._wait_callback(self._on_error(error))
            if self._ignore_exception:
                return None
            raise
        finally:
            if self._on_finally is not None:
                self._wait_callback(self._on_finally())

    def __call__(self, *args: Any, **kwargs: Any) -> T | None | Awaitable[T | None]:
        if self._use_async:
            return self.async_run(*args, **kwargs)
        return self.sync_run(*args, **kwargs)
