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

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, cast

from .Stage import Stage
from .StageException import StageClosedError, StageSettlementError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .StageHandle import StageHandle
    from .StageStream import StageStream

    Listener = Callable[..., Any]
    ListenerHandle = StageHandle[Any] | StageStream[Any]


class EventEmitter:
    """Thread-safe process-local listener fan-out backed by one Stage scope."""

    def __init__(self) -> None:
        self._registry_lock = threading.RLock()
        self._listeners: dict[str, list[Listener]] = {}
        self._once: dict[str, list[Listener]] = {}
        self._stage = Stage()
        self._closed = False

    def _ensure_open_locked(self) -> None:
        if self._closed:
            raise StageClosedError("Cannot use a closed EventEmitter")

    def add_listener(self, event: str, listener: Listener) -> Listener:
        with self._registry_lock:
            self._ensure_open_locked()
            listeners = self._listeners.setdefault(event, [])
            if listener not in listeners:
                listeners.append(listener)
        return listener

    def add_once_listener(self, event: str, listener: Listener) -> Listener:
        with self._registry_lock:
            self._ensure_open_locked()
            listeners = self._listeners.setdefault(event, [])
            once_listeners = self._once.setdefault(event, [])
            if listener not in listeners and listener not in once_listeners:
                once_listeners.append(listener)
        return listener

    def remove_listener(self, event: str, listener: Listener) -> None:
        with self._registry_lock:
            listeners = self._listeners.get(event)
            if listeners is not None and listener in listeners:
                listeners.remove(listener)
            once_listeners = self._once.get(event)
            if once_listeners is not None and listener in once_listeners:
                once_listeners.remove(listener)

    def remove_all_listeners(self, event_list: str | Iterable[str]) -> None:
        events = (event_list,) if isinstance(event_list, str) else tuple(event_list)
        with self._registry_lock:
            for event in events:
                self._listeners[event] = []
                self._once[event] = []

    def on(self, event: str, listener: Listener | None = None) -> Listener:
        if listener is not None:
            return self.add_listener(event, listener)

        def decorator(function: Listener) -> Listener:
            return self.add_listener(event, function)

        return decorator

    def off(self, event: str, listener: Listener) -> None:
        self.remove_listener(event, listener)

    def once(self, event: str, listener: Listener | None = None) -> Listener:
        if listener is not None:
            return self.add_once_listener(event, listener)

        def decorator(function: Listener) -> Listener:
            return self.add_once_listener(event, function)

        return decorator

    def listener_count(self, event: str) -> int:
        with self._registry_lock:
            return len(self._listeners.get(event, ())) + len(self._once.get(event, ()))

    @staticmethod
    def _wait_handles(handles: list[ListenerHandle]) -> None:
        for handle in handles:
            try:
                handle.get()
            except (Exception, asyncio.CancelledError):
                pass
            try:
                handle.wait_settled()
            except StageSettlementError:
                pass

    @staticmethod
    async def _async_wait_handles(handles: list[ListenerHandle]) -> None:
        for handle in handles:
            try:
                await handle.async_get()
            except (Exception, asyncio.CancelledError):
                pass
            try:
                await handle.async_wait_settled()
            except StageSettlementError:
                pass

    def emit(self, event: str, *args: Any, wait: bool = False, **kwargs: Any) -> list[ListenerHandle]:
        with self._registry_lock:
            self._ensure_open_locked()
            listeners = [*self._listeners.get(event, ()), *self._once.pop(event, ())]
            handles: list[ListenerHandle] = [
                cast("ListenerHandle", self._stage.go(listener, *args, **kwargs)) for listener in listeners
            ]
        if wait:
            self._wait_handles(handles)
        return handles

    async def async_emit(
        self,
        event: str,
        *args: Any,
        wait: bool = False,
        **kwargs: Any,
    ) -> list[ListenerHandle]:
        handles = self.emit(event, *args, wait=False, **kwargs)
        if wait:
            await self._async_wait_handles(handles)
        return handles

    def close(self) -> None:
        with self._registry_lock:
            if self._closed:
                return
            self._closed = True
        self._stage.close()

    async def async_close(self) -> None:
        with self._registry_lock:
            if self._closed:
                return
            self._closed = True
        await self._stage.async_close()
