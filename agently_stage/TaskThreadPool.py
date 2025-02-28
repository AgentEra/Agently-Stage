from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor


class TaskThreadPool:
    _executor = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._executor is None:
                print("Initializing the thread pool...")
                cls._executor = ThreadPoolExecutor()
        return cls._executor

    def submit(self, fn, *args, **kwargs):
        return self._executor.submit(fn, *args, **kwargs)
