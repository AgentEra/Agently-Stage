from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class Event:
    """Compatibility payload event using composition over threading.Event."""

    def __init__(
        self,
        events_data: dict[str, Any],
        name: str,
        data_lock: threading.RLock,
    ) -> None:
        self._event = threading.Event()
        self._events_data = events_data
        self._name = name
        self._data_lock = data_lock

    def get_data(self) -> Any | None:
        with self._data_lock:
            return self._events_data.get(self._name)

    def set_data(self, data: Any) -> None:
        with self._data_lock:
            self._events_data[self._name] = data

    def update_data(self, key: str, value: Any) -> None:
        with self._data_lock:
            data = self._events_data.get(self._name)
            if data is None:
                data = {}
                self._events_data[self._name] = data
            if not isinstance(data, dict):
                raise TypeError(
                    f"[Agently Stage] Event '{self._name}' can not update data because current data is not a dictionary."
                )
            data[key] = value

    def handle_data(self, handler: Callable[[Any | None], Any]) -> None:
        result = handler(self.get_data())
        if result is not None:
            self.set_data(result)

    def set(self, data: Any | None = None) -> None:
        if data is not None:
            self.set_data(data)
        self._event.set()

    def clear(self) -> None:
        with self._data_lock:
            self._events_data.pop(self._name, None)
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> Any | None:
        if not self._event.wait(timeout=timeout):
            return None
        return self.get_data()


class Events:
    """Compatibility registry for named payload Event instances."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}
        self._events_data: dict[str, Any] = {}
        self._data_lock = threading.RLock()

    def create(self, name: str) -> Event:
        with self._data_lock:
            event = self._events.get(name)
            if event is None:
                event = Event(self._events_data, name, self._data_lock)
                self._events[name] = event
            return event

    def wait_all(self) -> None:
        with self._data_lock:
            events = tuple(self._events.values())
        for event in events:
            event.wait()

    def get_events(self) -> dict[str, Event]:
        with self._data_lock:
            return self._events.copy()
