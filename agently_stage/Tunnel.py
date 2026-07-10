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

# pyright: reportPrivateUsage=false
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar, cast

from .StageException import TunnelClosedError

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, Future
    from collections.abc import AsyncIterator, Iterator

T = TypeVar("T")
_USE_DEFAULT_TIMEOUT = object()


@dataclass(frozen=True)
class _AsyncWaiter:
    loop: AbstractEventLoop
    future: Future[None]


class _TunnelIterator(Generic[T]):
    def __init__(self, tunnel: Tunnel[T], timeout: float | None) -> None:
        self._tunnel = tunnel
        self._timeout = timeout
        self._cursor = 0
        self._terminated = False

    def __iter__(self) -> _TunnelIterator[T]:
        return self

    def __next__(self) -> T:
        if self._terminated:
            raise StopIteration
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        with self._tunnel._condition:
            while True:
                if self._cursor < len(self._tunnel._items):
                    item = self._tunnel._items[self._cursor]
                    self._cursor += 1
                    return item
                if self._tunnel._failure is not None:
                    self._terminated = True
                    raise self._tunnel._failure
                if self._tunnel._closed:
                    self._terminated = True
                    raise StopIteration

                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._terminated = True
                    raise StopIteration
                self._tunnel._condition.wait(timeout=remaining)


class _TunnelAsyncIterator(Generic[T]):
    def __init__(self, tunnel: Tunnel[T], timeout: float | None) -> None:
        self._tunnel = tunnel
        self._timeout = timeout
        self._cursor = 0
        self._terminated = False

    def __aiter__(self) -> _TunnelAsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        if self._terminated:
            raise StopAsyncIteration
        loop = asyncio.get_running_loop()
        waiter: _AsyncWaiter | None = None

        while True:
            with self._tunnel._condition:
                if self._cursor < len(self._tunnel._items):
                    item = self._tunnel._items[self._cursor]
                    self._cursor += 1
                    return item
                if self._tunnel._failure is not None:
                    self._terminated = True
                    raise self._tunnel._failure
                if self._tunnel._closed:
                    self._terminated = True
                    raise StopAsyncIteration
                future = loop.create_future()
                waiter = _AsyncWaiter(loop, future)
                self._tunnel._async_waiters.add(waiter)

            try:
                if self._timeout is None:
                    await future
                else:
                    await asyncio.wait_for(asyncio.shield(future), self._timeout)
            except TimeoutError:
                self._terminated = True
                future.cancel()
                raise StopAsyncIteration from None
            finally:
                with self._tunnel._condition:
                    self._tunnel._async_waiters.discard(waiter)


class Tunnel(Generic[T]):
    """A writable, replayable channel with independent subscriber cursors."""

    def __init__(
        self,
        wait_interval: float = 0.1,
        timeout: float | None = None,
        timeout_after_start: bool = True,
    ) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._items: list[T] = []
        self._closed = False
        self._failure: BaseException | None = None
        self._async_waiters: set[_AsyncWaiter] = set()
        self._timeout = timeout
        self._compatibility_wait_interval = wait_interval
        self._compatibility_timeout_after_start = timeout_after_start

    @staticmethod
    def _resolve_waiter(future: Future[None]) -> None:
        if not future.done():
            future.set_result(None)

    def _wake_waiters_locked(self) -> None:
        self._condition.notify_all()
        waiters = tuple(self._async_waiters)
        self._async_waiters.clear()
        for waiter in waiters:
            try:
                waiter.loop.call_soon_threadsafe(self._resolve_waiter, waiter.future)
            except RuntimeError:
                waiter.future.cancel()

    def put(self, data: T) -> None:
        with self._condition:
            if self._closed or self._failure is not None:
                raise TunnelClosedError("Cannot put data after Tunnel terminal state")
            self._items.append(data)
            self._wake_waiters_locked()

    async def async_put(self, data: T) -> None:
        self.put(data)

    def close(self) -> None:
        with self._condition:
            if self._closed or self._failure is not None:
                return
            self._closed = True
            self._wake_waiters_locked()

    async def async_close(self) -> None:
        self.close()

    def fail(self, error: BaseException) -> None:
        with self._condition:
            if self._closed or self._failure is not None:
                return
            self._failure = error
            self._wake_waiters_locked()

    def put_stop(self) -> None:
        self.close()

    def get_generator(self) -> Iterator[T]:
        return iter(self)

    def __iter__(self) -> Iterator[T]:
        return _TunnelIterator(self, self._timeout)

    def __aiter__(self) -> AsyncIterator[T]:
        return _TunnelAsyncIterator(self, self._timeout)

    def __call__(self) -> Iterator[T]:
        return iter(self)

    def get(self, timeout: float | None | object = _USE_DEFAULT_TIMEOUT) -> list[T]:
        effective_timeout = self._timeout if timeout is _USE_DEFAULT_TIMEOUT else cast(float | None, timeout)
        return list(_TunnelIterator(self, effective_timeout))
