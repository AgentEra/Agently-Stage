# Copyright 2024 Maplemx(Mo Xin), AgentEra Ltd. Agently Team(https://Agently.tech)
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

# Contact us: Developer@Agently.tech

import time
import uuid
import atexit
import inspect
import asyncio
import threading
from typing import Callable
from concurrent.futures import ThreadPoolExecutor
from .StageException import StageException

class StageEventLoopThread:
    _thread_count = 0
    _all_daemon_loop_threads = set()

    def __init__(
            self,
            exception_handler: Callable[[Exception], any]=None,
            max_workers: int=None,
            is_daemon: bool=True,
        ):
        self._id = uuid.uuid4()
        self._exception_handler = exception_handler
        self._is_daemon = is_daemon
        self._loop = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._loop_thread = None
        self._loop_ready = threading.Event()
        self._exceptions = StageException()
        self._all_tasks = set()
        self._lock = threading.Lock()
        if self._is_daemon:
            StageEventLoopThread._all_daemon_loop_threads.add(self)
    
    def __hash__(self):
        return hash("loop_thread-" + str(self._id))
    
    def __eq__(self, target):
        return isinstance(self, StageEventLoopThread) and self._id == target._id
    
    def _start_loop_thread(self):
        with threading.Lock():
            if not self._loop_ready.is_set():
                StageEventLoopThread._thread_count += 1
                self._loop_thread = threading.Thread(
                    target=self._start_loop,
                    name=f"AgentlyStageThread-{ StageEventLoopThread._thread_count }",
                    daemon=self._is_daemon
                )
                self._loop_thread.start()
                self._loop_ready.wait()
    
    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        self._loop.set_default_executor(self._executor)
        self._loop.set_exception_handler(self._loop_exception_handler)
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon_threadsafe(lambda: self._loop_ready.set())
        if not self._loop.is_running():
            self._loop.run_forever()            
    
    def _loop_exception_handler(self, loop, context):
        if self._exception_handler is not None:
            if inspect.iscoroutinefunction(self._exception_handler):
               loop.call_soon_threadsafe(
                   lambda e: asyncio.ensure_future(self._exception_handler(e)),
                   context["exception"]
                )
            elif inspect.isfunction(self._exception_handler):
                loop.call_soon_threadsafe(self._exception_handler, context["exception"])
        else:
            self._exceptions.add_exception(context["exception"] if "exception" in context else RuntimeError(context["message"]), context)
            raise context["exception"]
    
    def get_loop(self):
        if not self._loop_ready.is_set():
            with self._lock:
                self._start_loop_thread()
                self._loop_ready.wait()
        return self._loop
        
    def set_exception_handler(self, exception_handler):
        self._exception_handler = exception_handler
        return self
    
    def set_daemon(self, is_daemon):
        self._is_daemon = is_daemon
        return self

    def set_hide_runtime_exception(self, hide_runtime_exception):
        self._hide_runtime_exception = hide_runtime_exception
        return self
    
    def raise_exception(self, e):
        def _raise_exception(e):
            raise e
        self.get_loop().call_soon(_raise_exception, e)
    
    def _register_task(self, task):
        with self._lock:
            self._all_tasks.add(task)
        
        def _discard_from_tasks(_):
            with self._lock:
                self._all_tasks.discard(task)
        task.add_done_callback(_discard_from_tasks)

    def run_async_function(self, async_func, *args, **kwargs):
        task = asyncio.run_coroutine_threadsafe(
            async_func(*args, **kwargs),
            self.get_loop(),
        )
        self._register_task(task)
        return task

    def run_coroutine(self, coro):
        task = asyncio.run_coroutine_threadsafe(coro, self.get_loop())
        self._register_task(task)
        return task
    
    def run_sync_function(self, func, *args, **kwargs):
        task = asyncio.run_coroutine_threadsafe(
            asyncio.to_thread(func, *args, **kwargs),
            self.get_loop(),
        )
        self._register_task(task)
        return task
    
    def ensure_tasks_start(self):
        def get_pending_tasks():
            with self._lock:
                pending_tasks = [task for task in self._all_tasks if not (task.running() or task.done())]
            return pending_tasks
        
        while get_pending_tasks():
            time.sleep(0.01)
    
    def ensure_tasks_done(self):
        with self._lock:
            all_tasks = list(self._all_tasks)
        
        if len(all_tasks) > 0:
            for task in all_tasks:
                task.result()
            self.ensure_tasks_done()

    def close(self):
        try:
            self.ensure_tasks_done()
            if self._loop_ready.is_set():
                with threading.Lock():
                    if self._loop:
                        pending = asyncio.all_tasks(self._loop)
                        if pending:
                            for task in pending:
                                task.cancel()
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    asyncio.gather(*pending, return_exceptions=True),
                                    self.get_loop(),
                                )
                            except:
                                pass
                    if self._loop and self._loop.is_running():
                        self._loop.call_soon_threadsafe(self._loop.stop)
                    
                    if self._loop_thread and self._loop_thread.is_alive():
                        self._loop_thread.join()
                        self._loop_thread = None
                    
                    if self._loop and not self._loop.is_closed():
                        self._loop.close()
                    
                    self._executor.shutdown(wait=True)
                
                self._loop_ready.clear()
        finally:
            StageEventLoopThread._all_daemon_loop_threads.discard(self)
            self._loop = None
            self._exceptions = StageException()

def _close_all_daemon_loop_thread():
    for loop_thread in StageEventLoopThread._all_daemon_loop_threads.copy():
        if loop_thread._exception_handler is None and loop_thread._exceptions.has_exceptions():
            print(loop_thread._exceptions)
        loop_thread.close()
    if len(StageEventLoopThread._all_daemon_loop_threads) > 0:
        _close_all_daemon_loop_thread()

atexit.register(_close_all_daemon_loop_thread)