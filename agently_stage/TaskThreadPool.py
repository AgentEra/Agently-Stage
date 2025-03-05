from __future__ import annotations

import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor


class TaskThreadPool:
    _executor = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor()
        return cls._executor

    def submit(self, fn, *args, **kwargs):
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(fn) or inspect.isawaitable(fn):
            # 处理异步函数
            def async_wrapper():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(fn(*args, **kwargs))
                finally:
                    loop.close()

            return self._executor.submit(async_wrapper)

        # 处理同步函数
        return self._executor.submit(fn, *args, **kwargs)
