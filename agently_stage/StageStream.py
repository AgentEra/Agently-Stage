from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

    from .StageHandle import StageHandle
    from .Tunnel import Tunnel

T = TypeVar("T")
_CallbackKind = Literal["success", "error", "finally"]


class StageStream(Generic[T]):
    """Read-only task-bound stream composed from Tunnel and StageHandle."""

    def __init__(
        self,
        start: Callable[[], StageHandle[list[T]]],
        tunnel: Tunnel[T],
        *,
        lazy: bool = False,
    ) -> None:
        self._start = start
        self._tunnel = tunnel
        self._start_lock = threading.RLock()
        self._handle: StageHandle[list[T]] | None = None
        self._pending_callbacks: list[tuple[_CallbackKind, Callable[..., object | Awaitable[object]]]] = []
        if not lazy:
            self._ensure_started()

    def _ensure_started(self) -> StageHandle[list[T]]:
        with self._start_lock:
            if self._handle is None:
                handle = self._start()
                for kind, callback in self._pending_callbacks:
                    if kind == "success":
                        handle.on_success(callback)
                    elif kind == "error":
                        handle.on_error(callback)
                    else:
                        handle.on_finally(callback)
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
        return self._ensure_started().get(timeout=timeout)

    async def async_get(self, timeout: float | None = None) -> list[T]:
        return await self._ensure_started().async_get(timeout=timeout)

    def wait_settled(self, timeout: float | None = None) -> None:
        self._ensure_started().wait_settled(timeout=timeout)

    async def async_wait_settled(self, timeout: float | None = None) -> None:
        await self._ensure_started().async_wait_settled(timeout=timeout)

    def cancel(self, timeout: float | None = None) -> bool:
        return self._ensure_started().cancel(timeout=timeout)

    def __iter__(self) -> Iterator[T]:
        self._ensure_started()
        return iter(self._tunnel)

    def __aiter__(self) -> AsyncIterator[T]:
        self._ensure_started()
        return self._tunnel.__aiter__()

    def _register_callback(
        self,
        kind: _CallbackKind,
        callback: Callable[..., object | Awaitable[object]],
    ) -> StageStream[T]:
        with self._start_lock:
            if self._handle is None:
                self._pending_callbacks.append((kind, callback))
                return self
            handle = self._handle
        if kind == "success":
            handle.on_success(callback)
        elif kind == "error":
            handle.on_error(callback)
        else:
            handle.on_finally(callback)
        return self

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
