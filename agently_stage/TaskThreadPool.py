from __future__ import annotations

import asyncio
import inspect
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor


class TaskThreadPool:
    _executor = None
    _lock = threading.Lock()

    @classmethod
    def _get_executor(cls):
        with cls._lock:
            if cls._executor is None or cls._executor._shutdown:
                cls._executor = ThreadPoolExecutor()
            return cls._executor

    def __new__(cls):
        return cls._get_executor()

    @classmethod
    def submit(cls, fn, *args, **kwargs):
        cls._get_executor()
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

            try:
                return cls._executor.submit(async_wrapper)
            except RuntimeError as e:
                if "cannot schedule new futures after shutdown" in str(e):
                    warnings.warn("cannot schedule new futures after shutdown", RuntimeWarning, stacklevel=2)
                    return asyncio.run(fn(*args, **kwargs))
                raise

        # 处理同步函数
        try:
            return cls._executor.submit(fn, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after shutdown" in str(e):
                warnings.warn("cannot schedule new futures after shutdown", RuntimeWarning, stacklevel=2)
                return fn(*args, **kwargs)
            raise
