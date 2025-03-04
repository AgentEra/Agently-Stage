from __future__ import annotations

import asyncio
import inspect
import threading
import warnings
from concurrent.futures import Future, ThreadPoolExecutor

from .StageException import StageException
from .TaskThreadPool import TaskThreadPool


class StageDispatchEnvironment:
    def __init__(
        self,
        *,
        exception_handler=None,
        max_workers=None,
        auto_close_timeout=10,
        is_daemon=True,
    ):
        self._exception_handler = exception_handler
        self._max_workers = max_workers
        self.loop = None
        self.loop_thread = None
        self.executor = None
        self.exceptions = None
        self._is_daemon = is_daemon
        if self._is_daemon:
            self.active_tasks = 0
            self.active_tasks_lock = threading.Lock()
            self._auto_close_timeout = auto_close_timeout  # 无任务状态持续多少秒后自动关闭
            self.auto_close_event: threading.Event | None = None
        self._closing_lock = threading.Lock()
        self.closing = False
        self._shutdown_monitor_thread = None  # 关闭监控线程
        self._loop_ready_event = threading.Event()  # 事件循环准备就绪事件
        self._start_loop_thread()
        if self._is_daemon:
            self._shutdown_event = threading.Event()  # 关闭事件标志
            self._start_shutdown_monitor()  # 启动关闭监控线程

    # Start Environment
    def _start_loop(self):
        self.loop = asyncio.new_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="AgentlyStageThreadPool")
        self.loop.set_default_executor(self.executor)
        self.exceptions = StageException()
        self.loop.set_exception_handler(self._loop_exception_handler)
        asyncio.set_event_loop(self.loop)
        self._loop_ready_event.set()  # 事件循环准备就绪
        self.loop.run_forever()

    def _start_loop_thread(self):
        self.loop_thread = threading.Thread(target=self._start_loop, name="AgentlyStageDispatchThread")
        self.loop_thread.start()
        self._loop_ready_event.wait()  # 等待事件循环准备就绪
        del self._loop_ready_event  # 删除事件循环准备就绪事件

    def _start_shutdown_monitor(self):
        """Start a monitoring thread to safely close the event loop if needed"""
        self._shutdown_monitor_thread = threading.Thread(
            target=self._shutdown_monitor_func, name="shutdown_monitor_thread", daemon=True
        )
        self._shutdown_monitor_thread.start()

    def _shutdown_monitor_func(self):
        """Monitor the thread function, wait for the shutdown signal and perform the shutdown operation"""
        self._shutdown_event.wait()  # 等待关闭信号
        if not self.closing:
            self.close()  # 在单独的线程中执行关闭操作

    async def auto_close_checker(self):
        """check if the event loop can be closed"""
        self.auto_close_event = threading.Event()
        result = self.auto_close_event.wait(self._auto_close_timeout)
        if result:
            # 有任务在运行，重置自动关闭事件
            self.auto_close_event = None
            return
        # 任务被取消时正常退出
        self._shutdown_event.set()  # 设置关闭事件标志

    # Handle Exception
    def _loop_exception_handler(self, loop, context):
        if self._exception_handler is not None:
            if inspect.iscoroutinefunction(self._exception_handler):
                loop.call_soon_threadsafe(
                    lambda e: asyncio.ensure_future(self._exception_handler(e)), context["exception"]
                )
            elif inspect.isfunction(self._exception_handler):
                loop.call_soon_threadsafe(self._exception_handler, context["exception"])
        else:
            self.exceptions.add_exception(
                context["exception"] if "exception" in context else RuntimeError(context["message"]), context
            )
            raise context["exception"]

    def raise_exception(self, e):
        def _raise_exception(e):
            raise e

        self.loop.call_soon(_raise_exception, e)

    def close(self):
        with self._closing_lock:
            if self.closing:
                return

            self.closing = True

        # 等待所有任务完成并关闭事件循环
        future = asyncio.run_coroutine_threadsafe(self._shutdown_loop(), self.loop)
        try:
            # 给一个超时，以防有些任务永远不会结束
            future.result(timeout=None)  # 5秒超时
        except TimeoutError:
            print("Warning: Some tasks did not complete within timeout")

        # 现在可以安全停止事件循环
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()
        self.loop.close()

        # 关闭线程池和等待线程结束
        self.executor.shutdown(wait=True)

    async def _shutdown_loop(self):
        """Safely close the event loop and wait for all tasks to complete"""
        # 获取所有待处理的任务
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task(self.loop)]

        if not tasks:
            return

        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)


class StageDispatch:
    # _instance = None
    _dispatch_env = None
    _lock = threading.Lock()

    """
    def __new__(
        cls,
        *,
        reuse_env=True,
        exception_handler=None,
        max_workers=None,
        is_daemon=True,
    ):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._dispatch_env = StageDispatchEnvironment(
                        exception_handler=exception_handler,
                        max_workers=max_workers,
                        is_daemon=is_daemon,
                    )
        return cls._instance
    """

    def __init__(
        self,
        *,
        reuse_env=False,
        exception_handler=None,
        max_workers=None,
        is_daemon=True,
    ):
        self._all_tasks = set()
        self._is_daemon = is_daemon
        if reuse_env:
            if StageDispatch._dispatch_env is None or StageDispatch._dispatch_env.closing:
                with StageDispatch._lock:
                    if StageDispatch._dispatch_env is None or StageDispatch._dispatch_env.closing:
                        StageDispatch._dispatch_env = StageDispatchEnvironment(
                            exception_handler=exception_handler,
                            max_workers=max_workers,
                        )
            self._dispatch_env = StageDispatch._dispatch_env
        else:
            self._dispatch_env = StageDispatchEnvironment(
                exception_handler=exception_handler,
                max_workers=max_workers,
                is_daemon=is_daemon,
            )
        self.raise_exception = self._dispatch_env.raise_exception

    def run_sync_function(self, func, *args, **kwargs):
        self._add_task()
        task = self.to_executor(self._wrap_sync_func, func, *args, **kwargs)
        return task

    def _wrap_sync_func(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            self._decrease_task()

    def run_async_function(self, func, *args, **kwargs):
        self._add_task()
        if inspect.iscoroutinefunction(func):
            coro = func(*args, **kwargs)
        elif inspect.iscoroutine(func):
            coro = func
        else:
            if self._is_daemon:
                with self._dispatch_env.active_tasks_lock:
                    self._dispatch_env.active_tasks -= 1
            raise ValueError("func must be a coroutine function or coroutine")

        task = asyncio.run_coroutine_threadsafe(
            self._wrap_async_func(coro),
            loop=self._dispatch_env.loop,
        )
        return task

    async def _wrap_async_func(self, coro):
        try:
            return await coro
        finally:
            self._decrease_task()

    def _add_task(self):
        """add a task to the event loop"""
        if self._is_daemon:
            with self._dispatch_env.active_tasks_lock:
                self._dispatch_env.active_tasks += 1
                if self._dispatch_env.auto_close_event is not None:
                    self._dispatch_env.auto_close_event.set()

    def _decrease_task(self):
        """decrease the number of tasks in the event loop"""
        if self._is_daemon:
            with self._dispatch_env.active_tasks_lock:
                self._dispatch_env.active_tasks -= 1
                if self._dispatch_env.active_tasks == 0:
                    asyncio.run_coroutine_threadsafe(
                        self._dispatch_env.auto_close_checker(),
                        loop=self._dispatch_env.loop,
                    )

    def to_executor(self, func, *args, **kwargs):
        try:
            return self._dispatch_env.executor.submit(func, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after" in str(e):
                warnings.warn("cannot schedule new futures after shutdown", RuntimeWarning, stacklevel=2)
                future = Future()
                try:
                    future.set_result(func(*args, **kwargs))
                except Exception as e:
                    future.set_exception(e)
                return future
            raise

    def close(self):
        """
        if StageDispatch._instance is not None:
            with self._lock:
                if StageDispatch._instance is not None:
                    StageDispatch._dispatch_env.close()
                    StageDispatch._instance = None
        """
        TaskThreadPool().submit(self._dispatch_env.close)
