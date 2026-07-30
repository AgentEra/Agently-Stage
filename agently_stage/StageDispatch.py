# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from .Stage import Stage
from .StageException import StageException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from concurrent.futures import Executor, Future


T = TypeVar("T")


class StageDispatchEnvironment:
    """Compatibility view over a logical Stage scope, not a loop owner."""

    def __init__(
        self,
        *,
        exception_handler: Callable[[BaseException], object] | None = None,
        max_workers: int | None = None,
        auto_close_timeout: float = 10,
        auto_close: bool = False,
    ) -> None:
        del auto_close_timeout
        self._stage = Stage(
            loop="stage",
            exception_handler=exception_handler,
            max_workers=max_workers,
        )
        self.loop: None = None
        self.loop_thread: None = None
        self.executor: Executor = self._stage._blocking_executor
        self.exceptions: StageException = StageException()
        self.auto_close = auto_close
        self.closing: bool = False

    def raise_exception(self, error: BaseException) -> None:
        raise error

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self._stage.close()


class StageDispatch:
    """Published preview facade delegating all execution to Stage."""

    def __init__(
        self,
        *,
        reuse_env: bool = False,
        exception_handler: Callable[[BaseException], object] | None = None,
        max_workers: int | None = None,
        auto_close: bool = False,
    ) -> None:
        del reuse_env
        self.auto_close = auto_close
        self._dispatch_env = StageDispatchEnvironment(
            exception_handler=exception_handler,
            max_workers=max_workers,
            auto_close=auto_close,
        )
        self.raise_exception: Callable[[BaseException], None] = self._dispatch_env.raise_exception

    def run_sync_function(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
        return self._dispatch_env._stage.go(func, *args, **kwargs)._body_future

    def run_async_function(
        self,
        func: Callable[..., Awaitable[T]] | Awaitable[T],
        *args: Any,
        **kwargs: Any,
    ) -> Future[T]:
        return cast("Any", self._dispatch_env._stage.go(func, *args, **kwargs)._body_future)

    def to_executor(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
        def invoke() -> T:
            return func(*args, **kwargs)

        handle = self._dispatch_env._stage.go(invoke)
        return handle._body_future

    def close(self) -> None:
        self._dispatch_env.close()
