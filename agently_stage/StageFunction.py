from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from .Stage import Stage
    from .StageHandle import StageHandle
    from .StageStream import StageStream

T = TypeVar("T")


class StageFunction(Generic[T]):
    """Compatibility helper caching the first Stage submission for a callable.

    ``Any`` is retained for call arguments because this preview facade erases
    the wrapped callable's parameter specification. Canonical new code should
    call ``Stage.go`` directly for precise overloads.
    """

    def __init__(self, stage: Stage, func: Callable[..., T]) -> None:
        self._stage = stage
        self._func = func
        self._response: StageHandle[Any] | StageStream[Any] | None = None
        self._is_started = threading.Event()
        self._response_lock = threading.RLock()

    def __call__(self, *args: Any, **kwargs: Any) -> StageHandle[Any] | StageStream[Any]:
        return self.go(*args, **kwargs)

    def go(self, *args: Any, **kwargs: Any) -> StageHandle[Any] | StageStream[Any]:
        with self._response_lock:
            if self._response is None:
                self._response = self._stage.go(self._func, *args, **kwargs)
                self._is_started.set()
            return self._response

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.go(*args, **kwargs).get()

    def wait(self, timeout: float | None = None, no_exception: bool = True) -> Any | None:
        try:
            if not self._is_started.wait(timeout=timeout):
                return None
            with self._response_lock:
                response = self._response
            if response is None:
                return None
            return response.get()
        except Exception:
            if no_exception:
                return None
            raise

    def reset(self) -> StageFunction[T]:
        with self._response_lock:
            self._is_started.clear()
            self._response = None
        return self
