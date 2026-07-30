from __future__ import annotations

# pyright: reportPrivateUsage=false
import contextvars
import threading
from typing import TYPE_CHECKING, Generic, Literal, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator

    from .StageHandle import StageHandle
    from .Tunnel import Tunnel

T = TypeVar("T")
_CallbackKind = Literal["success", "error", "finally"]


class StageStream(Generic[T]):
    """Read-only task-bound stream composed from Tunnel and StageHandle."""

    def __init__(
        self,
        start: Callable[[], StageHandle[object]],
        tunnel: Tunnel[T],
        *,
        lazy: bool = False,
        source_stop: Callable[[], object] | None = None,
    ) -> None:
        self._start = start
        self._tunnel = tunnel
        self._start_lock = threading.RLock()
        self._handle: StageHandle[object] | None = None
        self._source_stop = source_stop
        self._closed = False
        self._pending_callbacks: list[
            tuple[_CallbackKind, Callable[..., object | Awaitable[object]], contextvars.Context]
        ] = []
        if not lazy:
            self._ensure_started()

    def _ensure_started(self) -> StageHandle[object]:
        with self._start_lock:
            if self._handle is None:
                handle = self._start()
                for kind, callback, context in self._pending_callbacks:
                    self._register_on_handle(handle, kind, callback, context)
                self._pending_callbacks.clear()
                self._handle = handle
            return self._handle

    @property
    def generation_id(self) -> int:
        return self._ensure_started().generation_id

    def is_ready(self) -> bool:
        with self._start_lock:
            return self._handle is not None and self._handle.is_ready()

    def get(self, timeout: float | None = None) -> list[T]:
        values = self._ensure_started().get(timeout=timeout)
        return list(cast("Iterable[T]", values))

    async def async_get(self, timeout: float | None = None) -> list[T]:
        values = await self._ensure_started().async_get(timeout=timeout)
        return list(cast("Iterable[T]", values))

    def wait_settled(self, timeout: float | None = None) -> None:
        self._ensure_started().wait_settled(timeout=timeout)

    async def async_wait_settled(self, timeout: float | None = None) -> None:
        await self._ensure_started().async_wait_settled(timeout=timeout)

    def cancel(self, timeout: float | None = None) -> bool:
        return self._ensure_started().cancel(timeout=timeout)

    @property
    def closed(self) -> bool:
        with self._start_lock:
            return self._closed

    def close(self, timeout: float | None = None) -> None:
        with self._start_lock:
            first_request = not self._closed
            if first_request:
                self._closed = True
                source_stop = self._source_stop
                if source_stop is not None:
                    source_stop()
            else:
                source_stop = None
        handle = self._ensure_started()
        if first_request:
            handle.cancel(timeout=0)
        handle.wait_settled(timeout=timeout)

    async def async_close(self, timeout: float | None = None) -> None:
        with self._start_lock:
            first_request = not self._closed
            if first_request:
                self._closed = True
                source_stop = self._source_stop
                if source_stop is not None:
                    source_stop()
            else:
                source_stop = None
        handle = self._ensure_started()
        if first_request:
            handle.cancel(timeout=0)
        await handle.async_wait_settled(timeout=timeout)

    def __iter__(self) -> Iterator[T]:
        handle = self._ensure_started()
        handle._ensure_not_owner_loop_sync_wait(
            operation="iterate StageStream synchronously",
            async_operation="async for",
            already_done=handle.is_ready(),
        )
        return iter(self._tunnel)

    def __aiter__(self) -> AsyncIterator[T]:
        self._ensure_started()
        return self._tunnel.__aiter__()

    def _register_callback(
        self,
        kind: _CallbackKind,
        callback: Callable[..., object | Awaitable[object]],
    ) -> StageStream[T]:
        callback_context = contextvars.copy_context()
        with self._start_lock:
            if self._handle is None:
                self._pending_callbacks.append((kind, callback, callback_context))
                return self
            handle = self._handle
        self._register_on_handle(handle, kind, callback, callback_context)
        return self

    @staticmethod
    def _register_on_handle(
        handle: StageHandle[object],
        kind: _CallbackKind,
        callback: Callable[..., object | Awaitable[object]],
        context: contextvars.Context,
    ) -> None:
        if kind == "success":

            def success_callback(values: object) -> object | Awaitable[object]:
                return callback(list(cast("Iterable[T]", values)))

            registered_callback = success_callback
        else:
            registered_callback = callback
        handle._register_callback(kind, registered_callback, context=context)

    def on_success(
        self,
        callback: Callable[[list[T]], object | Awaitable[object]],
    ) -> StageStream[T]:
        return self._register_callback("success", callback)

    def on_error(
        self,
        callback: Callable[[BaseException], object | Awaitable[object]],
    ) -> StageStream[T]:
        return self._register_callback("error", callback)

    def on_finally(
        self,
        callback: Callable[[], object | Awaitable[object]],
    ) -> StageStream[T]:
        return self._register_callback("finally", callback)
