# pyright: reportPrivateUsage=false
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ._runtime import _RUNTIME_CARRIER
from .Stage import Stage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from concurrent.futures import Future, ThreadPoolExecutor

    from .StageHandle import StageHandle

T = TypeVar("T")


class TaskThreadPool:
    """Compatibility facade over Stage's canonical blocking and async paths."""

    def __new__(cls) -> ThreadPoolExecutor:
        return _RUNTIME_CARRIER.blocking_executor

    @classmethod
    def submit(
        cls,
        function: Callable[..., T] | Callable[..., Awaitable[T]] | Awaitable[T],
        *args: Any,
        **kwargs: Any,
    ) -> Future[T]:
        if inspect.isawaitable(function) or inspect.iscoroutinefunction(function):
            handle = cast("StageHandle[T]", Stage().go(cast(Any, function), *args, **kwargs))
            return handle._body_future
        return _RUNTIME_CARRIER.blocking_executor.submit(cast(Any, function), *args, **kwargs)
