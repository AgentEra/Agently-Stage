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
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeAlias, TypeVar, cast

from .StageException import TunnelClosedError, TunnelLagError

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop, Future
    from collections.abc import AsyncIterator, Iterator

T = TypeVar("T")
_USE_DEFAULT_TIMEOUT = object()
TunnelStart: TypeAlias = Literal["earliest", "latest"] | int


@dataclass(frozen=True)
class _AsyncWaiter:
    loop: AbstractEventLoop
    future: Future[None]


class TunnelSubscription(Generic[T]):
    """One independent sync/async cursor over a process-local Tunnel."""

    def __init__(self, tunnel: Tunnel[T], *, cursor: int, timeout: float | None) -> None:
        self._tunnel = tunnel
        self._timeout = timeout
        self._cursor = cursor
        self._terminated = False

    def __iter__(self) -> TunnelSubscription[T]:
        return self

    def __next__(self) -> T:
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        with self._tunnel._condition:
            while True:
                if self._terminated:
                    raise StopIteration
                if self._cursor < self._tunnel._base_sequence:
                    self._terminated = True
                    raise TunnelLagError(
                        expected_sequence=self._cursor,
                        available_from=self._tunnel._base_sequence,
                    )
                item_offset = self._cursor - self._tunnel._base_sequence
                if item_offset < len(self._tunnel._items):
                    item = self._tunnel._items[item_offset]
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

    def __aiter__(self) -> TunnelSubscription[T]:
        return self

    async def __anext__(self) -> T:
        loop = asyncio.get_running_loop()
        waiter: _AsyncWaiter | None = None

        while True:
            with self._tunnel._condition:
                if self._terminated:
                    raise StopAsyncIteration
                if self._cursor < self._tunnel._base_sequence:
                    self._terminated = True
                    raise TunnelLagError(
                        expected_sequence=self._cursor,
                        available_from=self._tunnel._base_sequence,
                    )
                item_offset = self._cursor - self._tunnel._base_sequence
                if item_offset < len(self._tunnel._items):
                    item = self._tunnel._items[item_offset]
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
            except asyncio.TimeoutError:
                self._terminated = True
                future.cancel()
                raise StopAsyncIteration from None
            finally:
                with self._tunnel._condition:
                    self._tunnel._async_waiters.discard(waiter)

    @property
    def next_sequence(self) -> int:
        with self._tunnel._condition:
            return self._cursor

    def close(self) -> None:
        with self._tunnel._condition:
            if self._terminated:
                return
            self._terminated = True
            self._tunnel._wake_waiters_locked()

    async def async_close(self) -> None:
        self.close()


class Tunnel(Generic[T]):
    """A writable, replayable channel with independent subscriber cursors."""

    def __init__(
        self,
        wait_interval: float = 0.1,
        timeout: float | None = 10,
        timeout_after_start: bool = True,
        max_history: int | None = None,
    ) -> None:
        if max_history is not None and max_history <= 0:
            raise ValueError("Tunnel max_history must be positive")
        self._condition = threading.Condition(threading.RLock())
        self._items: deque[T] = deque()
        self._base_sequence = 0
        self._next_sequence = 0
        self._closed = False
        self._failure: BaseException | None = None
        self._async_waiters: set[_AsyncWaiter] = set()
        self._timeout = timeout
        self._max_history = max_history
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
            self._next_sequence += 1
            if self._max_history is not None and len(self._items) > self._max_history:
                self._items.popleft()
                self._base_sequence += 1
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

    @property
    def retained_range(self) -> tuple[int, int]:
        """Return the half-open absolute sequence range currently retained."""

        with self._condition:
            return self._base_sequence, self._next_sequence

    def subscribe(
        self,
        *,
        start: TunnelStart = "earliest",
        timeout: float | None | object = _USE_DEFAULT_TIMEOUT,
    ) -> TunnelSubscription[T]:
        """Create one independent reader at retained history, live edge, or checkpoint."""

        effective_timeout = self._timeout if timeout is _USE_DEFAULT_TIMEOUT else cast("float | None", timeout)
        with self._condition:
            if start == "earliest":
                cursor = self._base_sequence
            elif start == "latest":
                cursor = self._next_sequence
            elif type(start) is int:
                if start < 0:
                    raise ValueError("Tunnel subscription start sequence must be non-negative")
                if start > self._next_sequence:
                    raise ValueError(
                        f"Tunnel subscription start sequence {start} is after the next Tunnel sequence "
                        f"{self._next_sequence}"
                    )
                cursor = start
            else:
                raise ValueError("Tunnel subscription start must be 'earliest', 'latest', or an absolute sequence")
        return TunnelSubscription(self, cursor=cursor, timeout=effective_timeout)

    def _retained_items_reference(self) -> deque[T]:
        """Return the terminal retained buffer to the owning StageStream."""

        with self._condition:
            if not self._closed:
                raise RuntimeError("Tunnel retained buffer is unavailable before close")
            return self._items

    def get_generator(self) -> Iterator[T]:
        return iter(self)

    def __iter__(self) -> Iterator[T]:
        return self.subscribe(start="earliest", timeout=self._timeout)

    def __aiter__(self) -> AsyncIterator[T]:
        return self.subscribe(start="earliest", timeout=self._timeout)

    def __call__(self) -> Iterator[T]:
        return iter(self)

    def get(self, timeout: float | None | object = _USE_DEFAULT_TIMEOUT) -> list[T]:
        effective_timeout = self._timeout if timeout is _USE_DEFAULT_TIMEOUT else cast("float | None", timeout)
        return list(self.subscribe(start="earliest", timeout=effective_timeout))
